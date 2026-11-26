# rules.md — Non-negotiable rules for the AI developer

Read order for every session: `brain.md` → `rules.md` → `architecture.md` → `design.md`.
You are an executor. The docs contain the decisions. Do not redesign, do not ask the user questions.
If the docs are silent, choose the simplest option that does not break any rule here, then log it in `brain.md` → Decisions log.

---

## 1. Privacy rules (a violation is a critical bug)

| ID | Rule |
|---|---|
| P1 | Real patient values (names, IDs, phones, dates, addresses, etc.) exist only in the in-memory Vault and in the HTTP responses that go to the logged-in owner. They are never written to the database, disk, logs, audit metadata, error messages, or analytics. |
| P2 | The original PDF bytes and the original extracted text live only in the Vault (RAM). Never write them to disk (no temp files; use in-memory streams). |
| P3 | Only plain sanitized text is ever sent to an external LLM. Never send: the PDF, images, filename, user id, email, role, document id, or any metadata. |
| P4 | Sanitized text is persisted to the database only after the safety scan has PASSED. Before that it lives in the Vault only. |
| P5 | Detection, OCR, tokenization, safety scan and re-hydration run locally. Never call an external service to find or classify identifiers. |
| P6 | Logs never contain document text, filenames, entity values, request bodies, tokens, passwords, cookies or API keys. Log ids, codes, durations, counts only. |
| P7 | Admins and auditors can never read, list, download or search document content or filenames. Admin analytics use aggregate counts only. |
| P8 | No auto-send. A human must press "Approve and generate" after seeing the sanitized text. Any manual mark or re-scan resets approval. |
| P9 | The app is a demo: UI must show "Demo environment — use synthetic data only" on the upload page and in the footer. |

## 2. Security rules

- S1 Passwords: argon2id (`argon2-cffi`), min length 10, at least one letter and one digit. Never log or return hashes.
- S2 Tokens: access JWT 15 min, refresh token 7 days, both in httpOnly, Secure, SameSite=Lax cookies. Refresh tokens are random 256-bit values stored only as SHA-256 hashes; rotate on every refresh; reuse of a revoked token revokes the whole family.
- S3 Every request loads the user from the DB (status, role, token_version). Never trust role or status from the JWT alone.
- S4 Authorization is enforced in the backend by dependencies (`require_role`, `require_active`, `get_owned_document`). Hiding buttons in the UI is never enough.
- S5 Another user's document returns **404** (not 403) and writes an audit row (`DOC_ACCESS_DENIED`). Admin or auditor calling any document endpoint gets **403 `ADMIN_NO_DOCUMENT_ACCESS`** and an audit row.
- S6 The role field is never accepted from public endpoints. Role changes only via admin endpoint, only doctor↔auditor, never on self, never on another admin. Admins are created only by the seed script.
- S7 State-changing requests (POST/PUT/PATCH/DELETE) require header `X-Requested-With: fetch` and a matching `Origin`. Otherwise 403 `CSRF_REJECTED`.
- S8 Login errors are generic ("Invalid email or password"). Lock an account 15 min after 5 failed logins.
- S9 Rate limits (slowapi): auth 10/min/IP; upload 20/hour/user; LLM send 10/min/user; default 120/min/IP. Return 429 with `Retry-After`.
- S10 Audit log is append-only: DB trigger blocks UPDATE and DELETE; each row stores a hash chain (`prev_hash`, `hash`).
- S11 Security headers on every response: `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN` (needed for PDF preview iframe), `Referrer-Policy: no-referrer`, `Cache-Control: no-store` on all `/api` responses.
- S12 No secrets in the repo. `.env.example` has placeholders only. Never print keys.
- S13 All SQL through SQLAlchemy ORM / bound parameters. No string-built SQL.

## 3. Code rules

Backend (Python 3.11):
- B1 Type hints everywhere; Pydantic v2 schemas for every request and response. No `dict` returns.
- B2 Sync SQLAlchemy 2.0 + sync FastAPI routes + one `ThreadPoolExecutor` for pipeline jobs. No asyncio mixing.
- B3 Run **one** uvicorn worker (the Vault is in process memory). Never add `--workers > 1`.
- B4 Every state change on a document goes through `services/state.py::transition()` (atomic conditional UPDATE). Never assign `document.status` directly.
- B5 Every DB write sequence is in a transaction; on error roll back and return the standard error shape.
- B6 Every error uses `AppError(code, http_status, message)` from `errors.py`. Codes come only from the catalog in `architecture.md §19`. Add new codes there first.
- B7 Error response shape is always `{"error":{"code","message","request_id"}}`. Never leak stack traces or SQL.
- B8 Business rules live in `services/` (pure functions where possible), not in routers.
- B9 Config only via `config.py` (pydantic-settings) from environment variables.
- B10 All timestamps are UTC, ISO 8601.
- B11 Every endpoint writes its audit rows via `audit.record(...)` inside the same transaction as the change.
- B12 Dependencies pinned in `requirements.txt` with exact versions.

Frontend (Next.js 14, TypeScript strict, Tailwind):
- F1 Follow `design.md` exactly: palette, spacing, components, copy. No extra colors, no theme switcher, no dark mode.
- F2 No card grids. Use plain sections, tables and forms (see design.md §3).
- F3 All API calls go through one `lib/api.ts` wrapper that adds `X-Requested-With: fetch`, handles 401 with one refresh attempt, and maps the error shape to toasts.
- F4 Every form validates with zod and shows inline messages; every async action shows a loading state; every list has loading, empty and error states.
- F5 Keyboard accessible, visible focus ring, semantic HTML, labels on all inputs, `aria-live` for toasts and status changes.
- F6 Never store documents or tokens in localStorage/sessionStorage. Server state via TanStack Query only.
- F7 Never render untrusted text with `dangerouslySetInnerHTML`.

## 4. Testing rules

- T1 Write the tests listed in `architecture.md §24` as you build each milestone. A milestone is not done until its tests pass.
- T2 Tests run against PostgreSQL (docker-compose service), not SQLite.
- T3 LLM providers are mocked in tests (no real API calls). A separate manual smoke script `scripts/smoke_llm.py` hits real APIs.
- T4 Use only synthetic patients. Fixtures live in `backend/tests/fixtures/` (generated by `scripts/make_sample_pdfs.py`).
- T5 One test asserts that no real entity value appears in: DB dump of documents/entities tables, audit_logs, application logs, and the captured outbound LLM request body.

## 5. Process rules

- G1 After **every** change (feature, fix, decision, file added), update `brain.md`: tick the checklist, append one line to Changelog, update Status. This is mandatory, not optional.
- G2 Small commits, message format `type(scope): summary` (feat, fix, test, docs, chore).
- G3 Do not start a milestone before the previous milestone's "Done when" is true.
- G4 When you finish a milestone, run the full test suite and note the result in `brain.md`.
- G5 If a rule here conflicts with another doc, this file wins, then `architecture.md`, then `design.md`.
- G6 Keep the README current: setup, env vars, run, test, deploy, architecture summary, demo accounts note (credentials are given privately, never committed).

## 6. Forbidden

- No `print()` of data; no `console.log` of data.
- No `localStorage` for anything sensitive. No `eval`. No `dangerouslySetInnerHTML`.
- No external APIs other than: the LLM providers, Google ID-token verification.
- No telemetry, analytics scripts, or third-party fonts/CDN scripts that receive user data (Google Identity script on the login page only).
- No new dependencies without adding them to `architecture.md §2` and `brain.md` Decisions log.
- No TODO/placeholder code left in a finished milestone.
- No disabling a test to make it pass.
- No features outside the docs (no password reset, no email verification, no OAuth other than Google, no 3D, no theme toggle).

## 7. Definition of done (every milestone)

1. Code matches `architecture.md` / `design.md`.
2. Tests for the milestone pass; full suite still green.
3. No rule in this file violated (self-check P1–P9, S1–S13).
4. `brain.md` updated.
5. App starts cleanly with `docker compose up` from a fresh clone and a fresh DB.
