import base64
from datetime import datetime, timezone
import hashlib
import os
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, Response, UploadFile
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
from app.models.audit import AuditOutcome
from app.models.document import Document, DocumentStatus, TaskType
from app.models.entity import DocumentEntity
from app.models.step import PipelineStep, PipelineStepName, PipelineStepStatus
from app.ratelimit import limiter, user_or_ip_key
from app.schemas.auth import MessageResponse
from app.schemas.document import (
    ApproveDocumentRequest,
    DocumentDetailResponse,
    DocumentEntityResponse,
    DocumentListItem,
    DocumentListResponse,
    DocumentStepsResponse,
    DocumentUploadResponse,
    ManualMarkRequest,
    ManualMarkResponse,
    OriginalHighlight,
    OriginalTextResponse,
    PipelineStepResponse,
    SafetyFindingView,
    SanitizedTextResponse,
)
from app.services import audit, jobs
from app.services.pipeline import apply_manual_mark, run_document_pipeline
from app.services.state import transition
from app.services.vault import vault

router = APIRouter(prefix="/api/documents", tags=["documents"])

CHUNK_SIZE = 64 * 1024
PDF_MAGIC = b"%PDF-"

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
    stmt = select(Document).where(Document.owner_id == auth.user.id)

    if q and q.strip():
        needle = f"%{q.strip()}%"
        id_prefix = f"{q.strip()}%"
        stmt = stmt.where(
            or_(
                Document.original_filename.ilike(needle),
                cast(Document.id, String).ilike(id_prefix),
            )
        )
    if status is not None:
        stmt = stmt.where(Document.status == status)
    if task_type is not None:
        stmt = stmt.where(Document.task_type == task_type)
    if date_from is not None:
        stmt = stmt.where(Document.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(Document.created_at <= date_to)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    if sort == "entity_count":
        all_rows = db.execute(stmt.order_by(desc(Document.created_at))).scalars().all()
        all_rows.sort(
            key=lambda d: sum((d.entity_summary or {}).values()),
            reverse=(order == "desc"),
        )
        start_idx = (page - 1) * page_size
        rows = all_rows[start_idx : start_idx + page_size]
    else:
        col_map = {
            "created_at": Document.created_at,
            "original_filename": Document.original_filename,
            "status": Document.status,
        }
        direction = asc if order == "asc" else desc
        rows = (
            db.execute(
                stmt.order_by(direction(col_map[sort]), desc(Document.created_at))
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )

    return DocumentListResponse(
        items=[
            DocumentListItem(
                id=d.id,
                original_filename=d.original_filename,
                size_bytes=d.size_bytes,
                page_count=d.page_count,
                task_type=d.task_type.value,
                status=d.status.value,
                entity_count=sum((d.entity_summary or {}).values()),
                vault_expired=d.vault_expired,
                created_at=d.created_at,
                updated_at=d.updated_at,
            )
            for d in rows
        ],
        total=int(total),
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
    pdf_bytes = base64.b64decode(vault_data["original_pdf_b64"])
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="original.pdf"'},
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
