import base64
from datetime import datetime, timezone
import hashlib
import io
import os
import re
from typing import Literal
import uuid
import xml.etree.ElementTree as ET

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, Response, UploadFile
from PIL import Image
import pymupdf
from sqlalchemy import String, asc, cast, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import (
    AuthContext,
    get_client_ip,
    get_owned_document,
    require_active_doctor_for_documents,
    require_doctor_for_documents,
)
from app.errors import AppError, ErrorCode
from app.models.audit import AuditLog, AuditOutcome
from app.models.document import Document, DocumentStatus, TaskType
from app.models.entity import DocumentEntity
from app.models.llm_request import LLMRequest, LLMRequestStatus
from app.models.step import PipelineStep, PipelineStepName, PipelineStepStatus
from app.ratelimit import limiter, user_or_ip_key
from app.schemas.auth import MessageResponse
from app.schemas.document import (
    ApproveDocumentRequest,
    DocumentDetailResponse,
    DocumentEntityResponse,
    DocumentListItem,
    DocumentListResponse,
    DocumentResultResponse,
    DocumentStepsResponse,
    DocumentUploadResponse,
    ManualMarkRequest,
    ManualMarkResponse,
    OriginalHighlight,
    OriginalTextResponse,
    PipelineStepResponse,
    RehydrateWarning,
    SafetyFindingView,
    SanitizedTextResponse,
    SendDocumentResponse,
)
from app.services import audit, jobs
from app.services.documents_query import query_user_documents
from app.services.exporter import export_docx, export_txt
from app.services.pipeline import apply_manual_mark, run_document_pipeline, run_llm_stage
from app.services.rehydrate import rehydrate_text
from app.services.state import transition
from app.services.vault import vault

router = APIRouter(prefix="/api/documents", tags=["documents"])

CHUNK_SIZE = 64 * 1024
PDF_MAGIC = b"%PDF-"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"

MEDIA_TYPE_TO_EXT: dict[str, str] = {
    "application/pdf": "pdf",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/svg+xml": "svg",
}

STEP_ORDER: dict[str, int] = {
    "EXTRACT": 0,
    "DETECT": 1,
    "TOKENIZE": 2,
    "SAFETY_CHECK": 3,
    "LLM_CALL": 4,
    "REHYDRATE": 5,
}


def _sanitize_filename(raw: str | None) -> str:
    base = os.path.basename((raw or "document.pdf").replace("\\", "/")).strip()
    if not base:
        base = "document.pdf"
    return base[:200]


def _read_upload_bounded(upload: UploadFile, max_bytes: int) -> bytes:
    buf = bytearray()
    while True:
        chunk = upload.file.read(CHUNK_SIZE)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise AppError(
                ErrorCode.FILE_TOO_LARGE,
                413,
                f"File exceeds the maximum allowed size of {max_bytes // (1024 * 1024)} MB.",
            )
    return bytes(buf)


def _looks_like_svg(raw_bytes: bytes) -> bool:
    head = raw_bytes[:1024].lstrip(b"\xef\xbb\xbf \t\r\n")
    lower = head.lower()
    if lower.startswith(b"<svg"):
        return True
    if lower.startswith(b"<?xml") and b"<svg" in lower:
        return True
    return False


def _validate_upload_bytes(file_bytes: bytes, max_pages: int) -> tuple[str, int]:
    """Validate uploaded PDF, PNG, JPG, or SVG bytes by magic header & structure."""
    if file_bytes.startswith(PDF_MAGIC):
        try:
            doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        except Exception as exc:
            raise AppError(ErrorCode.PDF_CORRUPT, 422, "The uploaded PDF appears to be corrupt.") from exc

        try:
            if doc.is_encrypted or doc.needs_pass:
                raise AppError(ErrorCode.PDF_ENCRYPTED, 422, "Password-protected PDFs are not supported.")
            page_count = doc.page_count
            if page_count < 1:
                raise AppError(ErrorCode.PDF_CORRUPT, 422, "The uploaded PDF contains no pages.")
            if page_count > max_pages:
                raise AppError(
                    ErrorCode.TOO_MANY_PAGES,
                    422,
                    f"PDF has {page_count} pages; maximum allowed is {max_pages}.",
                )
            return "application/pdf", page_count
        finally:
            doc.close()

    if file_bytes.startswith(PNG_MAGIC) or file_bytes.startswith(JPEG_MAGIC):
        expected_media = "image/png" if file_bytes.startswith(PNG_MAGIC) else "image/jpeg"
        try:
            with Image.open(io.BytesIO(file_bytes)) as img:
                img.verify()
            with Image.open(io.BytesIO(file_bytes)) as img:
                width, height = img.size
                if width < 1 or height < 1 or (width * height) > 50_000_000:
                    raise AppError(ErrorCode.PDF_CORRUPT, 422, "The uploaded image dimensions are invalid.")
        except AppError:
            raise
        except Exception as exc:
            raise AppError(ErrorCode.PDF_CORRUPT, 422, "The uploaded image appears to be corrupt.") from exc
        return expected_media, 1

    if _looks_like_svg(file_bytes):
        try:
            svg_text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise AppError(ErrorCode.PDF_CORRUPT, 422, "The uploaded SVG file is not valid UTF-8.") from exc
        if re.search(r"<!\s*(DOCTYPE|ENTITY)\b", svg_text, re.IGNORECASE):
            raise AppError(ErrorCode.PDF_CORRUPT, 422, "Unsupported XML declarations in SVG file.")
        try:
            root = ET.fromstring(svg_text)
        except ET.ParseError as exc:
            raise AppError(ErrorCode.PDF_CORRUPT, 422, "The uploaded SVG appears to be corrupt.") from exc
        root_tag = root.tag.split("}")[-1].lower() if "}" in root.tag else root.tag.lower()
        if root_tag != "svg":
            raise AppError(ErrorCode.PDF_CORRUPT, 422, "The uploaded file is not a valid SVG.")
        return "image/svg+xml", 1

    raise AppError(
        ErrorCode.NOT_A_PDF,
        415,
        "Only PDF, PNG, JPG, and SVG files are supported.",
    )


def _serialize_detail(db: Session, doc: Document, *, vault_sanitized_text: str | None = None) -> DocumentDetailResponse:
    steps = (
        db.execute(select(PipelineStep).where(PipelineStep.document_id == doc.id)).scalars().all()
    )
    steps.sort(key=lambda s: STEP_ORDER.get(s.step.value, 99))

    entities = (
        db.execute(
            select(DocumentEntity)
            .where(DocumentEntity.document_id == doc.id)
            .order_by(DocumentEntity.token.asc())
        )
        .scalars()
        .all()
    )
    sanitized_source = doc.sanitized_text or vault_sanitized_text
    sanitized_sha = (
        hashlib.sha256(sanitized_source.encode("utf-8")).hexdigest() if sanitized_source else None
    )
    return DocumentDetailResponse(
        id=doc.id,
        original_filename=doc.original_filename,
        size_bytes=doc.size_bytes,
        page_count=doc.page_count,
        task_type=doc.task_type.value,
        status=doc.status.value,
        failure_code=doc.failure_code,
        entity_summary=doc.entity_summary or {},
        safety_report=doc.safety_report,
        llm_provider_used=doc.llm_provider_used,
        approved_at=doc.approved_at,
        vault_expired=doc.vault_expired,
        version=doc.version,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        completed_at=doc.completed_at,
        sanitized_sha256=sanitized_sha,
        steps=[
            PipelineStepResponse(
                step=s.step.value,
                status=s.status.value,
                attempts=s.attempts,
                error_code=s.error_code,
                error_message=s.error_message,
                started_at=s.started_at,
                finished_at=s.finished_at,
            )
            for s in steps
        ],
        entities=[
            DocumentEntityResponse(
                id=e.id,
                token=e.token,
                entity_type=e.entity_type,
                source=e.source.value,
                detector=e.detector,
                rule_id=e.rule_id,
                reason=e.reason,
                score=float(e.score),
                occurrences=e.occurrences,
            )
            for e in entities
        ],
    )


@router.get("", response_model=DocumentListResponse)
def list_documents(
    q: str | None = Query(default=None),
    status: DocumentStatus | None = Query(default=None),
    task_type: TaskType | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    sort: Literal["created_at", "original_filename", "status", "entity_count"] = Query(default="created_at"),
    order: Literal["asc", "desc"] = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    auth: AuthContext = Depends(require_doctor_for_documents),
    db: Session = Depends(get_db),
) -> DocumentListResponse:
    return query_user_documents(
        db,
        owner_id=auth.user.id,
        q=q,
        status=status,
        task_type=task_type,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=DocumentUploadResponse, status_code=202)
@limiter.limit("20/hour", key_func=user_or_ip_key)
def upload_document(
    request: Request,
    file: UploadFile = File(...),
    task_type: TaskType = Form(...),
    auth: AuthContext = Depends(require_active_doctor_for_documents),
    db: Session = Depends(get_db),
) -> DocumentUploadResponse:
    settings = get_settings()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    ip = get_client_ip(request)

    file_bytes = _read_upload_bounded(file, max_bytes)
    media_type, page_count = _validate_upload_bytes(file_bytes, settings.MAX_PDF_PAGES)
    file_sha256 = hashlib.sha256(file_bytes).hexdigest()

    existing = db.execute(
        select(Document.id).where(
            Document.owner_id == auth.user.id,
            Document.file_sha256 == file_sha256,
        )
    ).scalar_one_or_none()
    if existing is not None:
        audit.record(
            db,
            action="DOC_DUPLICATE",
            outcome=AuditOutcome.denied,
            actor=auth.user,
            resource_type="document",
            resource_id=str(existing),
            ip=ip,
        )
        db.commit()
        raise AppError(
            ErrorCode.DUPLICATE_DOCUMENT,
            409,
            "This file has already been uploaded.",
            existing_document_id=str(existing),
        )

    doc = Document(
        owner_id=auth.user.id,
        original_filename=_sanitize_filename(file.filename),
        file_sha256=file_sha256,
        size_bytes=len(file_bytes),
        page_count=page_count,
        task_type=task_type,
        status=DocumentStatus.UPLOADED,
    )
    db.add(doc)

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        winner_id = db.execute(
            select(Document.id).where(
                Document.owner_id == auth.user.id,
                Document.file_sha256 == file_sha256,
            )
        ).scalar_one_or_none()
        audit.record(
            db,
            action="DOC_DUPLICATE",
            outcome=AuditOutcome.denied,
            actor=auth.user,
            resource_type="document",
            resource_id=str(winner_id) if winner_id else None,
            ip=ip,
        )
        db.commit()
        raise AppError(
            ErrorCode.DUPLICATE_DOCUMENT,
            409,
            "This file has already been uploaded.",
            existing_document_id=str(winner_id) if winner_id else None,
        ) from exc

    for step_name in PipelineStepName:
        db.add(
            PipelineStep(
                document_id=doc.id,
                step=step_name,
                status=PipelineStepStatus.pending,
            )
        )

    audit.record(
        db,
        action="DOC_UPLOAD",
        outcome=AuditOutcome.allowed,
        actor=auth.user,
        resource_type="document",
        resource_id=str(doc.id),
        ip=ip,
        metadata={
            "task_type": task_type.value,
            "page_count": page_count,
            "size_bytes": len(file_bytes),
            "media_type": media_type,
        },
    )
    db.commit()

    vault.put(
        auth.session_family_id,
        doc.id,
        {
            "original_pdf_b64": base64.b64encode(file_bytes).decode("ascii"),
            "original_media_type": media_type,
            "original_text": None,
            "sanitized_text": None,
            "mapping": {},
            "entities": [],
            "anchor_date": None,
            "name_components": [],
            "metadata_hints": [],
            "manual_spans": [],
            "detected_spans": None,
        },
        user_id=auth.user.id,
    )

    jobs.submit(run_document_pipeline, doc.id, auth.session_family_id)
    return DocumentUploadResponse(id=doc.id, status=doc.status.value)


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document_detail(
    doc: Document = Depends(get_owned_document),
    auth: AuthContext = Depends(require_doctor_for_documents),
    db: Session = Depends(get_db),
) -> DocumentDetailResponse:
    vault_data = vault.get(auth.session_family_id, doc.id)
    vault_sanitized = vault_data.get("sanitized_text") if vault_data else None
    return _serialize_detail(db, doc, vault_sanitized_text=vault_sanitized)


@router.get("/{document_id}/steps", response_model=DocumentStepsResponse)
def get_document_steps(
    doc: Document = Depends(get_owned_document),
    db: Session = Depends(get_db),
) -> DocumentStepsResponse:
    steps = db.execute(select(PipelineStep).where(PipelineStep.document_id == doc.id)).scalars().all()
    steps.sort(key=lambda s: STEP_ORDER.get(s.step.value, 99))
    return DocumentStepsResponse(
        document_id=doc.id,
        status=doc.status.value,
        steps=[
            PipelineStepResponse(
                step=s.step.value,
                status=s.status.value,
                attempts=s.attempts,
                error_code=s.error_code,
                error_message=s.error_message,
                started_at=s.started_at,
                finished_at=s.finished_at,
            )
            for s in steps
        ],
    )


@router.get("/{document_id}/original-text", response_model=OriginalTextResponse)
def get_original_text(
    doc: Document = Depends(get_owned_document),
    auth: AuthContext = Depends(require_doctor_for_documents),
) -> OriginalTextResponse:
    vault_data = vault.get(auth.session_family_id, doc.id)
    if vault_data is None or not vault_data.get("original_text"):
        raise AppError(ErrorCode.VAULT_EXPIRED, 409, "Session data expired. Upload the file again.")

    return OriginalTextResponse(
        document_id=doc.id,
        original_text=vault_data["original_text"],
        highlights=[
            OriginalHighlight(
                start=int(e["start"]),
                end=int(e["end"]),
                type=str(e["type"]),
                token=str(e["token"]),
                source=str(e["source"]),
                rule=str(e["rule"]),
            )
            for e in (vault_data.get("entities") or [])
        ],
    )


@router.get("/{document_id}/original-pdf")
def get_original_pdf(
    doc: Document = Depends(get_owned_document),
    auth: AuthContext = Depends(require_doctor_for_documents),
) -> Response:
    vault_data = vault.get(auth.session_family_id, doc.id)
    if vault_data is None or not vault_data.get("original_pdf_b64"):
        raise AppError(ErrorCode.VAULT_EXPIRED, 409, "Session data expired. Upload the file again.")
    raw_bytes = base64.b64decode(vault_data["original_pdf_b64"])
    media_type = str(vault_data.get("original_media_type") or "application/pdf")
    ext = MEDIA_TYPE_TO_EXT.get(media_type, "pdf")
    headers = {"Content-Disposition": f'inline; filename="original.{ext}"'}
    if media_type == "image/svg+xml":
        headers["Content-Security-Policy"] = "sandbox"
    return Response(
        content=raw_bytes,
        media_type=media_type,
        headers=headers,
    )


@router.get("/{document_id}/sanitized", response_model=SanitizedTextResponse)
def get_sanitized_text(
    doc: Document = Depends(get_owned_document),
    auth: AuthContext = Depends(require_doctor_for_documents),
) -> SanitizedTextResponse:
    vault_data = vault.get(auth.session_family_id, doc.id)
    vault_text = vault_data.get("sanitized_text") if vault_data else None
    text_value = vault_text if vault_text is not None else doc.sanitized_text

    if text_value is None:
        raise AppError(ErrorCode.VAULT_EXPIRED, 409, "Session data expired. Upload the file again.")

    report = doc.safety_report or {}
    raw_findings = report.get("findings") or []
    finding_views: list[SafetyFindingView] = []
    for f in raw_findings:
        start = int(f.get("start", 0))
        end = int(f.get("end", 0))
        snippet: str | None = None
        if vault_text is not None and 0 <= start < end <= len(vault_text):
            snippet = vault_text[start:end]
        finding_views.append(
            SafetyFindingView(
                type=str(f.get("type", "OTHER")),
                reason=str(f.get("reason", "")),
                start=start,
                end=end,
                snippet=snippet,
            )
        )

    return SanitizedTextResponse(
        document_id=doc.id,
        status=doc.status.value,
        sanitized_text=text_value,
        sanitized_sha256=hashlib.sha256(text_value.encode("utf-8")).hexdigest(),
        vault_expired=(vault_data is None or doc.vault_expired),
        version=doc.version,
        safety_status=report.get("status"),
        findings=finding_views,
        warnings=list(report.get("warnings") or []),
    )


@router.post("/{document_id}/manual-marks", response_model=ManualMarkResponse)
def create_manual_mark(
    request: Request,
    payload: ManualMarkRequest,
    if_match: str | None = Header(default=None, alias="If-Match"),
    doc: Document = Depends(get_owned_document),
    auth: AuthContext = Depends(require_active_doctor_for_documents),
    db: Session = Depends(get_db),
) -> ManualMarkResponse:
    if if_match is None or not if_match.strip():
        raise AppError(ErrorCode.VERSION_CONFLICT, 409, "Missing If-Match version header.")
    try:
        expected_version = int(if_match.strip().strip('"'))
    except ValueError as exc:
        raise AppError(ErrorCode.VERSION_CONFLICT, 409, "Invalid If-Match version header.") from exc

    updated_doc, count = apply_manual_mark(
        db,
        doc=doc,
        session_family_id=auth.session_family_id,
        text_to_mark=payload.text,
        entity_type=payload.entity_type,
        expected_version=expected_version,
        ip=get_client_ip(request),
    )
    vault_data = vault.get(auth.session_family_id, updated_doc.id)
    vault_sanitized = vault_data.get("sanitized_text") if vault_data else None
    return ManualMarkResponse(
        document=_serialize_detail(db, updated_doc, vault_sanitized_text=vault_sanitized),
        occurrences=count,
    )


@router.post("/{document_id}/approve", response_model=DocumentDetailResponse)
def approve_document(
    request: Request,
    payload: ApproveDocumentRequest,
    doc: Document = Depends(get_owned_document),
    auth: AuthContext = Depends(require_active_doctor_for_documents),
    db: Session = Depends(get_db),
) -> DocumentDetailResponse:
    if doc.status != DocumentStatus.REVIEW_REQUIRED:
        raise AppError(ErrorCode.INVALID_STATE, 409, "Document is not ready for approval.")

    report = doc.safety_report or {}
    if report.get("status") != "PASS" or not doc.sanitized_text:
        raise AppError(ErrorCode.INVALID_STATE, 409, "Document must pass safety check before approval.")

    current_sha = hashlib.sha256(doc.sanitized_text.encode("utf-8")).hexdigest()
    if payload.sanitized_sha256.lower() != current_sha.lower():
        raise AppError(
            ErrorCode.STALE_REVIEW,
            409,
            "The cleaned text has changed since you reviewed it. Please review again.",
        )

    now = datetime.now(timezone.utc)
    updated = transition(
        db,
        doc.id,
        {DocumentStatus.REVIEW_REQUIRED},
        DocumentStatus.APPROVED,
        approved_at=now,
    )
    audit.record(
        db,
        action="DOC_APPROVE",
        outcome=AuditOutcome.allowed,
        actor=auth.user,
        resource_type="document",
        resource_id=str(doc.id),
        ip=get_client_ip(request),
    )
    db.commit()
    return _serialize_detail(db, updated)


@router.post("/{document_id}/send", response_model=SendDocumentResponse, status_code=202)
@limiter.limit("10/minute", key_func=user_or_ip_key)
def send_document(
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    doc: Document = Depends(get_owned_document),
    auth: AuthContext = Depends(require_active_doctor_for_documents),
    db: Session = Depends(get_db),
) -> SendDocumentResponse:
    if not idempotency_key or not idempotency_key.strip():
        raise AppError(
            ErrorCode.IDEMPOTENCY_KEY_REQUIRED,
            400,
            "Idempotency-Key header is required to send a document.",
        )
    idem_key = idempotency_key.strip()[:128]
    ip = get_client_ip(request)

    locked_doc = db.execute(
        select(Document)
        .where(Document.id == doc.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if locked_doc is None:
        raise AppError(ErrorCode.NOT_FOUND, 404, "Document not found.")

    existing_req = db.execute(
        select(LLMRequest).where(
            LLMRequest.document_id == locked_doc.id,
            LLMRequest.idempotency_key == idem_key,
        )
    ).scalar_one_or_none()
    if existing_req is not None:
        response.status_code = 200
        return SendDocumentResponse(
            document_id=locked_doc.id,
            status=locked_doc.status.value,
            llm_request_id=existing_req.id,
            idempotency_key=idem_key,
            replayed=True,
        )

    transition(db, locked_doc.id, {DocumentStatus.APPROVED}, DocumentStatus.SENDING, failure_code=None)
    llm_req = LLMRequest(
        document_id=locked_doc.id,
        idempotency_key=idem_key,
        status=LLMRequestStatus.running,
    )
    db.add(llm_req)
    db.flush()

    audit.record(
        db,
        action="DOC_SEND",
        outcome=AuditOutcome.allowed,
        actor=auth.user,
        resource_type="document",
        resource_id=str(locked_doc.id),
        ip=ip,
        metadata={"task_type": locked_doc.task_type.value},
    )
    db.commit()

    jobs.submit(run_llm_stage, locked_doc.id, llm_req.id)
    return SendDocumentResponse(
        document_id=locked_doc.id,
        status=DocumentStatus.SENDING.value,
        llm_request_id=llm_req.id,
        idempotency_key=idem_key,
        replayed=False,
    )


@router.post("/{document_id}/retry", response_model=DocumentUploadResponse, status_code=202)
def retry_document(
    request: Request,
    doc: Document = Depends(get_owned_document),
    auth: AuthContext = Depends(require_active_doctor_for_documents),
    db: Session = Depends(get_db),
) -> DocumentUploadResponse:
    ip = get_client_ip(request)
    locked_doc = db.execute(
        select(Document)
        .where(Document.id == doc.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if locked_doc is None:
        raise AppError(ErrorCode.NOT_FOUND, 404, "Document not found.")

    if locked_doc.status == DocumentStatus.LLM_FAILED:
        if not locked_doc.sanitized_text:
            raise AppError(ErrorCode.INVALID_STATE, 409, "Sanitized text is unavailable for retry.")
        fresh_key = str(uuid.uuid4())
        transition(db, locked_doc.id, {DocumentStatus.LLM_FAILED}, DocumentStatus.SENDING, failure_code=None)
        llm_req = LLMRequest(
            document_id=locked_doc.id,
            idempotency_key=fresh_key,
            status=LLMRequestStatus.running,
        )
        db.add(llm_req)
        db.flush()
        audit.record(
            db,
            action="DOC_SEND",
            outcome=AuditOutcome.allowed,
            actor=auth.user,
            resource_type="document",
            resource_id=str(locked_doc.id),
            ip=ip,
            metadata={"retry": True},
        )
        db.commit()
        jobs.submit(run_llm_stage, locked_doc.id, llm_req.id)
        return DocumentUploadResponse(id=locked_doc.id, status=DocumentStatus.SENDING.value)

    if locked_doc.status == DocumentStatus.FAILED:
        vault_data = vault.get(auth.session_family_id, locked_doc.id)
        if vault_data is None:
            raise AppError(ErrorCode.VAULT_EXPIRED, 409, "Session data expired. Upload the file again.")
        transition(db, locked_doc.id, {DocumentStatus.FAILED}, DocumentStatus.PROCESSING, failure_code=None)
        db.commit()
        jobs.submit(run_document_pipeline, locked_doc.id, auth.session_family_id)
        return DocumentUploadResponse(id=locked_doc.id, status=DocumentStatus.PROCESSING.value)

    raise AppError(ErrorCode.INVALID_STATE, 409, "Document cannot be retried in its current state.")


@router.get("/{document_id}/result", response_model=DocumentResultResponse)
def get_document_result(
    doc: Document = Depends(get_owned_document),
    auth: AuthContext = Depends(require_doctor_for_documents),
    db: Session = Depends(get_db),
) -> DocumentResultResponse:
    if doc.status != DocumentStatus.COMPLETED or not doc.llm_response_tokenized:
        raise AppError(ErrorCode.INVALID_STATE, 409, "Document draft is not yet available.")

    vault_data = vault.get(auth.session_family_id, doc.id)
    mapping = vault_data.get("mapping") if vault_data is not None else None
    rehydrated = rehydrate_text(doc.llm_response_tokenized, mapping)

    # Mark REHYDRATE pipeline step succeeded when first served (architecture.md §10)
    rehydrate_step = db.execute(
        select(PipelineStep).where(
            PipelineStep.document_id == doc.id,
            PipelineStep.step == PipelineStepName.REHYDRATE,
        )
    ).scalar_one_or_none()
    if rehydrate_step is not None and rehydrate_step.status != PipelineStepStatus.succeeded:
        now = datetime.now(timezone.utc)
        rehydrate_step.status = PipelineStepStatus.succeeded
        rehydrate_step.attempts += 1
        rehydrate_step.started_at = rehydrate_step.started_at or now
        rehydrate_step.finished_at = now
        db.commit()

    fallback_row = db.execute(
        select(AuditLog.id)
        .where(
            AuditLog.action == "DOC_LLM_FALLBACK",
            AuditLog.resource_id == str(doc.id),
        )
        .limit(1)
    ).scalar_one_or_none()

    return DocumentResultResponse(
        document_id=doc.id,
        text=rehydrated.text,
        rehydrated=rehydrated.rehydrated,
        vault_expired=rehydrated.vault_expired or doc.vault_expired,
        llm_provider_used=doc.llm_provider_used,
        fallback_used=(fallback_row is not None),
        warnings=[RehydrateWarning(code=w["code"], token=w["token"]) for w in rehydrated.warnings],
    )


@router.get("/{document_id}/export")
def export_document_result(
    request: Request,
    export_format: Literal["txt", "docx"] = Query(alias="format", default="txt"),
    doc: Document = Depends(get_owned_document),
    auth: AuthContext = Depends(require_doctor_for_documents),
    db: Session = Depends(get_db),
) -> Response:
    if doc.status != DocumentStatus.COMPLETED or not doc.llm_response_tokenized:
        raise AppError(ErrorCode.INVALID_STATE, 409, "Document draft is not yet available.")

    vault_data = vault.get(auth.session_family_id, doc.id)
    mapping = vault_data.get("mapping") if vault_data is not None else None
    rehydrated = rehydrate_text(doc.llm_response_tokenized, mapping)

    short_id = str(doc.id)[:8]
    if export_format == "docx":
        content = export_docx(rehydrated.text)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = f"summary-{short_id}.docx"
    else:
        content = export_txt(rehydrated.text)
        media_type = "text/plain; charset=utf-8"
        filename = f"summary-{short_id}.txt"

    audit.record(
        db,
        action="DOC_EXPORT",
        outcome=AuditOutcome.allowed,
        actor=auth.user,
        resource_type="document",
        resource_id=str(doc.id),
        ip=get_client_ip(request),
        metadata={"format": export_format},
    )
    db.commit()

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{document_id}", response_model=MessageResponse)
def delete_document(
    request: Request,
    doc: Document = Depends(get_owned_document),
    auth: AuthContext = Depends(require_active_doctor_for_documents),
    db: Session = Depends(get_db),
) -> MessageResponse:
    doc_id = doc.id
    vault.wipe_document(doc_id, mark_db=False)
    db.delete(doc)
    audit.record(
        db,
        action="DOC_DELETE",
        outcome=AuditOutcome.allowed,
        actor=auth.user,
        resource_type="document",
        resource_id=str(doc_id),
        ip=get_client_ip(request),
    )
    db.commit()
    return MessageResponse(message="Document deleted.")
