import os
import hashlib
import logging
import sqlite3
import time
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from psycopg import Error as PsycopgError
from psycopg_pool import PoolTimeout
from db import (
    init_db,
    get_conn,
    verify_password,
    hash_password,
    password_needs_rehash,
    close_pool,
    is_postgres,
)
from auth import create_token, current_user, require_roles
from review import ensure_columns
from kb import router as kb_router
from submissions import router as submissions_router
from revisions import router as revisions_router
from approvals import router as approvals_router
from insights import router as insights_router
from visual_analysis import router as visual_analysis_router

log = logging.getLogger("verity.api")
app = FastAPI(title="Verity API")
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 15 * 60
app.include_router(kb_router)
app.include_router(submissions_router)
app.include_router(revisions_router)
app.include_router(approvals_router)
app.include_router(insights_router)
app.include_router(visual_analysis_router)


@app.on_event("startup")
def startup():
    init_db()
    ensure_columns()


@app.on_event("shutdown")
def shutdown():
    close_pool()


@app.get("/api/health")
def health():
    conn = get_conn()
    try:
        conn.execute("SELECT 1").fetchone()
    finally:
        conn.close()
    return {"status": "ok", "app": "Verity", "database": "postgresql" if is_postgres() else "sqlite"}


class LoginIn(BaseModel):
    company_id: str = Field(min_length=1, max_length=64)
    employee_id: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


def _login_account_key(company_id, employee_id):
    normalized = f"{company_id.strip().upper()}\0{employee_id.strip().lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _consume_login_attempt(conn, account_key, now):
    reset_before = now - LOGIN_WINDOW_SECONDS
    conn.execute(
        "DELETE FROM login_rate_limits WHERE window_started <= ?",
        (reset_before,),
    )
    conn.execute(
        "INSERT INTO login_rate_limits (account_key, window_started, attempts) VALUES (?,?,1) "
        "ON CONFLICT(account_key) DO UPDATE SET "
        "attempts=CASE WHEN login_rate_limits.window_started <= ? THEN 1 "
        "ELSE login_rate_limits.attempts + 1 END, "
        "window_started=CASE WHEN login_rate_limits.window_started <= ? THEN ? "
        "ELSE login_rate_limits.window_started END",
        (account_key, now, reset_before, reset_before, now),
    )
    row = conn.execute(
        "SELECT window_started, attempts FROM login_rate_limits WHERE account_key=?",
        (account_key,),
    ).fetchone()
    conn.commit()
    if row["attempts"] > LOGIN_MAX_ATTEMPTS:
        retry_after = max(1, row["window_started"] + LOGIN_WINDOW_SECONDS - now)
        raise HTTPException(
            429,
            "Too many sign-in attempts. Please wait before trying again.",
            headers={"Retry-After": str(retry_after)},
        )


@app.post("/api/login")
def login(body: LoginIn):
    conn = get_conn()
    account_key = _login_account_key(body.company_id, body.employee_id)
    try:
        _consume_login_attempt(conn, account_key, int(time.time()))
        row = conn.execute(
            "SELECT u.*, c.name AS company_name FROM users u JOIN companies c ON c.id = u.company_id "
            "WHERE c.code = ? AND u.employee_id = ?",
            (body.company_id.strip().upper(), body.employee_id.strip().lower()),
        ).fetchone()
        if not row or not verify_password(body.password, row["password_hash"]):
            raise HTTPException(401, "Invalid company ID, employee ID or password")
        if password_needs_rehash(row["password_hash"]):
            conn.execute(
                "UPDATE users SET password_hash=? WHERE id=?",
                (hash_password(body.password), row["id"]),
            )
        conn.execute("DELETE FROM login_rate_limits WHERE account_key=?", (account_key,))
        conn.commit()
    finally:
        conn.close()
    user = {k: row[k] for k in ("id", "employee_id", "name", "role", "team", "company_id", "company_name")}
    return {"token": create_token(row["id"]), "user": user}


@app.get("/api/me")
def me(user=Depends(current_user)):
    return user


@app.get("/api/admin/ping")
def admin_ping(user=Depends(require_roles("admin"))):
    return {"ok": True, "role": user["role"]}

@app.get("/debug-dist")
def debug_dist(user=Depends(require_roles("admin"))):
    d = os.path.abspath(DIST)
    root = os.path.abspath(os.path.join(d, "..", ".."))
    return {
        "dist_path": d,
        "dist_exists": os.path.isdir(d),
        "assets_exists": os.path.isdir(os.path.join(d, "assets")),
        "repo_root_contents": os.listdir(root) if os.path.isdir(root) else "root missing",
    }


async def database_error_handler(request, exc):
    log.error("Database request failed: %s %s", request.method, request.url.path,
              exc_info=(type(exc), exc, exc.__traceback__))
    return JSONResponse(
        status_code=503,
        content={"detail": "The database is temporarily unavailable. Please try again."},
    )


app.add_exception_handler(sqlite3.Error, database_error_handler)
app.add_exception_handler(PsycopgError, database_error_handler)
app.add_exception_handler(PoolTimeout, database_error_handler)
DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist")
if os.path.isdir(os.path.join(DIST, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST, "assets")), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "API endpoint not found")
        root = os.path.realpath(DIST)
        candidate = os.path.realpath(os.path.join(root, path))
        try:
            inside_dist = os.path.commonpath((root, candidate)) == root
        except ValueError:
            inside_dist = False
        if path and inside_dist and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(root, "index.html"))