# ClinicShield

Privacy-first clinical document de-identification and re-hydration gateway.

**Event:** Hack the Vibe 2026 (CODE-ARENAX)
**Track:** World Problem Solver (Health Safety)
**Declared advanced challenges:** **A03** (Security and Access Control) and **A06** (External API and Fault Tolerance)

> **Demo environment — use synthetic data only.**

## Problem

Clinicians frequently paste patient PDFs into cloud AI tools, exposing Protected Health Information (PHI). Blanket AI bans push staff toward shadow AI, naive `[REDACTED]` scrubbing destroys clinical meaning, and PDFs hide identities inside metadata, annotations, form fields, and scanned headers.

## Solution

ClinicShield runs local PDF extraction, OCR, HIPAA-18 identifier detection, context-preserving tokenization (`[PATIENT_A]`, `Age 58`, `[DAY_0]`), and a mandatory safety scan + human review (with highlight-to-tokenize) before sending **only plain sanitized text** to an external LLM. Real patient details live solely in an AES-256-GCM encrypted in-memory Vault and are restored locally on the clinician's screen, then wiped on logout, idle timeout, restriction, or server restart.

## Architecture

```text
Browser (Next.js)
   │  same-origin  /api/*   (Next.js rewrites → backend; cookies stay same-origin)
   ▼
FastAPI backend (single process, single uvicorn worker)
   ├── Auth / RBAC / Audit
   ├── Document pipeline  ──►  Vault (in-memory, AES-256-GCM)   ← real values live ONLY here
   │     extract → detect → tokenize → safety scan → [human review] → LLM → re-hydrate
   ├── LLM layer (Gemini → Groq fallback, retries, circuit breaker)  ──► external, sanitized text only
   └── PostgreSQL  (users, sessions, documents, entities(no values), steps, llm_requests, audit_logs, complaints)
```

## Quick start (local Docker)

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: `http://localhost:3000`
- Backend health: `http://localhost:8000/api/health` (and same-origin `http://localhost:3000/api/health`)

## Running tests

Tests run against PostgreSQL inside the Docker stack (no SQLite, no real external LLM calls):

```bash
docker compose exec backend pytest -v
docker compose exec backend pytest --cov=app --cov-report=term-missing
```

Generate the three synthetic sample PDF fixtures:

```bash
docker compose exec backend python scripts/make_sample_pdfs.py
```

Manual live LLM connectivity smoke check (uses synthetic tokens only, requires configured API keys):

```bash
docker compose exec backend python scripts/smoke_llm.py
```

## Environment variables

See [`.env.example`](.env.example). Never commit secrets. Demo credentials (`ADMIN_SEED_*`, `AUDITOR_SEED_*`, `DOCTOR_SEED_*`) are injected via environment variables and provided privately.

## Declared challenges (code map)

- **A03 — Security & Access Control**:
  - RBAC, active-account checks, owner-only document access (`404` + `DOC_ACCESS_DENIED`), admin/auditor document isolation (`403 ADMIN_NO_DOCUMENT_ACCESS` + `ADMIN_DOC_ACCESS_DENIED`): `backend/app/deps.py`
  - Argon2id passwords, 15m JWT + 7d SHA-256 refresh token rotation with family reuse detection, account lockout after 5 failures: `backend/app/security.py`, `backend/app/routers/auth.py`
  - CSRF header (`X-Requested-With: fetch`) + `Origin` check, security headers (`S11`), slowapi rate limits (`S9`): `backend/app/deps.py`, `backend/app/main.py`, `backend/app/ratelimit.py`
  - Tamper-evident append-only audit log with PostgreSQL immutability trigger, advisory-locked SHA-256 hash chain, and `/api/audit/verify`: `backend/alembic/versions/0001_initial_schema.py`, `backend/app/services/audit.py`, `backend/app/routers/audit.py`
  - Admin privilege guards (`CANNOT_MODIFY_SELF`, `CANNOT_MODIFY_ADMIN`, `INVALID_ROLE_CHANGE`) and restriction vault wipe: `backend/app/routers/admin.py`
- **A06 — External API & Fault Tolerance**:
  - Explicit `httpx` timeouts, Gemini primary + Groq fallback, 3 attempts with exponential backoff + jitter, `Retry-After` honoring (capped 10s), per-provider circuit breaker (5 failures / 60s → open 30s → half-open trial), output Markdown heading validation + single repair retry, global `Semaphore(4)`, safe failure (`LLM_FAILED`) + recovery retry: `backend/app/services/llm/`

## Known limitations

- Detection is rule and small-model based and not perfect, so mandatory human review and a second-pass safety gate are enforced before any LLM call.
- Python cannot guarantee memory zeroing; the in-memory encrypted Vault is best effort.
- Vault data is lost on server restart (documents then show placeholders only).
- No password reset, no email verification, and no un-marking of detected tokens.
- Free-tier hosts sleep after inactivity (warm up `/api/health` 1 minute before judging).
- Demo uses synthetic data only.
