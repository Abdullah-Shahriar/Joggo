"""Initial schema with all core tables and audit log immutability trigger.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-26 09:00:00+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    user_role = postgresql.ENUM("doctor", "admin", "auditor", name="user_role", create_type=False)
    user_status = postgresql.ENUM("active", "restricted", name="user_status", create_type=False)
    task_type = postgresql.ENUM(
        "discharge_summary",
        "case_summary",
        "treatment_plan",
        name="task_type",
        create_type=False,
    )
    document_status = postgresql.ENUM(
        "UPLOADED",
        "PROCESSING",
        "BLOCKED",
        "REVIEW_REQUIRED",
        "APPROVED",
        "SENDING",
        "COMPLETED",
        "LLM_FAILED",
        "FAILED",
        name="document_status",
        create_type=False,
    )
    entity_source = postgresql.ENUM(
        "auto",
        "manual",
        "metadata",
        "sweep",
        name="entity_source",
        create_type=False,
    )
    pipeline_step_name = postgresql.ENUM(
        "EXTRACT",
        "DETECT",
        "TOKENIZE",
        "SAFETY_CHECK",
        "LLM_CALL",
        "REHYDRATE",
        name="pipeline_step_name",
        create_type=False,
    )
    pipeline_step_status = postgresql.ENUM(
        "pending",
        "running",
        "succeeded",
        "failed",
        "skipped",
        name="pipeline_step_status",
        create_type=False,
    )
    llm_request_status = postgresql.ENUM(
        "running",
        "succeeded",
        "failed",
        name="llm_request_status",
        create_type=False,
    )
    audit_outcome = postgresql.ENUM(
        "allowed",
        "denied",
        "error",
        name="audit_outcome",
        create_type=False,
    )
    complaint_category = postgresql.ENUM(
        "bug",
        "account",
        "privacy",
        "other",
        name="complaint_category",
        create_type=False,
    )
    complaint_status = postgresql.ENUM(
        "open",
        "in_progress",
        "resolved",
        name="complaint_status",
        create_type=False,
    )

    for enum_type in (
        user_role,
        user_status,
        task_type,
        document_status,
        entity_source,
        pipeline_step_name,
        pipeline_step_status,
        llm_request_status,
        audit_outcome,
        complaint_category,
        complaint_status,
    ):
        enum_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(length=320), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("google_sub", sa.String(length=255), nullable=True, unique=True),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("role", user_role, nullable=False, server_default="doctor"),
        sa.Column("status", user_status, nullable=False, server_default="active"),
        sa.Column("restricted_reason", sa.Text(), nullable=True),
        sa.Column("restricted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("password_hash IS NOT NULL OR google_sub IS NOT NULL", name="ck_users_auth_method"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id"), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_family_id", "sessions", ["family_id"])

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("original_filename", sa.String(length=200), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("task_type", task_type, nullable=False),
        sa.Column("status", document_status, nullable=False, server_default="UPLOADED"),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("sanitized_text", sa.Text(), nullable=True),
        sa.Column("entity_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("safety_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("llm_response_tokenized", sa.Text(), nullable=True),
        sa.Column("llm_provider_used", sa.String(length=64), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vault_expired", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("owner_id", "file_sha256", name="uq_documents_owner_sha256"),
    )
    op.create_index("ix_documents_owner_created_at", "documents", ["owner_id", sa.text("created_at DESC")])
    op.create_index("ix_documents_owner_status", "documents", ["owner_id", "status"])

    op.create_table(
        "document_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("source", entity_source, nullable=False),
        sa.Column("detector", sa.String(length=64), nullable=False),
        sa.Column("rule_id", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("score", sa.Numeric(4, 3), nullable=False),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("document_id", "token", name="uq_document_entities_doc_token"),
    )
    op.create_index("ix_document_entities_document_id", "document_entities", ["document_id"])

    op.create_table(
        "pipeline_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step", pipeline_step_name, nullable=False),
        sa.Column("status", pipeline_step_status, nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("document_id", "step", name="uq_pipeline_steps_doc_step"),
    )
    op.create_index("ix_pipeline_steps_document_id", "pipeline_steps", ["document_id"])

    op.create_table(
        "llm_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("status", llm_request_status, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "idempotency_key", name="uq_llm_requests_doc_idem"),
    )
    op.create_index("ix_llm_requests_document_id", "llm_requests", ["document_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("actor_role", sa.String(length=32), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("outcome", audit_outcome, nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_audit_logs_ts", "audit_logs", [sa.text("ts DESC")])
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only; % is not allowed', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_immutable
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_log_mutation();
        """
    )

    op.create_table(
        "complaints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("subject", sa.String(length=120), nullable=False),
        sa.Column("category", complaint_category, nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", complaint_status, nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_complaints_user_id", "complaints", ["user_id"])
    op.create_index("ix_complaints_status", "complaints", ["status"])

    op.create_table(
        "complaint_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("complaint_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("author_role", sa.String(length=32), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_complaint_messages_complaint_id", "complaint_messages", ["complaint_id"])


def downgrade() -> None:
    op.drop_table("complaint_messages")
    op.drop_table("complaints")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_immutable ON audit_logs;")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_log_mutation();")
    op.drop_table("audit_logs")
    op.drop_table("llm_requests")
    op.drop_table("pipeline_steps")
    op.drop_table("document_entities")
    op.drop_table("documents")
    op.drop_table("sessions")
    op.drop_table("users")

    for enum_name in (
        "complaint_status",
        "complaint_category",
        "audit_outcome",
        "llm_request_status",
        "pipeline_step_status",
        "pipeline_step_name",
        "entity_source",
        "document_status",
        "task_type",
        "user_status",
        "user_role",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name};")
