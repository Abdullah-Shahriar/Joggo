from decimal import Decimal
from enum import Enum
import uuid

from sqlalchemy import Enum as SAEnum, ForeignKey, Integer, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class EntitySource(str, Enum):
    auto = "auto"
    manual = "manual"
    metadata = "metadata"
    sweep = "sweep"


class DocumentEntity(Base):
    """Stores detected placeholder tokens and provenance only. Never stores real values (rules.md P1)."""

    __tablename__ = "document_entities"
    __table_args__ = (
        UniqueConstraint("document_id", "token", name="uq_document_entities_doc_token"),
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
    token: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[EntitySource] = mapped_column(
        SAEnum(EntitySource, name="entity_source", native_enum=True),
        nullable=False,
    )
    detector: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
