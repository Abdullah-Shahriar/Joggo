from dataclasses import dataclass
import io
import logging
import re
import time
import unicodedata
import xml.etree.ElementTree as ET

from PIL import ExifTags, Image, ImageOps
import pymupdf
import pytesseract

from app.config import get_settings
from app.errors import ErrorCode

logger = logging.getLogger("app.extraction")

PAGE_OCR_TEXT_THRESHOLD = 40
MIN_IMAGE_DIMENSION = 100
PER_PAGE_OCR_TIMEOUT_SECONDS = 20
WHOLE_DOC_TIMEOUT_SECONDS = 120
MIN_EXTRACTED_TEXT_CHARS = 20

SOFTWARE_NAME_IGNORE_LIST: frozenset[str] = frozenset(
    {
        "microsoft word",
        "microsoft excel",
        "microsoft office",
        "adobe",
        "adobe acrobat",
        "libreoffice",
        "openoffice",
        "reportlab",
        "pymupdf",
        "mupdf",
        "wkhtmltopdf",
        "chrome",
        "chromium",
        "google docs",
        "latex",
        "pdflatex",
        "scanner",
        "unknown",
        "anonymous",
        "admin",
        "administrator",
        "user",
        "owner",
        "system",
        "clinicshield",
        "joggo",
    }
)


class ExtractionError(Exception):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    page_count: int
    metadata_hints: list[str]


def _clean_hint(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = " ".join(unicodedata.normalize("NFC", raw).split()).strip()
    if len(cleaned) < 4:
        return None
    lowered = cleaned.lower()
    if lowered in SOFTWARE_NAME_IGNORE_LIST:
        return None
    for ignored in SOFTWARE_NAME_IGNORE_LIST:
        if len(ignored) >= 6 and ignored in lowered:
            return None
    return cleaned


def _extract_xmp_creators(xml_meta: str | None) -> list[str]:
    if not xml_meta:
        return []
    creators: list[str] = []
    try:
        root = ET.fromstring(xml_meta)
    except ET.ParseError:
        return []

    for elem in root.iter():
        tag_local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag_local == "creator":
            # dc:creator may contain rdf:Seq/rdf:li children or direct text
            li_texts = [child.text.strip() for child in elem.iter() if child is not elem and child.text and child.text.strip()]
            if li_texts:
                creators.extend(li_texts)
            elif elem.text and elem.text.strip():
                creators.append(elem.text.strip())
    return creators


def _normalize_text(raw: str) -> str:
    text = unicodedata.normalize("NFC", raw)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _check_doc_deadline(start_time: float, timeout_seconds: float) -> None:
    if (time.monotonic() - start_time) > timeout_seconds:
        raise ExtractionError(
            ErrorCode.EXTRACTION_TIMEOUT,
            "Document text extraction timed out.",
        )


def extract_pdf(
    pdf_bytes: bytes,
    *,
    ocr_langs: str | None = None,
    whole_doc_timeout: float = WHOLE_DOC_TIMEOUT_SECONDS,
) -> ExtractionResult:
    """Extract text, annotations, widgets, OCR pages/images, and metadata hints in memory (P2/§11)."""
    settings = get_settings()
    langs = ocr_langs or settings.OCR_LANGS
    start = time.monotonic()

    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise ExtractionError(ErrorCode.PDF_CORRUPT, "The PDF file could not be opened.") from exc

    try:
        if doc.is_encrypted or doc.needs_pass:
            raise ExtractionError(ErrorCode.PDF_ENCRYPTED, "Password-protected PDFs are not supported.")

        page_count = doc.page_count
        if page_count < 1:
            raise ExtractionError(ErrorCode.PDF_CORRUPT, "The PDF contains no pages.")

        # Metadata hints: author + XMP dc:creator only (architecture.md §11)
        hints_set: dict[str, None] = {}
        raw_author = (doc.metadata or {}).get("author")
        cleaned_author = _clean_hint(raw_author)
        if cleaned_author:
            hints_set[cleaned_author] = None

        try:
            xml_meta = doc.get_xml_metadata()
        except Exception:
            xml_meta = None
        for creator in _extract_xmp_creators(xml_meta):
            cleaned_creator = _clean_hint(creator)
            if cleaned_creator:
                hints_set[cleaned_creator] = None

        page_chunks: list[str] = []

        for page_index in range(page_count):
            _check_doc_deadline(start, whole_doc_timeout)
            page = doc.load_page(page_index)
            page_num = page_index + 1

            parts: list[str] = []
            native_text = (page.get_text("text", sort=True) or "").strip()
            if native_text:
                parts.append(native_text)

            # Annotations (contents / titles)
            annots = page.annots()
            if annots is not None:
                for annot in annots:
                    info = annot.info or {}
                    title = (info.get("title") or "").strip()
                    content = (info.get("content") or "").strip()
                    if title and content:
                        parts.append(f"{title}: {content}")
                    elif content:
                        parts.append(content)
                    elif title:
                        parts.append(title)

            # Form widgets
            widgets = page.widgets()
            if widgets is not None:
                for widget in widgets:
                    val = widget.field_value
                    if val is None:
                        continue
                    val_str = str(val).strip()
                    if not val_str or val_str.lower() in {"off", "false"}:
                        continue
                    label = (widget.field_label or widget.field_name or "").strip()
                    if label:
                        parts.append(f"{label}: {val_str}")
                    else:
                        parts.append(val_str)

            combined_page = "\n".join(parts).strip()

            # Full-page OCR if extracted text < 40 chars
            if len(combined_page) < PAGE_OCR_TEXT_THRESHOLD:
                _check_doc_deadline(start, whole_doc_timeout)
                try:
                    pix = page.get_pixmap(dpi=200)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    ocr_text = pytesseract.image_to_string(
                        img,
                        lang=langs,
                        timeout=PER_PAGE_OCR_TIMEOUT_SECONDS,
                    ).strip()
                    if ocr_text:
                        combined_page = f"{combined_page}\n{ocr_text}".strip() if combined_page else ocr_text
                except RuntimeError as exc:
                    raise ExtractionError(
                        ErrorCode.EXTRACTION_TIMEOUT,
                        "OCR timed out while reading a scanned page.",
                    ) from exc
                except Exception as exc:
                    raise ExtractionError(
                        ErrorCode.OCR_FAILED,
                        "OCR failed while reading a scanned page.",
                    ) from exc

            # Embedded images >= 100x100 px (skip on timeout, continue)
            seen_xrefs: set[int] = set()
            for img_info in page.get_images(full=True):
                _check_doc_deadline(start, whole_doc_timeout)
                xref = int(img_info[0])
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)
                try:
                    extracted_img = doc.extract_image(xref)
                    img_bytes = extracted_img.get("image")
                    if not img_bytes:
                        continue
                    pil_img = Image.open(io.BytesIO(img_bytes))
                    width, height = pil_img.size
                    if width < MIN_IMAGE_DIMENSION or height < MIN_IMAGE_DIMENSION:
                        continue
                    img_ocr = pytesseract.image_to_string(
                        pil_img,
                        lang=langs,
                        timeout=PER_PAGE_OCR_TIMEOUT_SECONDS,
                    ).strip()
                    if img_ocr:
                        combined_page = (
                            f"{combined_page}\n[IMAGE_TEXT p{page_num}]\n{img_ocr}\n"
                            if combined_page
                            else f"[IMAGE_TEXT p{page_num}]\n{img_ocr}\n"
                        )
                except RuntimeError:
                    # Skip embedded image OCR on timeout and continue (architecture.md §11)
                    logger.warning(
                        "Embedded image OCR timed out; continuing",
                        extra={"event": "image_ocr_timeout"},
                    )
                    continue
                except Exception:
                    continue

            if combined_page:
                page_chunks.append(combined_page)

        normalized = _normalize_text("\n\n".join(page_chunks))
        if len(normalized) < MIN_EXTRACTED_TEXT_CHARS:
            raise ExtractionError(
                ErrorCode.EMPTY_DOCUMENT,
                "No readable text could be extracted from this PDF.",
            )

        return ExtractionResult(
            text=normalized,
            page_count=page_count,
            metadata_hints=list(hints_set.keys()),
        )
    finally:
        doc.close()


def extract_image(
    image_bytes: bytes,
    *,
    ocr_langs: str | None = None,
    whole_doc_timeout: float = WHOLE_DOC_TIMEOUT_SECONDS,
) -> ExtractionResult:
    """Extract text via local OCR and author metadata hints from PNG/JPG images in memory."""
    settings = get_settings()
    langs = ocr_langs or settings.OCR_LANGS
    start = time.monotonic()

    try:
        pil_img = Image.open(io.BytesIO(image_bytes))
        pil_img = ImageOps.exif_transpose(pil_img)
        if pil_img.mode not in {"RGB", "L"}:
            pil_img = pil_img.convert("RGB")
    except Exception as exc:
        raise ExtractionError(ErrorCode.PDF_CORRUPT, "The uploaded image could not be opened.") from exc

    hints_set: dict[str, None] = {}
    # PNG text chunks & general info
    for key in ("Author", "author", "Creator", "creator", "Artist", "artist"):
        val = pil_img.info.get(key)
        if isinstance(val, str):
            cleaned = _clean_hint(val)
            if cleaned:
                hints_set[cleaned] = None

    # EXIF Artist / Author tags (JPEG)
    try:
        exif = pil_img.getexif()
        if exif:
            for tag_id, val in exif.items():
                tag_name = ExifTags.TAGS.get(tag_id, "")
                if tag_name in {"Artist", "XPAuthor", "Author"} and isinstance(val, (str, bytes)):
                    raw_val = val.decode("utf-16le", errors="ignore").rstrip("\x00") if isinstance(val, bytes) else val
                    cleaned = _clean_hint(raw_val)
                    if cleaned:
                        hints_set[cleaned] = None
    except Exception:
        pass

    _check_doc_deadline(start, whole_doc_timeout)
    try:
        ocr_text = pytesseract.image_to_string(
            pil_img,
            lang=langs,
            timeout=PER_PAGE_OCR_TIMEOUT_SECONDS,
        ).strip()
    except RuntimeError as exc:
        raise ExtractionError(
            ErrorCode.EXTRACTION_TIMEOUT,
            "Reading text from this image timed out.",
        ) from exc
    except Exception as exc:
        raise ExtractionError(
            ErrorCode.OCR_FAILED,
            "Could not read text from this image.",
        ) from exc

    normalized = _normalize_text(ocr_text)
    if len(normalized) < MIN_EXTRACTED_TEXT_CHARS:
        raise ExtractionError(
            ErrorCode.EMPTY_DOCUMENT,
            "No readable text could be found in this image.",
        )

    return ExtractionResult(
        text=normalized,
        page_count=1,
        metadata_hints=list(hints_set.keys()),
    )


def extract_svg(svg_bytes: bytes) -> ExtractionResult:
    """Safely parse SVG XML in memory (blocking DOCTYPE/ENTITY) and extract visible text & metadata."""
    try:
        svg_text = svg_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ExtractionError(ErrorCode.PDF_CORRUPT, "The uploaded SVG is not valid UTF-8 text.") from exc

    if re.search(r"<!\s*(DOCTYPE|ENTITY)\b", svg_text, re.IGNORECASE):
        raise ExtractionError(ErrorCode.PDF_CORRUPT, "Unsupported XML declarations in SVG file.")

    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError as exc:
        raise ExtractionError(ErrorCode.PDF_CORRUPT, "The uploaded SVG file is malformed.") from exc

    root_tag = root.tag.split("}")[-1].lower() if "}" in root.tag else root.tag.lower()
    if root_tag != "svg":
        raise ExtractionError(ErrorCode.PDF_CORRUPT, "The uploaded file is not a valid SVG document.")

    chunks: list[str] = []
    hints_set: dict[str, None] = {}

    for elem in root.iter():
        local_tag = elem.tag.split("}")[-1].lower() if "}" in elem.tag else elem.tag.lower()
        if local_tag in {"text", "title", "desc"}:
            piece = " ".join(t.strip() for t in elem.itertext() if t and t.strip()).strip()
            if piece:
                chunks.append(piece)
        elif local_tag == "creator":
            val = " ".join(t.strip() for t in elem.itertext() if t and t.strip()).strip()
            cleaned = _clean_hint(val)
            if cleaned:
                hints_set[cleaned] = None

    normalized = _normalize_text("\n".join(chunks))
    if len(normalized) < MIN_EXTRACTED_TEXT_CHARS:
        raise ExtractionError(
            ErrorCode.EMPTY_DOCUMENT,
            "No readable text could be found in this SVG file.",
        )

    return ExtractionResult(
        text=normalized,
        page_count=1,
        metadata_hints=list(hints_set.keys()),
    )


def extract_document(
    file_bytes: bytes,
    *,
    media_type: str = "application/pdf",
    ocr_langs: str | None = None,
    whole_doc_timeout: float = WHOLE_DOC_TIMEOUT_SECONDS,
) -> ExtractionResult:
    """Dispatch extraction by validated media type (PDF, PNG, JPEG, or SVG)."""
    if media_type == "application/pdf":
        return extract_pdf(file_bytes, ocr_langs=ocr_langs, whole_doc_timeout=whole_doc_timeout)
    if media_type in {"image/png", "image/jpeg"}:
        return extract_image(file_bytes, ocr_langs=ocr_langs, whole_doc_timeout=whole_doc_timeout)
    if media_type == "image/svg+xml":
        return extract_svg(file_bytes)
    raise ExtractionError(ErrorCode.NOT_A_PDF, "Supported file types are PDF, PNG, JPG, and SVG.")
