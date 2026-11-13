import hashlib
import importlib
import io
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import zipfile

import jwt
from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.actions import JavaScript
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


def _pdf_with_text(text):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    }))
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})
    })
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    result = io.BytesIO()
    writer.write(result)
    return result.getvalue()


def _pdf_with_javascript():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_open_action(JavaScript("app.alert('blocked')"))
    result = io.BytesIO()
    writer.write(result)
    return result.getvalue()


def _docx_with_text(text):
    document = Document()
    document.add_paragraph(text)
    result = io.BytesIO()
    document.save(result)
    return result.getvalue()


def _docx_with_macro():
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
        archive.writestr("word/vbaProject.bin", b"macro")
    return result.getvalue()


class SecurityApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.temp_dir.name, "security.sqlite")
        cls.env_patch = patch.dict(os.environ, {
            "DATABASE_URL": "",
            "DB_HOST": "",
            "DB_NAME": "",
            "DB_USER": "",
            "SQLITE_PATH": cls.db_path,
            "REVIEW_PROVIDER": "rules",
        })
        cls.env_patch.start()

        cls.db = importlib.import_module("db")
        cls.old_db_path = cls.db.DB_PATH
        cls.db.DB_PATH = cls.db_path
        cls.review = importlib.import_module("review")
        cls.old_review_provider = cls.review.PROVIDER
        cls.review.PROVIDER = "rules"
        cls.submissions = importlib.import_module("submissions")
        cls.old_upload_dir = cls.submissions.UPLOAD_DIR
        cls.submissions.UPLOAD_DIR = os.path.join(cls.temp_dir.name, "uploads")
        os.makedirs(cls.submissions.UPLOAD_DIR)

        from main import app
        cls.client = TestClient(app)
        cls.client.__enter__()
        cls.creator = cls._login("creator01")
        cls.admin = cls._login("admin01")
        cls.manager = cls._login("manager01")
        cls.reviewer = cls._login("reviewer01")

    @classmethod
    def _login(cls, employee_id, company_id="NORTHWIND", password="demo123"):
        response = cls.client.post("/api/login", json={
            "company_id": company_id,
            "employee_id": employee_id,
            "password": password,
        })
        if response.status_code != 200:
            raise AssertionError(f"Login failed for test user {employee_id}: {response.text}")
        return {"Authorization": f"Bearer {response.json()['token']}"}

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls.db.close_pool()
        cls.db.DB_PATH = cls.old_db_path
        cls.review.PROVIDER = cls.old_review_provider
        cls.submissions.UPLOAD_DIR = cls.old_upload_dir
        cls.env_patch.stop()
        cls.temp_dir.cleanup()

    def _submit(self, content, headers=None):
        return self.client.post(
            "/api/submissions",
            headers=headers or self.creator,
            data={"title": "Security test", "channel": "social", "purpose": "test", "content": content},
        )

    def _upload(self, filename, data):
        return self.client.post(
            "/api/submissions",
            headers=self.creator,
            data={"title": "Uploaded test", "channel": "ad", "purpose": "file validation"},
            files={"file": (filename, data, "application/octet-stream")},
        )

    def test_jwt_auth_legacy_password_upgrade_and_login_throttling(self):
        self.assertEqual(self.client.get("/api/me").status_code, 401)
        from auth import SECRET
        expired = jwt.encode({
            "sub": "1",
            "iat": datetime.now(timezone.utc) - timedelta(hours=13),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }, SECRET, algorithm="HS256")
        self.assertEqual(
            self.client.get("/api/me", headers={"Authorization": f"Bearer {expired}"}).status_code,
            401,
        )
        malformed = jwt.encode({"sub": "not-an-id", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                               SECRET, algorithm="HS256")
        self.assertEqual(
            self.client.get("/api/me", headers={"Authorization": f"Bearer {malformed}"}).status_code,
            401,
        )

        conn = self.db.get_conn()
        company_id = conn.execute(
            "SELECT id FROM companies WHERE code='NORTHWIND'").fetchone()["id"]
        salt = "legacy-salt"
        digest = hashlib.pbkdf2_hmac("sha256", b"legacy-pass", salt.encode(), 100_000).hex()
        conn.execute(
            "INSERT INTO users (company_id, employee_id, name, role, team, password_hash) "
            "VALUES (?,?,?,?,?,?)",
            (company_id, "legacy01", "Legacy User", "creator", "Test", f"{salt}${digest}"),
        )
        conn.commit()
        conn.close()
        legacy_login = self.client.post("/api/login", json={
            "company_id": "NORTHWIND", "employee_id": "legacy01", "password": "legacy-pass",
        })
        self.assertEqual(legacy_login.status_code, 200, legacy_login.text)
        conn = self.db.get_conn()
        upgraded = conn.execute(
            "SELECT password_hash FROM users WHERE employee_id='legacy01'").fetchone()["password_hash"]
        conn.close()
        self.assertTrue(upgraded.startswith("pbkdf2_sha256$600000$"))

        failed_login = {
            "company_id": "NORTHWIND", "employee_id": "limit01", "password": "wrong",
        }
        for _ in range(5):
            self.assertEqual(self.client.post("/api/login", json=failed_login).status_code, 401)
        limited = self.client.post("/api/login", json=failed_login)
        self.assertEqual(limited.status_code, 429)
        self.assertIn("Retry-After", limited.headers)

    def test_production_secret_must_be_explicit_and_long_enough(self):
        from auth import _secret_key

        with patch.dict(os.environ, {
            "APP_ENV": "production",
            "RENDER": "",
            "DATABASE_URL": "",
            "DB_HOST": "",
            "SECRET_KEY": "",
        }):
            with self.assertRaises(RuntimeError):
                _secret_key()
        with patch.dict(os.environ, {
            "APP_ENV": "production",
            "RENDER": "",
            "DATABASE_URL": "",
            "DB_HOST": "",
            "SECRET_KEY": "x" * 32,
        }):
            self.assertEqual(_secret_key(), "x" * 32)

    def test_roles_company_isolation_and_admin_guideline_management(self):
        self.assertEqual(self.client.get("/api/kb").status_code, 401)
        for role, user in (("creator", self.creator), ("manager", self.manager), ("reviewer", self.reviewer)):
            with self.subTest(role=role):
                self.assertEqual(
                    self.client.post("/api/kb", headers=user, json={
                        "kind": "guideline", "title": "Not allowed", "content": "Cannot edit this.",
                    }).status_code,
                    403,
                )
        created = self.client.post("/api/kb", headers=self.admin, json={
            "kind": "guideline", "title": "Test Security Guideline", "content": "Use clear language.",
        })
        self.assertEqual(created.status_code, 200, created.text)

        conn = self.db.get_conn()
        company_id = conn.execute(
            "INSERT INTO companies (code, name) VALUES (?,?)",
            ("ACME-SECURITY", "Acme Security Test"),
        ).lastrowid
        conn.execute(
            "INSERT INTO users (company_id, employee_id, name, role, password_hash) "
            "VALUES (?,?,?,?,?)",
            (company_id, "admin01", "Acme Admin", "admin", self.db.hash_password("demo123")),
        )
        conn.commit()
        conn.close()
        other_company = self._login("admin01", "ACME-SECURITY")
        self.assertEqual(self.client.get("/api/kb", headers=other_company).json(), [])

        own = self._submit("Northwind content for access check.")
        self.assertEqual(own.status_code, 200, own.text)
        sid = own.json()["id"]
        self.assertEqual(self.client.get(f"/api/submissions/{sid}", headers=other_company).status_code, 404)
        self.assertEqual(self.client.get(f"/api/submissions/{sid}").status_code, 401)
        another_creator = self._login("creator02")
        self.assertEqual(self.client.get(f"/api/submissions/{sid}", headers=another_creator).status_code, 404)

    def test_upload_pdf_docx_txt_and_reject_invalid_or_oversized_files(self):
        samples = [
            ("campaign.pdf", _pdf_with_text("Northwind Daily members")),
            ("campaign.docx", _docx_with_text("Northwind Daily members")),
            ("campaign.txt", b"Northwind Daily members"),
        ]
        for filename, data in samples:
            with self.subTest(filename=filename):
                response = self._upload(filename, data)
                self.assertEqual(response.status_code, 200, response.text)
                detail = self.client.get(
                    f"/api/submissions/{response.json()['id']}", headers=self.creator).json()
                self.assertIn("Northwind Daily", detail["versions"][0]["content"])

        self.assertEqual(self._upload("fake.pdf", b"not a PDF").status_code, 400)
        self.assertEqual(self._upload("active.pdf", _pdf_with_javascript()).status_code, 400)
        self.assertEqual(self._upload("fake.docx", b"not a DOCX").status_code, 400)
        self.assertEqual(self._upload("macro.docx", _docx_with_macro()).status_code, 400)
        self.assertEqual(self._upload("binary.txt", b"not\x00text").status_code, 400)
        self.assertEqual(self._upload("spoof.png", b"%PDF-1.7").status_code, 400)
        self.assertEqual(self._upload("large.txt", b"x" * (5 * 1024 * 1024 + 1)).status_code, 400)
        self.assertEqual(self._upload("unsupported.exe", b"payload").status_code, 400)

    def test_knowledge_base_accepts_pdf_docx_and_txt_uploads(self):
        samples = [
            ("guide.pdf", _pdf_with_text("Use approved brand language.")),
            ("guide.docx", _docx_with_text("Use approved brand language.")),
            ("guide.txt", b"Use approved brand language."),
        ]
        for filename, data in samples:
            with self.subTest(filename=filename):
                response = self.client.post(
                    "/api/kb/upload",
                    headers=self.admin,
                    data={"kind": "guideline", "title": f"Upload {filename}"},
                    files={"file": (filename, data, "application/octet-stream")},
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertGreater(response.json()["chars"], 0)
        denied = self.client.post(
            "/api/kb/upload",
            headers=self.creator,
            data={"kind": "guideline", "title": "Forbidden upload"},
            files={"file": ("guide.txt", b"Not authorized.", "text/plain")},
        )
        self.assertEqual(denied.status_code, 403)
        invalid = self.client.post(
            "/api/kb/upload",
            headers=self.admin,
            data={"kind": "guideline", "title": "Invalid upload"},
            files={"file": ("bad.pdf", b"not a PDF", "application/pdf")},
        )
        self.assertEqual(invalid.status_code, 400)

    def test_database_failures_return_a_safe_retryable_response(self):
        with self.assertLogs("verity.api", level="ERROR"):
            with patch("main.get_conn", side_effect=sqlite3.OperationalError("private database detail")):
                response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"],
            "The database is temporarily unavailable. Please try again.",
        )
        self.assertNotIn("private database detail", response.text)

    def test_unknown_api_route_is_not_returned_as_the_spa(self):
        response = self.client.get("/api/unknown-audit-route")
        self.assertEqual(response.status_code, 404)
        self.assertTrue(response.headers["content-type"].startswith("application/json"))

    def test_review_fallback_score_resubmission_comments_approval_rejection_and_audit(self):
        bad = self._submit("Our miracle Northwind Daily is guaranteed to work. Only $29 per month!!!")
        self.assertEqual(bad.status_code, 200, bad.text)
        bad_id = bad.json()["id"]
        with self.assertLogs("verity.review", level="ERROR"):
            with patch.object(self.review, "PROVIDER", "gemini"), patch.object(
                self.review, "call_gemini", side_effect=RuntimeError("provider unavailable")
            ):
                sent = self.client.post(f"/api/submissions/{bad_id}/submit", headers=self.creator)
        self.assertEqual(sent.status_code, 200, sent.text)
        reviewed = self.client.get(f"/api/submissions/{bad_id}", headers=self.creator).json()
        self.assertEqual(reviewed["submission"]["status"], "needs_changes")
        self.assertGreater(len(reviewed["findings"]), 0)
        expected_score = max(0, 100 - sum(
            {"high": 15, "medium": 8, "low": 3}[finding["severity"]]
            for finding in reviewed["findings"]
        ))
        self.assertEqual(reviewed["versions"][0]["score"], expected_score)
        self.assertIn("only the built-in rule checks ran", reviewed["submission"]["review_error"])

        invalid_ai = self._submit("Our miracle Northwind Daily is guaranteed to work.")
        invalid_ai_id = invalid_ai.json()["id"]
        with self.assertLogs("verity.review", level="ERROR"):
            with patch.object(self.review, "PROVIDER", "gemini"), patch.object(
                self.review, "call_gemini", return_value=[None]
            ):
                sent = self.client.post(f"/api/submissions/{invalid_ai_id}/submit", headers=self.creator)
        self.assertEqual(sent.status_code, 200, sent.text)
        invalid_ai_review = self.client.get(
            f"/api/submissions/{invalid_ai_id}", headers=self.creator).json()
        self.assertEqual(invalid_ai_review["submission"]["status"], "needs_changes")
        self.assertGreater(len(invalid_ai_review["findings"]), 0)
        self.assertIn("only the built-in rule checks ran", invalid_ai_review["submission"]["review_error"])

        for finding in reviewed["findings"]:
            decided = self.client.post(
                f"/api/submissions/{bad_id}/findings/{finding['id']}/decision",
                headers=self.creator,
                json={"decision": "accepted"},
            )
            self.assertEqual(decided.status_code, 200, decided.text)
        revised = self.client.post(
            f"/api/submissions/{bad_id}/revise",
            headers=self.creator,
            json={"content": "Northwind Daily gives members 12 vitamins and minerals. It costs $39 per month."},
        )
        self.assertEqual(revised.status_code, 200, revised.text)
        self.assertEqual(revised.json()["version"], 2)
        comment = self.client.post(
            f"/api/submissions/{bad_id}/comments",
            headers=self.manager,
            json={"body": "Please review the revised content."},
        )
        self.assertEqual(comment.status_code, 200, comment.text)
        rejected = self.client.post(
            f"/api/submissions/{bad_id}/approval",
            headers=self.reviewer,
            json={"action": "reject", "comment": "Needs another human review."},
        )
        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertEqual(rejected.json()["status"], "rejected")

        clean = self._submit("Northwind Daily gives members 12 vitamins and minerals.")
        clean_id = clean.json()["id"]
        self.assertEqual(
            self.client.post(f"/api/submissions/{clean_id}/submit", headers=self.creator).status_code,
            200,
        )
        no_approval = self.client.post(f"/api/submissions/{clean_id}/publish", headers=self.manager)
        self.assertEqual(no_approval.status_code, 400)
        self.assertEqual(
            self.client.post(f"/api/submissions/{clean_id}/approval", headers=self.creator,
                             json={"action": "approve"}).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(f"/api/submissions/{clean_id}/approval", headers=self.reviewer,
                             json={"action": "approve"}).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(f"/api/submissions/{clean_id}/publish", headers=self.creator).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(f"/api/submissions/{clean_id}/publish", headers=self.reviewer).status_code,
            200,
        )
        audit = self.client.get(f"/api/submissions/{bad_id}/audit", headers=self.manager).json()["events"]
        actions = {event["action"] for event in audit}
        self.assertIn("rejected", actions)
        self.assertIn("revised", actions)
        self.assertIn("comment_added", actions)


if __name__ == "__main__":
    unittest.main()
