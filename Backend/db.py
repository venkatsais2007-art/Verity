"""
Verity database layer.

* PostgreSQL is used whenever DATABASE_URL (or DB_HOST/DB_NAME/DB_USER/DB_PASSWORD) is set.
* If no PostgreSQL settings exist the app falls back to the local SQLite file (verity.db),
  so local development keeps working exactly as before.

The rest of the code base keeps using  conn.execute("... ? ...", params)  with
row["column"] / row[0] access, exactly like sqlite3. This module translates those
calls for PostgreSQL, so no endpoint had to be rewritten.
"""
import os, re, sqlite3, hashlib, secrets, logging

log = logging.getLogger("verity.db")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("SQLITE_PATH", os.path.join(BASE_DIR, "verity.db"))


# --------------------------------------------------------------------------- #
# Configuration (everything comes from environment variables)
# --------------------------------------------------------------------------- #
def database_url():
    """Return a postgresql:// URL built from the environment, or None for SQLite mode."""
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        host = os.getenv("DB_HOST", "").strip()
        name = os.getenv("DB_NAME", "").strip()
        user = os.getenv("DB_USER", "").strip()
        if host and name and user:
            from urllib.parse import quote
            pwd = quote(os.getenv("DB_PASSWORD", ""), safe="")
            port = os.getenv("DB_PORT", "5432").strip()
            url = f"postgresql://{quote(user, safe='')}:{pwd}@{host}:{port}/{name}"
    if not url:
        return None
    if url.startswith("postgres://"):           # Render/Heroku style
        url = "postgresql://" + url[len("postgres://"):]
    sslmode = os.getenv("DB_SSLMODE", "").strip()
    if sslmode and "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + f"sslmode={sslmode}"
    return url


def is_postgres():
    return database_url() is not None


# --------------------------------------------------------------------------- #
# Password helpers (unchanged, authentication stays compatible)
# --------------------------------------------------------------------------- #
PASSWORD_HASH_ITERATIONS = 600_000
LEGACY_PASSWORD_HASH_ITERATIONS = 100_000


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), PASSWORD_HASH_ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt}${digest}"


def verify_password(password, stored):
    try:
        parts = stored.split("$")
        if len(parts) == 4 and parts[0] == "pbkdf2_sha256":
            iterations = int(parts[1])
            if not 1 <= iterations <= 2_000_000:
                return False
            salt, expected = parts[2], parts[3]
        elif len(parts) == 2:
            salt, expected = parts
            iterations = LEGACY_PASSWORD_HASH_ITERATIONS
        else:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations
        ).hex()
        return secrets.compare_digest(digest, expected)
    except (AttributeError, TypeError, ValueError):
        return False


def password_needs_rehash(stored):
    parts = stored.split("$") if isinstance(stored, str) else []
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256" or not parts[1].isdigit():
        return True
    try:
        return int(parts[1]) < PASSWORD_HASH_ITERATIONS
    except ValueError:
        return True


# --------------------------------------------------------------------------- #
# PostgreSQL compatibility wrapper
# --------------------------------------------------------------------------- #
NOW_TEXT = "to_char(timezone('utc', now()), 'YYYY-MM-DD HH24:MI:SS')"
_RE_NOW_MOD = re.compile(r"datetime\('now',\s*\?\)", re.I)
_RE_NOW = re.compile(r"datetime\('now'\)", re.I)
_RE_INSERT = re.compile(r"^\s*INSERT\s+INTO\s+(\w+)", re.I)
_TABLES_WITH_ID = {"companies", "users", "kb_items", "submissions", "submission_versions",
                   "findings", "comments", "audit_log", "brand_logos"}


def translate_sql(sql):
    """sqlite-style SQL  ->  PostgreSQL SQL."""
    sql = sql.replace("%", "%%")
    sql = _RE_NOW_MOD.sub(
        "to_char(timezone('utc', now()) + (?)::interval, 'YYYY-MM-DD HH24:MI:SS')", sql)
    sql = _RE_NOW.sub(NOW_TEXT, sql)
    sql = sql.replace("?", "%s")
    m = _RE_INSERT.match(sql)
    if m and m.group(1).lower() in _TABLES_WITH_ID and "returning" not in sql.lower():
        sql = sql.rstrip().rstrip(";") + " RETURNING id"
    return sql


class Row(dict):
    """dict that also supports row[0] like sqlite3.Row."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


def _row_factory(cursor):
    cols = [c.name for c in (cursor.description or [])]
    return lambda values: Row(zip(cols, values))


class PGCursor:
    def __init__(self, cur, returned_id=None):
        self._cur = cur
        self.lastrowid = returned_id

    @property
    def rowcount(self):
        return self._cur.rowcount

    def fetchone(self):
        return self._cur.fetchone() if self._cur.description else None

    def fetchall(self):
        return self._cur.fetchall() if self._cur.description else []

    def __iter__(self):
        return iter(self.fetchall())


class PGConnection:
    """Gives a psycopg connection the small sqlite3-style API the app uses."""
    def __init__(self, pool):
        self._pool = pool
        self._conn = pool.getconn()
        self._closed = False

    def execute(self, sql, params=()):
        cur = self._conn.cursor(row_factory=_row_factory)
        t = translate_sql(sql)
        cur.execute(t, tuple(params))
        rid = None
        if t.endswith("RETURNING id"):
            row = cur.fetchone()
            rid = row["id"] if row else None
        return PGCursor(cur, rid)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self._conn.rollback()           # never leave a transaction open in the pool
        except Exception:
            pass
        self._pool.putconn(self._conn)


# --------------------------------------------------------------------------- #
# Connection handling
# --------------------------------------------------------------------------- #
_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        from psycopg_pool import ConnectionPool
        _pool = ConnectionPool(
            conninfo=database_url(),
            min_size=int(os.getenv("DB_POOL_MIN", "1")),
            max_size=int(os.getenv("DB_POOL_MAX", "10")),
            timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
            max_idle=300,
            check=ConnectionPool.check_connection,   # drops dead connections after restarts/idle
            open=False,
            kwargs={"connect_timeout": 10},
        )
        _pool.open(wait=True, timeout=60)
    return _pool


def close_pool():
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def get_conn():
    if is_postgres():
        return PGConnection(_get_pool())
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# --------------------------------------------------------------------------- #
# Schema + versioned migrations
# --------------------------------------------------------------------------- #
SQLITE_SCHEMA = """
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
CREATE TABLE IF NOT EXISTS brand_logos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id INTEGER NOT NULL REFERENCES companies(id),
  file_name TEXT NOT NULL,
  original_name TEXT NOT NULL,
  width INTEGER NOT NULL,
  height INTEGER NOT NULL,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS visual_reviews (
  submission_id INTEGER NOT NULL REFERENCES submissions(id),
  version INTEGER NOT NULL,
  status TEXT NOT NULL,
  result_json TEXT,
  error TEXT,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (submission_id, version)
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
CREATE TABLE IF NOT EXISTS login_rate_limits (
  account_key TEXT PRIMARY KEY,
  window_started INTEGER NOT NULL,
  attempts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_login_rate_limits_window ON login_rate_limits(window_started);
"""

_PG_NOW = f"DEFAULT ({NOW_TEXT})"

# Same tables, columns and relationships as SQLite. Identity columns accept explicit ids
# (needed so migrated rows keep their ids and foreign keys stay valid).
PG_MIGRATIONS = [
    ("001_base_schema", f"""
CREATE TABLE IF NOT EXISTS companies (
  id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
  id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  company_id INTEGER NOT NULL REFERENCES companies(id),
  employee_id TEXT NOT NULL,
  name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin','creator','manager','reviewer')),
  team TEXT,
  password_hash TEXT NOT NULL,
  UNIQUE(company_id, employee_id)
);
CREATE TABLE IF NOT EXISTS kb_items (
  id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  company_id INTEGER NOT NULL REFERENCES companies(id),
  kind TEXT NOT NULL CHECK (kind IN ('guideline','fact','term','tone','asset')),
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL {_PG_NOW}
);
CREATE TABLE IF NOT EXISTS submissions (
  id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  company_id INTEGER NOT NULL REFERENCES companies(id),
  creator_id INTEGER NOT NULL REFERENCES users(id),
  title TEXT NOT NULL,
  channel TEXT NOT NULL,
  purpose TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  current_version INTEGER NOT NULL DEFAULT 1,
  risk_level TEXT,
  created_at TEXT NOT NULL {_PG_NOW},
  updated_at TEXT NOT NULL {_PG_NOW}
);
CREATE TABLE IF NOT EXISTS submission_versions (
  id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  submission_id INTEGER NOT NULL REFERENCES submissions(id),
  version INTEGER NOT NULL,
  content TEXT,
  file_name TEXT,
  file_type TEXT,
  score INTEGER,
  created_at TEXT NOT NULL {_PG_NOW}
);
CREATE TABLE IF NOT EXISTS findings (
  id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
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
  id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  submission_id INTEGER NOT NULL REFERENCES submissions(id),
  user_id INTEGER NOT NULL REFERENCES users(id),
  body TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'comment',
  created_at TEXT NOT NULL {_PG_NOW}
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  company_id INTEGER NOT NULL,
  submission_id INTEGER,
  user_id INTEGER,
  action TEXT NOT NULL,
  detail TEXT,
  created_at TEXT NOT NULL {_PG_NOW}
);
"""),
    ("002_review_columns", """
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS review_progress TEXT;
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS review_error TEXT;
"""),
    ("003_indexes", """
CREATE INDEX IF NOT EXISTS idx_users_company ON users(company_id);
CREATE INDEX IF NOT EXISTS idx_kb_company_active ON kb_items(company_id, is_active);
CREATE INDEX IF NOT EXISTS idx_sub_company ON submissions(company_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_sub_creator ON submissions(creator_id);
CREATE INDEX IF NOT EXISTS idx_ver_sub ON submission_versions(submission_id, version);
CREATE INDEX IF NOT EXISTS idx_find_sub ON findings(submission_id, version);
CREATE INDEX IF NOT EXISTS idx_comments_sub ON comments(submission_id);
CREATE INDEX IF NOT EXISTS idx_audit_sub ON audit_log(submission_id);
CREATE INDEX IF NOT EXISTS idx_audit_company ON audit_log(company_id);
"""),
    ("004_visual_analysis", """
CREATE TABLE IF NOT EXISTS brand_logos (
  id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  company_id INTEGER NOT NULL REFERENCES companies(id),
  file_name TEXT NOT NULL,
  original_name TEXT NOT NULL,
  width INTEGER NOT NULL,
  height INTEGER NOT NULL,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL DEFAULT (to_char(timezone('utc', now()), 'YYYY-MM-DD HH24:MI:SS'))
);
CREATE TABLE IF NOT EXISTS visual_reviews (
  submission_id INTEGER NOT NULL REFERENCES submissions(id),
  version INTEGER NOT NULL,
  status TEXT NOT NULL,
  result_json TEXT,
  error TEXT,
  updated_at TEXT NOT NULL DEFAULT (to_char(timezone('utc', now()), 'YYYY-MM-DD HH24:MI:SS')),
  PRIMARY KEY (submission_id, version)
);
CREATE INDEX IF NOT EXISTS idx_brand_logos_company ON brand_logos(company_id);
"""),
    ("005_login_rate_limits", """
CREATE TABLE IF NOT EXISTS login_rate_limits (
  account_key TEXT PRIMARY KEY,
  window_started BIGINT NOT NULL,
  attempts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_login_rate_limits_window ON login_rate_limits(window_started);
"""),
]


def run_pg_migrations():
    """Apply any migration not yet recorded in schema_migrations (safe to run on every start)."""
    conn = get_conn()
    try:
        conn.execute("SELECT pg_advisory_lock(727001)")      # one instance migrates at a time
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations ("
                         "version TEXT PRIMARY KEY, "
                         f"applied_at TEXT NOT NULL {_PG_NOW})")
            conn.commit()
            done = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
            for version, ddl in PG_MIGRATIONS:
                if version in done:
                    continue
                for stmt in [s.strip() for s in ddl.split(";") if s.strip()]:
                    conn.execute(stmt)
                conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
                conn.commit()
                log.info("Applied migration %s", version)
        finally:
            conn.rollback()
            conn.execute("SELECT pg_advisory_unlock(727001)")
            conn.commit()
    finally:
        conn.close()


def ensure_review_columns():
    """Kept for sqlite mode (PostgreSQL gets these columns from migration 002)."""
    if is_postgres():
        return
    conn = get_conn()
    for col in ("review_progress TEXT", "review_error TEXT"):
        try:
            conn.execute(f"ALTER TABLE submissions ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


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


def _seed_default_company(conn):
    cur = conn.execute("INSERT INTO companies (code, name) VALUES (?, ?)",
                       ("NORTHWIND", "Northwind Wellness"))
    company_id = cur.lastrowid
    admin_id = None
    for emp, name, role, team in USERS_SEED:
        c = conn.execute(
            "INSERT INTO users (company_id, employee_id, name, role, team, password_hash) "
            "VALUES (?,?,?,?,?,?)",
            (company_id, emp, name, role, team, hash_password(os.getenv("DEMO_PASSWORD") or "demo123")))
        if role == "admin":
            admin_id = c.lastrowid
    for kind, title, content in KB_SEED:
        conn.execute(
            "INSERT INTO kb_items (company_id, kind, title, content, created_by) VALUES (?,?,?,?,?)",
            (company_id, kind, title, content, admin_id))
    conn.commit()


def init_db():
    """Create/upgrade the schema, import legacy SQLite data once, seed only if still empty."""
    if is_postgres():
        run_pg_migrations()
        # One-time, idempotent import of an existing verity.db (e.g. committed to the repo).
        if os.getenv("AUTO_IMPORT_SQLITE", "true").lower() in ("1", "true", "yes") and os.path.isfile(DB_PATH):
            from migrate_sqlite_to_postgres import auto_import
            auto_import(DB_PATH)
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.executescript(SQLITE_SCHEMA)
        conn.commit()
        conn.close()
        ensure_review_columns()

    conn = get_conn()
    try:
        if conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 0:
            _seed_default_company(conn)
    finally:
        conn.close()
