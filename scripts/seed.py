"""Idempotent seed script for admin, auditor, and demo doctor accounts (from env vars)."""

import logging
from pathlib import Path
import sys

# Ensure backend/ is importable whether invoked from repo root or /app inside Docker.
SCRIPT_DIR = Path(__file__).resolve().parent
CANDIDATE_ROOTS = [SCRIPT_DIR.parent / "backend", SCRIPT_DIR.parent]
for root in CANDIDATE_ROOTS:
    if (root / "app").is_dir() and str(root) not in sys.path:
        sys.path.insert(0, str(root))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.logging import configure_logging
from app.models.user import User, UserRole, UserStatus
from app.security import hash_password

logger = logging.getLogger("scripts.seed")


def seed_users(db: Session, settings: Settings | None = None) -> int:
    """Create configured seed users if absent. Returns number of newly created users."""
    cfg = settings or get_settings()
    candidates: list[tuple[str, str, str, UserRole]] = [
        (cfg.ADMIN_SEED_EMAIL, cfg.ADMIN_SEED_PASSWORD, "ClinicShield Admin", UserRole.admin),
        (cfg.AUDITOR_SEED_EMAIL, cfg.AUDITOR_SEED_PASSWORD, "ClinicShield Auditor", UserRole.auditor),
        (cfg.DOCTOR_SEED_EMAIL, cfg.DOCTOR_SEED_PASSWORD, "Demo Clinician", UserRole.doctor),
    ]

    created = 0
    for raw_email, raw_password, full_name, role in candidates:
        email = raw_email.strip().lower()
        if not email or not raw_password:
            continue

        existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if existing is not None:
            continue

        user = User(
            email=email,
            password_hash=hash_password(raw_password),
            full_name=full_name,
            role=role,
            status=UserStatus.active,
        )
        db.add(user)
        created += 1

    db.commit()
    logger.info("Seed completed", extra={"event": "seed_complete", "count": created})
    return created


def main() -> None:
    configure_logging()
    with SessionLocal() as db:
        seed_users(db)


if __name__ == "__main__":
    main()
