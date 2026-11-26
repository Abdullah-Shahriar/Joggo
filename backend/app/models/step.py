from datetime import datetime
from enum import Enum
import uuid

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PipelineStepName(str, Enum):
    EXTRACT = "EXTRACT"
    DETECT = "DETECT"
    TOKENIZE = "TOKENIZE"
    SAFETY_CHECK = "SAFETY_CHECK"
    LLM_CALL = "LLM_CALL"
    REHYDRATE = "REHYDRATE"


class PipelineStepStatus(str, Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    skipped = "skipped"


class PipelineStep(Base):
    __tablename__ = "pipeline_steps"
    __table_args__ = (
        UniqueConstraint("document_id", "step", name="uq_pipeline_steps_doc_step"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step: Mapped[PipelineStepName] = mapped_column(
        SAEnum(PipelineStepName, name="pipeline_step_name", native_enum=True),
        nullable=False,
    )
    status: Mapped[PipelineStepStatus] = mapped_column(
        SAEnum(PipelineStepStatus, name="pipeline_step_status", native_enum=True),
        nullable=False,
        default=PipelineStepStatus.pending,
        server_default=PipelineStepStatus.pending.value,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
