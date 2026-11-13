"""
End-to-end check of the API against PostgreSQL (or SQLite if DATABASE_URL is not set).

    set DATABASE_URL=postgresql://user:pass@host:5432/dbname
    python run_postgres_flow.py

Covers: login, company separation, content submission, review history, approvals,
comments, knowledge base, insights, and persistence after an application restart.
Uses only the built-in rule checks (no AI key needed).
"""
import os, sys
os.environ["REVIEW_PROVIDER"] = "rules"

from fastapi.testclient import TestClient
import db
from main import app

fails = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def login(c, company, emp, pw="demo123"):
    r = c.post("/api/login", json={"company_id": company, "employee_id": emp, "password": pw})
    return r, ({"Authorization": "Bearer " + r.json()["token"]} if r.status_code == 200 else None)


BAD = "Our miracle Northwind Daily is guaranteed to work. Only $29 per month!!!"
GOOD = "Northwind Daily gives members 12 vitamins and minerals. Now $39 per month."

print("Backend:", "PostgreSQL" if db.is_postgres() else "SQLite")

with TestClient(app) as c:                       # startup => init_db()
    check("health reports database", c.get("/api/health").json().get("database") == ("postgresql" if db.is_postgres() else "sqlite"))

    # --- registration (accounts are created by admins/seed: no signup endpoint exists) ---
    conn = db.get_conn()
    cid = conn.execute("SELECT id FROM companies WHERE code='NORTHWIND'").fetchone()["id"]
    conn.execute("DELETE FROM users WHERE employee_id='newhire01' AND company_id=?", (cid,))
    conn.execute("INSERT INTO users (company_id, employee_id, name, role, team, password_hash) VALUES (?,?,?,?,?,?)",
                 (cid, "newhire01", "New Hire", "creator", "Email", db.hash_password("pass1234")))
    conn.commit(); conn.close()
    r, _ = login(c, "NORTHWIND", "newhire01", "pass1234")
    check("new account can log in", r.status_code == 200)
    try:
        conn = db.get_conn()
        conn.execute("INSERT INTO users (company_id, employee_id, name, role, team, password_hash) VALUES (?,?,?,?,?,?)",
                     (cid, "newhire01", "Dup", "creator", "x", "a$b")); conn.commit()
        check("duplicate employee id is rejected", False)
    except Exception:
        check("duplicate employee id is rejected", True)
    finally:
        try: conn.rollback()
        except Exception: pass
        conn.close()

    # --- login ---
    r, _ = login(c, "NORTHWIND", "creator01", "wrong")
    check("wrong password -> 401", r.status_code == 401)
    r, creator = login(c, "northwind", "creator01")
    check("creator login (case-insensitive company)", r.status_code == 200 and r.json()["user"]["role"] == "creator")
    _, manager = login(c, "NORTHWIND", "manager01")
    _, admin = login(c, "NORTHWIND", "admin01")
    check("/api/me works", c.get("/api/me", headers=creator).json()["employee_id"] == "creator01")

    # --- existing (migrated/seeded) data is visible ---
    subs_before = c.get("/api/submissions", headers=manager).json()
    kb = c.get("/api/kb", headers=admin).json()
    check("knowledge base items present", len(kb) >= 8, len(kb))
    check("existing submissions present", len(subs_before) >= 1, len(subs_before))

    # --- submission -> AI/rules review -> decisions -> revise -> human review -> approve -> publish ---
    r = c.post("/api/submissions", headers=creator, data={"title": "PG test post", "channel": "social", "purpose": "test", "content": BAD})
    check("create submission", r.status_code == 200, r.text)
    sid = r.json()["id"]
    check("submit for review", c.post(f"/api/submissions/{sid}/submit", headers=creator).status_code == 200)
    d = c.get(f"/api/submissions/{sid}", headers=creator).json()
    check("review finished with findings", d["submission"]["status"] == "needs_changes" and len(d["findings"]) >= 3,
          (d["submission"]["status"], len(d["findings"])))
    for f in d["findings"]:
        c.post(f"/api/submissions/{sid}/findings/{f['id']}/decision", headers=creator, json={"decision": "accepted"})
    r = c.post(f"/api/submissions/{sid}/revise", headers=creator, json={"content": GOOD})
    check("revise creates v2", r.status_code == 200 and r.json()["version"] == 2, r.text)
    d = c.get(f"/api/submissions/{sid}", headers=creator).json()
    check("v2 goes to human review", d["submission"]["status"] == "in_human_review", d["submission"]["status"])
    check("both versions stored", len(d["versions"]) == 2)
    cmp_ = c.get(f"/api/submissions/{sid}/compare", headers=creator).json()
    check("compare shows previous version", cmp_.get("has_previous") and cmp_["previous_version"] == 1)

    check("creator cannot approve", c.post(f"/api/submissions/{sid}/approval", headers=creator, json={"action": "approve"}).status_code == 403)
    check("add comment", c.post(f"/api/submissions/{sid}/comments", headers=manager, json={"body": "Looks good to me"}).status_code == 200)
    r = c.post(f"/api/submissions/{sid}/approval", headers=manager, json={"action": "approve", "comment": "ok"})
    check("manager approves", r.status_code == 200 and r.json()["status"] == "approved", r.text)
    r = c.post(f"/api/submissions/{sid}/publish", headers=manager)
    check("publish after approval", r.status_code == 200 and r.json()["status"] == "published", r.text)

    audit = c.get(f"/api/submissions/{sid}/audit", headers=manager).json()
    actions = [e["action"] for e in audit["events"]]
    for a in ("submission_created", "sent_for_ai_review", "ai_review_completed", "finding_accepted", "revised", "approved", "published", "comment_added"):
        check(f"audit has '{a}'", a in actions)
    comments = c.get(f"/api/submissions/{sid}/comments", headers=creator).json()
    check("comments readable", len(comments) == 2 and comments[0]["name"])

    # --- knowledge base versioning + audit ---
    r = c.post("/api/kb", headers=admin, json={"kind": "fact", "title": "PG Test Fact", "content": "v1 text"})
    check("kb create", r.status_code == 200, r.text)
    kid = r.json()["id"]
    r = c.put(f"/api/kb/{kid}", headers=admin, json={"content": "v2 text"})
    check("kb update -> version 2", r.status_code == 200 and r.json()["version"] == 2, r.text)
    check("kb history", len(c.get(f"/api/kb/{r.json()['id']}/history", headers=admin).json()) == 2)
    ins = c.get("/api/insights", headers=manager)
    check("insights endpoint", ins.status_code == 200 and ins.json()["total_submissions"] >= 1, ins.text[:200])
    check("users list (admin)", len(c.get("/api/users", headers=admin).json()) >= 7)

    # --- company separation ---
    conn = db.get_conn()
    acme = conn.execute("SELECT id FROM companies WHERE code='ACME'").fetchone()
    if acme is None:
        acme_id = conn.execute("INSERT INTO companies (code, name) VALUES (?,?)", ("ACME", "Acme Corp")).lastrowid
    else:
        acme_id = acme["id"]
    if not conn.execute("SELECT 1 FROM users WHERE company_id=? AND employee_id='admin01'", (acme_id,)).fetchone():
        conn.execute("INSERT INTO users (company_id, employee_id, name, role, team, password_hash) VALUES (?,?,?,?,?,?)",
                     (acme_id, "admin01", "Acme Admin", "admin", "HQ", db.hash_password("demo123")))
    else:
        conn.execute("UPDATE users SET password_hash=? WHERE company_id=? AND employee_id='admin01'",
                     (db.hash_password("demo123"), acme_id))
    conn.commit(); conn.close()
    _, acme_admin = login(c, "ACME", "admin01")
    check("other company sees no submissions", c.get("/api/submissions", headers=acme_admin).json() == [])
    check("other company sees no KB", c.get("/api/kb", headers=acme_admin).json() == [])
    check("other company cannot open our submission", c.get(f"/api/submissions/{sid}", headers=acme_admin).status_code == 404)
    check("other company users list is separate", len(c.get("/api/users", headers=acme_admin).json()) == 1)

    n_subs = len(c.get("/api/submissions", headers=manager).json())
    n_kb = len(c.get("/api/kb", headers=admin).json())

# --- simulate Render restart / redeploy: drop every connection, start a brand-new app instance ---
db.close_pool()
with TestClient(app) as c2:
    r, manager2 = login(c2, "NORTHWIND", "manager01")
    check("login works after restart", r.status_code == 200)
    _, creator2 = login(c2, "NORTHWIND", "creator01")
    _, newhire = login(c2, "NORTHWIND", "newhire01", "pass1234")
    check("new account still exists after restart", newhire is not None)
    d = c2.get(f"/api/submissions/{sid}", headers=manager2).json()
    check("submission still published after restart", d["submission"]["status"] == "published")
    check("versions/findings persisted", len(d["versions"]) == 2 and len(c2.get(f"/api/submissions/{sid}/audit", headers=manager2).json()["events"]) >= 8)
    check("comments persisted", len(c2.get(f"/api/submissions/{sid}/comments", headers=manager2).json()) == 2)
    check("submission count unchanged (no duplicates / no re-seed)", len(c2.get("/api/submissions", headers=manager2).json()) == n_subs)
    check("kb count unchanged", len(c2.get("/api/kb", headers={"Authorization": "Bearer " + c2.post("/api/login", json={"company_id": "NORTHWIND", "employee_id": "admin01", "password": "demo123"}).json()["token"]}).json()) == n_kb)
    # new records after restart keep numbering correctly
    r = c2.post("/api/submissions", headers=creator2, data={"title": "after restart", "channel": "web", "content": GOOD})
    check("new submission after restart gets a fresh id", r.status_code == 200 and r.json()["id"] > sid, r.text)

db.close_pool()
print("\n%d check(s) failed" % len(fails) if fails else "\nALL CHECKS PASSED")
sys.exit(1 if fails else 0)
