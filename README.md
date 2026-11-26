# ClinicShield

Privacy-first clinical document de-identification and re-hydration gateway.

- **Event:** Hack the Vibe 2026 (CODE-ARENAX)
- **Track:** World Problem Solver (Health Safety)
- **Declared advanced challenges:** **A03** (Security and Access Control) and **A06** (External API and Fault Tolerance)
- **Also implemented:** A07 (Resumable workflow), A05 (Concurrency & idempotency), A02 (Explainable detection rules), A08-lite (SQL aggregate analytics)

> **Demo environment — use synthetic data only.**

---

## Problem

Clinicians paste patient PDFs into cloud AI tools to save documentation time, exposing Protected Health Information (PHI). Blanket AI bans push staff to shadow AI, naive `[REDACTED]` scrubbing destroys clinical meaning (ages, relative timelines, recurring people), and clinical PDFs hide identities inside author metadata, annotations, form widgets, and scanned headers.

## Solution

ClinicShield runs local extraction + OCR + HIPAA-18 identifier detection + context-preserving tokenization (`[PATIENT_A]`, `Age 58`, `[DAY_0]`) + an independent safety scan + mandatory human review (with highlight-to-tokenize) before sending **only plain sanitized text** to an external LLM. Real patient details live solely in an AES-256-GCM encrypted in-memory Vault, are restored locally on the clinician's screen, and are wiped on logout, idle timeout, account restriction, or server restart.

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

- **Trusted zone:** Browser + FastAPI backend + in-memory AES-256-GCM Vault.
- **Database (PostgreSQL):** Stores zero real patient values; `sanitized_text` is persisted only after safety `PASS`; `document_entities` stores tokens and explainability reasons only.
- **Untrusted zone (External LLM):** Receives static system prompt + task headings + plain `sanitized_text` only. Never receives PDFs, images, filenames, user IDs, emails, roles, or document IDs.

## Setup & local run

```bash
cp .env.example .env
# Fill in GEMINI_API_KEY, GEMINI_MODEL, GROQ_API_KEY, GROQ_MODEL, and optional seed credentials in .env
docker compose up --build
```

- Frontend: `http://localhost:3000`
- Backend health: `http://localhost:8000/api/health` (and same-origin `http://localhost:3000/api/health`)

## Environment variables

See [`.env.example`](.env.example). Never commit secrets or `.env`.

- `DATABASE_URL` — PostgreSQL 15+ connection string (`postgresql+psycopg://...`)
- `JWT_SECRET` — random 32+ char signing secret
- `FRONTEND_ORIGIN` — allowed CSRF `Origin` (e.g., `http://localhost:3000` or Vercel URL)
- `BACKEND_URL` — backend base URL used by Next.js `/api/:path*` rewrites
- `GEMINI_API_KEY`, `GEMINI_MODEL`, `GROQ_API_KEY`, `GROQ_MODEL`, `LLM_PROVIDER_ORDER=gemini,groq`
- `GOOGLE_CLIENT_ID` (and `NEXT_PUBLIC_GOOGLE_CLIENT_ID` for frontend Google Identity Services button)
- `ADMIN_SEED_EMAIL`, `ADMIN_SEED_PASSWORD`, `AUDITOR_SEED_EMAIL`, `AUDITOR_SEED_PASSWORD`, `DOCTOR_SEED_EMAIL`, `DOCTOR_SEED_PASSWORD` (demo credentials are provided privately, never committed)

## Running tests & tools

Backend tests run against PostgreSQL (never SQLite) with mocked LLM providers:

```bash
docker compose exec backend pytest -v
docker compose exec backend pytest --cov=app --cov-report=term-missing
```

Frontend typecheck & lint:

```bash
docker compose exec frontend npm run typecheck
docker compose exec frontend npm run lint
```

Generate the three synthetic sample PDF fixtures (`backend/tests/fixtures/`):

```bash
docker compose exec backend python scripts/make_sample_pdfs.py
```

Manual live LLM smoke test (synthetic tokenized text only, requires real API keys):

```bash
docker compose exec backend python scripts/smoke_llm.py
```

## Deployment

### Backend + PostgreSQL (Render / Docker host)
1. Provision a PostgreSQL 15+ database.
2. Deploy a Docker web service using repo root context (`.`) and `backend/Dockerfile` (`--workers 1` is mandatory because the Vault lives in process memory).
3. Configure environment variables (`ENV=prod`, `DATABASE_URL`, `JWT_SECRET`, `FRONTEND_ORIGIN`, `GEMINI_*`, `GROQ_*`, seed credentials).
4. Container startup automatically runs `alembic upgrade head && python scripts/seed.py && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1`.
5. Free-tier hosts sleep after inactivity — ping `GET /api/health` 1 minute before judging.

### Frontend (Vercel)
1. Set Root Directory to `frontend`.
2. Set `BACKEND_URL` to your deployed backend origin (and optional `NEXT_PUBLIC_GOOGLE_CLIENT_ID`).
3. `frontend/next.config.js` rewrites `/api/:path*` to `${BACKEND_URL}/api/:path*`, keeping `httpOnly` auth cookies first-party and same-origin.

## Security model & declared challenges

### A03 — Security and Access Control
- **Auth & sessions:** Argon2id password hashing (`argon2-cffi`, min 10 chars with letter + digit), 15-minute JWT + 7-day 256-bit refresh tokens stored only as SHA-256 hashes, rotation on refresh with full-family revocation and vault wipe on reuse, 15-minute lockout after 5 failed logins (`backend/app/security.py`, `backend/app/routers/auth.py`).
- **RBAC & isolation:** User status, role, and `token_version` loaded from PostgreSQL on every request; non-owner document access returns `404` + `DOC_ACCESS_DENIED` audit; admin/auditor document access returns `403 ADMIN_NO_DOCUMENT_ACCESS` + `ADMIN_DOC_ACCESS_DENIED` audit (`backend/app/deps.py`).
- **Privilege escalation guards:** Signup ignores any supplied `role`; admin cannot modify self (`CANNOT_MODIFY_SELF`) or another admin (`CANNOT_MODIFY_ADMIN`); role changes restricted to `doctor ↔ auditor` (`INVALID_ROLE_CHANGE`) with session revocation (`backend/app/routers/admin.py`).
- **CSRF, headers, rate limits:** `X-Requested-With: fetch` + `Origin` verification on all state-changing routes, S11 security headers (`nosniff`, `SAMEORIGIN`, `no-referrer`, `Cache-Control: no-store` on `/api`), `slowapi` rate limits with `429 Retry-After` (`backend/app/main.py`, `backend/app/ratelimit.py`).
- **Tamper-evident audit log:** PostgreSQL `BEFORE UPDATE OR DELETE` trigger blocks mutations; SHA-256 hash chain serialized with `pg_advisory_xact_lock(7001)` and verifiable via `GET /api/audit/verify` (`backend/alembic/versions/0001_initial_schema.py`, `backend/app/services/audit.py`, `backend/app/routers/audit.py`).

### A06 — External API and Fault Tolerance
- **Resilient LLM router:** Gemini primary with Groq fallback, explicit `httpx` timeouts (5s connect, 30s read), up to 3 attempts per provider with exponential backoff (1s, 2s, 4s + jitter) and `Retry-After` honoring (capped at 10s), per-provider circuit breaker (5 failures in 60s → open 30s → half-open trial), Markdown heading validation with single repair retry, global `Semaphore(4)`, and safe `LLM_FAILED` recovery via `POST /api/documents/{id}/retry` (`backend/app/services/llm/`).
- **Idempotency & concurrency (A05):** `POST /api/documents/{id}/send` requires `Idempotency-Key` with `SELECT ... FOR UPDATE` and atomic state transitions (`backend/app/services/state.py`, `backend/app/routers/documents.py`).

## Known limitations

- Automated identifier detection is rule + small-model based and not perfect, so mandatory human review and a second-pass safety scan are enforced before any LLM call.
- Python cannot guarantee memory zeroing; the AES-256-GCM in-memory Vault is best effort.
- Vault data is lost on server restart (documents then show placeholders only).
- No password reset, no email verification, and no un-marking of detected tokens.
- Free-tier hosts sleep after inactivity.
- Demo uses synthetic patient data only.
