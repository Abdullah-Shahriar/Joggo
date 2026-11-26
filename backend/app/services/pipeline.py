import base64
from datetime import date, datetime, timezone
import logging
from typing import Any
import uuid

import regex
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.errors import AppError, ErrorCode
from app.models.audit import AuditOutcome
from app.models.document import Document, DocumentStatus
from app.models.entity import DocumentEntity, EntitySource
from app.models.llm_request import LLMRequest, LLMRequestStatus
from app.models.step import PipelineStep, PipelineStepName, PipelineStepStatus
from app.services import audit
from app.services.detection.base import (
    MANUAL_MARK_TYPES,
    TOKEN_PATTERN_RE,
    UNICODE_WORD_BOUNDARY_LEFT,
    UNICODE_WORD_BOUNDARY_RIGHT,
    Span,
)
from app.services.detection.resolve import run_detection
from app.services.extraction import ExtractionError, extract_document
from app.services.llm.router import LLMRouterError, route_generate
from app.services.memory import log_process_rss
from app.services.safety import run_safety_scan
from app.services.state import transition
from app.services.tokenizer import TokenizationResult, tokenize_text
from app.services.vault import vault

logger = logging.getLogger("app.pipeline")


def _get_step(db: Session, doc_id: uuid.UUID, step_name: PipelineStepName) -> PipelineStep:
    return db.execute(
        select(PipelineStep).where(
            PipelineStep.document_id == doc_id,
            PipelineStep.step == step_name,
        )
    ).scalar_one()


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


def _serialize_spans(spans: list[Span]) -> list[dict[str, Any]]:
    return [
        {
            "start": s.start,
            "end": s.end,
            "entity_type": s.entity_type,
            "score": s.score,
            "detector": s.detector,
            "rule_id": s.rule_id,
            "reason": s.reason,
            "source": s.source,
            "unparsed": s.unparsed,
            "parsed_date": s.parsed_date.isoformat() if s.parsed_date else None,
            "parent_value": s.parent_value,
        }
        for s in spans
    ]


def _deserialize_spans(raw_spans: list[dict[str, Any]]) -> list[Span]:
    result: list[Span] = []
    for item in raw_spans:
        parsed_raw = item.get("parsed_date")
        parsed_dt = date.fromisoformat(parsed_raw) if parsed_raw else None
        result.append(
            Span(
                start=int(item["start"]),
                end=int(item["end"]),
                entity_type=str(item["entity_type"]),
                score=float(item["score"]),
                detector=str(item["detector"]),
                rule_id=str(item["rule_id"]),
                reason=str(item["reason"]),
                source=str(item.get("source", "auto")),
                unparsed=bool(item.get("unparsed", False)),
                parsed_date=parsed_dt,
                parent_value=item.get("parent_value"),
            )
        )
    return result


def _replace_document_entities(db: Session, doc_id: uuid.UUID, tok_result: TokenizationResult) -> None:
    db.execute(delete(DocumentEntity).where(DocumentEntity.document_id == doc_id))
    for row in tok_result.entity_rows:
        db.add(
            DocumentEntity(
                document_id=doc_id,
                token=row.token,
                entity_type=row.entity_type,
                source=EntitySource(row.source),
                detector=row.detector,
                rule_id=row.rule_id,
                reason=row.reason,
                score=row.score,
                occurrences=row.occurrences,
            )
        )
    db.flush()


def _finalize_safety_result(
    db: Session,
    *,
    doc: Document,
    tok_result: TokenizationResult,
    safety_report: dict[str, Any],
    allowed_from: set[DocumentStatus],
) -> Document:
    _replace_document_entities(db, doc.id, tok_result)

    if safety_report["status"] == "PASS":
        # Rules.md P4: persist sanitized_text ONLY after safety PASS.
        updated = transition(
            db,
            doc.id,
            allowed_from,
            DocumentStatus.REVIEW_REQUIRED,
            sanitized_text=tok_result.sanitized_text,
            entity_summary=tok_result.entity_summary,
            safety_report=safety_report,
            failure_code=None,
            approved_at=None,
        )
        audit.record(
            db,
            action="DOC_PIPELINE_COMPLETED",
            outcome=AuditOutcome.allowed,
            actor_id=doc.owner_id,
            actor_role="doctor",
            resource_type="document",
            resource_id=str(doc.id),
            metadata={"entity_count": sum(tok_result.entity_summary.values())},
        )
        return updated

    # Rules.md P4: on BLOCK keep sanitized_text NULL in DB (Vault only).
    updated = transition(
        db,
        doc.id,
        allowed_from,
        DocumentStatus.BLOCKED,
        sanitized_text=None,
        entity_summary=tok_result.entity_summary,
        safety_report=safety_report,
        failure_code=ErrorCode.SAFETY_BLOCKED.value,
        approved_at=None,
    )
    audit.record(
        db,
        action="DOC_SAFETY_BLOCK",
        outcome=AuditOutcome.denied,
        actor_id=doc.owner_id,
        actor_role="doctor",
        resource_type="document",
        resource_id=str(doc.id),
        metadata={"finding_count": len(safety_report.get("findings", []))},
    )
    return updated


def run_document_pipeline(doc_id: uuid.UUID, session_family_id: uuid.UUID) -> None:
    """Execute local 4-step pipeline (EXTRACT -> DETECT -> TOKENIZE -> SAFETY_CHECK) with resume."""
    with SessionLocal() as db:
        doc = db.get(Document, doc_id)
        if doc is None:
            return
        if doc.status in {DocumentStatus.UPLOADED, DocumentStatus.FAILED}:
            transition(db, doc_id, {DocumentStatus.UPLOADED, DocumentStatus.FAILED}, DocumentStatus.PROCESSING)
            db.commit()

        # --- Step 1: EXTRACT ---
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

        if not (extract_step.status == PipelineStepStatus.succeeded and vault_data.get("original_text")):
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
                media_type = str(vault_data.get("original_media_type") or "application/pdf")
                extracted = extract_document(base64.b64decode(pdf_b64), media_type=media_type)
            except ExtractionError as exc:
                _mark_step_failed(db, doc_id, extract_step, error_code=exc.code.value, error_message=exc.message)
                return
            except Exception:
                logger.error("Unexpected extraction error", extra={"event": "extract_error", "document_id": str(doc_id)})
                _mark_step_failed(
                    db,
                    doc_id,
                    extract_step,
                    error_code=ErrorCode.OCR_FAILED.value,
                    error_message="Failed to extract text from the uploaded file.",
                )
                return

            if not vault.update(
                session_family_id,
                doc_id,
                {"original_text": extracted.text, "metadata_hints": extracted.metadata_hints},
            ):
                _mark_step_failed(
                    db,
                    doc_id,
                    extract_step,
                    error_code=ErrorCode.VAULT_EXPIRED.value,
                    error_message="Session data expired during extraction.",
                )
                return
            _mark_step_succeeded(db, extract_step)
            vault_data = vault.get(session_family_id, doc_id)
            if vault_data is None:
                return

        # --- Step 2: DETECT ---
        detect_step = _get_step(db, doc_id, PipelineStepName.DETECT)
        original_text: str = vault_data["original_text"]
        metadata_hints: list[str] = vault_data.get("metadata_hints") or []
        manual_spans = _deserialize_spans(vault_data.get("manual_spans") or [])

        if detect_step.status == PipelineStepStatus.succeeded and vault_data.get("detected_spans") is not None:
            resolved_spans = _deserialize_spans(vault_data["detected_spans"])
        else:
            _mark_step_running(db, detect_step)
            try:
                resolved_spans = run_detection(
                    original_text,
                    metadata_hints=metadata_hints,
                    manual_spans=manual_spans,
                )
            except Exception:
                logger.error("Detection failed", extra={"event": "detect_error", "document_id": str(doc_id)})
                _mark_step_failed(
                    db,
                    doc_id,
                    detect_step,
                    error_code=ErrorCode.DETECTION_FAILED.value,
                    error_message="Identifier detection failed.",
                )
                return

            if not vault.update(session_family_id, doc_id, {"detected_spans": _serialize_spans(resolved_spans)}):
                _mark_step_failed(
                    db,
                    doc_id,
                    detect_step,
                    error_code=ErrorCode.VAULT_EXPIRED.value,
                    error_message="Session data expired during detection.",
                )
                return
            _mark_step_succeeded(db, detect_step)

        # --- Step 3: TOKENIZE ---
        tok_step = _get_step(db, doc_id, PipelineStepName.TOKENIZE)
        vault_data = vault.get(session_family_id, doc_id)
        if vault_data is None:
            _mark_step_failed(
                db,
                doc_id,
                tok_step,
                error_code=ErrorCode.VAULT_EXPIRED.value,
                error_message="Session data expired before tokenization.",
            )
            return

        if tok_step.status == PipelineStepStatus.succeeded and vault_data.get("sanitized_text"):
            tok_result = tokenize_text(original_text, resolved_spans)
        else:
            _mark_step_running(db, tok_step)
            try:
                tok_result = tokenize_text(original_text, resolved_spans)
            except Exception:
                logger.error("Tokenization failed", extra={"event": "tokenize_error", "document_id": str(doc_id)})
                _mark_step_failed(
                    db,
                    doc_id,
                    tok_step,
                    error_code=ErrorCode.DETECTION_FAILED.value,
                    error_message="Tokenization failed.",
                )
                return

            if not vault.update(
                session_family_id,
                doc_id,
                {
                    "sanitized_text": tok_result.sanitized_text,
                    "mapping": tok_result.mapping,
                    "entities": tok_result.vault_entities,
                    "anchor_date": tok_result.anchor_date,
                    "name_components": tok_result.name_components,
                },
            ):
                _mark_step_failed(
                    db,
                    doc_id,
                    tok_step,
                    error_code=ErrorCode.VAULT_EXPIRED.value,
                    error_message="Session data expired during tokenization.",
                )
                return
            _mark_step_succeeded(db, tok_step)

        # --- Step 4: SAFETY_CHECK ---
        safety_step = _get_step(db, doc_id, PipelineStepName.SAFETY_CHECK)
        _mark_step_running(db, safety_step)
        try:
            safety_report = run_safety_scan(
                sanitized_text=tok_result.sanitized_text,
                mapping=tok_result.mapping,
                name_components=tok_result.name_components,
                entity_count=sum(tok_result.entity_summary.values()),
            )
        except Exception:
            logger.error("Safety scan failed", extra={"event": "safety_error", "document_id": str(doc_id)})
            _mark_step_failed(
                db,
                doc_id,
                safety_step,
                error_code=ErrorCode.DETECTION_FAILED.value,
                error_message="Safety scan failed.",
            )
            return

        doc = db.get(Document, doc_id)
        if doc is None:
            return
        _finalize_safety_result(
            db,
            doc=doc,
            tok_result=tok_result,
            safety_report=safety_report,
            allowed_from={DocumentStatus.PROCESSING},
        )
        safety_step.status = PipelineStepStatus.succeeded
        safety_step.finished_at = datetime.now(timezone.utc)
        db.commit()
        log_process_rss("pipeline_complete", document_id=str(doc_id))


def apply_manual_mark(
    db: Session,
    *,
    doc: Document,
    session_family_id: uuid.UUID,
    text_to_mark: str,
    entity_type: str,
    expected_version: int,
    ip: str | None = None,
) -> tuple[Document, int]:
    """Highlight-to-tokenize manual mark (architecture.md §15, §17)."""
    if entity_type not in MANUAL_MARK_TYPES:
        raise AppError(ErrorCode.VALIDATION_ERROR, 422, "Invalid entity type for manual marking.")

    locked_doc = db.execute(
        select(Document)
        .where(Document.id == doc.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if locked_doc is None:
        raise AppError(ErrorCode.NOT_FOUND, 404, "Document not found.")

    if locked_doc.version != expected_version:
        raise AppError(
            ErrorCode.VERSION_CONFLICT,
            409,
            "Document was modified by another request. Please refresh and try again.",
        )

    if locked_doc.status not in {DocumentStatus.BLOCKED, DocumentStatus.REVIEW_REQUIRED, DocumentStatus.APPROVED}:
        raise AppError(ErrorCode.INVALID_STATE, 409, "Manual marking is only allowed during review.")

    vault_data = vault.get(session_family_id, locked_doc.id)
    if vault_data is None or not vault_data.get("original_text"):
        raise AppError(ErrorCode.VAULT_EXPIRED, 409, "Session data expired. Upload the file again.")

    cleaned = text_to_mark.strip()
    if len(cleaned) < 2 or len(cleaned) > 200:
        raise AppError(ErrorCode.VALIDATION_ERROR, 422, "Marked text must be between 2 and 200 characters.")

    current_sanitized: str = vault_data.get("sanitized_text") or ""
    original_text: str = vault_data["original_text"]

    # If the selection is purely existing placeholder token(s) (e.g. "[PATIENT_A]"), reject as overlap.
    # If it mixes an already-replaced token with unmasked text (e.g. "Dr. [DOCTOR_A] Karim"),
    # strip the token portions and resolve only the remaining unmasked segment(s) cleanly.
    candidate_segments: list[str]
    if TOKEN_PATTERN_RE.search(cleaned):
        stripped_parts = [
            part.strip(" \t\r\n,.;:()[]{}")
            for part in TOKEN_PATTERN_RE.split(cleaned)
        ]
        candidate_segments = [p for p in stripped_parts if len(p) >= 2]
        if not candidate_segments:
            raise AppError(
                ErrorCode.MARK_OVERLAPS_TOKEN,
                422,
                "Selection cannot overlap an existing placeholder token.",
            )
    else:
        candidate_segments = [cleaned]

    def _find_matches_in_text(target_text: str, needle: str) -> list[regex.Match[str]]:
        if any(ch.isdigit() for ch in needle):
            pat = regex.compile(regex.escape(needle), regex.IGNORECASE)
            found = list(pat.finditer(target_text))
        else:
            pat = regex.compile(
                r"(?i)" + UNICODE_WORD_BOUNDARY_LEFT + regex.escape(needle) + UNICODE_WORD_BOUNDARY_RIGHT
            )
            found = list(pat.finditer(target_text))
            if not found:
                # Fallback for terms containing/bounded by punctuation (e.g. "Dr.", "(555)", "O'Brien")
                found = list(regex.compile(regex.escape(needle), regex.IGNORECASE).finditer(target_text))
        return found

    matches: list[tuple[int, int]] = []
    seen_ranges: set[tuple[int, int]] = set()
    found_in_sanitized = False

    for seg in candidate_segments:
        if seg.casefold() in current_sanitized.casefold():
            found_in_sanitized = True
        for m in _find_matches_in_text(original_text, seg):
            rng = (m.start(), m.end())
            if rng not in seen_ranges:
                seen_ranges.add(rng)
                matches.append(rng)

    if not found_in_sanitized:
        raise AppError(ErrorCode.MARK_NOT_FOUND, 422, "Selected text was not found in the cleaned document.")

    if not matches:
        raise AppError(ErrorCode.MARK_NOT_FOUND, 422, "Selected text was not found in the original document.")

    existing_manual = _deserialize_spans(vault_data.get("manual_spans") or [])
    new_manual_spans = [
        Span(
            start=start,
            end=end,
            entity_type=entity_type,
            score=1.0,
            detector="manual",
            rule_id="manual.user",
            reason="Manually marked by clinician",
            source="manual",
        )
        for start, end in matches
    ]
    # Replace any older manual marks overlapped by the new mark so re-marking/updating always succeeds
    non_overlapping_existing = [
        old
        for old in existing_manual
        if not any(new.start < old.end and new.end > old.start for new in new_manual_spans)
    ]
    all_manual = non_overlapping_existing + new_manual_spans

    # Re-resolve (existing detected + new manual + sweep), re-tokenize, re-run safety scan
    metadata_hints: list[str] = vault_data.get("metadata_hints") or []
    resolved_spans = run_detection(
        original_text,
        metadata_hints=metadata_hints,
        manual_spans=all_manual,
    )
    tok_result = tokenize_text(original_text, resolved_spans)
    safety_report = run_safety_scan(
        sanitized_text=tok_result.sanitized_text,
        mapping=tok_result.mapping,
        name_components=tok_result.name_components,
        entity_count=sum(tok_result.entity_summary.values()),
    )

    if not vault.update(
        session_family_id,
        locked_doc.id,
        {
            "manual_spans": _serialize_spans(all_manual),
            "detected_spans": _serialize_spans(resolved_spans),
            "sanitized_text": tok_result.sanitized_text,
            "mapping": tok_result.mapping,
            "entities": tok_result.vault_entities,
            "anchor_date": tok_result.anchor_date,
            "name_components": tok_result.name_components,
        },
    ):
        raise AppError(ErrorCode.VAULT_EXPIRED, 409, "Session data expired. Upload the file again.")

    updated_doc = _finalize_safety_result(
        db,
        doc=locked_doc,
        tok_result=tok_result,
        safety_report=safety_report,
        allowed_from={DocumentStatus.BLOCKED, DocumentStatus.REVIEW_REQUIRED, DocumentStatus.APPROVED},
    )
    audit.record(
        db,
        action="DOC_MANUAL_MARK",
        outcome=AuditOutcome.allowed,
        actor_id=locked_doc.owner_id,
        actor_role="doctor",
        resource_type="document",
        resource_id=str(locked_doc.id),
        ip=ip,
        metadata={"entity_type": entity_type, "occurrences": len(matches)},
    )
    db.commit()
    db.refresh(updated_doc)
    return updated_doc, len(matches)


def run_llm_stage(doc_id: uuid.UUID, llm_request_id: uuid.UUID) -> None:
    """Execute LLM_CALL pipeline step in background worker using sanitized text only (P3/A06)."""
    with SessionLocal() as db:
        doc = db.get(Document, doc_id)
        llm_req = db.get(LLMRequest, llm_request_id)
        if doc is None or llm_req is None:
            return
        if doc.status != DocumentStatus.SENDING or not doc.sanitized_text:
            return

        llm_step = _get_step(db, doc_id, PipelineStepName.LLM_CALL)
        _mark_step_running(db, llm_step)
        sanitized_text = doc.sanitized_text
        task_type = doc.task_type
        owner_id = doc.owner_id

    try:
        outcome = route_generate(task_type, sanitized_text)
    except LLMRouterError as exc:
        total_attempts = sum(item.attempts for item in exc.history)
        total_latency = sum(item.latency_ms for item in exc.history)
        last_prov = exc.history[-1].provider if exc.history else None
        last_model = exc.history[-1].model if exc.history else None

        with SessionLocal() as db:
            llm_req = db.get(LLMRequest, llm_request_id)
            if llm_req is not None:
                llm_req.provider = last_prov
                llm_req.model = last_model
                llm_req.status = LLMRequestStatus.failed
                llm_req.attempts = total_attempts
                llm_req.latency_ms = total_latency
                llm_req.error_code = exc.failure_code.value

            detail_parts = [
                f"{item.provider}: {item.detail}" if item.detail else f"{item.provider}: {item.error_code or 'failed'}"
                for item in exc.history
                if not item.succeeded
            ]
            safe_detail = "; ".join(detail_parts)[:500] if detail_parts else "Could not generate a draft from AI providers."

            llm_step = _get_step(db, doc_id, PipelineStepName.LLM_CALL)
            llm_step.status = PipelineStepStatus.failed
            llm_step.error_code = exc.failure_code.value
            llm_step.error_message = safe_detail
            llm_step.finished_at = datetime.now(timezone.utc)

            doc = db.get(Document, doc_id)
            if doc is not None and doc.status == DocumentStatus.SENDING:
                transition(
                    db,
                    doc_id,
                    {DocumentStatus.SENDING},
                    DocumentStatus.LLM_FAILED,
                    failure_code=exc.failure_code.value,
                )
                audit.record(
                    db,
                    action="DOC_PIPELINE_FAILED",
                    outcome=AuditOutcome.error,
                    actor_id=owner_id,
                    actor_role="doctor",
                    resource_type="document",
                    resource_id=str(doc_id),
                    metadata={"step": "LLM_CALL", "error_code": exc.failure_code.value, "attempts": total_attempts},
                )
            db.commit()
        return

    with SessionLocal() as db:
        llm_req = db.get(LLMRequest, llm_request_id)
        if llm_req is not None:
            llm_req.provider = outcome.result.provider
            llm_req.model = outcome.result.model
            llm_req.status = LLMRequestStatus.succeeded
            llm_req.attempts = outcome.attempts_total
            llm_req.latency_ms = outcome.result.latency_ms
            llm_req.error_code = None

        llm_step = _get_step(db, doc_id, PipelineStepName.LLM_CALL)
        llm_step.status = PipelineStepStatus.succeeded
        llm_step.finished_at = datetime.now(timezone.utc)

        doc = db.get(Document, doc_id)
        if doc is not None and doc.status == DocumentStatus.SENDING:
            now = datetime.now(timezone.utc)
            transition(
                db,
                doc_id,
                {DocumentStatus.SENDING},
                DocumentStatus.COMPLETED,
                llm_response_tokenized=outcome.result.text,
                llm_provider_used=outcome.result.provider,
                failure_code=None,
                completed_at=now,
            )
            if outcome.used_fallback:
                audit.record(
                    db,
                    action="DOC_LLM_FALLBACK",
                    outcome=AuditOutcome.allowed,
                    actor_id=owner_id,
                    actor_role="doctor",
                    resource_type="document",
                    resource_id=str(doc_id),
                    metadata={"provider": outcome.result.provider, "attempts": outcome.attempts_total},
                )
            audit.record(
                db,
                action="DOC_COMPLETE",
                outcome=AuditOutcome.allowed,
                actor_id=owner_id,
                actor_role="doctor",
                resource_type="document",
                resource_id=str(doc_id),
                metadata={
                    "provider": outcome.result.provider,
                    "attempts": outcome.attempts_total,
                    "latency_ms": outcome.result.latency_ms,
                },
            )
        db.commit()
