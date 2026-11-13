import os
import secrets
import datetime
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from db import get_conn


def _secret_key():
    secret = os.getenv("SECRET_KEY", "").strip()
    production = (
        os.getenv("APP_ENV", "").lower() in {"prod", "production"}
        or bool(os.getenv("RENDER"))
        or bool(os.getenv("DATABASE_URL") or os.getenv("DB_HOST"))
    )
    if not secret:
        if production:
            raise RuntimeError("SECRET_KEY must be configured in production.")
        return secrets.token_urlsafe(48)
    if production and len(secret.encode("utf-8")) < 32:
        raise RuntimeError("SECRET_KEY must contain at least 32 bytes in production.")
    return secret


SECRET = _secret_key()
bearer = HTTPBearer(auto_error=False)
TOKEN_TTL = datetime.timedelta(hours=12)


def create_token(user_id):
    now = datetime.datetime.now(datetime.timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + TOKEN_TTL},
        SECRET,
        algorithm="HS256",
    )


def current_user(creds=Depends(bearer)):
    if not creds:
        raise HTTPException(401, "Not logged in")
    try:
        data = jwt.decode(
            creds.credentials,
            SECRET,
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
        )
        subject = data.get("sub")
        if not isinstance(subject, str) or not subject.isdecimal():
            raise ValueError("Invalid token subject")
    except (jwt.PyJWTError, TypeError, ValueError):
        raise HTTPException(401, "Invalid or expired token")
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT u.id, u.employee_id, u.name, u.role, u.team, u.company_id, c.name AS company_name "
            "FROM users u JOIN companies c ON c.id = u.company_id WHERE u.id = ?",
            (int(subject),),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(401, "User not found")
    return dict(row)


def require_roles(*roles):
    def checker(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, "Not allowed for your role")
        return user
    return checker