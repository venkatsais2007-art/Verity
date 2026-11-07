import re
from fastapi import APIRouter, Depends
from db import get_conn
from auth import current_user, require_roles
from submissions import get_submission

router = APIRouter(prefix="/api", tags=["insights"])

NOT_CARRIED = "NOT (f.decision='dismissed' AND f.decision_reason LIKE '(carried over%')"


@router.get("/submissions/{sid}/audit")
def audit_trail(sid: int, user=Depends(current_user)):
    conn = get_conn()
    try:
        get_submission(conn, user, sid)
        events = conn.execute(
            "SELECT a.id, a.action, a.detail, a.created_at, u.name, u.role "
            "FROM audit_log a LEFT JOIN users u ON u.id = a.user_id "
            "WHERE a.submission_id=? ORDER BY a.id", (sid,)).fetchall()
        versions = conn.execute(
            "SELECT v.version, v.score, v.created_at, v.content, "
            "(SELECT COUNT(*) FROM findings f WHERE f.submission_id=v.submission_id AND f.version=v.version) AS findings_count "
            "FROM submission_versions v WHERE v.submission_id=? ORDER BY v.version", (sid,)).fetchall()
        return {"events": [dict(e) for e in events], "versions": [dict(v) for v in versions]}
    finally:
        conn.close()


@router.get("/users")
def list_users(user=Depends(require_roles("admin"))):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT employee_id, name, role, team FROM users WHERE company_id=? ORDER BY role, name",
            (user["company_id"],)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/insights")
def insights(user=Depends(require_roles("admin", "manager", "reviewer"))):
    conn = get_conn()
    try:
        cid = user["company_id"]
        base = ("FROM findings f JOIN submissions s ON s.id = f.submission_id "
                "WHERE s.company_id=? AND " + NOT_CARRIED)

        kb_titles = [r["title"] for r in conn.execute(
            "SELECT DISTINCT title FROM kb_items WHERE company_id=?", (cid,))]

        def guideline_title(ref):
            ref = ref or ""
            low = ref.lower()
            hits = [t for t in kb_titles if t.lower() in low]
            if hits:
                return max(hits, key=len)
            cleaned = re.sub(r"^\[[A-Za-z]+\]\s*", "", ref)
            cleaned = cleaned.split(":")[0].split(" - ")[0]
            cleaned = re.sub(r"\s*\(v\d+\)\s*$", "", cleaned).strip()
            return cleaned or "Unspecified"

        total_sub = conn.execute("SELECT COUNT(*) FROM submissions WHERE company_id=?", (cid,)).fetchone()[0]
        by_status = {r["status"]: r["n"] for r in conn.execute(
            "SELECT status, COUNT(*) AS n FROM submissions WHERE company_id=? GROUP BY status", (cid,))}
        avg_latest = conn.execute(
            "SELECT AVG(v.score) FROM submissions s JOIN submission_versions v "
            "ON v.submission_id=s.id AND v.version=s.current_version "
            "WHERE s.company_id=? AND v.score IS NOT NULL", (cid,)).fetchone()[0]
        avg_first = conn.execute(
            "SELECT AVG(v.score) FROM submissions s JOIN submission_versions v "
            "ON v.submission_id=s.id AND v.version=1 "
            "WHERE s.company_id=? AND v.score IS NOT NULL", (cid,)).fetchone()[0]
        total_flags = conn.execute("SELECT COUNT(*) " + base, (cid,)).fetchone()[0]

        by_category = [dict(r) for r in conn.execute(
            "SELECT f.category, COUNT(*) AS n " + base + " GROUP BY f.category ORDER BY n DESC", (cid,))]
        phrases = [dict(r) for r in conn.execute(
            "SELECT lower(f.flagged_text) AS phrase, f.category, COUNT(*) AS n " + base +
            " GROUP BY lower(f.flagged_text), f.category ORDER BY n DESC LIMIT 8", (cid,))]

        teams = []
        for r in conn.execute(
            "SELECT u.team, COUNT(DISTINCT s.id) AS submissions, COUNT(f.id) AS flags, "
            "COALESCE(SUM(CASE WHEN f.severity='high' THEN 1 ELSE 0 END),0) AS high "
            "FROM submissions s JOIN users u ON u.id = s.creator_id "
            "LEFT JOIN findings f ON f.submission_id = s.id AND " + NOT_CARRIED +
            " WHERE s.company_id=? AND u.role='creator' GROUP BY u.team", (cid,)):
            d = dict(r)
            d["flags_per_submission"] = round(d["flags"] / d["submissions"], 1) if d["submissions"] else 0
            teams.append(d)
        teams.sort(key=lambda d: -d["flags_per_submission"])

        g = {}
        for r in conn.execute("SELECT f.source_ref, f.decision, f.decision_reason " + base, (cid,)):
            title = guideline_title(r["source_ref"])
            d = g.setdefault(title, {"title": title, "flagged": 0, "dismissed": 0, "accepted": 0, "reasons": []})
            d["flagged"] += 1
            if r["decision"] == "dismissed":
                d["dismissed"] += 1
                if r["decision_reason"] and r["decision_reason"] not in d["reasons"]:
                    d["reasons"].append(r["decision_reason"])
            elif r["decision"] in ("accepted", "edited"):
                d["accepted"] += 1
        guidelines = []
        for d in g.values():
            d["dismiss_rate"] = round(100 * d["dismissed"] / d["flagged"])
            d["reasons"] = d["reasons"][:3]
            d["unclear"] = d["flagged"] >= 2 and d["dismissed"] / d["flagged"] >= 0.4
            guidelines.append(d)
        guidelines.sort(key=lambda d: -d["flagged"])

        return {
            "total_submissions": total_sub,
            "by_status": by_status,
            "avg_score_latest": round(avg_latest) if avg_latest is not None else None,
            "avg_score_first": round(avg_first) if avg_first is not None else None,
            "total_flags": total_flags,
            "by_category": by_category,
            "top_phrases": phrases,
            "teams": teams,
            "guidelines": guidelines,
        }
    finally:
        conn.close()