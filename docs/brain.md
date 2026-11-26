# brain.md — Living memory of the project

**Update this file after EVERY change** (rules.md G1): tick the checklist, update Status, append one line to Changelog.
Read order each session: `brain.md` → `rules.md` → `architecture.md` → `design.md`.

---

## 1. Status (edit me)

- Current milestone: **Judge-Review Hardening — Phases 1–6 complete (all tests, build, lint, memory, and docs green)**
- Last updated: 2026-11-26
- Last full test run: pass (44/44 backend pytest, 90% coverage; frontend `next build`, `tsc --noEmit`, `next lint` 0 errors/warnings; live backend RSS 204.0 MB startup → 267.1 MB after spaCy/Presidio → 295.5 MB peak across 3 sample PDFs)
- Blockers: YouTube demo recording remains for final submission; Chrome remote debugging was unavailable locally for automated browser-tool clicking (verified live via Next.js proxy/headers + full test suite).

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
- 2026-11-26 (M2): Auth cookies set `Secure=True` when `ENV=prod` (`Secure=False` in local HTTP dev/test so localhost/TestClient works without TLS); `refresh_token` path strictly `/api/auth` per `architecture.md §6`. `GET /api/audit/verify` permits both `admin` and `auditor` (read-only) to align `architecture.md §7` and `design.md §5`.
- 2026-11-26 (M3): Added `python-multipart==0.0.20` (required by FastAPI for `UploadFile`/`Form` multipart uploads) and recorded it in `architecture.md §2`.
- 2026-11-26 (UI/UX Refinements — user approved): Renamed user-facing `APP_NAME` from `ClinicShield` to `JOGGO`; added Alembic migration `0002_user_profile_fields` (`age`, `designation`, `hospital_name`, `avatar_data_url` <= 256 KB) on `users` + `/api/me`; added 91-day SQL activity heatmap to Doctor Dashboard and Admin Analytics using teal `#0F766E` intensity levels; redesigned Login/Signup into 50/50 trust split and Document Review into 50/50 split (Left=Modified with red issue lines & enlarged Jump button, Right=Original, full-width Generated Draft below).

## 5. Build order and checklist

Do the milestones in order. Each has a "Done when". Do not start the next until it is true.

### M0 — Scaffold
- [x] Repo layout per architecture.md §3; `docker-compose.yml` (db, backend, frontend); `.env.example`
- [x] FastAPI app with `/api/health`, error handler (standard shape), request-id middleware, JSON logging with PHI-safe filter
- [x] Next.js app with Tailwind, Inter font, `next.config.js` rewrites
- **Done when:** `docker compose up --build` serves the health endpoint and the frontend home page from a clean clone.

### M1 — Database
- [x] SQLAlchemy models for all tables (architecture.md §5); Alembic migration; audit-log immutability trigger
- [x] `scripts/seed.py` (admin, auditor, demo doctor from env)
- **Done when:** migration applies on an empty DB; seed is idempotent; trigger blocks UPDATE/DELETE on `audit_logs`.

### M2 — Auth, RBAC, audit
- [x] Signup, login, lockout, refresh rotation with reuse detection, logout, Google login, `/me`, sessions, password change
- [x] Dependencies: `current_user`, `require_active`, `require_role`, CSRF header + Origin check, rate limits, security headers
- [x] `audit.record` with hash chain and advisory lock; `/api/audit` + `/api/audit/verify`
- **Done when:** all Auth and Authorization tests in architecture.md §24 pass (document-related ones come in later milestones).

### M3 — Vault and upload
- [x] `vault.py` (encryption, LRU, sweeper, wipe triggers, startup routine)
- [x] `POST /api/documents` with all validations, duplicate handling, job submission
- [x] `extraction.py` (text, annotations, widgets, OCR pages, OCR images, metadata hints)
- **Done when:** sample PDFs (text, scanned, image header) extract correctly; bad files give the right error codes; vault wipes on logout and idle.

### M4 — Detection, tokenization, safety, review
- [x] Detectors, date/age rules, stoplists, overlap resolution, sweep
- [x] Tokenizer + render + entity rows; safety scan; state machine `transition()`
- [x] Pipeline orchestrator with step rows; resume; manual marks; approve with `sanitized_sha256` check; version conflict
- [x] Endpoints: list/detail/steps/original-text/original-pdf/sanitized/delete
- **Done when:** the Detection, Safety, Pipeline and privacy (P1/T5) tests pass on the three sample PDFs; a seeded leak yields BLOCK and a manual mark clears it.

### M5 — LLM layer and results (A06, A05, A07)
- [x] Providers (Gemini, Groq), router with retries/backoff/Retry-After, circuit breaker, validation + repair, fallback, semaphore, per-user limit
- [x] `send` with idempotency and atomic transition; `retry`; `result` (re-hydration); `export` txt/docx
- [x] `scripts/smoke_llm.py` (real call, manual)
- **Done when:** all LLM, Concurrency and Pipeline-failure tests pass; outbound payload test proves no real values leave.

### M6 — Remaining backend features
- [x] Dashboard, documents query (filters/sort/pagination), admin users (restrict/restore/role), complaints (user + admin), analytics, audit filters
- **Done when:** Data, Complaints, Admin tests pass; admin endpoints never expose filenames or text.

### M7 — Backend hardening
- [x] Full test suite green; coverage report; fix every flaw found; review rules.md S1–S13 and P1–P9 one by one
- [x] README draft (setup, env, architecture, limitations)
- **Done when:** `pytest` is green from a fresh DB and the checklist in §6 is satisfied for all backend items.

### M8 — Frontend foundation and public site
- [x] Tokens, base components (design.md §2–3), layouts (public header/footer, app header/footer)
- [x] `lib/api.ts`, auth context, middleware redirects
- [x] Landing, About, FAQ, Login (with Back), Signup, Google button, 404, 403, error boundary, BrandLoader, route progress bar
- **Done when:** public pages match design.md; logged-in users are redirected away from public pages; 404 works for unknown routes.

### M9 — Frontend app
- [x] Doctor: Dashboard, New document (live steps), My documents, Review page (panes, highlight-to-tokenize, safety banner, approve/generate, result, export), Help (form + thread), Profile
- [x] Admin: Overview, Users, Complaints (+thread), Audit logs, Analytics; update animation on every mutation
- [x] Auditor: Audit logs
- **Done when:** a full end-to-end run works in the browser for each role; all states (loading, empty, error) exist; keyboard navigation works.

### M10 — Deploy, docs, demo
- [x] Deploy backend (Docker, one worker) + Postgres + frontend; set env vars; seed; verify live URL
- [x] README final (problem, track, architecture, setup, limitations, A03 + A06 map)
- [x] `scripts/make_sample_pdfs.py` fixtures; demo script (see §7)
- [x] Verify the published build matches the repo; no secrets committed
- **Done when:** the submission checklist in §8 is all ticked.

### Judge-Review Hardening (Phases 1–6)
- [x] Phase 1 — Approved & audited external AI handoff (`POST /api/documents/{id}/handoff`, `DOC_EXTERNAL_HANDOFF`, confirmation modal)
- [x] Phase 2 — Local Bangla identifier detection (digits, labels, titles, Unicode-aware sweep/safety/manual-mark, `tesseract-ocr-ben`, `OCR_LANGS=eng+ben`)
- [x] Phase 3 — Honest privacy & audit copy across landing, About, FAQ, AuthSplitShell, and footers
- [x] Phase 4 — `joggo_session=1` hint cookie (zero logged-out 401s), Google `locale: "en"`, strict page CSP & security headers, full multi-field `VALIDATION_ERROR`, real support email
- [x] Phase 5 — Render 512 MB reliability (RSS logging, singleton NLP, `MALLOC_ARENA_MAX=2`, `PIPELINE_MAX_WORKERS`, 200 DPI cap, `.github/workflows/keepalive.yml`, clear restart vault-loss UX)
- [x] Phase 6 — Docs consistency (`README.md`, `docs/architecture.md`, `docs/brain.md`)

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
- 2026-11-26 — M1 — Added SQLAlchemy 2.0 models for all 9 tables, Alembic initial migration with audit_logs immutability trigger, idempotent scripts/seed.py, backend Dockerfile startup command, and M1 database tests (8/8 passed on fresh Postgres).
- 2026-11-26 — M2 — Added auth (signup, login, lockout, refresh rotation + reuse detection, logout, Google ID token login, /me profile/password/sessions), RBAC dependencies, S7 CSRF enforcement, slowapi rate limiting, hash-chained audit service + /api/audit & /api/audit/verify, and M2 tests (18/18 passed).
- 2026-11-26 — M3 — Added AES-256-GCM in-memory Vault (HKDF, LRU, 20-entry cap, sweeper, startup recovery), atomic state machine, ThreadPoolExecutor jobs, PyMuPDF + Tesseract PDF extraction (annotations, widgets, OCR pages/images, metadata hints), POST /api/documents with all validations and duplicate race handling, scripts/make_sample_pdfs.py, and M3 tests (22/22 passed).
- 2026-11-26 — M4 — Added HIPAA-18 detection suite (regex, labels, titles, facility, dates/ages, Presidio/spaCy, stoplists, metadata hints, literal sweep, overlap resolution), context-preserving tokenizer, safety gate (literal leak + masked re-detection + pattern checks), 4-step resumable pipeline, manual highlight-to-tokenize with If-Match optimistic locking, approval sha256 check, document review endpoints, and M4 tests (26/26 passed).
- 2026-11-26 — M5 — Added Gemini & Groq LLM providers, A06 fault-tolerant router (retries, backoff, Retry-After, circuit breaker, output validation + repair retry, provider fallback, semaphore), idempotent send + retry + local re-hydration + TXT/DOCX export, scripts/smoke_llm.py, and M5 tests (31/31 passed).
- 2026-11-26 — M6 — Added doctor dashboard, documents_query service, user & admin complaints workflow, admin user management (restrict/restore/role + escalation guards + vault wipe), SQL aggregate analytics, and M6 tests (34/34 passed).
- 2026-11-26 — M7 — Added Gemini/Groq HTTP provider tests, session revocation/audit filter/expired-retry hardening tests, completed P1-P9 & S1-S13 audit, updated README.md draft, verified 36/36 tests passing with 91% coverage on fresh PostgreSQL.
- 2026-11-26 — M8 — Built frontend foundation (lib/api.ts, auth context, formatters, middleware redirects, base UI components, BrandLoader, RouteProgressBar, PublicLayout, AppLayout) and public/auth/error pages (Landing, About, FAQ, Login, Signup, Google button, 404, 403, error boundary); verified next build, tsc, lint, and live routes.
- 2026-11-26 — M9 — Built all authenticated frontend pages for Doctor (Dashboard, New Document with live polling, My Documents, 3-pane Review with highlight-to-tokenize & PDF preview, Help + threads), Admin (Overview, Users, Complaints + threads, Analytics, Audit Logs with update animations), Auditor (Audit Logs), and Profile; verified production build, typecheck, lint (0 warnings), and live same-origin E2E flow.
- 2026-11-26 — M10 — Finalized README.md (problem, track, architecture, deploy guide, A03/A06 map, limitations), generated 3 synthetic sample PDF fixtures in backend/tests/fixtures/, verified 0 secrets/TODOs and 36/36 pytest + frontend typecheck/lint green from fresh Docker stack.
- 2026-11-26 — UI/UX Refinements — Updated brand to JOGGO, raised readable body text size (15px), added crisp navbar border + shadow, redesigned Login/Signup 50/50 trust split, added 91-day teal GitHub-style ActivityHeatmap on Dashboard & Admin Analytics, redesigned Document Review to 50/50 split (Left=Modified with red issue lines & prominent Jump button, Right=Original, Generated Draft below) with high-visibility steppers, and added Alembic migration 0002 + editable Profile fields (age, designation, hospital_name, profile picture); 36/36 pytest + frontend build/tsc/lint passed.
- 2026-11-26 — Branding & Footer — Processed uploaded JOGGO logo to transparent PNG (`frontend/public/logo.png`), wired into `Logo`, `BrandLoader`, `AppLayout`, and favicon metadata; added `lib/utils.ts` (`cn`) + Tailwind shadcn color/spacing aliases; integrated `components/ui/modem-animated-footer.tsx` into `PublicLayout` preserving `rules.md P9` synthetic-data notice.
- 2026-11-26 — Clarity, Multi-Format/Camera Upload, Full-Width Activity & Delete Fix — Rewrote public & workspace copy in plain non-technical language; moved full-width `ActivityHeatmap` right above the logged-in `Footer` in `AppLayout` with role-based quick-access links; redesigned Document Review & Generated Draft panes into clean PDF paper-sheet views (removing raw markdown appearance) with PDF/PNG/JPG/SVG original preview; added backend + frontend support for PNG, JPG, and SVG uploads (magic-byte/XXE-safe validation + Pillow OCR + safe XML parsing) plus live camera photo capture on `/documents/new`; fixed icon button layout (`Button.tsx`), CSRF same-origin `Referer` fallback for bodyless `DELETE`, and document deletion flows on `/documents` and `/documents/[id]`; renamed remaining `clinicshield-frontend` package metadata to `joggo-frontend`.
- 2026-11-26 — Landing Problem Focus, Non-Copyable Security Views, Activity Shadows & Responsive Polish — Added dedicated highlighted "The problem JOGGO solves" section to landing page (`frontend/app/page.tsx`); enforced non-copyable protection (`cs-no-copy` CSS, clipboard/context-menu/drag/shortcut blocking, print-hide, `#toolbar=0`) on Original/Cleaned document security views and Audit Logs; added subtle card and cell drop-shadows to `ActivityHeatmap` preserving existing teal/neutral colors; polished phone/tablet/PC breakpoints across layouts, footer, auth split, and PDF review panes.
- 2026-11-26 — Render Deploy Port Fix — Updated `backend/Dockerfile` CMD to bind `--port ${PORT:-8000}` so Render's dynamic `$PORT` works alongside local Docker Compose port `8000`.
- 2026-11-26 — Render + Vercel Deploy Hardening — Auto-normalized `postgres://` and `postgresql://` `DATABASE_URL` strings to `postgresql+psycopg://` in `backend/app/config.py`, and stripped trailing slashes from `BACKEND_URL` in `frontend/next.config.js`.
- 2026-11-26 — Vercel Build Fix — Un-ignored `frontend/lib/` in `.gitignore` (which had been matched by Python's `lib/` rule) and committed missing `frontend/lib/{api.ts,auth.tsx,constants.ts,format.ts,types.ts}` files.
- 2026-11-26 — DNA Helix Loading Transitions — Added `components/ui/loader-helix.tsx` (`variant="dna"`), updated `BrandLoader`, added global `app/loading.tsx`, and upgraded `RouteProgressBar` to show the full-screen DNA helix loading animation on every internal link navigation before the next page renders.
- 2026-11-26 — DNA Helix Timing Fix — Moved helix keyframes into `globals.css`, switched `LoaderHelix` to negative `animationDelay` so the full DNA double-helix wave is immediately in motion at `t=0`, centered dots cleanly, and extended `RouteProgressBar` transition visibility (`750ms` + smooth fade-out) for both link clicks and programmatic route navigations.
- 2026-11-26 — DNA Initial Load Splash — Enabled `RouteProgressBar` DNA Helix overlay on initial website load (`900ms` splash + fade-out) in addition to link and route navigations.
- 2026-11-26 — PDF/PNG/JPG Exports, Runtime Gmail Sign-In & Secret Role Portals — Added ReportLab/PyMuPDF/Pillow `export_pdf`, `export_png`, `export_jpg` on `/api/documents/{id}/export` and Download PDF/PNG/JPG buttons on Generated Draft; added `/api/auth/config` runtime Google Client ID discovery and script-reload fix in `GoogleSignInButton`; added strict backend `portal` role enforcement blocking Admin/Auditor on `/login` and created hidden login portals at `/00admin/00admin` (Admin only) and `/00auditor` (Auditor only).
- 2026-11-26 — Upload Animation & Line-by-Line / Auto-Fix-All Conflict Resolution — Added animated file-upload progress stage (lifting file badge, shimmer progress bar, scan beam, DNA Helix) in `frontend/app/documents/new/page.tsx` and `globals.css`; added inline "Auto-fix line" buttons on every red conflict line and in the safety banner plus an "Auto-fix all" sequential batch button in `frontend/app/documents/[id]/page.tsx`.
- 2026-11-26 — Clickable Problem Words, Conflict Box Buttons & Manual-Mark Bug Fix — Fixed `apply_manual_mark` in `backend/app/services/pipeline.py` so mixed token+text selections strip tokens instead of falsely failing with `MARK_OVERLAPS_TOKEN`, punctuation-bounded words fall back to exact matching, and overlapping manual marks replace older ones cleanly; upgraded `frontend/app/documents/[id]/page.tsx` with explicit "Verdict: Manual resolution required" banner, inline clickable problem-word `<button>` elements inside red lines, full clickable Conflict Box buttons, and immediate progression to "Approve and generate" on PASS.
- 2026-11-26 — LLM Draft Generation Hardening & Diagnostics — Added safe default production model fallbacks (`gemini-2.5-flash` and `llama-3.3-70b-versatile`) in `backend/app/config.py`, `backend/app/services/llm/gemini.py`, `backend/app/services/llm/groq.py`, and `.env.example` so blank or placeholder `*_MODEL` env vars no longer trigger `LLM_AUTH_ERROR`; filtered Gemini thought parts and bumped output token limits; relaxed `validate_llm_output` in `backend/app/services/llm/validate.py` to accept standard Markdown heading variations (`###`, bold, numbered, trailing colon); preserved `LLM_AUTH_ERROR` in `router.py` and added non-PHI provider error logging; updated `frontend/app/documents/[id]/page.tsx` to fetch fresh `sanitized_sha256` before approving and surface actionable `LLM_FAILED` guidance.
- 2026-11-26 — Full-Stack Backend & Frontend Stability Audit Fixes — Fixed `refresh_session` in `backend/app/routers/auth.py` to return a `JSONResponse` with cleared auth cookies on 401 (preventing stale-cookie redirect loops with Next.js middleware); updated `verify_csrf` in `backend/app/deps.py` to support comma-separated `FRONTEND_ORIGIN` values; fixed `extract_image` in `backend/app/services/extraction.py` to read PNG/EXIF metadata hints before image conversion strips them; enhanced `export_docx` & `export_pdf` in `backend/app/services/exporter.py` for `#{1,4}` headings, `**bold**`, and `_italic_`; excluded `/00admin/00admin` and `/00auditor` from `redirectToLogin` in `frontend/lib/api.ts`; moved role redirect in `frontend/components/layout/AppLayout.tsx` into `useEffect`; stabilized `GoogleSignInButton.tsx` callbacks with refs to prevent GSI re-initialization on parent re-renders; improved draft `_italic_` rendering, `retryMutation` refetching, and safe deferred `URL.revokeObjectURL` downloads in `frontend/app/documents/[id]/page.tsx`.
- 2026-11-26 — Self-Healing LLM Auto-Model Discovery & Provider Diagnostics — Added automatic live model discovery on HTTP 404 / model-decommissioned errors in `backend/app/services/llm/gemini.py` and `backend/app/services/llm/groq.py`, increased `DEFAULT_LLM_TIMEOUT` to 45s read / 10s connect in `backend/app/services/llm/base.py`, prevented unconfigured secondary providers from tripping circuit breakers or overwriting primary errors in `router.py`, persisted safe non-PHI provider error summaries on `LLM_CALL` pipeline steps in `pipeline.py`, and surfaced them in `frontend/app/documents/[id]/page.tsx`.
- 2026-11-26 — Comprehensive README, Frontend UX/SEO/Mobile Polish & Image Compression — Rewrote `README.md` with Problem, Solution, Trust Boundaries, Mermaid architecture/pipeline/portal diagrams, Roadmap, Setup, Deployment, and API reference; compressed `frontend/public/logo.png` and generated `favicon.ico`, `app/icon.png`, and `app/apple-icon.png`; added per-route page titles and meta descriptions across all routes; eliminated horizontal scroll with `overflow-x: clip` and responsive mobile tables/cards; upgraded `PublicLayout` and `AppLayout` mobile menus; fixed broken admin filter links (`?status=...` query params in `/admin/users` and `/admin/complaints`); removed footer placeholder defaults, made footer brand & logo clickable, added clickable `mailto:` email links across profile/admin/help/footer, and added success/error feedback toasts across auth, upload, profile, audit verify, and export flows.
- 2026-11-26 — Direct Web AI Text Handoff Buttons (`Take to Gemini`, `Take to ChatGPT`, `Take to Claude`) — Added `frontend/components/documents/SendToAiButtons.tsx` and wired it into `frontend/app/documents/[id]/page.tsx` so clinicians can open a brand-new web session on ChatGPT (`?q=` prefilled), Claude (`/new?q=` prefilled), or Gemini (new session + full text copied to clipboard) using only the safety-checked de-identified text format with zero APIs and zero browser extensions; processed the user-provided Gemini, ChatGPT, and Claude brand logos into crisp transparent 64x64 PNGs (`frontend/public/icons/{gemini,chatgpt,claude}.png`) and added a clear 1.5-second "File copied in text format!" confirmation banner & progress bar before launching the AI tab (with a direct link fallback if pop-ups are paused).
- 2026-11-26 — Dead Code & Leftover Cleanup — Removed stray empty root `package-lock.json`, unused legacy CSS classes/keyframes (`.cs-brand-ring`, `.cs-brand-cross`, `cs-cross-pulse`, `helix-ribbon-gradient`) from `frontend/app/globals.css`, unused template variants/props from `frontend/components/ui/loader-helix.tsx` and `frontend/components/ui/modem-animated-footer.tsx`, and unused imports/helpers from `backend/app/main.py`, `backend/app/routers/documents.py`, and `backend/app/services/jobs.py`.
- 2026-11-26 — Phase 1 (Approved & Audited External AI Handoff, A03/P8) — Documented `DOC_EXTERNAL_HANDOFF` and `/api/documents/{id}/handoff` in `docs/architecture.md`; added `POST /api/documents/{id}/handoff` enforcing `get_owned_document`, `require_active`, `PASS` safety report, allowed status, `sanitized_sha256` freshness, CSRF, 10/min rate limit, and `DOC_EXTERNAL_HANDOFF` audit logging (provider metadata only) with server-built `prompt_text`; updated `frontend/components/documents/SendToAiButtons.tsx` to require confirmation modal + checkbox before calling `/handoff`, removed frontend prompt building, added external placeholder disclaimer, and added full RBAC/privacy tests in `backend/tests/test_m9_judge_review.py`.
- 2026-11-26 — Phase 2 (Local Bangla Identifier Detection & OCR, P5) — Added 1-to-1 Bangla digit (`০–৯`) normalization preserving offsets for phone/NID/MRN/date/age matching; added Bangla clinical labels (`:` and `ঃ` separators), `জন্ম তারিখ` DOB marker, `ভর্তির তারিখ` admission anchor, and Bangla title prefixes (`ডাঃ`/`ডা.`, `জনাব`, `মোঃ`, `মোছাঃ`, `বেগম`, `শ্রী`, `শ্রীমতী`); upgraded literal sweep, safety leak scan, and manual marking to `regex` Unicode-aware word boundaries (`[\p{L}\p{N}\p{M}]`); added `tesseract-ocr-ben` to `backend/Dockerfile` and `OCR_LANGS=eng+ben` defaults; updated `docs/architecture.md` & `README.md`; verified 42/42 pytest passing and peak RSS 226.6 MB with `eng+ben` OCR.
- 2026-11-26 — Phase 3 (Honest Copy, design.md §8) — Replaced absolute privacy and immutability claims across `frontend/app/page.tsx`, `frontend/app/about/page.tsx`, `frontend/app/faq/page.tsx`, `frontend/components/auth/AuthSplitShell.tsx`, and public/app footers with honest review-and-safety-gate wording and "tamper-evident activity history (any change is detected)"; verified 42/42 pytest and frontend typecheck/lint/build green.
- 2026-11-26 — Phase 4 (Frontend Polish & Hardening) — Added non-httpOnly `joggo_session=1` hint cookie (`Path=/`, refresh lifetime) set on signup/login/google/refresh and cleared on logout/refresh-fail/reuse so public pages skip `/api/me` when logged out (zero console 401s); set `locale: "en"` and `?hl=en` on `GoogleSignInButton`; added strict CSP and page security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Strict-Transport-Security`, `Permissions-Policy`) for non-`/api` routes in `frontend/next.config.js`; ensured `VALIDATION_ERROR` reports all invalid field names without values; updated support email to `abdullahshahriar2140@gmail.com`; verified 43/43 pytest and frontend build/typecheck/lint green.
- 2026-11-26 — Phase 5 (Render 512 MB Reliability, Keep-Alive & Restart UX) — Added zero-PHI process RSS logging (`backend/app/services/memory.py`) at startup, after singleton spaCy/Presidio load, and after pipeline runs; confirmed singleton NLP loading (`_load_count == 1`), set `MALLOC_ARENA_MAX=2` in `backend/Dockerfile`, added `PIPELINE_MAX_WORKERS` env cap (default 2 in prod, 4 in dev), and enforced `MAX_OCR_DPI = 200`; measured live backend RSS: 204.0 MB startup, 267.1 MB after Presidio/spaCy, 279.4 / 279.5 / 295.5 MB across the 3 sample PDFs; added `.github/workflows/keepalive.yml` (10-min cron ping to `https://joggo-nine.vercel.app/api/health`); updated review page and documents list vault-loss copy to "The server restarted, so original details were cleared. Upload the file again."; verified 44/44 pytest (90% coverage) and frontend build/typecheck/lint green.
- 2026-11-26 — Phase 6 (Docs Consistency) — Updated `README.md` with real test count/coverage (44/44 tests, 90% coverage), "separate role portals; access is enforced on the server" wording for `/00admin/00admin` and `/00auditor`, `POST /api/documents/{id}/handoff`, `DOC_EXTERNAL_HANDOFF`, Bangla support, `PIPELINE_MAX_WORKERS`, and `.github/workflows/keepalive.yml`; aligned `docs/architecture.md` (§2, §4, §12, §16, §17, §20, §25) and `docs/brain.md` checklists & status.
