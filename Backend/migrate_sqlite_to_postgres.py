"""
One-time (and safe to re-run) migration of the old SQLite database into PostgreSQL.

Usage (from the Backend folder):
    set DATABASE_URL=postgresql://user:pass@host:5432/dbname      (Windows cmd)
    export DATABASE_URL=postgresql://user:pass@host:5432/dbname   (Mac/Linux)
    python migrate_sqlite_to_postgres.py                 # imports verity.db
    python migrate_sqlite_to_postgres.py --sqlite path/to/verity.db
    python migrate_sqlite_to_postgres.py --replace       # wipe PostgreSQL data first, then import

* Row ids are preserved, so every relationship (company -> users -> submissions ->
  versions / findings / comments / audit log) stays intact.
* INSERT ... ON CONFLICT DO NOTHING => running it twice never creates duplicates.
* Everything happens in ONE transaction: it fully succeeds or changes nothing.
* The SQLite file is only read, never modified or deleted.
"""
import os, sys, sqlite3, argparse
from dotenv import load_dotenv

load_dotenv()

TABLES = ["companies", "users", "kb_items", "submissions", "submission_versions",
          "findings", "comments", "audit_log", "brand_logos", "visual_reviews"]
ID_TABLES = {"companies", "users", "kb_items", "submissions", "submission_versions",
             "findings", "comments", "audit_log", "brand_logos"}
MARKER = "sqlite_import_done"


def _pg_columns(cur, table):
    cur.execute("SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = %s", (table,))
    return {r[0] for r in cur.fetchall()}


def _sqlite_tables(sconn):
    return {r[0] for r in sconn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _sqlite_rows(sconn, table, pg_columns):
    schema = sconn.execute(f"PRAGMA table_info({table})").fetchall()
    columns = [row[1] for row in schema if row[1] in pg_columns]
    if not columns:
        return columns, []
    primary_key = [row[1] for row in schema if row[5]]
    order_by = ", ".join(primary_key) if primary_key else "rowid"
    rows = sconn.execute(
        f"SELECT {', '.join(columns)} FROM {table} ORDER BY {order_by}").fetchall()
    return columns, rows


def migrate(sqlite_path, replace=False, quiet=False):
    import psycopg
    from db import database_url, run_pg_migrations

    url = database_url()
    if not url:
        raise SystemExit("Set DATABASE_URL (or DB_HOST/DB_NAME/DB_USER/DB_PASSWORD) first.")
    if not os.path.isfile(sqlite_path):
        raise SystemExit(f"SQLite file not found: {sqlite_path}")

    say = (lambda *a: None) if quiet else print
    run_pg_migrations()                       # make sure the PostgreSQL schema exists

    sconn = sqlite3.connect(os.path.abspath(sqlite_path))
    sconn.row_factory = sqlite3.Row
    try:
        sconn.execute("PRAGMA query_only = ON")
        present = _sqlite_tables(sconn)

        with psycopg.connect(url) as pg:
            cur = pg.cursor()
            cur.execute("SELECT pg_advisory_xact_lock(727002)")
            cur.execute("SELECT 1 FROM schema_migrations WHERE version=%s", (MARKER,))
            already = cur.fetchone() is not None
            cur.execute("SELECT COUNT(*) FROM companies")
            has_data = cur.fetchone()[0] > 0

            if replace:
                say("Replacing existing PostgreSQL data ...")
                cur.execute("TRUNCATE " + ", ".join(TABLES) + " RESTART IDENTITY CASCADE")
                cur.execute("DELETE FROM schema_migrations WHERE version=%s", (MARKER,))
                already = has_data = False
            elif already or has_data:
                say("PostgreSQL already contains Verity data "
                    f"({'import already done' if already else 'tables not empty'}). Nothing imported.\n"
                    "Use --replace only if you really want to overwrite it with the SQLite data.")
                return False

            for table in TABLES:
                if table not in present:
                    say(f"  {table:22s} not in SQLite file, skipped")
                    continue
                cols, rows = _sqlite_rows(sconn, table, _pg_columns(cur, table))
                if not cols:
                    if rows:
                        raise RuntimeError(f"No compatible columns found for SQLite table {table}.")
                    say(f"  {table:22s} has no compatible columns, skipped")
                    continue
                sql = (f"INSERT INTO {table} ({', '.join(cols)}) "
                       f"VALUES ({', '.join(['%s'] * len(cols))}) ON CONFLICT DO NOTHING")
                cur.executemany(sql, [tuple(row) for row in rows])
                say(f"  {table:22s} {len(rows):6d} rows read")

            # Keep auto-numbering ahead of imported ids.
            for table in ID_TABLES:
                cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                            f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {table}")

            ok = True
            say("\nVerification (SQLite -> PostgreSQL):")
            for table in TABLES:
                if table not in present:
                    continue
                n_s = sconn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                n_p = cur.fetchone()[0]
                flag = "OK " if n_s == n_p else "MISMATCH"
                ok = ok and n_s == n_p
                say(f"  {flag} {table:22s} {n_s:6d} -> {n_p:6d}")
            if not ok:
                raise RuntimeError("Row counts differ; the PostgreSQL transaction was rolled back.")
            cur.execute("INSERT INTO schema_migrations (version) VALUES (%s) ON CONFLICT DO NOTHING",
                        (MARKER,))
        say("\nMigration finished successfully.")
        return True
    finally:
        sconn.close()


def auto_import(sqlite_path):
    """Used at app start-up: imports verity.db only if PostgreSQL is still empty."""
    return migrate(sqlite_path, replace=False, quiet=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Copy verity.db (SQLite) into PostgreSQL")
    ap.add_argument("--sqlite", default=os.getenv("SQLITE_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "verity.db")))
    ap.add_argument("--replace", action="store_true", help="delete existing PostgreSQL data first")
    a = ap.parse_args()
    if a.replace and input("This ERASES the PostgreSQL Verity data. Type YES to continue: ") != "YES":
        raise SystemExit("Cancelled.")
    migrate(a.sqlite, replace=a.replace)
