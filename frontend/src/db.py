import sqlite3, os, hashlib, secrets

DB_PATH = os.path.join(os.path.dirname(__file__), "verity.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(8)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return f"{salt}${h}"


def verify_password(password, stored):
    salt, _ = stored.split("$")
    return secrets.compare_digest(hash_password(password, salt), stored)


SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id INTEGER NOT NULL REFERENCES companies(id),
  employee_id TEXT NOT NULL,
  name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin','creator','manager','reviewer')),
  team TEXT,
  password_hash TEXT NOT NULL,
  UNIQUE(company_id, employee_id)
);
CREATE TABLE IF NOT EXISTS kb_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id INTEGER NOT NULL REFERENCES companies(id),
  kind TEXT NOT NULL CHECK (kind IN ('guideline','fact','term','tone','asset')),
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS submissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id INTEGER NOT NULL REFERENCES companies(id),
  creator_id INTEGER NOT NULL REFERENCES users(id),
  title TEXT NOT NULL,
  channel TEXT NOT NULL,
  purpose TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  current_version INTEGER NOT NULL DEFAULT 1,
  risk_level TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS submission_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  submission_id INTEGER NOT NULL REFERENCES submissions(id),
  version INTEGER NOT NULL,
  content TEXT,
  file_name TEXT,
  file_type TEXT,
  score INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS findings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  submission_id INTEGER NOT NULL REFERENCES submissions(id),
  version INTEGER NOT NULL,
  severity TEXT NOT NULL,
  category TEXT NOT NULL,
  flagged_text TEXT,
  reason TEXT,
  source_ref TEXT,
  suggestion TEXT,
  decision TEXT NOT NULL DEFAULT 'open',
  decision_reason TEXT,
  decided_by INTEGER REFERENCES users(id),
  decided_at TEXT
);
CREATE TABLE IF NOT EXISTS comments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  submission_id INTEGER NOT NULL REFERENCES submissions(id),
  user_id INTEGER NOT NULL REFERENCES users(id),
  body TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'comment',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id INTEGER NOT NULL,
  submission_id INTEGER,
  user_id INTEGER,
  action TEXT NOT NULL,
  detail TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

KB_SEED = [
    ("guideline", "Brand Voice",
     "Northwind speaks in a warm, clear and confident voice. Address the reader as 'you'. "
     "Avoid hype, slang and fear-based messaging. Use at most one exclamation mark per post. "
     "Sentences should be short and readable at an 8th-grade level."),
    ("tone", "Tone Rules",
     "Friendly but professional. Never sarcastic. Never shame the reader. "
     "Do not compare ourselves to named competitors. Do not use ALL CAPS for emphasis."),
    ("term", "Preferred Terminology",
     "Preferred: 'members' (not 'customers'), 'Northwind Daily' (always capitalised, never 'the Daily'), "
     "'plant-based' (not 'vegan-ish'), 'wellness' (not 'health cure'). "
     "Banned words: miracle, guaranteed, cure, detox, best in the world, instant results."),
    ("fact", "Approved Company Facts",
     "Northwind Wellness was founded in 2016 in Austin, Texas. "
     "Northwind Daily contains 12 vitamins and minerals and 0 artificial colours. "
     "Free shipping applies to orders over $40. Members can pause or cancel anytime. "
     "Northwind is available in the US and Canada only."),
    ("fact", "Approved Claims and Evidence",
     "An 8-week internal survey of 120 members reported 18% higher self-reported energy. "
     "This must be described as 'self-reported' and 'internal survey', never as a clinical study. "
     "Northwind products do not treat, cure or prevent any disease. "
     "The 2025 price of Northwind Daily is $39 per month (the old $29 price is outdated)."),
    ("asset", "Brand Colours",
     "Primary green #1F6F5C. Secondary sunrise yellow #F4B942. Text charcoal #1A1A1A. "
     "Background off-white #FAFAF7. Text on the primary green must be white. "
     "Never place yellow text on a white background (low contrast)."),
    ("asset", "Brand Fonts",
     "Headings: Poppins (semi-bold). Body: Inter (regular). No other typefaces in brand materials."),
    ("asset", "Logo Usage",
     "Use only the official Northwind logo. Minimum width 120px. Keep clear space equal to the height of the 'N'. "
     "Do not stretch, recolour, rotate or add effects to the logo. Every image needs descriptive alt text."),
]

USERS_SEED = [
    ("admin01", "Aisha Rahman", "admin", "Brand Office"),
    ("creator01", "Rohan Mehta", "creator", "Social Media"),
    ("creator02", "Priya Nair", "creator", "Performance Ads"),
    ("creator03", "Daniel Cho", "creator", "Email"),
    ("manager01", "Sara Lindqvist", "manager", "Marketing"),
    ("reviewer01", "Marcus Bell", "reviewer", "Brand Office"),
]


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 0:
        cur = conn.execute("INSERT INTO companies (code, name) VALUES (?, ?)",
                           ("NORTHWIND", "Northwind Wellness"))
        company_id = cur.lastrowid
        admin_id = None
        for emp, name, role, team in USERS_SEED:
            c = conn.execute(
                "INSERT INTO users (company_id, employee_id, name, role, team, password_hash) "
                "VALUES (?,?,?,?,?,?)",
                (company_id, emp, name, role, team, hash_password("demo123")))
            if role == "admin":
                admin_id = c.lastrowid
        for kind, title, content in KB_SEED:
            conn.execute(
                "INSERT INTO kb_items (company_id, kind, title, content, created_by) VALUES (?,?,?,?,?)",
                (company_id, kind, title, content, admin_id))
        conn.commit()
    conn.close()