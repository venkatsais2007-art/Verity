import json
import logging
import os
import re
import uuid

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from auth import current_user, require_roles
from db import get_conn
from file_validation import validate_image
from submissions import UPLOAD_DIR as SUBMISSION_UPLOAD_DIR

router = APIRouter(tags=["visual analysis"])

BRAND_LOGO_DIR = os.path.join(SUBMISSION_UPLOAD_DIR, "brand_logos")
MAX_UPLOAD = 5 * 1024 * 1024
MAX_PIXELS = 20_000_000
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
COLOR_PATTERN = re.compile(r"#[0-9a-fA-F]{6}\b")
PROVIDER = os.getenv("REVIEW_PROVIDER", "gemini")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
AI_TIMEOUT = int(os.getenv("REVIEW_AI_TIMEOUT", "45"))
log = logging.getLogger("verity.visual_analysis")


def decode_image(data, filename=None):
    validate_image(data, filename)
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError("The uploaded file is not a supported image")
    height, width = image.shape[:2]
    if width < 8 or height < 8 or width * height > MAX_PIXELS:
        raise ValueError("Image dimensions must be at least 8x8 and no more than 20 megapixels")
    return image


def _bgr(image):
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    return image


def dominant_colors(image, limit=5):
    """Return dominant RGB hex colors and their approximate share of sampled pixels."""
    rgb = cv2.cvtColor(_bgr(image), cv2.COLOR_BGR2RGB)
    height, width = rgb.shape[:2]
    scale = min(1.0, 200 / max(height, width))
    if scale < 1:
        rgb = cv2.resize(rgb, (max(1, int(width * scale)), max(1, int(height * scale))),
                         interpolation=cv2.INTER_AREA)
    quantized = rgb // 16
    bins, counts = np.unique(quantized.reshape(-1, 3), axis=0, return_counts=True)
    order = np.argsort(counts)[::-1][:limit]
    total = int(counts.sum())
    return [
        {
            "hex": "#{:02X}{:02X}{:02X}".format(*(int(v) * 16 + 8 for v in bins[i])),
            "share": round(int(counts[i]) / total, 4),
        }
        for i in order
    ]


def palette_from_guidelines(items):
    colors = {}
    for item in items:
        if item["kind"] != "asset":
            continue
        for color in COLOR_PATTERN.findall(item["content"]):
            colors.setdefault(color.upper(), item["title"])
    return colors


def _rgb(hex_color):
    value = hex_color.lstrip("#")
    return np.array([int(value[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.int16)


def analyze_colors(image, palette):
    if not palette:
        return {
            "status": "not_configured",
            "method": "dominant-color sampling (RGB quantization)",
            "detected": dominant_colors(image),
            "expected": [],
            "findings": [],
        }

    detected = dominant_colors(image)
    expected = [{"hex": color, "guideline": title} for color, title in palette.items()]
    findings = []
    for color in detected:
        if color["share"] < 0.06:
            continue
        nearest = min(palette, key=lambda value: float(np.linalg.norm(_rgb(color["hex"]) - _rgb(value))))
        distance = float(np.linalg.norm(_rgb(color["hex"]) - _rgb(nearest)))
        if distance > 65:
            findings.append({
                "category": "color",
                "severity": "medium" if color["share"] < 0.2 else "high",
                "description": f"Dominant color {color['hex']} is outside the configured brand palette.",
                "reason": f"It covers about {round(color['share'] * 100)}% of sampled pixels and is {round(distance)} RGB units from the nearest approved color {nearest}.",
                "guideline": palette[nearest],
                "suggestion": f"Replace or reduce {color['hex']} in favor of an approved brand color such as {nearest}.",
                "bbox": None,
                "source": "image_measurement",
                "confidence": "high",
                "detected_color": color["hex"],
                "expected_color": nearest,
            })
    return {
        "status": "complete",
        "method": "dominant-color sampling (RGB quantization); deviations use RGB distance > 65",
        "detected": detected,
        "expected": expected,
        "findings": findings,
    }


def estimate_text_contrast(image, bbox):
    """Estimate contrast between two dominant pixel groups inside an AI-located text region."""
    height, width = image.shape[:2]
    left = max(0, min(width - 1, int(bbox["x"] * width)))
    top = max(0, min(height - 1, int(bbox["y"] * height)))
    right = max(left + 1, min(width, int((bbox["x"] + bbox["width"]) * width)))
    bottom = max(top + 1, min(height, int((bbox["y"] + bbox["height"]) * height)))
    region = cv2.cvtColor(_bgr(image[top:bottom, left:right]), cv2.COLOR_BGR2RGB)
    if region.shape[0] * region.shape[1] > 20000:
        region = cv2.resize(region, (160, 120), interpolation=cv2.INTER_AREA)
    pixels = region.reshape(-1, 3).astype(np.float32)
    _, _, centers = cv2.kmeans(
        pixels,
        2,
        None,
        (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.1),
        3,
        cv2.KMEANS_PP_CENTERS,
    )
    linear = np.where(centers / 255 <= 0.04045, (centers / 255) / 12.92,
                      ((centers / 255 + 0.055) / 1.055) ** 2.4)
    luminance = np.sort(linear @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32))
    return round(float((luminance[1] + 0.05) / (luminance[0] + 0.05)), 2)


def _scaled_logo_match(creative, logo):
    canvas = _bgr(creative)
    template = _bgr(logo)
    height, width = canvas.shape[:2]
    gray_canvas = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
    edge_canvas = cv2.Canny(gray_canvas, 50, 150)
    scales = sorted(set(np.geomspace(0.2, 1.5, 16).tolist() + [1.0]))
    best = None
    for scale in scales:
        tw, th = int(round(template.shape[1] * scale)), int(round(template.shape[0] * scale))
        if tw < 20 or th < 12 or tw > width or th > height:
            continue
        candidate = cv2.resize(template, (tw, th), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
        gray_candidate = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
        if logo.ndim == 3 and logo.shape[2] == 4:
            alpha = cv2.resize(logo[:, :, 3], (tw, th), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
            mask = np.where(alpha > 24, 255, 0).astype(np.uint8)
            if np.count_nonzero(mask) < 20:
                continue
            color_mask = np.repeat(mask[:, :, None], 3, axis=2)
            color_result = cv2.matchTemplate(canvas, candidate, cv2.TM_CCORR_NORMED, mask=color_mask)
        else:
            mask = None
            color_result = cv2.matchTemplate(canvas, candidate, cv2.TM_CCOEFF_NORMED)
        edge_template = cv2.Canny(gray_candidate, 50, 150)
        if cv2.countNonZero(edge_template) == 0:
            continue
        shape_result = cv2.matchTemplate(edge_canvas, edge_template, cv2.TM_CCORR_NORMED, mask=mask)
        shape_result = np.nan_to_num(shape_result, nan=-1.0, posinf=-1.0, neginf=-1.0)
        _, shape_score, _, location = cv2.minMaxLoc(shape_result)
        if not np.isfinite(shape_score):
            continue
        color_score = float(color_result[location[1], location[0]])
        if best is None or shape_score > best["score"]:
            best = {
                "score": float(shape_score),
                "color_score": color_score,
                "x": location[0],
                "y": location[1],
                "width": tw,
                "height": th,
            }
    if best:
        best["bbox"] = {
            "x": round(best["x"] / width, 4),
            "y": round(best["y"] / height, 4),
            "width": round(best["width"] / width, 4),
            "height": round(best["height"] / height, 4),
        }
    return best


def analyze_logos(image, logos):
    if not logos:
        return {
            "status": "not_configured",
            "method": "approved-logo template matching",
            "findings": [],
        }
    matches = []
    for logo in logos:
        match = _scaled_logo_match(image, logo["image"])
        if match:
            matches.append((match["score"], logo, match))
    if not matches:
        return {
            "status": "failed",
            "method": "approved-logo template matching",
            "findings": [],
            "error": "No usable logo template could be compared.",
        }

    score, logo, match = max(matches, key=lambda item: item[0])
    if score >= 0.88 and match["color_score"] >= 0.82:
        findings = []
    elif score >= 0.70:
        findings = [{
            "category": "logo",
            "severity": "medium",
            "description": "A logo-like region differs from the approved logo.",
            "reason": f"Shape similarity was {score:.2f} and colour similarity was {match['color_score']:.2f}; this may indicate recolouring, distortion, an altered version, or a false match.",
            "guideline": "Logo Usage",
            "suggestion": "Confirm the suspected region and replace it with an unaltered approved logo.",
            "bbox": match["bbox"],
            "source": "image_measurement",
            "confidence": "medium",
            "similarity": round(score, 3),
            "color_similarity": round(match["color_score"], 3),
        }]
    else:
        findings = [{
            "category": "logo",
            "severity": "high",
            "description": "No matching approved logo was detected.",
            "reason": f"The strongest shape similarity was {score:.2f}. The logo may be missing, an unapproved version, or too small/obscured to match.",
            "guideline": "Logo Usage",
            "suggestion": f"Add the approved {logo['name']} logo without distortion; verify its placement manually.",
            "bbox": None,
            "source": "image_measurement",
            "confidence": "medium",
            "similarity": round(score, 3),
            "color_similarity": round(match["color_score"], 3),
        }]
    return {"status": "complete", "method": "multi-scale edge and colour template matching", "findings": findings}


AI_SCHEMA = {
    "type": "object",
    "properties": {
        "observations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": ["text_contrast", "visual_guideline"]},
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "description": {"type": "string"},
                    "reason": {"type": "string"},
                    "guideline": {"type": "string"},
                    "suggestion": {"type": "string"},
                    "has_location": {"type": "boolean"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "width": {"type": "number"},
                    "height": {"type": "number"},
                    "confidence": {"type": "number"},
                },
                "required": ["category", "severity", "description", "reason", "guideline",
                             "suggestion", "has_location", "x", "y", "width", "height", "confidence"],
            },
        }
    },
    "required": ["observations"],
}


def _ai_observations(image_bytes, mime_type, kb_items):
    if PROVIDER != "gemini" or not os.getenv("GEMINI_API_KEY"):
        return None, "Visual AI is not configured; text-contrast and semantic guideline checks were not run."
    from google import genai
    from google.genai import types

    guidelines = "\n".join(f"- {item['title']}: {item['content']}" for item in kb_items)
    prompt = (
        "Inspect this promotional image only for visible text contrast/accessibility problems and "
        "visual assets that conflict with the supplied brand guidelines. Return only evidence-based "
        "observations; do not infer missing elements unless the guideline explicitly requires them. "
        "Do not repeat or assess logo identity (that is separately template-checked). "
        "Do not report exact WCAG contrast ratios unless the foreground/background pixels are clear; "
        "describe uncertain contrast as an estimate. Include normalized image coordinates (0 to 1) "
        "only when a region can be located. An empty list means no issue was observed, not proof of compliance.\n"
        f"BRAND GUIDELINES:\n{guidelines}"
    )
    client = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"].strip(),
        http_options=types.HttpOptions(timeout=AI_TIMEOUT * 1000),
    )
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            prompt,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=AI_SCHEMA,
            temperature=0.1,
        ),
    )
    parsed = json.loads((response.text or "").strip())
    return parsed.get("observations", []), None


def _sanitize_ai_observations(observations, kb_items, image=None):
    titles = {item["title"] for item in kb_items}
    clean = []
    for item in observations:
        if item.get("category") not in {"text_contrast", "visual_guideline"}:
            continue
        location = None
        if item.get("has_location"):
            coords = [item.get(key) for key in ("x", "y", "width", "height")]
            if all(isinstance(value, (int, float)) for value in coords):
                x, y, width, height = coords
                if 0 <= x <= 1 and 0 <= y <= 1 and 0 < width <= 1 and 0 < height <= 1:
                    location = {key: round(value, 4) for key, value in zip(("x", "y", "width", "height"), coords)}
        severity = item.get("severity")
        if severity not in {"low", "medium", "high"}:
            continue
        title = item.get("guideline", "")
        finding = {
            "category": item["category"],
            "severity": severity,
            "description": str(item.get("description", ""))[:500],
            "reason": str(item.get("reason", ""))[:800],
            "guideline": title if title in titles else "Guideline citation could not be verified",
            "suggestion": str(item.get("suggestion", ""))[:500],
            "bbox": location,
            "source": "ai_estimate",
            "confidence": max(0, min(1, float(item.get("confidence", 0)))),
        }
        if image is not None and finding["category"] == "text_contrast" and location:
            finding["estimated_contrast_ratio"] = estimate_text_contrast(image, location)
            finding["contrast_basis"] = "Two-cluster pixel estimate within an AI-located text region; not a certified WCAG result."
        clean.append(finding)
    return clean


def _save_report(sid, version, status, result=None, error=None):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM visual_reviews WHERE submission_id=? AND version=?", (sid, version))
        conn.execute(
            "INSERT INTO visual_reviews (submission_id, version, status, result_json, error) VALUES (?,?,?,?,?)",
            (sid, version, status, json.dumps(result) if result is not None else None, error),
        )
        conn.commit()
    finally:
        conn.close()


def run_visual_analysis(sid, version):
    _save_report(sid, version, "running")
    conn = get_conn()
    try:
        sub = conn.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        ver = conn.execute(
            "SELECT * FROM submission_versions WHERE submission_id=? AND version=?", (sid, version)
        ).fetchone()
        if not sub or not ver or ver["file_type"] != "image" or not ver["file_name"]:
            raise ValueError("Visual analysis requires an uploaded image in this submission version.")
        kb_items = conn.execute(
            "SELECT kind, title, content FROM kb_items WHERE company_id=? AND is_active=1",
            (sub["company_id"],),
        ).fetchall()
        logos = conn.execute(
            "SELECT id, file_name, original_name FROM brand_logos WHERE company_id=? ORDER BY id",
            (sub["company_id"],),
        ).fetchall()
    finally:
        conn.close()

    try:
        image_path = os.path.join(SUBMISSION_UPLOAD_DIR, ver["file_name"])
        with open(image_path, "rb") as image_file:
            image_bytes = image_file.read()
        image = decode_image(image_bytes)
        logo_templates = []
        for logo in logos:
            logo_path = os.path.join(BRAND_LOGO_DIR, logo["file_name"])
            with open(logo_path, "rb") as logo_file:
                logo_templates.append({
                    "name": logo["original_name"],
                    "image": decode_image(logo_file.read()),
                })

        logo_check = analyze_logos(image, logo_templates)
        palette = palette_from_guidelines(kb_items)
        color_check = analyze_colors(image, palette)
        ext = os.path.splitext(ver["file_name"])[1].lower()
        mime_type = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                     ".webp": "image/webp"}[ext]
        try:
            ai_items, ai_error = _ai_observations(image_bytes, mime_type, kb_items)
            ai_status = "complete" if ai_items is not None else "not_configured"
        except Exception:
            log.exception("Visual AI failed for submission %s version %s", sid, version)
            ai_items = None
            ai_error = "Visual AI was unavailable; text-contrast and guideline checks were not run."
            ai_status = "failed"
        observations = _sanitize_ai_observations(ai_items, kb_items, image) if ai_items is not None else []
        findings = logo_check["findings"] + color_check["findings"] + observations
        checks = {
            "logos": logo_check,
            "colors": color_check,
            "text_contrast": {
                "status": ai_status,
                "method": "AI text-region detection with a two-cluster pixel contrast estimate; not a certified WCAG result",
                "findings": [item for item in observations if item["category"] == "text_contrast"],
            },
            "visual_guidelines": {
                "status": ai_status,
                "method": "AI visual observation grounded in active brand knowledge-base entries",
                "findings": [item for item in observations if item["category"] == "visual_guideline"],
            },
        }
        statuses = [check["status"] for check in checks.values()]
        status = "complete" if all(value == "complete" for value in statuses) else "partial"
        report = {
            "version": version,
            "status": status,
            "checks": checks,
            "findings": findings,
            "summary": {
                "total_findings": len(findings),
                "high": sum(item["severity"] == "high" for item in findings),
                "medium": sum(item["severity"] == "medium" for item in findings),
                "low": sum(item["severity"] == "low" for item in findings),
            },
            "note": ai_error,
            "human_approval_required": True,
            "images_modified": False,
        }
        _save_report(sid, version, status, result=report)
    except Exception:
        log.exception("Visual analysis failed for submission %s version %s", sid, version)
        _save_report(
            sid,
            version,
            "failed",
            error="Visual analysis could not be completed. Please retry or contact an administrator.",
        )
        raise


def _company_submission(conn, user, sid):
    row = conn.execute(
        "SELECT id, creator_id FROM submissions WHERE id=? AND company_id=?",
        (sid, user["company_id"]),
    ).fetchone()
    if not row or (user["role"] == "creator" and row["creator_id"] != user["id"]):
        raise HTTPException(404, "Submission not found")
    return row


@router.get("/api/visual/logos")
def list_brand_logos(user=Depends(current_user)):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, original_name, width, height, created_at FROM brand_logos "
            "WHERE company_id=? ORDER BY id DESC",
            (user["company_id"],),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@router.post("/api/visual/logos")
async def upload_brand_logo(file: UploadFile = File(...), user=Depends(require_roles("admin"))):
    name = os.path.basename(file.filename or "approved-logo")
    if os.path.splitext(name)[1].lower() not in IMAGE_EXTENSIONS:
        raise HTTPException(400, "Upload an approved logo as PNG, JPG, WEBP, or JPEG.")
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(400, "File too large (max 5 MB)")
    try:
        image = decode_image(data, name)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    os.makedirs(BRAND_LOGO_DIR, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{os.path.splitext(name)[1].lower()}"
    path = os.path.join(BRAND_LOGO_DIR, stored_name)
    with open(path, "wb") as logo_file:
        logo_file.write(data)
    conn = get_conn()
    try:
        cursor = conn.execute(
            "INSERT INTO brand_logos (company_id, file_name, original_name, width, height, created_by) "
            "VALUES (?,?,?,?,?,?)",
            (user["company_id"], stored_name, name[:200], image.shape[1], image.shape[0], user["id"]),
        )
        conn.execute(
            "INSERT INTO audit_log (company_id, user_id, action, detail) VALUES (?,?,?,?)",
            (user["company_id"], user["id"], "brand_logo_uploaded", name[:200]),
        )
        conn.commit()
        return {"id": cursor.lastrowid, "name": name, "width": image.shape[1], "height": image.shape[0]}
    except Exception:
        conn.rollback()
        os.remove(path)
        raise
    finally:
        conn.close()


@router.delete("/api/visual/logos/{logo_id}")
def delete_brand_logo(logo_id: int, user=Depends(require_roles("admin"))):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT file_name, original_name FROM brand_logos WHERE id=? AND company_id=?",
            (logo_id, user["company_id"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Approved logo not found")
        conn.execute("DELETE FROM brand_logos WHERE id=?", (logo_id,))
        conn.execute(
            "INSERT INTO audit_log (company_id, user_id, action, detail) VALUES (?,?,?,?)",
            (user["company_id"], user["id"], "brand_logo_removed", row["original_name"]),
        )
        conn.commit()
    finally:
        conn.close()
    path = os.path.join(BRAND_LOGO_DIR, row["file_name"])
    if os.path.isfile(path):
        os.remove(path)
    return {"ok": True}


@router.get("/api/submissions/{sid}/visual-analysis")
def get_visual_analysis(sid: int, user=Depends(current_user)):
    conn = get_conn()
    try:
        _company_submission(conn, user, sid)
        version = conn.execute("SELECT current_version FROM submissions WHERE id=?", (sid,)).fetchone()
        row = conn.execute(
            "SELECT status, result_json, error, updated_at FROM visual_reviews "
            "WHERE submission_id=? AND version=?",
            (sid, version["current_version"]),
        ).fetchone()
        if not row:
            return {"status": "not_run", "version": version["current_version"]}
        result = json.loads(row["result_json"]) if row["result_json"] else None
        return {
            "status": row["status"],
            "version": version["current_version"],
            "result": result,
            "error": row["error"],
            "updated_at": row["updated_at"],
        }
    finally:
        conn.close()
