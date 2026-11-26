from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import threading
from typing import Any, Final
import uuid

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models.audit import AuditOutcome
from app.models.document import Document, DocumentStatus
from app.services import audit

logger = logging.getLogger("app.vault")

PER_SESSION_CAP: Final[int] = 20
SWEEP_INTERVAL_SECONDS: Final[int] = 60


@dataclass
class VaultEntry:
    nonce: bytes
    ciphertext: bytes
    created_at: datetime
    last_access: datetime
    size: int
    user_id: str | None = None


def _to_str(value: uuid.UUID | str) -> str:
    return str(value)


def _to_uuid_list(doc_ids: set[str]) -> list[uuid.UUID]:
    result: list[uuid.UUID] = []
    for raw in doc_ids:
        try:
            result.append(uuid.UUID(raw))
        except ValueError:
            continue
    return result


class VaultService:
    """In-memory AES-256-GCM encrypted ephemeral store keyed by (sid, document_id) (architecture.md §8)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._master_key: bytes = os.urandom(32)
        self._entries: OrderedDict[tuple[str, str], VaultEntry] = OrderedDict()
        self._total_bytes: int = 0
        self._stop_event = threading.Event()
        self._sweeper_thread: threading.Thread | None = None

    def _derive_key(self, sid: str, doc_id: str) -> bytes:
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=f"{sid}|{doc_id}".encode("utf-8"),
        )
        return hkdf.derive(self._master_key)

    def _encrypt(self, sid: str, doc_id: str, payload: dict[str, Any]) -> tuple[bytes, bytes]:
        key = self._derive_key(sid, doc_id)
        nonce = os.urandom(12)
        plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
        return nonce, ciphertext

    def _decrypt(self, sid: str, doc_id: str, entry: VaultEntry) -> dict[str, Any]:
        key = self._derive_key(sid, doc_id)
        plaintext = AESGCM(key).decrypt(entry.nonce, entry.ciphertext, None)
        data: dict[str, Any] = json.loads(plaintext.decode("utf-8"))
        return data

    def _is_expired(self, entry: VaultEntry, now: datetime) -> bool:
        settings = get_settings()
        idle_limit = timedelta(minutes=settings.VAULT_IDLE_MINUTES)
        abs_limit = timedelta(hours=settings.VAULT_ABSOLUTE_HOURS)
        return (now - entry.last_access) > idle_limit or (now - entry.created_at) > abs_limit

    def _remove_key_locked(self, key: tuple[str, str]) -> VaultEntry | None:
        removed = self._entries.pop(key, None)
        if removed is not None:
            self._total_bytes = max(0, self._total_bytes - removed.size)
        return removed

    def _mark_expired_in_db(self, doc_ids: list[uuid.UUID], *, reason: str) -> None:
        if not doc_ids:
            return
        try:
            with SessionLocal() as db:
                db.execute(
                    update(Document)
                    .where(Document.id.in_(doc_ids), Document.vault_expired.is_(False))
                    .values(vault_expired=True)
                )
                audit.record(
                    db,
                    action="VAULT_WIPE",
                    outcome=AuditOutcome.allowed,
                    actor_role="system",
                    resource_type="vault",
                    metadata={"reason": reason, "count": len(doc_ids)},
                )
                db.commit()
        except Exception:
            logger.warning("Failed to mark wiped documents expired", extra={"event": "vault_db_sync_error"})

    def put(
        self,
        sid: uuid.UUID | str,
        doc_id: uuid.UUID | str,
        payload: dict[str, Any],
        *,
        user_id: uuid.UUID | str | None = None,
        now: datetime | None = None,
    ) -> None:
        sid_s = _to_str(sid)
        doc_s = _to_str(doc_id)
        user_s = _to_str(user_id) if user_id is not None else None
        ts = now or datetime.now(timezone.utc)
        nonce, ciphertext = self._encrypt(sid_s, doc_s, payload)
        entry_size = len(nonce) + len(ciphertext)
        max_bytes = get_settings().VAULT_MAX_MB * 1024 * 1024
        evicted_docs: set[str] = set()

        with self._lock:
            key = (sid_s, doc_s)
            old = self._remove_key_locked(key)
            if old is not None and user_s is None:
                user_s = old.user_id

            # Enforce per-session cap (20 entries per architecture.md §8)
            session_keys = [k for k in self._entries.keys() if k[0] == sid_s]
            while len(session_keys) >= PER_SESSION_CAP:
                oldest_key = session_keys.pop(0)
                if self._remove_key_locked(oldest_key) is not None:
                    evicted_docs.add(oldest_key[1])

            self._entries[key] = VaultEntry(
                nonce=nonce,
                ciphertext=ciphertext,
                created_at=old.created_at if old is not None else ts,
                last_access=ts,
                size=entry_size,
                user_id=user_s,
            )
            self._entries.move_to_end(key)
            self._total_bytes += entry_size

            # Evict globally least-recently-used entries if over VAULT_MAX_MB
            while self._total_bytes > max_bytes and len(self._entries) > 1:
                lru_key, _lru_val = self._entries.popitem(last=False)
                self._total_bytes = max(0, self._total_bytes - _lru_val.size)
                evicted_docs.add(lru_key[1])

        if evicted_docs:
            self._mark_expired_in_db(_to_uuid_list(evicted_docs), reason="lru_eviction")

    def get(
        self,
        sid: uuid.UUID | str,
        doc_id: uuid.UUID | str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        sid_s = _to_str(sid)
        doc_s = _to_str(doc_id)
        ts = now or datetime.now(timezone.utc)
        expired_doc: str | None = None

        with self._lock:
            key = (sid_s, doc_s)
            entry = self._entries.get(key)
            if entry is None:
                return None
            if self._is_expired(entry, ts):
                self._remove_key_locked(key)
                expired_doc = doc_s
            else:
                entry.last_access = ts
                self._entries.move_to_end(key)
                return self._decrypt(sid_s, doc_s, entry)

        if expired_doc is not None:
            self._mark_expired_in_db(_to_uuid_list({expired_doc}), reason="idle_or_age_expired")
        return None

    def update(
        self,
        sid: uuid.UUID | str,
        doc_id: uuid.UUID | str,
        updates: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> bool:
        sid_s = _to_str(sid)
        doc_s = _to_str(doc_id)
        ts = now or datetime.now(timezone.utc)
        with self._lock:
            existing = self.get(sid_s, doc_s, now=ts)
            if existing is None:
                return False
            entry = self._entries.get((sid_s, doc_s))
            user_s = entry.user_id if entry is not None else None
            existing.update(updates)
            self.put(sid_s, doc_s, existing, user_id=user_s, now=ts)
            return True

    def wipe(self, sid: uuid.UUID | str, doc_id: uuid.UUID | str, *, mark_db: bool = True) -> bool:
        sid_s = _to_str(sid)
        doc_s = _to_str(doc_id)
        with self._lock:
            removed = self._remove_key_locked((sid_s, doc_s))
        if removed is not None and mark_db:
            self._mark_expired_in_db(_to_uuid_list({doc_s}), reason="wipe_entry")
        return removed is not None

    def wipe_session(self, sid: uuid.UUID | str, *, mark_db: bool = True) -> list[uuid.UUID]:
        sid_s = _to_str(sid)
        removed_docs: set[str] = set()
        with self._lock:
            keys = [k for k in self._entries.keys() if k[0] == sid_s]
            for key in keys:
                if self._remove_key_locked(key) is not None:
                    removed_docs.add(key[1])
        doc_uuids = _to_uuid_list(removed_docs)
        if doc_uuids and mark_db:
            self._mark_expired_in_db(doc_uuids, reason="session_wipe")
        return doc_uuids

    def wipe_document(self, doc_id: uuid.UUID | str, *, mark_db: bool = False) -> list[uuid.UUID]:
        doc_s = _to_str(doc_id)
        removed = False
        with self._lock:
            keys = [k for k in self._entries.keys() if k[1] == doc_s]
            for key in keys:
                if self._remove_key_locked(key) is not None:
                    removed = True
        doc_uuids = _to_uuid_list({doc_s}) if removed else []
        if doc_uuids and mark_db:
            self._mark_expired_in_db(doc_uuids, reason="document_wipe")
        return doc_uuids

    def wipe_user(self, user_id: uuid.UUID | str, *, mark_db: bool = True) -> list[uuid.UUID]:
        user_s = _to_str(user_id)
        removed_docs: set[str] = set()
        with self._lock:
            keys = [k for k, v in self._entries.items() if v.user_id == user_s]
            for key in keys:
                if self._remove_key_locked(key) is not None:
                    removed_docs.add(key[1])
        doc_uuids = _to_uuid_list(removed_docs)
        if doc_uuids and mark_db:
            self._mark_expired_in_db(doc_uuids, reason="user_restricted")
        return doc_uuids

    def sweep_expired(self, *, now: datetime | None = None, mark_db: bool = True) -> list[uuid.UUID]:
        ts = now or datetime.now(timezone.utc)
        expired_docs: set[str] = set()
        with self._lock:
            keys = [k for k, v in self._entries.items() if self._is_expired(v, ts)]
            for key in keys:
                if self._remove_key_locked(key) is not None:
                    expired_docs.add(key[1])
        doc_uuids = _to_uuid_list(expired_docs)
        if doc_uuids and mark_db:
            self._mark_expired_in_db(doc_uuids, reason="sweeper_expired")
        return doc_uuids

    def stats(self) -> dict[str, int]:
        with self._lock:
            sessions = {k[0] for k in self._entries.keys()}
            return {
                "entries": len(self._entries),
                "total_bytes": self._total_bytes,
                "sessions": len(sessions),
            }

    def clear_all_for_tests(self) -> None:
        with self._lock:
            self._entries.clear()
            self._total_bytes = 0

    def start_sweeper(self) -> None:
        if self._sweeper_thread is not None and self._sweeper_thread.is_alive():
            return
        self._stop_event.clear()

        def _loop() -> None:
            while not self._stop_event.wait(SWEEP_INTERVAL_SECONDS):
                self.sweep_expired()

        self._sweeper_thread = threading.Thread(
            target=_loop,
            name="vault-sweeper",
            daemon=True,
        )
        self._sweeper_thread.start()

    def stop_sweeper(self) -> None:
        self._stop_event.set()


def run_startup_recovery(db: Session) -> dict[str, int]:
    """Architecture.md §8 startup routine: mark vault expired and recover interrupted jobs."""
    now = datetime.now(timezone.utc)
    expired_res = db.execute(
        update(Document)
        .where(Document.vault_expired.is_(False))
        .values(vault_expired=True, updated_at=now)
    )
    proc_res = db.execute(
        update(Document)
        .where(Document.status == DocumentStatus.PROCESSING)
        .values(
            status=DocumentStatus.FAILED,
            failure_code="SERVER_RESTART",
            version=Document.version + 1,
            updated_at=now,
        )
    )
    send_res = db.execute(
        update(Document)
        .where(Document.status == DocumentStatus.SENDING)
        .values(
            status=DocumentStatus.LLM_FAILED,
            failure_code="SERVER_RESTART",
            version=Document.version + 1,
            updated_at=now,
        )
    )
    db.commit()
    summary = {
        "vault_expired": expired_res.rowcount or 0,
        "processing_failed": proc_res.rowcount or 0,
        "sending_failed": send_res.rowcount or 0,
    }
    logger.info("Startup recovery complete", extra={"event": "startup_recovery", "count": sum(summary.values())})
    return summary


vault = VaultService()
