from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Final
import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.audit import AuditLog, AuditOutcome
from app.models.user import User

GENESIS_PREV_HASH: Final[str] = "0" * 64
ADVISORY_LOCK_KEY: Final[int] = 7001

FORBIDDEN_METADATA_SUBSTRINGS: Final[tuple[str, ...]] = (
    "password",
    "secret",
    "token",
    "cookie",
    "filename",
    "document_text",
    "original_text",
    "sanitized_text",
    "entity_value",
    "patient",
    "email",
    "phone",
    "full_name",
)


def _sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        lowered = str(key).lower()
        if any(part in lowered for part in FORBIDDEN_METADATA_SUBSTRINGS):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            clean[str(key)] = value
        elif isinstance(value, list):
            clean[str(key)] = [v for v in value if isinstance(v, (str, int, float, bool))]
        elif isinstance(value, dict):
            clean[str(key)] = _sanitize_metadata(value)
        else:
            clean[str(key)] = str(value)
    return clean


def _canonical_row_dict(
    *,
    ts: datetime,
    actor_id: uuid.UUID | None,
    actor_role: str | None,
    action: str,
    resource_type: str | None,
    resource_id: str | None,
    outcome: AuditOutcome,
    ip: str | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    ts_utc = ts.astimezone(timezone.utc)
    return {
        "ts": ts_utc.isoformat(),
        "actor_id": str(actor_id) if actor_id is not None else None,
        "actor_role": actor_role,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "outcome": outcome.value,
        "ip": ip,
        "metadata": metadata,
    }


def compute_audit_hash(prev_hash: str, row_without_hash: dict[str, Any]) -> str:
    canonical = json.dumps(row_without_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


def record(
    db: Session,
    *,
    action: str,
    outcome: AuditOutcome,
    actor: User | None = None,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    ip: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Append a tamper-evident audit row inside the caller's transaction (architecture.md §20)."""
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": ADVISORY_LOCK_KEY})

    prev_hash = (
        db.execute(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1)).scalar_one_or_none()
        or GENESIS_PREV_HASH
    )

    resolved_actor_id = actor.id if actor is not None else actor_id
    resolved_actor_role = actor.role.value if actor is not None else actor_role
    safe_meta = _sanitize_metadata(metadata)
    ts = datetime.now(timezone.utc)

    payload = _canonical_row_dict(
        ts=ts,
        actor_id=resolved_actor_id,
        actor_role=resolved_actor_role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        ip=ip,
        metadata=safe_meta,
    )
    row_hash = compute_audit_hash(prev_hash, payload)

    entry = AuditLog(
        ts=ts,
        actor_id=resolved_actor_id,
        actor_role=resolved_actor_role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        ip=ip,
        metadata_=safe_meta,
        prev_hash=prev_hash,
        hash=row_hash,
    )
    db.add(entry)
    db.flush()
    return entry


def verify_chain(db: Session) -> tuple[bool, int, int | None]:
    """Recompute the entire audit log hash chain and report first broken row if any."""
    rows = db.execute(select(AuditLog).order_by(AuditLog.id.asc())).scalars().all()
    expected_prev = GENESIS_PREV_HASH
    checked = 0

    for row in rows:
        checked += 1
        if row.prev_hash != expected_prev:
            return False, checked, row.id

        payload = _canonical_row_dict(
            ts=row.ts,
            actor_id=row.actor_id,
            actor_role=row.actor_role,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            outcome=row.outcome,
            ip=row.ip,
            metadata=row.metadata_ or {},
        )
        expected_hash = compute_audit_hash(row.prev_hash, payload)
        if row.hash != expected_hash:
            return False, checked, row.id

        expected_prev = row.hash

    return True, checked, None
