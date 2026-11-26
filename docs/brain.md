# brain.md — Living memory of the project

**Update this file after EVERY change** (rules.md G1): tick the checklist, update Status, append one line to Changelog.
Read order each session: `brain.md` → `rules.md` → `architecture.md` → `design.md`.

---

## 1. Status (edit me)

- Current milestone: **M0 (complete — ready for M1)**
- Last updated: 2026-11-26
- Last full test run: pass (4/4 backend pytest; frontend `tsc --noEmit` & `next build` passed)
- Blockers: none

## 2. Project summary

**Name (working):** ClinicShield (placeholder; one constant to change).
**Event:** Hack the Vibe 2026 (CODE-ARENAX), solo. **Track:** World Problem Solver.
**Problem:** Doctors paste patient PDFs into cloud AI tools, exposing PHI. Bans push staff to shadow AI; naive `[REDACTED]` ruins clinical meaning; PDFs hide identities in metadata, headers and scanned images.
**Solution:** A local "de-identify and re-hydrate" gateway (web app). Upload PDF → local extraction + OCR → local detection of the HIPAA 18 → context-preserving tokens (`[PATIENT_A]`, `Age 58`, `[DAY_0]`) → safety scan → human review (with highlight-to-tokenize) → only sanitized text goes to an external LLM → real details restored locally on screen. Real values live only in an encrypted in-memory vault, wiped on logout/idle.
**Users:** doctors (main), admins (manage users and complaints, never see documents), auditors (read-only audit logs).
**Declared advanced challenges:** **A03** (security and access control) and **A06** (external API and fault tolerance). Also built: A07 (workflow), A05 (concurrency), A02 (explainable rules), A08-lite (analytics).
**Scoring reminder:** 60 mandatory (M01–M08) + 2 × 20 advanced. Judges verify live behavior, run hidden tests, and ask questions. Submission needs: YouTube video, public GitHub repo, live URL (+ fields: title, track, problem, challenges A03 and A06).

## 3. Decisions (locked)

| # | Decision |
|---|---|
| D1 | Web app: Next.js frontend + FastAPI backend + PostgreSQL. Not a browser extension. |
| D2 | LLM via API only (Gemini primary, Groq fallback). Identifier detection is 100% local. |
| D3 | Vault is in RAM (AES-256-GCM), keyed by (session, document). Single uvicorn worker. |
| D4 | Sanitized text persisted only after safety PASS. Entities stored without values. |
| D5 | Roles: doctor, admin, auditor. Admin cannot read documents (enforced in backend). |
| D6 | Restricted users: can sign in, use Profile and Help only. |
| D7 | Auth: email+password (argon2id) and Google ID token. httpOnly cookies via same-origin Next.js rewrites. |
| D8 | Human approval is mandatory before any LLM call. No auto-send. |
| D9 | UI: white/black-family palette + one teal accent `#0F766E`, flat, no 3D, no theme switcher, no card grids, custom 404, BrandLoader, admin update animation, arranged Profile page. |
| D10 | Navbar before login: Home · About · FAQ (center), Login (right), logo (left). Logged-in users never see the landing page. Login page has a Back button to home. |
| D11 | Help page lets users file complaints; admin handles them (open → in_progress → resolved). |
| D12 | Highlight-to-tokenize in the review step (replaces all occurrences, resets approval). |
| D13 | No password reset, no email verification, no un-marking of tokens (documented limitations). |

## 4. Decisions log (AI developer appends here)

- 2026-11-26 (M0): Placed frontend `APP_NAME` constant in `frontend/lib/constants.ts`; `docker-compose.yml` provides local dev `${VAR:-default}` fallbacks so `docker compose up --build` succeeds directly from a clean clone without manual `.env` creation. Backend Dockerfile starts uvicorn directly in M0 (Alembic + seed command added in M1).

## 5. Build order and checklist

Do the milestones in order. Each has a "Done when". Do not start the next until it is true.

### M0 — Scaffold
- [x] Repo layout per architecture.md §3; `docker-compose.yml` (db, backend, frontend); `.env.example`
- [x] FastAPI app with `/api/health`, error handler (standard shape), request-id middleware, JSON logging with PHI-safe filter
- [x] Next.js app with Tailwind, Inter font, `next.config.js` rewrites
- **Done when:** `docker compose up --build` serves the health endpoint and the frontend home page from a clean clone.

### M1 — Database
- [ ] SQLAlchemy models for all tables (architecture.md §5); Alembic migration; audit-log immutability trigger
- [ ] `scripts/seed.py` (admin, auditor, demo doctor from env)
- **Done when:** migration applies on an empty DB; seed is idempotent; trigger blocks UPDATE/DELETE on `audit_logs`.

### M2 — Auth, RBAC, audit
- [ ] Signup, login, lockout, refresh rotation with reuse detection, logout, Google login, `/me`, sessions, password change
- [ ] Dependencies: `current_user`, `require_active`, `require_role`, CSRF header + Origin check, rate limits, security headers
- [ ] `audit.record` with hash chain and advisory lock; `/api/audit` + `/api/audit/verify`
- **Done when:** all Auth and Authorization tests in architecture.md §24 pass (document-related ones come in later milestones).

### M3 — Vault and upload
- [ ] `vault.py` (encryption, LRU, sweeper, wipe triggers, startup routine)
- [ ] `POST /api/documents` with all validations, duplicate handling, job submission
- [ ] `extraction.py` (text, annotations, widgets, OCR pages, OCR images, metadata hints)
- **Done when:** sample PDFs (text, scanned, image header) extract correctly; bad files give the right error codes; vault wipes on logout and idle.

### M4 — Detection, tokenization, safety, review
- [ ] Detectors, date/age rules, stoplists, overlap resolution, sweep
- [ ] Tokenizer + render + entity rows; safety scan; state machine `transition()`
- [ ] Pipeline orchestrator with step rows; resume; manual marks; approve with `sanitized_sha256` check; version conflict
- [ ] Endpoints: list/detail/steps/original-text/original-pdf/sanitized/delete
- **Done when:** the Detection, Safety, Pipeline and privacy (P1/T5) tests pass on the three sample PDFs; a seeded leak yields BLOCK and a manual mark clears it.

### M5 — LLM layer and results (A06, A05, A07)
- [ ] Providers (Gemini, Groq), router with retries/backoff/Retry-After, circuit breaker, validation + repair, fallback, semaphore, per-user limit
- [ ] `send` with idempotency and atomic transition; `retry`; `result` (re-hydration); `export` txt/docx
- [ ] `scripts/smoke_llm.py` (real call, manual)
- **Done when:** all LLM, Concurrency and Pipeline-failure tests pass; outbound payload test proves no real values leave.

### M6 — Remaining backend features
- [ ] Dashboard, documents query (filters/sort/pagination), admin users (restrict/restore/role), complaints (user + admin), analytics, audit filters
- **Done when:** Data, Complaints, Admin tests pass; admin endpoints never expose filenames or text.

### M7 — Backend hardening
- [ ] Full test suite green; coverage report; fix every flaw found; review rules.md S1–S13 and P1–P9 one by one
- [ ] README draft (setup, env, architecture, limitations)
- **Done when:** `pytest` is green from a fresh DB and the checklist in §6 is satisfied for all backend items.

### M8 — Frontend foundation and public site
- [ ] Tokens, base components (design.md §2–3), layouts (public header/footer, app header/footer)
- [ ] `lib/api.ts`, auth context, middleware redirects
- [ ] Landing, About, FAQ, Login (with Back), Signup, Google button, 404, 403, error boundary, BrandLoader, route progress bar
- **Done when:** public pages match design.md; logged-in users are redirected away from public pages; 404 works for unknown routes.

### M9 — Frontend app
- [ ] Doctor: Dashboard, New document (live steps), My documents, Review page (panes, highlight-to-tokenize, safety banner, approve/generate, result, export), Help (form + thread), Profile
- [ ] Admin: Overview, Users, Complaints (+thread), Audit logs, Analytics; update animation on every mutation
- [ ] Auditor: Audit logs
- **Done when:** a full end-to-end run works in the browser for each role; all states (loading, empty, error) exist; keyboard navigation works.

### M10 — Deploy, docs, demo
- [ ] Deploy backend (Docker, one worker) + Postgres + frontend; set env vars; seed; verify live URL
- [ ] README final (problem, track, architecture, setup, limitations, A03 + A06 map)
- [ ] `scripts/make_sample_pdfs.py` fixtures; demo script (see §7)
- [ ] Verify the published build matches the repo; no secrets committed
- **Done when:** the submission checklist in §8 is all ticked.

## 6. Rubric traceability (what proves each mark)

| Req | Where it is implemented | Proof |
|---|---|---|
| M01 Complete system (3 modules + E2E) | Modules: Document pipeline · Review/Vault · AI generation (+ Admin and Help) | E2E demo upload → generate → export |
| M02 Database | architecture §5; CRUD on documents, complaints, users, sessions | tables + FKs + unique constraints; persistence across restart (except vault by design) |
| M03 Auth | architecture §6–7 | tests: lockout, refresh reuse, RBAC matrix |
| M04 Business logic | tokenization rules §13, state machine §9, safety gate §14, restrict/role rules §23, complaint workflow §22 | tests for each rule and transition |
| M05 Dynamic data | §21 filters/sort/search/pagination; dashboard and analytics aggregates | tests on fixtures |
| M06 Errors | error catalog §19; duplicate upload; corrupt/encrypted PDF; LLM failure recovery | tests per code |
| M07 UI | design.md §4–7 | manual check at 360px and 1280px; keyboard-only run |
| M08 Deploy + docs | architecture §25 | live URL + README |
| A03 Security (declared) | RBAC, owner-only resources, admin cannot read docs, audit hash chain + immutable trigger, refresh reuse detection, escalation guards | tests: B→A's document, admin 403, escalation attempts, tamper detection |
| A06 External API (declared) | LLM router: timeouts, retries with backoff and Retry-After, circuit breaker, per-user rate limit, malformed-output repair, provider fallback, safe failure | tests: timeout, 429, malformed, both fail, breaker |
| A07 Workflow (bonus) | pipeline steps + state machine + resume | failure-at-each-step tests |
| A05 Concurrency (bonus) | idempotency keys, atomic transitions, version conflict, unique constraints | double-send test |

Hidden-test readiness (judges' stated tests): "user modifies another user's restricted record" (A03) → 404 + audit row. "External API times out or returns malformed data" (A06) → retry, repair, fallback, then clean `LLM_FAILED`. Rehearse both in the video.

## 7. Demo script (for the YouTube video, ~6–8 min)

1. Problem (30 s) and track. 2. Landing → login as doctor. 3. Upload sample PDF (text + hidden author metadata + image header) → live steps → review page: show Original vs Cleaned, tokens, "Why was this replaced?". 4. Edge case: sample with a leaked name → BLOCKED → highlight → replace → PASS. 5. Approve and generate → result with real details restored → export. 6. A06: switch the primary provider key to invalid (or use the test toggle) → fallback happens; show timeout case. 7. A03: second doctor cannot open first doctor's document (404); admin sees users but gets 403 on documents; show audit log + integrity check. 8. Admin: restrict a user (update animation), complaint handling. 9. Logout → vault wiped (document shows "details expired"). 10. Architecture and limitations (30 s). Show no secrets on screen.

## 8. Submission checklist

- [ ] Public GitHub repo (README, setup, architecture, no secrets)
- [ ] Live URL works; build matches repo; test credentials sent privately
- [ ] YouTube video (public/unlisted): problem, main workflow, A03 + A06, at least one edge case
- [ ] Submission fields: title, track (World Problem Solver), problem statement, challenges (A03, A06), the three links
- [ ] Both landing and app tested on mobile and desktop
- [ ] Free-tier backend warmed up before judging

## 9. Known limitations (copy to README)

Detection is rule + small-model based and not perfect → mandatory human review and safety gate. Python cannot guarantee memory zeroing. Vault is lost on server restart (documents then show placeholders only). No password reset or email verification. Free-tier hosts sleep. Demo uses synthetic data only.

## 10. Changelog (append only, newest last)

- 2026-11-26 — M0 — Added docs/ specs, root scaffold (.env.example, docker-compose.yml, README.md), FastAPI backend scaffold (/api/health, standard error handlers, request-id + S11 security middleware, PHI-safe JSON logging, M0 tests), and Next.js 14 frontend scaffold (Tailwind tokens, Inter font, /api rewrites).
