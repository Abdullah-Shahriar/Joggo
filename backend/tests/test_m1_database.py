from decimal import Decimal
import uuid

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import SessionLocal, engine
from app.models import (
    AuditLog,
    AuditOutcome,
    Document,
    DocumentEntity,
    DocumentStatus,
    EntitySource,
    LLMRequest,
    LLMRequestStatus,
    PipelineStep,
    PipelineStepName,
    PipelineStepStatus,
    TaskType,
    User,
    UserRole,
    UserStatus,
)
from app.security import hash_password
from scripts.seed import seed_users


@pytest.fixture()
def db_session() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_all_tables_exist_after_migration() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    expected = {
        "users",
        "sessions",
        "documents",
        "document_entities",
        "pipeline_steps",
        "llm_requests",
        "audit_logs",
        "complaints",
        "complaint_messages",
        "alembic_version",
    }
    assert expected.issubset(tables)


def test_users_auth_check_constraint_and_document_cascades(db_session: Session) -> None:
    # Check constraint: user must have password_hash OR google_sub.
    bad_user = User(
        email=f"invalid-{uuid.uuid4()}@example.com",
        password_hash=None,
        google_sub=None,
        full_name="Invalid User",
        role=UserRole.doctor,
        status=UserStatus.active,
    )
    db_session.add(bad_user)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    owner = User(
        email=f"doc-{uuid.uuid4()}@example.com",
        password_hash=hash_password("ValidPass123"),
        full_name="Synthetic Clinician",
        role=UserRole.doctor,
        status=UserStatus.active,
    )
    db_session.add(owner)
    db_session.flush()

    doc = Document(
        owner_id=owner.id,
        original_filename="synthetic_report.pdf",
        file_sha256="a" * 64,
        size_bytes=2048,
        page_count=1,
        task_type=TaskType.discharge_summary,
        status=DocumentStatus.UPLOADED,
    )
    db_session.add(doc)
    db_session.flush()

    entity = DocumentEntity(
        document_id=doc.id,
        token="[PATIENT_A]",
        entity_type="PATIENT",
        source=EntitySource.auto,
        detector="labels",
        rule_id="label.patient_name",
        reason="Label 'Patient Name:' + value",
        score=Decimal("0.950"),
        occurrences=2,
    )
    step = PipelineStep(
        document_id=doc.id,
        step=PipelineStepName.EXTRACT,
        status=PipelineStepStatus.pending,
    )
    llm_req = LLMRequest(
        document_id=doc.id,
        idempotency_key=str(uuid.uuid4()),
        status=LLMRequestStatus.running,
    )
    db_session.add_all([entity, step, llm_req])
    db_session.commit()

    # Duplicate (owner_id, file_sha256) rejected by unique constraint.
    dup = Document(
        owner_id=owner.id,
        original_filename="duplicate.pdf",
        file_sha256="a" * 64,
        size_bytes=2048,
        page_count=1,
        task_type=TaskType.case_summary,
        status=DocumentStatus.UPLOADED,
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Deleting document cascades entities, steps, llm_requests.
    doc_ref = db_session.get(Document, doc.id)
    assert doc_ref is not None
    db_session.delete(doc_ref)
    db_session.commit()

    assert db_session.execute(select(DocumentEntity).where(DocumentEntity.document_id == doc.id)).all() == []
    assert db_session.execute(select(PipelineStep).where(PipelineStep.document_id == doc.id)).all() == []
    assert db_session.execute(select(LLMRequest).where(LLMRequest.document_id == doc.id)).all() == []


def test_seed_is_idempotent(db_session: Session) -> None:
    suffix = uuid.uuid4().hex[:8]
    cfg = Settings(
        ADMIN_SEED_EMAIL=f"admin-{suffix}@example.com",
        ADMIN_SEED_PASSWORD="SeedPassword123",
        AUDITOR_SEED_EMAIL=f"auditor-{suffix}@example.com",
        AUDITOR_SEED_PASSWORD="SeedPassword123",
        DOCTOR_SEED_EMAIL=f"doctor-{suffix}@example.com",
        DOCTOR_SEED_PASSWORD="SeedPassword123",
    )

    first = seed_users(db_session, cfg)
    second = seed_users(db_session, cfg)
    assert first == 3
    assert second == 0

    roles = {
        u.role
        for u in db_session.execute(
            select(User).where(
                User.email.in_(
                    [
                        cfg.ADMIN_SEED_EMAIL,
                        cfg.AUDITOR_SEED_EMAIL,
                        cfg.DOCTOR_SEED_EMAIL,
                    ]
                )
            )
        ).scalars()
    }
    assert roles == {UserRole.admin, UserRole.auditor, UserRole.doctor}


def test_audit_log_immutability_trigger_blocks_update_and_delete(db_session: Session) -> None:
    from app.services import audit

    row = audit.record(
        db_session,
        action="TEST_IMMUTABILITY",
        outcome=AuditOutcome.allowed,
        actor_role="system",
        resource_type="system",
        resource_id="m1",
        ip="127.0.0.1",
        metadata={"check": True},
    )
    db_session.commit()

    with pytest.raises(DBAPIError) as upd_exc:
        db_session.execute(
            text("UPDATE audit_logs SET action = 'TAMPERED' WHERE id = :id"),
            {"id": row.id},
        )
        db_session.commit()
    assert "append-only" in str(upd_exc.value)
    db_session.rollback()

    with pytest.raises(DBAPIError) as del_exc:
        db_session.execute(
            text("DELETE FROM audit_logs WHERE id = :id"),
            {"id": row.id},
        )
        db_session.commit()
    assert "append-only" in str(del_exc.value)
    db_session.rollback()
