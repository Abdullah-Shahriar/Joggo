import base64
from datetime import datetime, timezone
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.errors import ErrorCode
from app.models.audit import AuditOutcome
from app.models.document import Document, DocumentStatus
from app.models.step import PipelineStep, PipelineStepName, PipelineStepStatus
from app.services import audit
from app.services.extraction import ExtractionError, extract_pdf
from app.services.state import transition
from app.services.vault import vault

logger = logging.getLogger("app.pipeline")


def _get_step(db: Session, doc_id: uuid.UUID, step_name: PipelineStepName) -> PipelineStep:
    step = db.execute(
        select(PipelineStep).where(
            PipelineStep.document_id == doc_id,
            PipelineStep.step == step_name,
        )
    ).scalar_one()
    return step


def _mark_step_running(db: Session, step: PipelineStep) -> None:
    step.status = PipelineStepStatus.running
    step.attempts += 1
    step.error_code = None
    step.error_message = None
    step.started_at = datetime.now(timezone.utc)
    step.finished_at = None
    db.commit()


def _mark_step_succeeded(db: Session, step: PipelineStep) -> None:
    step.status = PipelineStepStatus.succeeded
    step.finished_at = datetime.now(timezone.utc)
    db.commit()


def _mark_step_failed(
    db: Session,
    doc_id: uuid.UUID,
    step: PipelineStep,
    *,
    error_code: str,
    error_message: str,
) -> None:
    step.status = PipelineStepStatus.failed
    step.error_code = error_code
    step.error_message = error_message
    step.finished_at = datetime.now(timezone.utc)
    doc = db.get(Document, doc_id)
    if doc is not None and doc.status in {DocumentStatus.UPLOADED, DocumentStatus.PROCESSING}:
        transition(
            db,
            doc_id,
            {DocumentStatus.UPLOADED, DocumentStatus.PROCESSING},
            DocumentStatus.FAILED,
            failure_code=error_code,
        )
        audit.record(
            db,
            action="DOC_PIPELINE_FAILED",
            outcome=AuditOutcome.error,
            actor_id=doc.owner_id,
            actor_role="doctor",
            resource_type="document",
            resource_id=str(doc_id),
            metadata={"step": step.step.value, "error_code": error_code},
        )
    db.commit()


def run_extraction_stage(doc_id: uuid.UUID, session_family_id: uuid.UUID) -> None:
    """Execute the EXTRACT pipeline step in a background worker thread."""
    with SessionLocal() as db:
        doc = db.get(Document, doc_id)
        if doc is None:
            return
        if doc.status == DocumentStatus.UPLOADED:
            transition(db, doc_id, {DocumentStatus.UPLOADED}, DocumentStatus.PROCESSING)
            db.commit()

        extract_step = _get_step(db, doc_id, PipelineStepName.EXTRACT)
        vault_data = vault.get(session_family_id, doc_id)
        if vault_data is None:
            _mark_step_failed(
                db,
                doc_id,
                extract_step,
                error_code=ErrorCode.VAULT_EXPIRED.value,
                error_message="Session data expired. Upload the file again.",
            )
            return

        if extract_step.status == PipelineStepStatus.succeeded and vault_data.get("original_text"):
            return

        _mark_step_running(db, extract_step)
        pdf_b64 = vault_data.get("original_pdf_b64")
        if not pdf_b64:
            _mark_step_failed(
                db,
                doc_id,
                extract_step,
                error_code=ErrorCode.VAULT_EXPIRED.value,
                error_message="Original PDF data is no longer in memory.",
            )
            return

        try:
            pdf_bytes = base64.b64decode(pdf_b64)
            extracted = extract_pdf(pdf_bytes)
        except ExtractionError as exc:
            _mark_step_failed(
                db,
                doc_id,
                extract_step,
                error_code=exc.code.value,
                error_message=exc.message,
            )
            return
        except Exception:
            logger.error(
                "Unexpected extraction error",
                extra={"event": "extract_error", "document_id": str(doc_id)},
            )
            _mark_step_failed(
                db,
                doc_id,
                extract_step,
                error_code=ErrorCode.OCR_FAILED.value,
                error_message="Failed to extract text from the PDF.",
            )
            return

        updated = vault.update(
            session_family_id,
            doc_id,
            {
                "original_text": extracted.text,
                "metadata_hints": extracted.metadata_hints,
            },
        )
        if not updated:
            _mark_step_failed(
                db,
                doc_id,
                extract_step,
                error_code=ErrorCode.VAULT_EXPIRED.value,
                error_message="Session data expired during extraction.",
            )
            return

        _mark_step_succeeded(db, extract_step)
