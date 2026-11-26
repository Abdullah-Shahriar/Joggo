import base64
import hashlib
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
import pymupdf
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import (
    AuthContext,
    get_client_ip,
    get_owned_document,
    require_active_doctor_for_documents,
)
from app.errors import AppError, ErrorCode
from app.models.audit import AuditOutcome
from app.models.document import Document, DocumentStatus, TaskType
from app.models.entity import DocumentEntity
from app.models.step import PipelineStep, PipelineStepName, PipelineStepStatus
from app.ratelimit import limiter, user_or_ip_key
from app.schemas.document import (
    DocumentDetailResponse,
    DocumentEntityResponse,
    DocumentUploadResponse,
    PipelineStepResponse,
)
from app.services import audit, jobs
from app.services.pipeline import run_extraction_stage
from app.services.vault import vault

router = APIRouter(prefix="/api/documents", tags=["documents"])

CHUNK_SIZE = 64 * 1024
PDF_MAGIC = b"%PDF-"


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


def _validate_pdf_bytes(pdf_bytes: bytes, max_pages: int) -> int:
    if len(pdf_bytes) < len(PDF_MAGIC) or not pdf_bytes.startswith(PDF_MAGIC):
        raise AppError(ErrorCode.NOT_A_PDF, 415, "Only PDF files are supported.")

    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
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
        return page_count
    finally:
        doc.close()


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

    pdf_bytes = _read_upload_bounded(file, max_bytes)
    page_count = _validate_pdf_bytes(pdf_bytes, settings.MAX_PDF_PAGES)
    file_sha256 = hashlib.sha256(pdf_bytes).hexdigest()

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
        size_bytes=len(pdf_bytes),
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
            "size_bytes": len(pdf_bytes),
        },
    )
    db.commit()

    vault.put(
        auth.session_family_id,
        doc.id,
        {
            "original_pdf_b64": base64.b64encode(pdf_bytes).decode("ascii"),
            "original_text": None,
            "sanitized_text": None,
            "mapping": {},
            "entities": [],
            "anchor_date": None,
            "name_components": [],
            "metadata_hints": [],
        },
        user_id=auth.user.id,
    )

    jobs.submit(run_extraction_stage, doc.id, auth.session_family_id)
    return DocumentUploadResponse(id=doc.id, status=doc.status.value)


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document_detail(
    doc: Document = Depends(get_owned_document),
    db: Session = Depends(get_db),
) -> DocumentDetailResponse:
    steps = (
        db.execute(
            select(PipelineStep)
            .where(PipelineStep.document_id == doc.id)
            .order_by(PipelineStep.step.asc())
        )
        .scalars()
        .all()
    )
    entities = (
        db.execute(
            select(DocumentEntity)
            .where(DocumentEntity.document_id == doc.id)
            .order_by(DocumentEntity.token.asc())
        )
        .scalars()
        .all()
    )
    sanitized_sha = (
        hashlib.sha256(doc.sanitized_text.encode("utf-8")).hexdigest()
        if doc.sanitized_text
        else None
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
