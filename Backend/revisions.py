from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from db import get_conn
from auth import current_user, require_roles
from submissions import get_submission, audit
from review import run_review

router = APIRouter(prefix="/api/submissions", tags=["revisions"])


def review_and_carry(sid, version):
    """Run the review, then carry over earlier dismissals so the creator isn't asked twice."""
    run_review(sid, version)
    conn = get_conn()
    try:
        s = conn.execute("SELECT status, company_id FROM submissions WHERE id=?", (sid,)).fetchone()
        prev = conn.execute(
            "SELECT lower(flagged_text) AS ft, category, decision_reason, decided_by FROM findings "
            "WHERE submission_id=? AND version<? AND decision='dismissed'", (sid, version)).fetchall()
        carried = {(p["ft"], p["category"]): p for p in prev}
        rows = conn.execute(
            "SELECT id, flagged_text, category FROM findings WHERE submission_id=? AND version=?",
            (sid, version)).fetchall()
        for r in rows:
            p = carried.get(((r["flagged_text"] or "").lower(), r["category"]))
            if p:
                conn.execute(
                    "UPDATE findings SET decision='dismissed', decision_reason=?, decided_by=?, "
                    "decided_at=datetime('now') WHERE id=?",
                    ("(carried over from an earlier version) " + (p["decision_reason"] or ""),
                     p["decided_by"], r["id"]))
        open_left = conn.execute(
            "SELECT COUNT(*) FROM findings WHERE submission_id=? AND version=? AND decision='open'",
            (sid, version)).fetchone()[0]
        if s and s["status"] == "needs_changes" and open_left == 0:
            conn.execute(
                "UPDATE submissions SET status='in_human_review', updated_at=datetime('now') WHERE id=?", (sid,))
            conn.execute(
                "INSERT INTO audit_log (company_id, submission_id, user_id, action, detail) VALUES (?,?,?,?,?)",
                (s["company_id"], sid, None, "sent_to_human_review",
                 f"v{version}: only previously dismissed flags remain"))
        conn.commit()
    finally:
        conn.close()


class DecisionIn(BaseModel):
    decision: str
    reason: str = ""


class ReviseIn(BaseModel):
    content: str


class EscalateIn(BaseModel):
    note: str = ""


@router.post("/{sid}/findings/{fid}/decision")
def decide(sid: int, fid: int, body: DecisionIn, user=Depends(require_roles("creator"))):
    if body.decision not in ("accepted", "edited", "dismissed", "open"):
        raise HTTPException(400, "Invalid decision")
    reason = body.reason.strip()
    if body.decision == "dismissed" and len(reason) < 5:
        raise HTTPException(400, "Please give a reason for dismissing (at least 5 characters)")
    conn = get_conn()
    try:
        s = get_submission(conn, user, sid)
        if s["status"] != "needs_changes":
            raise HTTPException(400, "Decisions can only be made while changes are needed")
        f = conn.execute(
            "SELECT * FROM findings WHERE id=? AND submission_id=? AND version=?",
            (fid, sid, s["current_version"])).fetchone()
        if not f:
            raise HTTPException(404, "Finding not found")
        if body.decision == "open":
            conn.execute(
                "UPDATE findings SET decision='open', decision_reason=NULL, decided_by=NULL, decided_at=NULL WHERE id=?",
                (fid,))
        else:
            conn.execute(
                "UPDATE findings SET decision=?, decision_reason=?, decided_by=?, decided_at=datetime('now') WHERE id=?",
                (body.decision, reason or None, user["id"], fid))
        action = "finding_reopened" if body.decision == "open" else f"finding_{body.decision}"
        detail = f"{f['category']}: {(f['flagged_text'] or '')[:80]}"
        if reason:
            detail += f" | reason: {reason}"
        audit(conn, user, sid, action, detail)
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.post("/{sid}/revise")
def revise(sid: int, body: ReviseIn, background: BackgroundTasks,
           user=Depends(require_roles("creator"))):
    content = body.content.strip()
    if not content:
        raise HTTPException(400, "Content can't be empty")
    conn = get_conn()
    try:
        s = get_submission(conn, user, sid)
        if s["status"] != "needs_changes":
            raise HTTPException(400, "This submission can't be resubmitted right now")
        cur_v = s["current_version"]
        open_count = conn.execute(
            "SELECT COUNT(*) FROM findings WHERE submission_id=? AND version=? AND decision='open'",
            (sid, cur_v)).fetchone()[0]
        if open_count:
            raise HTTPException(
                400, f"Decide on the {open_count} remaining flag(s) (accept, edit or dismiss) before resubmitting")
        old = conn.execute(
            "SELECT * FROM submission_versions WHERE submission_id=? AND version=?", (sid, cur_v)).fetchone()
        if content == (old["content"] or "").strip():
            raise HTTPException(
                400, "The content hasn't changed. Edit it first, or use 'Send to human review' if you dismissed the flags.")
        new_v = cur_v + 1
        conn.execute(
            "INSERT INTO submission_versions (submission_id, version, content, file_name, file_type) VALUES (?,?,?,?,?)",
            (sid, new_v, content, old["file_name"], old["file_type"]))
        conn.execute(
            "UPDATE submissions SET current_version=?, status='ai_review', review_progress='Queued...', "
            "review_error=NULL, updated_at=datetime('now') WHERE id=?", (new_v, sid))
        audit(conn, user, sid, "revised", f"v{new_v} created by creator, re-check started")
        conn.commit()
    finally:
        conn.close()
    background.add_task(review_and_carry, sid, new_v)
    return {"version": new_v}


@router.post("/{sid}/escalate")
def escalate(sid: int, body: EscalateIn, user=Depends(require_roles("creator"))):
    note = body.note.strip()
    if len(note) < 5:
        raise HTTPException(400, "Please add a short note for the human reviewer")
    conn = get_conn()
    try:
        s = get_submission(conn, user, sid)
        if s["status"] != "needs_changes":
            raise HTTPException(400, "This submission can't be escalated right now")
        conn.execute(
            "INSERT INTO comments (submission_id, user_id, body, kind) VALUES (?,?,?, 'escalation')",
            (sid, user["id"], note))
        conn.execute(
            "UPDATE submissions SET status='in_human_review', updated_at=datetime('now') WHERE id=?", (sid,))
        audit(conn, user, sid, "escalated", f"Sent to human review with open flags. Note: {note[:120]}")
        conn.commit()
    finally:
        conn.close()
    return {"status": "in_human_review"}


@router.get("/{sid}/compare")
def compare(sid: int, user=Depends(current_user)):
    conn = get_conn()
    try:
        s = get_submission(conn, user, sid)
        cur_v = s["current_version"]
        if cur_v < 2:
            return {"has_previous": False}
        pv = conn.execute(
            "SELECT content, score FROM submission_versions WHERE submission_id=? AND version=?",
            (sid, cur_v - 1)).fetchone()
        pf = conn.execute(
            "SELECT id, severity, category, flagged_text, decision, decision_reason FROM findings "
            "WHERE submission_id=? AND version=?", (sid, cur_v - 1)).fetchall()
        return {"has_previous": True, "previous_version": cur_v - 1,
                "previous_content": pv["content"] if pv else "",
                "previous_score": pv["score"] if pv else None,
                "previous_findings": [dict(r) for r in pf]}
    finally:
        conn.close()