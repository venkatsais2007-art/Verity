# Verity: PostgreSQL migration

## Modified / new files
| File | Change |
|---|---|
| `Backend/db.py` | PostgreSQL via env vars + connection pool; SQLite fallback when no DB env vars; versioned migrations (`schema_migrations`); same tables/columns/relationships; startup import of old `verity.db`; upgraded password hashing and rate-limit schema. |
| `Backend/migrate_sqlite_to_postgres.py` | Copies application tables (including visual-analysis reports and approved-logo metadata) with ids preserved, duplicate protection, and row-count verification. |
| `Backend/review.py` | Cross-database review setup, AI response validation, rule-only fallback, and Gemini retry handling. |
| `Backend/main.py` | Closes the pool on shutdown; `/api/health` reports `database`; unknown API paths return JSON 404s instead of the SPA. |
| `Backend/reset.py`, `Backend/seed_demo.py` | Use `db.get_conn()` instead of raw sqlite. |
| `Backend/requirements.txt` | Includes `psycopg[binary,pool]` and Pillow for validated image uploads. |
| `Backend/auth.py`, `Backend/main.py` | Strong JWT configuration and validation, password rehash on login, persistent failed-login throttling, and database error responses. |
| `Backend/extract.py`, `Backend/file_validation.py`, `Backend/submissions.py`, `Backend/kb.py`, `Backend/visual_analysis.py` | Bounded uploads, extension/content validation, safe document parsing, and actionable error logging. |
| `Backend/approvals.py`, `Backend/review.py` | Atomic workflow transitions, audit-preserving decisions, and sanitized AI/database failure handling. |
| `Backend/test_security.py`, `Backend/test_review_provider.py`, `Backend/test_visual_analysis.py` | Authentication, rate limit, RBAC, company isolation, document uploads, review fallback, approvals, audit, and visual-analysis tests. |
| `Backend/test_ai.py`, `Backend/run_postgres_flow.py`, `Backend/test_postgres_flow.py` | Opt-in live Gemini smoke test and end-to-end workflow check for a disposable database. |
| `frontend/src/AuthContext.jsx`, `frontend/src/api.js`, `frontend/src/components/ProtectedRoute.jsx` | Validate stored sessions on startup and clear expired/invalid sessions. |
| `frontend/src/App.jsx` | Corrected case-sensitive Insights import for production builds. |
| `frontend/src/pages/NewSubmission.jsx`, `frontend/src/pages/Login.jsx` | Enable TXT content uploads and use provider-neutral login copy. |
| `Backend/.env.example` | Leaves SQLite and development-secret defaults blank; production credentials must be configured explicitly. |
| `frontend/src/auth.py`, `frontend/src/db.py`, `frontend/src/components/submissions.py` | Removed unused legacy Python copies/stub from the frontend source tree. |
| `Backend/.env.example`, `Backend/.gitignore`, `render.yaml` | NEW/updated. |

Existing API paths and the user-facing workflow are preserved. Legacy password hashes remain valid and are upgraded after successful login.

## Deploy on Render (step by step)
1. Push this project to a GitHub repository (the repo root must contain `Backend/`, `frontend/` and `render.yaml`). `node_modules`, `dist`, `.env` and `uploads` are ignored by git.
2. In Render: **New > Blueprint**, pick the repo. Render reads `render.yaml` and creates the PostgreSQL database and the web service together.
3. When asked, enter `GEMINI_API_KEY` (leave blank to use rule-based review only). `SECRET_KEY` and `DEMO_PASSWORD` are generated for you.
4. Wait for the build, then open `https://<your-app>.onrender.com/api/health`. Expect `"database":"postgresql"`.
5. Sign in with company `NORTHWIND`, an employee ID such as `admin01`, and the password shown in Render > your service > Environment > `DEMO_PASSWORD`.
6. Free plan notes: the free web service sleeps after inactivity, free PostgreSQL expires after about 30 days, and uploaded files are lost on restart. See "Persistent uploads" below.

Manual setup (instead of a Blueprint): create a PostgreSQL instance, then a Python web service with the same build and start commands as `render.yaml`, and set `DATABASE_URL` (Internal Database URL), `SECRET_KEY` (32+ random bytes), `PYTHON_VERSION=3.12.8`, `DEMO_PASSWORD`, `REVIEW_PROVIDER` and `GEMINI_API_KEY`.

### Persistent uploads
Uploaded creatives and brand logos are stored in the folder given by `UPLOAD_DIR` (default `Backend/uploads`). To keep them across restarts, use a paid web service plan, set the plan to `starter`, uncomment the `disk:` block and `UPLOAD_DIR=/var/data/uploads` in `render.yaml`, and redeploy.

### Moving existing SQLite data
If you already have a `verity.db`, either place it at `Backend/verity.db` before the first start (it is imported into an empty PostgreSQL automatically), or import it manually from your PC:
```
cd Backend
pip install -r requirements.txt
set DATABASE_URL=<external database URL>
set DB_SSLMODE=require
python migrate_sqlite_to_postgres.py
```
(macOS/Linux: use `export` instead of `set`.) Verify every reported row count is `OK`. The importer refuses to overwrite a populated target unless `--replace` is used. It does not copy the files in `Backend/uploads/`.

## Test locally against PostgreSQL
```
cd Backend
set DATABASE_URL=postgresql://USER:PASS@localhost:5432/verity
python seed_demo.py
set RUN_POSTGRES_FLOW=1
python -m unittest test_postgres_flow
```
Without `DATABASE_URL` the app and the test run on SQLite as before.

## Notes
- The original app has no registration endpoint, so none was added; the flow test provisions a test account in the database and verifies it can log in.
- An empty database is seeded with the NORTHWIND demo users. Their password is `DEMO_PASSWORD` (default `demo123` only when the variable is unset, so always set it in production). The login page shows the demo password only in local development or when the frontend is built with `VITE_DEMO_HINT=true`. Treat the seeded accounts as demo-only; change or remove them before using real customer data.
- The importer preserves all database records, but not the files in `Backend/uploads/`; copy those to the persistent `UPLOAD_DIR` if they must stay viewable.
- Render's free PostgreSQL instances expire after a limited period; upgrade the plan or export a backup (`pg_dump`) before then.

## Security validation

- The API accepts existing legacy PBKDF2 hashes and upgrades them to 600,000-round PBKDF2-SHA256 after a successful login. New JWTs are signed with HS256, expire after 12 hours, and are checked against the current user record on protected requests. Production requires a 32-byte `SECRET_KEY`.
- Login attempts are limited to five per account per 15-minute window. Existing role and company checks remain server-side; content transitions use conditional updates to avoid concurrent duplicate approvals or publishes.
- Image uploads are checked against their decoded format and pixel limits. PDF/DOCX/TXT uploads are size-limited, parsed, and rejected for invalid content; active PDF actions and DOCX macros/embedded objects are not accepted.
- Run the complete local suite from `Backend`: `python -m unittest discover -v`. The live Gemini smoke test is skipped unless `RUN_GEMINI_SMOKE=1` and `GEMINI_API_KEY` are set. Run `npm run build` from `frontend`.
- To run the end-to-end PostgreSQL workflow check, set `RUN_POSTGRES_FLOW=1` and `DATABASE_URL` to a **disposable test database**, then run `python -m unittest test_postgres_flow`. It mutates test data and must not point at production.

## Visual brand analysis

- Admins upload approved logo image files in **Knowledge base → Approved logos**. The image analyzer uses these company-scoped files as logo templates.
- Dominant colours are compared to six-digit hex colours in active **Asset** knowledge-base entries. Add or maintain the palette in the existing knowledge base; no second palette store is used.
- Logo matching and dominant-colour checks are deterministic image measurements. Text contrast and broader visual-guideline observations use Gemini vision when `REVIEW_PROVIDER=gemini` and `GEMINI_API_KEY` is configured; those observations are explicitly marked as AI estimates, not measured contrast ratios.
- If an approved logo, palette, image file, or AI service is unavailable, the report marks that check unconfigured/failed/partial rather than treating it as passed. Visual reports are stored per submission version and do not alter the text-review score or auto-edit images.
- If Gemini fails during visual analysis, completed deterministic logo and colour checks are retained; AI-dependent contrast and guideline checks are marked failed in a partial report.
- PostgreSQL migrations (`004_visual_analysis` and `005_login_rate_limits`) run automatically at startup. Uploaded logo and submission image files use `Backend/uploads/`, so configure persistent storage (for example a Render Disk or object storage) to retain them across redeployments.
- Focused local checks: `cd Backend` then `python -m unittest discover -v`. End-to-end API flow: `python run_postgres_flow.py` against an isolated test database.
