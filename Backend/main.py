import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from db import init_db, get_conn, verify_password
from auth import create_token, current_user, require_roles
from review import ensure_columns
from kb import router as kb_router
from submissions import router as submissions_router
from revisions import router as revisions_router
from approvals import router as approvals_router
from insights import router as insights_router

app = FastAPI(title="Verity API")
app.include_router(kb_router)
app.include_router(submissions_router)
app.include_router(revisions_router)
app.include_router(approvals_router)
app.include_router(insights_router)


@app.on_event("startup")
def startup():
    init_db()
    ensure_columns()


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "Verity"}


class LoginIn(BaseModel):
    company_id: str
    employee_id: str
    password: str


@app.post("/api/login")
def login(body: LoginIn):
    conn = get_conn()
    row = conn.execute(
        "SELECT u.*, c.name AS company_name FROM users u JOIN companies c ON c.id = u.company_id "
        "WHERE c.code = ? AND u.employee_id = ?",
        (body.company_id.strip().upper(), body.employee_id.strip().lower())).fetchone()
    conn.close()
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "Invalid company ID, employee ID or password")
    user = {k: row[k] for k in ("id", "employee_id", "name", "role", "team", "company_id", "company_name")}
    return {"token": create_token(row["id"]), "user": user}


@app.get("/api/me")
def me(user=Depends(current_user)):
    return user


@app.get("/api/admin/ping")
def admin_ping(user=Depends(require_roles("admin"))):
    return {"ok": True, "role": user["role"]}

@app.get("/debug-dist")
def debug_dist():
    d = os.path.abspath(DIST)
    root = os.path.abspath(os.path.join(d, "..", ".."))
    return {
        "dist_path": d,
        "dist_exists": os.path.isdir(d),
        "assets_exists": os.path.isdir(os.path.join(d, "assets")),
        "repo_root_contents": os.listdir(root) if os.path.isdir(root) else "root missing",
    }
DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist")
if os.path.isdir(os.path.join(DIST, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST, "assets")), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = os.path.join(DIST, path)
        if path and os.path.isfile(f):
            return FileResponse(f)
        return FileResponse(os.path.join(DIST, "index.html"))