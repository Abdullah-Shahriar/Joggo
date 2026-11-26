# ClinicShield

Privacy-first clinical document de-identification and re-hydration gateway.

**Track:** World Problem Solver (Health Safety)
**Declared advanced challenges:** A03 (Security and Access Control), A06 (External API and Fault Tolerance)

> Demo environment — use synthetic data only.

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

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: `http://localhost:3000`
- Backend health: `http://localhost:8000/api/health` (also reachable via Next.js rewrite at `http://localhost:3000/api/health`)

## Tests

```bash
docker compose exec backend pytest
```

## Environment variables

See `.env.example` for all supported configuration variables. Never commit secrets. Demo credentials are configured via seed environment variables and are not committed to the repository.

## Known limitations

- Detection is rule and small-model based and not perfect, so mandatory human review and a safety gate are enforced before any external LLM call.
- Python cannot guarantee memory zeroing; the in-memory encrypted Vault is best effort.
- Vault data is lost on server restart (documents then show placeholders only).
- No password reset or email verification.
- Free-tier hosts sleep after inactivity.
- Demo uses synthetic data only.
