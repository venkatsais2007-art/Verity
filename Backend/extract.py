import io
import os
import zipfile
from pypdf import PdfReader
from docx import Document


MAX_DOCX_FILES = 200
MAX_DOCX_UNCOMPRESSED = 32 * 1024 * 1024
MAX_PDF_PAGES = 200


def _extract_pdf(data):
    if b"%PDF-" not in data[:1024]:
        raise ValueError("The file extension does not match a valid PDF.")
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ValueError("Password-protected PDF files are not supported.")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ValueError(f"PDF files may contain at most {MAX_PDF_PAGES} pages.")
        root = reader.trailer["/Root"].get_object()
        if root.get("/AA"):
            raise ValueError("PDF files containing active actions are not supported.")
        open_action = root.get("/OpenAction")
        if isinstance(open_action, dict) and open_action.get("/S") in {"/JavaScript", "/Launch"}:
            raise ValueError("PDF files containing active actions are not supported.")
        names = root.get("/Names")
        if names and (names.get("/JavaScript") or names.get("/EmbeddedFiles")):
            raise ValueError("PDF files containing scripts or embedded files are not supported.")
        texts = []
        for page in reader.pages:
            if page.get("/AA"):
                raise ValueError("PDF files containing active actions are not supported.")
            for annotation_ref in page.get("/Annots", []):
                annotation = annotation_ref.get_object()
                action = annotation.get("/A")
                if annotation.get("/AA") or (
                    isinstance(action, dict) and action.get("/S") in {"/JavaScript", "/Launch"}
                ):
                    raise ValueError("PDF files containing active actions are not supported.")
            texts.append(page.extract_text() or "")
        return "\n".join(texts).strip()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("The PDF is corrupted or could not be safely read.") from exc


def _validate_docx(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_DOCX_FILES:
                raise ValueError("The DOCX contains too many internal files.")
            if sum(entry.file_size for entry in entries) > MAX_DOCX_UNCOMPRESSED:
                raise ValueError("The uncompressed DOCX is too large to safely process.")
            names = {entry.filename for entry in entries}
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise ValueError("The file extension does not match a valid DOCX.")
            if any(
                name.lower().endswith("vbaproject.bin") or name.lower().startswith("word/embeddings/")
                for name in names
            ):
                raise ValueError("DOCX files containing macros or embedded objects are not supported.")
            if archive.testzip() is not None:
                raise ValueError("The DOCX is corrupted.")
    except ValueError:
        raise
    except (zipfile.BadZipFile, OSError, EOFError) as exc:
        raise ValueError("The DOCX is corrupted or could not be safely read.") from exc


def extract_text(filename: str, data: bytes) -> str:
    extension = os.path.splitext(os.path.basename(filename or ""))[1].lower()
    if extension == ".pdf":
        return _extract_pdf(data)
    if extension == ".docx":
        if not data.startswith(b"PK"):
            raise ValueError("The file extension does not match a valid DOCX.")
        _validate_docx(data)
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs).strip()
    if extension in {".txt", ".md"}:
        try:
            text = data.decode("utf-8-sig").strip()
        except UnicodeDecodeError as exc:
            raise ValueError("Text files must use UTF-8 encoding.") from exc
        if "\x00" in text:
            raise ValueError("Text files containing binary data are not supported.")
        return text
    raise ValueError("Unsupported file type. Use PDF, DOCX or TXT.")