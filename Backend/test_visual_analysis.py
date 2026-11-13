import importlib
import os
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from visual_analysis import analyze_colors, analyze_logos, dominant_colors, _sanitize_ai_observations


def logo_fixture():
    logo = np.zeros((48, 96, 4), dtype=np.uint8)
    cv2.rectangle(logo, (8, 8), (40, 40), (20, 40, 230, 255), -1)
    cv2.circle(logo, (70, 24), 16, (30, 190, 60, 255), -1)
    return logo


def creative_with_logo(logo):
    creative = np.full((220, 320, 3), 245, dtype=np.uint8)
    crop = creative[85:133, 110:206]
    alpha = logo[:, :, 3:4].astype(np.float32) / 255
    crop[:] = (logo[:, :, :3] * alpha + crop * (1 - alpha)).astype(np.uint8)
    return creative


class VisualAnalysisTests(unittest.TestCase):
    def test_correct_logo_is_detected_without_a_finding(self):
        logo = logo_fixture()
        result = analyze_logos(creative_with_logo(logo), [{"name": "Official logo", "image": logo}])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["findings"], [])

    def test_recolored_logo_is_flagged_with_an_approximate_location(self):
        logo = logo_fixture()
        changed = logo.copy()
        changed[:, :, :3] = np.where(
            (changed[:, :, 3:4] > 0),
            np.array([210, 30, 20], dtype=np.uint8),
            changed[:, :, :3],
        )
        result = analyze_logos(creative_with_logo(changed), [{"name": "Official logo", "image": logo}])
        self.assertTrue(result["findings"])
        self.assertIsNotNone(result["findings"][0]["bbox"])
        self.assertIn(result["findings"][0]["severity"], {"medium", "high"})

    def test_logo_check_is_not_claimed_when_no_approved_logo_exists(self):
        result = analyze_logos(np.full((32, 32, 3), 255, dtype=np.uint8), [])
        self.assertEqual(result["status"], "not_configured")
        self.assertEqual(result["findings"], [])

    def test_dominant_off_palette_color_is_reported_with_expected_value(self):
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        image[:, :70] = (220, 20, 180)
        image[:, 70:] = (92, 111, 31)
        result = analyze_colors(image, {"#1F6F5C": "Brand Colours"})
        self.assertTrue(result["findings"])
        finding = result["findings"][0]
        self.assertEqual(finding["expected_color"], "#1F6F5C")
        self.assertEqual(finding["guideline"], "Brand Colours")
        self.assertIn(finding["detected_color"], {item["hex"] for item in dominant_colors(image)})

    def test_clean_brand_color_does_not_create_deviation(self):
        image = np.full((80, 80, 3), (92, 111, 31), dtype=np.uint8)
        result = analyze_colors(image, {"#1F6F5C": "Brand Colours"})
        self.assertEqual(result["findings"], [])

    def test_low_contrast_text_observation_is_kept_as_uncertain_ai_output(self):
        image = np.full((100, 300, 3), (247, 250, 250), dtype=np.uint8)
        cv2.putText(image, "Low contrast", (12, 60), cv2.FONT_HERSHEY_SIMPLEX, 1,
                    (230, 233, 233), 2)
        observation = {
            "category": "text_contrast",
            "severity": "medium",
            "description": "Small text appears difficult to read against the light background.",
            "reason": "The foreground and background shades appear similar.",
            "guideline": "Brand Colours",
            "suggestion": "Use charcoal text on the light background.",
            "has_location": True,
            "x": 0.04,
            "y": 0.35,
            "width": 0.5,
            "height": 0.3,
            "confidence": 0.72,
        }
        result = _sanitize_ai_observations([observation], [
            {"title": "Brand Colours", "content": "Text charcoal #1A1A1A", "kind": "asset"},
        ], image)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["category"], "text_contrast")
        self.assertEqual(result[0]["source"], "ai_estimate")
        self.assertEqual(result[0]["bbox"]["x"], 0.04)
        self.assertLess(result[0]["estimated_contrast_ratio"], 4.5)


class VisualAnalysisApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.env_patch = patch.dict(os.environ, {
            "DATABASE_URL": "",
            "DB_HOST": "",
            "DB_NAME": "",
            "DB_USER": "",
            "SQLITE_PATH": os.path.join(cls.temp_dir.name, "visual-api.sqlite"),
            "REVIEW_PROVIDER": "rules",
        })
        cls.env_patch.start()
        cls.db = importlib.import_module("db")
        cls.old_db_path = cls.db.DB_PATH
        cls.db.DB_PATH = os.environ["SQLITE_PATH"]
        cls.visual = importlib.import_module("visual_analysis")
        cls.review = importlib.import_module("review")
        cls.submissions = importlib.import_module("submissions")
        cls.old_logo_dir = cls.visual.BRAND_LOGO_DIR
        cls.old_submission_dir = cls.visual.SUBMISSION_UPLOAD_DIR
        cls.old_upload_dir = cls.submissions.UPLOAD_DIR
        cls.visual.BRAND_LOGO_DIR = os.path.join(cls.temp_dir.name, "logos")
        cls.visual.SUBMISSION_UPLOAD_DIR = os.path.join(cls.temp_dir.name, "submissions")
        cls.submissions.UPLOAD_DIR = cls.visual.SUBMISSION_UPLOAD_DIR
        os.makedirs(cls.visual.BRAND_LOGO_DIR)
        os.makedirs(cls.visual.SUBMISSION_UPLOAD_DIR)
        cls.old_visual_provider = cls.visual.PROVIDER
        cls.old_review_provider = cls.review.PROVIDER
        cls.visual.PROVIDER = "rules"
        cls.review.PROVIDER = "rules"
        from fastapi.testclient import TestClient
        from main import app
        cls.client = TestClient(app)
        cls.client.__enter__()
        cls.admin = cls._login("admin01")
        cls.creator = cls._login("creator01")

    @classmethod
    def _login(cls, employee_id):
        response = cls.client.post("/api/login", json={
            "company_id": "NORTHWIND",
            "employee_id": employee_id,
            "password": "demo123",
        })
        if response.status_code != 200:
            raise AssertionError(f"Could not log in test user {employee_id}: {response.text}")
        return {"Authorization": f"Bearer {response.json()['token']}"}

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls.db.close_pool()
        cls.db.DB_PATH = cls.old_db_path
        cls.visual.BRAND_LOGO_DIR = cls.old_logo_dir
        cls.visual.SUBMISSION_UPLOAD_DIR = cls.old_submission_dir
        cls.submissions.UPLOAD_DIR = cls.old_upload_dir
        cls.visual.PROVIDER = cls.old_visual_provider
        cls.review.PROVIDER = cls.old_review_provider
        cls.env_patch.stop()
        cls.temp_dir.cleanup()

    def test_company_scoped_logo_upload_and_submission_report(self):
        logo = logo_fixture()
        _, logo_data = cv2.imencode(".png", logo)
        self.assertEqual(self.client.post(
            "/api/visual/logos",
            headers=self.creator,
            files={"file": ("official.png", logo_data.tobytes(), "image/png")},
        ).status_code, 403)
        uploaded = self.client.post(
            "/api/visual/logos",
            headers=self.admin,
            files={"file": ("official.png", logo_data.tobytes(), "image/png")},
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        self.assertEqual(len(self.client.get("/api/visual/logos", headers=self.admin).json()), 1)

        creative = np.full((220, 320, 3), (247, 250, 250), dtype=np.uint8)
        cv2.putText(creative, "Low contrast", (12, 60), cv2.FONT_HERSHEY_SIMPLEX, 1,
                    (230, 233, 233), 2)
        crop = creative[85:133, 110:206]
        alpha = logo[:, :, 3:4].astype(np.float32) / 255
        crop[:] = (logo[:, :, :3] * alpha + crop * (1 - alpha)).astype(np.uint8)
        _, creative_data = cv2.imencode(".png", creative)
        created = self.client.post(
            "/api/submissions",
            headers=self.creator,
            data={
                "title": "Visual analysis integration test",
                "channel": "ad",
                "purpose": "Test logo, colour, and low contrast",
                "content": "Promotional image with pale text and the approved official logo.",
            },
            files={"file": ("creative.png", creative_data.tobytes(), "image/png")},
        )
        self.assertEqual(created.status_code, 200, created.text)
        sid = created.json()["id"]
        ai_observation = {
            "category": "text_contrast",
            "severity": "medium",
            "description": "Small text appears difficult to read against the light background.",
            "reason": "The foreground and background shades appear similar.",
            "guideline": "Brand Colours",
            "suggestion": "Use charcoal text on the light background.",
            "has_location": True,
            "x": 0.02,
            "y": 0.15,
            "width": 0.5,
            "height": 0.3,
            "confidence": 0.8,
        }
        with patch.object(self.visual, "_ai_observations", return_value=([ai_observation], None)):
            submitted = self.client.post(f"/api/submissions/{sid}/submit", headers=self.creator)
        self.assertEqual(submitted.status_code, 200, submitted.text)
        response = self.client.get(f"/api/submissions/{sid}/visual-analysis", headers=self.creator)
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()["result"]
        self.assertEqual(report["checks"]["logos"]["findings"], [])
        contrast = report["checks"]["text_contrast"]["findings"][0]
        self.assertEqual(contrast["source"], "ai_estimate")
        self.assertLess(contrast["estimated_contrast_ratio"], 4.5)
        self.assertTrue(report["human_approval_required"])
        self.assertFalse(report["images_modified"])
        details = self.client.get(f"/api/submissions/{sid}", headers=self.creator).json()
        self.assertEqual(details["submission"]["status"], "in_human_review")
        self.assertEqual(details["versions"][0]["score"], 100)

        with patch.object(self.visual, "_ai_observations", side_effect=RuntimeError("AI unavailable")):
            self.visual.run_visual_analysis(sid, 1)
        failed_ai_report = self.client.get(
            f"/api/submissions/{sid}/visual-analysis", headers=self.creator).json()["result"]
        self.assertEqual(failed_ai_report["status"], "partial")
        self.assertEqual(failed_ai_report["checks"]["logos"]["status"], "complete")
        self.assertEqual(failed_ai_report["checks"]["colors"]["status"], "complete")
        self.assertEqual(failed_ai_report["checks"]["text_contrast"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
