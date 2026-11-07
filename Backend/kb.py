from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from db import get_conn
from auth import current_user, require_roles
from extract import extract_text

router = APIRouter(prefix="/api/kb", tags=["knowledge base"])

KINDS = {"guideline", "fact", "term", "tone", "asset"}
MAX_UPLOAD = 5 * 1024 * 1024


def audit(conn, user, action, detail):
    conn.execute(
        "INSERT INTO audit_log (company_id, user_id, action, detail) VALUES (?,?,?,?)",
        (user["company_id"], user["id"], action, detail))


def next_version(conn, company_id, kind, title):
    row = conn.execute(
        "SELECT MAX(version) FROM kb_items WHERE company_id=? AND kind=? AND title=?",
        (company_id, kind, title)).fetchone()
    return (row[0] or 0) + 1


def create_item(conn, user, kind, title, content):
    title, content = title.strip(), content.strip()
    if kind not in KINDS:
        raise HTTPException(400, "Invalid kind")
    if not title or not content:
        raise HTTPException(400, "Title and content are required")
    exists = conn.execute(
        "SELECT 1 FROM kb_items WHERE company_id=? AND kind=? AND title=? AND is_active=1",
        (user["company_id"], kind, title)).fetchone()
    if exists:
        raise HTTPException(400, "An item with this title already exists. Edit it to make a new version.")
    version = next_version(conn, user["company_id"], kind, title)
    cur = conn.execute(
        "INSERT INTO kb_items (company_id, kind, title, content, version, created_by) VALUES (?,?,?,?,?,?)",
        (user["company_id"], kind, title, content, version, user["id"]))
    audit(conn, user, "kb_created", f"{kind}: {title} (v{version})")
    conn.commit()
    return cur.lastrowid


class ItemIn(BaseModel):
    kind: str
    title: str
    content: str


class UpdateIn(BaseModel):
    content: str


@router.get("")
def list_items(user=Depends(current_user)):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, kind, title, content, version, created_at FROM kb_items "
        "WHERE company_id=? AND is_active=1 ORDER BY kind, title",
        (user["company_id"],)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("")
def add_item(body: ItemIn, user=Depends(require_roles("admin"))):
    conn = get_conn()
    try:
        new_id = create_item(conn, user, body.kind, body.title, body.content)
    finally:
        conn.close()
    return {"id": new_id}


@router.post("/upload")
async def upload_item(kind: str = Form(...), title: str = Form(...),
                      file: UploadFile = File(...), user=Depends(require_roles("admin"))):
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(400, "File too large (max 5 MB)")
    try:
        text = extract_text(file.filename, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(400, "Could not read this file")
    if not text:
        raise HTTPException(400, "No readable text found in this file")
    conn = get_conn()
    try:
        new_id = create_item(conn, user, kind, title, text)
    finally:
        conn.close()
    return {"id": new_id, "chars": len(text)}


@router.put("/{item_id}")
def update_item(item_id: int, body: UpdateIn, user=Depends(require_roles("admin"))):
    content = body.content.strip()
    if not content:
        raise HTTPException(400, "Content is required")
    conn = get_conn()
    try:
        old = conn.execute(
            "SELECT * FROM kb_items WHERE id=? AND company_id=? AND is_active=1",
            (item_id, user["company_id"])).fetchone()
        if not old:
            raise HTTPException(404, "Item not found")
        version = next_version(conn, user["company_id"], old["kind"], old["title"])
        conn.execute("UPDATE kb_items SET is_active=0 WHERE id=?", (item_id,))
        cur = conn.execute(
            "INSERT INTO kb_items (company_id, kind, title, content, version, created_by) VALUES (?,?,?,?,?,?)",
            (user["company_id"], old["kind"], old["title"], content, version, user["id"]))
        audit(conn, user, "kb_updated", f"{old['kind']}: {old['title']} (v{version})")
        conn.commit()
        return {"id": cur.lastrowid, "version": version}
    finally:
        conn.close()


@router.delete("/{item_id}")
def archive_item(item_id: int, user=Depends(require_roles("admin"))):
    conn = get_conn()
    try:
        item = conn.execute(
            "SELECT * FROM kb_items WHERE id=? AND company_id=? AND is_active=1",
            (item_id, user["company_id"])).fetchone()
        if not item:
            raise HTTPException(404, "Item not found")
        conn.execute("UPDATE kb_items SET is_active=0 WHERE id=?", (item_id,))
        audit(conn, user, "kb_archived", f"{item['kind']}: {item['title']}")
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.get("/{item_id}/history")
def item_history(item_id: int, user=Depends(current_user)):
    conn = get_conn()
    try:
        item = conn.execute(
            "SELECT kind, title FROM kb_items WHERE id=? AND company_id=?",
            (item_id, user["company_id"])).fetchone()
        if not item:
            raise HTTPException(404, "Item not found")
        rows = conn.execute(
            "SELECT k.id, k.version, k.content, k.is_active, k.created_at, u.name AS author "
            "FROM kb_items k LEFT JOIN users u ON u.id = k.created_by "
            "WHERE k.company_id=? AND k.kind=? AND k.title=? ORDER BY k.version DESC",
            (user["company_id"], item["kind"], item["title"])).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()