import os, jwt, datetime
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from db import get_conn

SECRET = os.getenv("SECRET_KEY", "dev-secret-change-me")
bearer = HTTPBearer(auto_error=False)


def create_token(user_id):
    exp = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=12)
    return jwt.encode({"sub": str(user_id), "exp": exp}, SECRET, algorithm="HS256")


def current_user(creds=Depends(bearer)):
    if not creds:
        raise HTTPException(401, "Not logged in")
    try:
        data = jwt.decode(creds.credentials, SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    conn = get_conn()
    row = conn.execute(
        "SELECT u.id, u.employee_id, u.name, u.role, u.team, u.company_id, c.name AS company_name "
        "FROM users u JOIN companies c ON c.id = u.company_id WHERE u.id = ?",
        (int(data["sub"]),)).fetchone()
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