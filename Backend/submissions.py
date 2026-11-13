import os, re, uuid, logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
from db import get_conn
from auth import current_user, require_roles
from extract import extract_text
from file_validation import validate_image
from review import run_review

router = APIRouter(prefix="/api/submissions", tags=["submissions"])

# Set UPLOAD_DIR to a persistent path (e.g. a Render Disk mount) in production.
UPLOAD_DIR = os.getenv("UPLOAD_DIR") or os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
log = logging.getLogger("verity.submissions")

CHANNELS = {"social", "ad", "email", "web"}
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
DOC_EXT = (".pdf", ".docx")
MAX_UPLOAD = 5 * 1024 * 1024


def audit(conn, user, submission_id, action, detail=""):
    conn.execute(
        "INSERT INTO audit_log (company_id, submission_id, user_id, action, detail) VALUES (?,?,?,?,?)",
        (user["company_id"], submission_id, user["id"], action, detail))


def get_submission(conn, user, sid):
    row = conn.execute(
        "SELECT s.*, u.name AS creator_name, u.team AS creator_team "
        "FROM submissions s JOIN users u ON u.id = s.creator_id "
        "WHERE s.id=? AND s.company_id=?", (sid, user["company_id"])).fetchone()
    if not row:
        raise HTTPException(404, "Submission not found")
    if user["role"] == "creator" and row["creator_id"] != user["id"]:
        raise HTTPException(404, "Submission not found")
    return row


@router.post("")
async def create_submission(
    title: str = Form(...),
    channel: str = Form(...),
    purpose: str = Form(""),
    content: str = Form(""),
    file: Optional[UploadFile] = File(None),
    user=Depends(require_roles("creator")),
):
    title, content, purpose = title.strip(), content.strip(), purpose.strip()
    channel = channel.strip().lower()
    if not title:
        raise HTTPException(400, "Title is required")
    if channel not in CHANNELS:
        raise HTTPException(400, "Invalid channel")

    file_name, file_type = None, "text"
    if file is not None and file.filename:
        data = await file.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(400, "File too large (max 5 MB)")
        extension = os.path.splitext(file.filename)[1].lower()
        if extension in IMAGE_EXT:
            file_type = "image"
            try:
                validate_image(data, file.filename)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        elif extension in DOC_EXT or extension == ".txt":
            file_type = "document"
            try:
                text = extract_text(file.filename, data)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            except Exception as exc:
                log.exception("Unexpected document extraction error")
                raise HTTPException(400, "Could not safely read this document") from exc
            if not text:
                raise HTTPException(400, "No readable text found in this document")
            content = text
        else:
            raise HTTPException(400, "Unsupported file. Use PNG, JPG, WEBP, PDF, DOCX, or TXT.")
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(file.filename))[:120]
        file_name = f"{uuid.uuid4().hex}_{safe}"

    if file_type == "text" and not content:
        raise HTTPException(400, "Add some text or upload a file")

    saved_path = None
    try:
        if file_name:
            saved_path = os.path.join(UPLOAD_DIR, file_name)
            with open(saved_path, "xb") as f:
                f.write(data)
        conn = get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO submissions (company_id, creator_id, title, channel, purpose, status) "
                "VALUES (?,?,?,?,?, 'draft')",
                (user["company_id"], user["id"], title, channel, purpose))
            sid = cur.lastrowid
            conn.execute(
                "INSERT INTO submission_versions (submission_id, version, content, file_name, file_type) "
                "VALUES (?,?,?,?,?)", (sid, 1, content, file_name, file_type))
            audit(conn, user, sid, "submission_created", f"{title} ({channel}, {file_type})")
            conn.commit()
        finally:
            conn.close()
    except Exception:
        if saved_path and os.path.exists(saved_path):
            try:
                os.remove(saved_path)
            except OSError:
                log.exception("Could not remove an orphaned upload after a failed submission")
        raise
    return {"id": sid}


@router.get("")
def list_submissions(user=Depends(current_user)):
    conn = get_conn()
    q = ("SELECT s.id, s.title, s.channel, s.status, s.current_version, s.risk_level, "
         "s.created_at, s.updated_at, u.name AS creator_name, u.team AS creator_team "
         "FROM submissions s JOIN users u ON u.id = s.creator_id WHERE s.company_id=?")
    params = [user["company_id"]]
    if user["role"] == "creator":
        q += " AND s.creator_id=?"
        params.append(user["id"])
    q += " ORDER BY s.updated_at DESC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/{sid}")
def detail(sid: int, user=Depends(current_user)):
    conn = get_conn()
    try:
        s = get_submission(conn, user, sid)
        versions = conn.execute(
            "SELECT version, content, file_name, file_type, score, created_at "
            "FROM submission_versions WHERE submission_id=? ORDER BY version DESC", (sid,)).fetchall()
        findings = conn.execute(
            "SELECT * FROM findings WHERE submission_id=? AND version=? "
            "ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, id",
            (sid, s["current_version"])).fetchall()
        return {"submission": dict(s), "versions": [dict(v) for v in versions],
                "findings": [dict(f) for f in findings]}
    finally:
        conn.close()


@router.get("/{sid}/file")
def get_file(sid: int, user=Depends(current_user)):
    conn = get_conn()
    try:
        s = get_submission(conn, user, sid)
        v = conn.execute(
            "SELECT file_name FROM submission_versions WHERE submission_id=? AND version=?",
            (sid, s["current_version"])).fetchone()
    finally:
        conn.close()
    if not v or not v["file_name"]:
        raise HTTPException(404, "No file")
    path = os.path.join(UPLOAD_DIR, v["file_name"])
    if not os.path.isfile(path):
        raise HTTPException(404, "File missing")
    return FileResponse(path)


@router.post("/{sid}/submit")
def submit_for_review(sid: int, background: BackgroundTasks, user=Depends(require_roles("creator"))):
    conn = get_conn()
    try:
        s = get_submission(conn, user, sid)
        if s["status"] not in ("draft", "needs_changes"):
            raise HTTPException(400, "This submission can't be sent for review right now")
        conn.execute(
            "UPDATE submissions SET status='ai_review', review_progress='Queued...', review_error=NULL, "
            "updated_at=datetime('now') WHERE id=?", (sid,))
        audit(conn, user, sid, "sent_for_ai_review", f"v{s['current_version']}")
        conn.commit()
        version = s["current_version"]
    finally:
        conn.close()
    background.add_task(run_review, sid, version)
    return {"status": "ai_review"}