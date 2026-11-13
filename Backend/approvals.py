from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from db import get_conn
from auth import current_user, require_roles
from submissions import get_submission, audit

router = APIRouter(prefix="/api/submissions", tags=["approvals"])


class CommentIn(BaseModel):
    body: str


class ApprovalIn(BaseModel):
    action: str
    comment: str = ""


@router.get("/{sid}/comments")
def list_comments(sid: int, user=Depends(current_user)):
    conn = get_conn()
    try:
        get_submission(conn, user, sid)
        rows = conn.execute(
            "SELECT c.id, c.body, c.kind, c.created_at, u.name, u.role "
            "FROM comments c JOIN users u ON u.id = c.user_id "
            "WHERE c.submission_id=? ORDER BY c.id", (sid,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/{sid}/comments")
def add_comment(sid: int, body: CommentIn, user=Depends(current_user)):
    text = body.body.strip()
    if not text:
        raise HTTPException(400, "Comment can't be empty")
    conn = get_conn()
    try:
        get_submission(conn, user, sid)
        conn.execute(
            "INSERT INTO comments (submission_id, user_id, body, kind) VALUES (?,?,?, 'comment')",
            (sid, user["id"], text))
        audit(conn, user, sid, "comment_added", text[:120])
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.post("/{sid}/approval")
def approval(sid: int, body: ApprovalIn, user=Depends(require_roles("manager", "reviewer"))):
    action = body.action
    if action not in ("approve", "request_changes", "reject"):
        raise HTTPException(400, "Invalid action")
    comment = body.comment.strip()
    if action != "approve" and len(comment) < 5:
        raise HTTPException(400, "Please explain your decision to the creator (at least 5 characters)")
    conn = get_conn()
    try:
        s = get_submission(conn, user, sid)
        if s["status"] != "in_human_review":
            raise HTTPException(400, "This submission is not waiting for human review")
        if s["creator_id"] == user["id"]:
            raise HTTPException(403, "You can't review your own submission")
        if action == "approve" and s["risk_level"] == "high" and user["role"] != "manager":
            raise HTTPException(403, "High-risk content needs a manager's approval")
        new_status, audit_action, kind = {
            "approve": ("approved", "approved", "approval"),
            "request_changes": ("needs_changes", "changes_requested", "request_changes"),
            "reject": ("rejected", "rejected", "rejection"),
        }[action]
        update = conn.execute(
            "UPDATE submissions SET status=?, updated_at=datetime('now') "
            "WHERE id=? AND status='in_human_review'", (new_status, sid))
        if update.rowcount != 1:
            raise HTTPException(409, "This submission has already been reviewed")
        if comment:
            conn.execute(
                "INSERT INTO comments (submission_id, user_id, body, kind) VALUES (?,?,?,?)",
                (sid, user["id"], comment, kind))
        audit(conn, user, sid, audit_action, comment[:120])
        conn.commit()
    finally:
        conn.close()
    return {"status": new_status}


@router.post("/{sid}/publish")
def publish(sid: int, user=Depends(require_roles("manager", "reviewer"))):
    conn = get_conn()
    try:
        s = get_submission(conn, user, sid)
        if s["status"] != "approved":
            raise HTTPException(400, "Only approved content can be published")
        human = conn.execute(
            "SELECT 1 FROM audit_log WHERE submission_id=? AND action='approved' AND user_id IS NOT NULL",
            (sid,)).fetchone()
        if not human:
            raise HTTPException(400, "No human approval is on record for this content")
        update = conn.execute(
            "UPDATE submissions SET status='published', updated_at=datetime('now') "
            "WHERE id=? AND status='approved'", (sid,))
        if update.rowcount != 1:
            raise HTTPException(409, "This submission is no longer awaiting publication")
        audit(conn, user, sid, "published", f"Published by {user['name']} ({user['role']})")
        conn.commit()
    finally:
        conn.close()
    return {"status": "published"}