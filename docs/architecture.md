# architecture.md — Full technical specification

Working name: `ClinicShield` (placeholder; set via `APP_NAME` env / one constant in the frontend).
Track: **World Problem Solver** (health safety). Declared advanced challenges: **A03** and **A06**. Also built (not declared): A07, A05, A02, A08.

---

## 1. System overview

```
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

Trust zones: Browser + Backend + Vault = trusted. PostgreSQL = holds no real identifiers. LLM provider = untrusted, sees tokens only.

## 2. Tech stack (exact)

Backend: Python 3.11, FastAPI, Uvicorn (1 worker), SQLAlchemy 2.0 (sync), psycopg 3, Alembic, Pydantic v2 + pydantic-settings, `python-multipart`, `argon2-cffi`, `PyJWT`, `google-auth`, `slowapi`, `httpx`, `cryptography`, `PyMuPDF`, `pytesseract` + system `tesseract-ocr`, `Pillow`, `presidio-analyzer`, `spacy` + model `en_core_web_sm` (configurable via `SPACY_MODEL`), `regex`, `python-dateutil`, `pycountry`, `python-docx`, `reportlab` (sample PDFs only), `pytest`, `pytest-cov`.
Frontend: Next.js 14 (App Router), TypeScript strict, Tailwind CSS, TanStack Query, react-hook-form + zod, `lucide-react`.
DB: PostgreSQL 15+. Infra: Docker, docker-compose (dev), Render (backend + Postgres) or equivalent, Vercel (frontend).

## 3. Repo structure

```
/
  README.md
  docker-compose.yml
  .env.example
  docs/                brain.md architecture.md design.md rules.md
  scripts/             make_sample_pdfs.py  seed.py  smoke_llm.py
  backend/
    Dockerfile  requirements.txt  alembic.ini  alembic/versions/
    app/
      main.py  config.py  db.py  deps.py  security.py  errors.py  logging.py  ratelimit.py
      models/      user.py session.py document.py entity.py step.py llm_request.py audit.py complaint.py
      schemas/     auth.py user.py document.py complaint.py admin.py common.py
      routers/     auth.py me.py documents.py dashboard.py complaints.py admin.py audit.py health.py
      services/
        audit.py  state.py  vault.py  pipeline.py  jobs.py  documents_query.py  analytics.py  complaints.py
        extraction.py
        detection/  base.py  regex_rules.py  labels.py  presidio_engine.py  dates.py  stoplists.py  resolve.py
        tokenizer.py  safety.py  rehydrate.py  exporter.py
        llm/  base.py  gemini.py  groq.py  router.py  breaker.py  prompts.py  validate.py
    tests/  conftest.py  fixtures/  test_*.py
  frontend/
    next.config.js (rewrites /api → BACKEND_URL)  middleware.ts
    app/ …  components/ …  lib/api.ts  lib/auth.ts  lib/format.ts
```

## 4. Environment variables (`.env.example`)

```
APP_NAME=ClinicShield
ENV=dev|prod
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db
JWT_SECRET=change-me-32+chars
FRONTEND_ORIGIN=http://localhost:3000
BACKEND_URL=http://localhost:8000          # used by Next.js rewrites
GOOGLE_CLIENT_ID=
GEMINI_API_KEY=
GEMINI_MODEL=<set to a current Gemini Flash-class model id from Google AI Studio docs>
GROQ_API_KEY=
GROQ_MODEL=<set to a current Groq-hosted instruct model id from Groq docs>
LLM_PROVIDER_ORDER=gemini,groq
SPACY_MODEL=en_core_web_sm
OCR_LANGS=eng
DATE_ORDER=DMY
MAX_UPLOAD_MB=10
MAX_PDF_PAGES=30
VAULT_IDLE_MINUTES=30
VAULT_ABSOLUTE_HOURS=8
VAULT_MAX_MB=300
ADMIN_SEED_EMAIL=  ADMIN_SEED_PASSWORD=   AUDITOR_SEED_EMAIL=  AUDITOR_SEED_PASSWORD=  DOCTOR_SEED_EMAIL=  DOCTOR_SEED_PASSWORD=
```
Model ids change over time: verify them in the provider docs at build time; never hard-code them.

## 5. Data model (PostgreSQL)

All ids are UUID (`gen_random_uuid()`), timestamps `timestamptz` UTC.

**users**: id, email (unique, stored lowercase), password_hash (nullable), google_sub (unique, nullable), full_name, role enum(`doctor`,`admin`,`auditor`), status enum(`active`,`restricted`), restricted_reason, restricted_at, failed_login_count int default 0, locked_until, token_version int default 0, created_at, last_login_at. Check: password_hash OR google_sub not null.

**sessions** (refresh tokens): id, user_id FK, family_id uuid, token_hash (unique), expires_at, revoked_at, replaced_by_id, user_agent, ip, created_at, last_used_at. Index (user_id), (family_id).

**documents**: id, owner_id FK users, original_filename, file_sha256, size_bytes, page_count, task_type enum(`discharge_summary`,`case_summary`,`treatment_plan`), status enum (see §9), failure_code, sanitized_text (nullable until safety PASS), entity_summary jsonb (counts by type), safety_report jsonb (status + findings with offsets/types, no values), llm_response_tokenized text, llm_provider_used, approved_at, vault_expired bool default false, version int default 1, created_at, updated_at, completed_at. **Unique (owner_id, file_sha256)**. Index (owner_id, created_at desc), (owner_id, status).

**document_entities**: id, document_id FK (cascade), token, entity_type, source enum(`auto`,`manual`,`metadata`,`sweep`), detector, rule_id, reason (human-readable "why", e.g. "Label 'Patient Name:' + value"), score numeric, occurrences int. **No real values.** Unique (document_id, token).

**pipeline_steps**: id, document_id FK (cascade), step enum(`EXTRACT`,`DETECT`,`TOKENIZE`,`SAFETY_CHECK`,`LLM_CALL`,`REHYDRATE`), status enum(`pending`,`running`,`succeeded`,`failed`,`skipped`), attempts int, error_code, error_message (safe text), started_at, finished_at. Unique (document_id, step).

**llm_requests**: id, document_id FK (cascade), idempotency_key text, provider, model, status enum(`running`,`succeeded`,`failed`), attempts int, latency_ms, error_code, created_at. **Unique (document_id, idempotency_key)**.

**audit_logs**: id bigserial, ts, actor_id (nullable), actor_role, action text, resource_type, resource_id, outcome enum(`allowed`,`denied`,`error`), ip, metadata jsonb (no PHI), prev_hash, hash. Trigger blocks UPDATE/DELETE. Index (ts desc), (actor_id), (action).

**complaints**: id, user_id FK, subject (3–120), category enum(`bug`,`account`,`privacy`,`other`), message (10–4000), document_id (nullable; must belong to the user at creation), status enum(`open`,`in_progress`,`resolved`), created_at, updated_at, resolved_at.
**complaint_messages**: id, complaint_id FK, author_id FK, author_role, body (1–4000), created_at.

Delete rules: deleting a document cascades entities, steps, llm_requests. Users are never deleted. Audit logs are never deleted.

## 6. Authentication and sessions

- **Signup** `POST /api/auth/signup` {email, password, full_name} → role `doctor`, status `active`. Duplicate email → 409 `EMAIL_TAKEN`.
- **Login** `POST /api/auth/login` {email, password}: check lock → verify argon2 → reset counter → create session family → set cookies `access_token` (path `/`, 15 min) and `refresh_token` (path `/api/auth`, 7 days). Failed: increment counter; at 5 set `locked_until = now+15min` (423 `ACCOUNT_LOCKED`). Always constant-ish time (verify a dummy hash for unknown emails).
- **Google** `POST /api/auth/google` {credential}: verify ID token with `google.oauth2.id_token.verify_oauth2_token` (audience = `GOOGLE_CLIENT_ID`); require `email_verified`. Existing email → link `google_sub` (if not already linked to another sub); else create doctor. Frontend uses Google Identity Services button on `/login` and `/signup`.
- **Refresh** `POST /api/auth/refresh`: look up hash; if revoked → revoke family, audit `AUTH_REFRESH_REUSE_DETECTED`, wipe the family's vault, 401. Otherwise rotate (new token, mark old revoked, `replaced_by`).
- **Logout** `POST /api/auth/logout`: revoke family, **wipe vault for that `sid`**, clear cookies.
- **JWT claims**: `sub`, `sid` (session family id), `tv` (token_version), `exp`. On every request the dependency loads the user and rejects if `tv` mismatch, user missing, or session family revoked.
- Role change, restriction (for Vault only), or password change → `token_version += 1` and revoke sessions where needed (role change and password change revoke all sessions; restriction does not).
- **Me** `GET /api/me`, `PATCH /api/me` {full_name}, `POST /api/me/password` {current, new} (not for Google-only accounts: 400 `NO_PASSWORD_SET`), `GET /api/me/sessions`, `DELETE /api/me/sessions/{id}`.

## 7. Authorization matrix

| Capability | doctor | auditor | admin | restricted doctor |
|---|---|---|---|---|
| Own profile, sessions | ✔ | ✔ | ✔ | ✔ |
| Help / complaints (own) | ✔ | ✔ | — | ✔ |
| Upload / process / send own documents | ✔ | ✗ | ✗ | ✗ (`ACCOUNT_RESTRICTED`) |
| Read any document content or filename | owner only | ✗ | ✗ | ✗ |
| Dashboard | ✔ | ✗ | ✗ | ✗ |
| Audit logs (no PHI) | ✗ | ✔ read-only | ✔ | ✗ |
| Users management | ✗ | ✗ | ✔ | ✗ |
| Complaints inbox | ✗ | ✗ | ✔ | ✗ |
| Analytics (aggregates) | ✗ | ✗ | ✔ | ✗ |

Dependencies: `current_user`, `require_active` (blocks restricted), `require_role(*roles)`, `get_owned_document(id)` (owner-only; others → 404 + audit; admin/auditor → 403 `ADMIN_NO_DOCUMENT_ACCESS` + audit). Admin rules: cannot act on own account, cannot act on other admins, role changes only doctor↔auditor.

## 8. Vault (ephemeral encrypted store)

`services/vault.py`, process-wide singleton, thread-safe (`threading.RLock`).
- Key: `(sid, document_id)` → `VaultEntry{nonce, ciphertext, created_at, last_access, size}`.
- Payload (JSON, encrypted with AES-256-GCM): `original_text`, `original_pdf_b64`, `sanitized_text`, `mapping {token: display_value}`, `entities [{start,end,type,token,source,rule}]` (offsets on original), `anchor_date`, `name_components`, `metadata_hints`.
- Key derivation: random 32-byte master key at process start (`os.urandom`), per-entry key = HKDF-SHA256(master, info=`sid|document_id`).
- API: `put`, `get` (updates `last_access`), `update`, `wipe(sid, doc_id)`, `wipe_session(sid)`, `wipe_document(doc_id)`, `wipe_user(user_id)`, `stats()`.
- Wipe triggers: logout, refresh-reuse detection, idle > `VAULT_IDLE_MINUTES`, age > `VAULT_ABSOLUTE_HOURS`, document delete, user restricted, total size > `VAULT_MAX_MB` (evict least-recently-used), process restart (memory is gone).
- After any wipe set `documents.vault_expired = true` for affected documents (batch update).
- Sweeper: daemon thread every 60 s.
- Startup routine: `vault_expired = true` for all documents; documents in `PROCESSING` → `FAILED` (`SERVER_RESTART`); documents in `SENDING` → `LLM_FAILED` (`SERVER_RESTART`) (retry works from DB sanitized text).
- Python cannot reliably zeroize memory; this is best effort. State it in the README limitations.
- Per-session cap: 20 vault entries.

## 9. Document status and state machine

Statuses: `UPLOADED`, `PROCESSING`, `BLOCKED`, `REVIEW_REQUIRED`, `APPROVED`, `SENDING`, `COMPLETED`, `LLM_FAILED`, `FAILED`.

| From | To | Trigger | Guard |
|---|---|---|---|
| (new) | UPLOADED | upload accepted | file valid, not duplicate |
| UPLOADED | PROCESSING | job starts | — |
| PROCESSING | REVIEW_REQUIRED | all pipeline steps ok | safety PASS |
| PROCESSING | BLOCKED | safety scan finds residual identifiers | — |
| PROCESSING | FAILED | step error | failure_code set |
| BLOCKED | PROCESSING→REVIEW_REQUIRED | manual mark + re-scan | vault alive; ends PASS → REVIEW_REQUIRED else BLOCKED |
| REVIEW_REQUIRED | REVIEW_REQUIRED / BLOCKED | manual mark | resets `approved_at` |
| REVIEW_REQUIRED | APPROVED | doctor approves | safety PASS, owner, active |
| APPROVED | SENDING | send | atomic conditional update |
| SENDING | COMPLETED | LLM output valid | — |
| SENDING | LLM_FAILED | all providers failed | — |
| LLM_FAILED | SENDING | retry | idempotency key new |
| FAILED | PROCESSING | retry | vault alive, else `VAULT_EXPIRED` |
| any non-terminal | FAILED | user restricted | code `ACCOUNT_RESTRICTED` |

Any other transition → 409 `INVALID_STATE`. `transition(doc_id, expected_from: set, to, **fields)` = `UPDATE documents SET status=:to, version=version+1, … WHERE id=:id AND status IN :expected` → if rowcount 0 raise 409.

## 10. Pipeline

Orchestrator `services/pipeline.py` runs in the `ThreadPoolExecutor` (max 4 workers). Each step: set step row `running` → execute → `succeeded` / `failed` (with error_code). Steps are idempotent. "Resume" = skip succeeded steps whose outputs are still in the Vault.

1. **EXTRACT** (needs upload bytes) 2. **DETECT** 3. **TOKENIZE** 4. **SAFETY_CHECK** → status becomes `REVIEW_REQUIRED` or `BLOCKED`.
Later (after approval): 5. **LLM_CALL** 6. **REHYDRATE** (on demand at `GET /result`; step row is marked succeeded when first served).

Upload endpoint flow (`POST /api/documents`, multipart `file`, `task_type`):
1. `require_active`, rate limit.
2. Validate: size ≤ `MAX_UPLOAD_MB` (413 `FILE_TOO_LARGE`), magic bytes `%PDF-` (415 `NOT_A_PDF`), open with PyMuPDF (corrupt → 422 `PDF_CORRUPT`), encrypted/password-protected (422 `PDF_ENCRYPTED`), pages ≤ `MAX_PDF_PAGES` (422 `TOO_MANY_PAGES`), ≥1 page.
3. Compute SHA-256. If `(owner, sha)` exists → 409 `DUPLICATE_DOCUMENT` with `{existing_document_id}`.
4. Insert document `UPLOADED` (filename sanitized: basename, max 200 chars) + step rows `pending`. Put bytes in Vault. Audit `DOC_UPLOAD`. Submit job. Return 202 `{id, status}`.
5. Frontend polls `GET /api/documents/{id}` every 1.5 s until status leaves `UPLOADED/PROCESSING`.

## 11. Extraction spec (`services/extraction.py`)

Open from bytes (`pymupdf.open(stream=..., filetype="pdf")`). Per page:
- `page.get_text("text", sort=True)` (includes headers/footers).
- Annotations (`page.annots()` contents/titles) and form widgets (`page.widgets()` values) → appended as lines.
- If page text < 40 chars → render at 200 DPI → Tesseract (`OCR_LANGS`), page timeout 20 s.
- Embedded images ≥ 100×100 px → OCR each (skip on timeout, continue); append as `\n[IMAGE_TEXT p{n}]\n{text}\n`.
- Collect metadata hints: `doc.metadata["author"]` and XMP creator (`doc.get_xml_metadata()` → `dc:creator`). Ignore producer/creator/title/dates. Use hints only as literal-search terms in DETECT (≥4 chars, not in software-name ignore list).
- Embedded files, JavaScript, XFA are ignored. Output is **text only**; no PDF is ever forwarded or re-saved, so metadata cannot leak by construction.
- Normalize: `\r\n`→`\n`, collapse >2 blank lines, NFC unicode, keep line structure (tables stay line-oriented).
- If total text < 20 chars after OCR → fail step `EMPTY_DOCUMENT`.
- Whole-document timeout 120 s → `EXTRACTION_TIMEOUT`. Run OCR in the worker thread (never in the request thread).

## 12. Detection spec (`services/detection/`)

Every detector returns `Span(start, end, type, score, detector, rule_id, reason)` on the **original text**. Types: `PATIENT, DOCTOR, PERSON, PHONE, EMAIL, ID, MRN, LOCATION, FACILITY, URL, IP, DOB, DATE, AGE90, OTHER`.

HIPAA 18 coverage map:
| HIPAA identifier | Handled by |
|---|---|
| Names | label rules, title prefix rules, spaCy PERSON (via Presidio), literal sweep |
| Geographic < state | label rules (Address, Village, Thana, District, Road, House), spaCy GPE/LOC/FAC (countries kept via `pycountry`), facility regex |
| Dates (except year) | date detector → `[DAY_n]`; DOB → `Age N`; ages ≥ 90 → `90+` |
| Phone / Fax | BD mobile regex, international regex, label-context landline |
| Email | regex |
| SSN / national ID | NID rules (label + 10/13/17 digits) |
| Medical record numbers | label rules (MRN, UHID, Hospital No, Registration No, Patient ID, Case/File No, Accession/Lab No) |
| Health plan / account / license / certificate numbers | label rules → `ID` |
| Vehicle / device identifiers, serials | label rules (Plate, VIN, Serial, S/N, Device ID, IMEI) → `ID` |
| URLs / IPs | regex |
| Biometric / photos | never forwarded (text only); OCR text of images is scanned like all text |
| Any other unique identifier | manual marking + safety scan |

**Detectors** (run all, then resolve):
1. `regex_rules.py` — Email; URL; IPv4; BD mobile `(?<!\d)(?:\+?88[\s-]?)?01[3-9][\s-]?\d{2}[\s-]?\d{6}(?!\d)`; international phone `(?<!\w)\+\d{1,3}[\s-]?\(?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4}(?!\d)`; NID standalone 13 or 17 digits (score 0.6, not adjacent to `.`/units); labelled 10/13/17 digits (score 0.95).
2. `labels.py` — "key: value" rules. Key list per type; value = rest of line (stop at `|` or 3+ spaces; max 80 chars; must contain a letter or digit). Keys: **PATIENT** (`Patient Name`, `Name of Patient`, `Pt Name`, and bare `Name` only at line start); **DOCTOR** (`Consultant`, `Doctor`, `Physician`, `Attending`, `Surgeon`, `Referred by`, `Signed by`, `Reported by`, `Verified by`, `Pathologist`, `Technologist`); **PERSON** (`Father's Name`, `Mother's Name`, `Spouse`, `Husband`, `Wife`, `Guardian`, `Next of Kin`, `Informant`, `Relative`); **MRN** (`MRN`, `UHID`, `Hospital No`, `Registration No`, `Reg No`, `Patient ID`, `Case No`, `File No`, `Visit No`, `Accession No`, `Lab ID`, `Lab No`); **ID** (`NID`, `National ID`, `NIN`, `Passport`, `License No`, `Policy No`, `Insurance ID`, `Member ID`, `Account No`, `Card No`, `Serial`, `S/N`, `Device ID`, `IMEI`, `VIN`, `Plate`); **PHONE** (`Tel`, `Phone`, `Mobile`, `Cell`, `Contact`, `Fax`); **LOCATION** (`Address`, `Permanent Address`, `Present Address`, `Residence`, `Village`, `Thana`, `Upazila`, `District`, `Postal Code`, `ZIP`); **EMAIL**. Bare-`Name` rule excludes lines starting with `Test Name`, `Drug Name`, `Medicine Name`, `Generic Name`, `Brand Name`. Address values also take one continuation line if it has no `:` and is < 80 chars.
   Title prefixes (use `regex`, Unicode letters): `Dr`, `Prof`, `Professor` + 1–4 capitalized words → `DOCTOR`; `Mr`, `Mrs`, `Ms`, `Md`, `Mst` + 1–4 capitalized words → `PERSON`.
   Facility regex: capitalized words (1–6) followed by `Hospital|Clinic|Medical College|Diagnostic|Laboratory|Lab|Health Centre|Health Center|Institute` → `FACILITY`.
3. `presidio_engine.py` — Presidio `AnalyzerEngine` with the spaCy NLP engine, entities `PERSON, LOCATION (GPE/LOC/FAC), EMAIL_ADDRESS, PHONE_NUMBER, URL, IP_ADDRESS`; `score_threshold=0.4`. Filters: reject PERSON spans that are a single token (unless matching a known name component via sweep), reject spans where any token is in `stoplists.py::MEDICAL_TERMS` (drugs, diseases, eponyms, lab names), reject GPE that is a country (`pycountry`). Medical-unit guard: never treat numbers followed within 3 chars by a unit (`mg|ml|mmol|g/dL|mg/dL|U/L|%|mmHg|bpm|cm|kg|IU|µg|ng`) as ID/phone.
4. `dates.py` — date candidates (numeric `d/m/y`, `y-m-d`, `12 Oct 2024`, `Oct 12, 2024`, `12 Oct` without year). Parse with `dateutil` (`dayfirst = DATE_ORDER=="DMY"`); two-digit year pivot: ≤ current yy → 20yy else 19yy. Invalid but date-shaped → token `[DAY_?]` kept as DATE span with `unparsed=True`. DOB = date within 25 chars after `DOB|D.O.B|Date of Birth|Born|Birth Date`.
   Also explicit ages ≥ 90: `\b(9\d|1[0-4]\d)\s*(?:y(?:ea)?rs?|y/o|yo|years?)\b` → `AGE90` → replaced by `90+ years`.
5. `metadata hints` — literal search of the hint strings in the body (source `metadata`, type `OTHER`).
6. **Literal sweep** (after the first resolve): for every PATIENT/DOCTOR/PERSON value, search each name component (≥3 chars, not in `MEDICAL_TERMS` or common-word list) case-insensitively with word boundaries; and every other entity value as an exact literal. New spans: source `sweep`, same token as the parent entity.

**Resolve overlaps** (`resolve.py`): priority MRN/ID/PHONE/EMAIL/URL/IP (90) > DOB/DATE/AGE90 (70) > PATIENT/DOCTOR/PERSON (50) > LOCATION/FACILITY (30) > OTHER (20). Sort by (start, -len). On overlap keep the higher priority; tie → higher score; tie → longer. Deterministic and stable.

**Explainability (A02)**: each entity row stores `rule_id` + `reason`; UI shows "Why was this replaced?" per token.

## 13. Tokenization / pseudonymization (`tokenizer.py`)

Token formats: `[PATIENT_A]` (A,B,…,Z,AA…), `[DOCTOR_1]`, `[PERSON_1]`, `[PHONE_1]`, `[EMAIL_1]`, `[ID_1]`, `[MRN_1]`, `[LOCATION_1]`, `[FACILITY_1]`, `[URL_1]`, `[IP_1]`, `[OTHER_1]`, `[DAY_n]`/`[DAY_-n]`/`[DAY_?]`.
Same normalized value → same token. Normalize: casefold, collapse whitespace, strip edge punctuation; phones → digits only; IDs → alphanumerics only.
Numbering is by first occurrence order in the text.

Date/age rules:
- **Anchor date** priority: (1) value after `Admission|Admitted|DOA|Date of Admission`; (2) after `Date of (Report|Collection|Sample|Service|Visit)`; (3) the earliest non-DOB date. Anchor lives only in the Vault.
- Date → `[DAY_n]`, n = (date − anchor) in days (`[DAY_0]` = anchor; negative allowed). The Vault maps each DAY token to the display text of its first occurrence.
- DOB → `Age N` where N = full years between DOB and anchor (if no anchor: today's date in UTC). Age > 89 → `Age 90+`. Mapping row `AGE_CALC` (no value needed). A DOB with no parseable date → `[DAY_?]`.
- Year-only mentions (e.g., "in 2019") are kept.
- Clinical lab values, doses, vitals are never touched.

Render: build sanitized text from original + resolved spans (single pass, right-to-left replacement by offsets). Save entity rows (no values), `entity_summary`, and mapping in Vault.

## 14. Safety scan (`safety.py`) — the gate

Run on the sanitized text. PASS only if **all** checks are clean:
1. **Literal leak check**: every Vault value (and each name component ≥3 chars) not found, case-insensitive.
2. **Re-detection**: run detectors 1–4 again on the sanitized text with token patterns masked; any span with score ≥ 0.5 = finding.
3. **Pattern checks**: no email, no URL, no IPv4, no run of 10+ digits, no full date pattern, no phone pattern.
4. **Sanity**: length ≥ 20, token count > 0 or (zero entities and a warning `NO_ENTITIES_FOUND` shown to the doctor).
Result stored in `safety_report`: `{status:"PASS|BLOCK", findings:[{type, reason, start, end}], checked_at}` — offsets and types only, never values. The API returns snippets only from the Vault-backed sanitized text to the owner.
BLOCK → status `BLOCKED`, `sanitized_text` stays out of the DB (P4).
PASS → persist `sanitized_text` to DB, status `REVIEW_REQUIRED`.

## 15. Manual marking

`POST /api/documents/{id}/manual-marks` `{text, entity_type}` (type ∈ PATIENT, DOCTOR, PERSON, PHONE, EMAIL, ID, MRN, LOCATION, FACILITY, OTHER).
1. Doc must be `BLOCKED` or `REVIEW_REQUIRED`; Vault alive (else 409 `VAULT_EXPIRED`).
2. Validate `text`: 2–200 chars, appears in the current sanitized text, contains no token pattern (else 422 `MARK_OVERLAPS_TOKEN`), not empty/whitespace.
3. Find all case-insensitive occurrences in the **original** text (word-boundary unless the text contains digits). None → 422 `MARK_NOT_FOUND`.
4. Add entities (source `manual`, rule `manual.user`), re-render, re-run the safety scan, update Vault and DB, reset `approved_at`, status → `REVIEW_REQUIRED` or `BLOCKED`. Audit `DOC_MANUAL_MARK` (type + occurrence count only).
Out of scope: un-marking a detected token.

## 16. LLM layer (A06)

Interface `LLMProvider.generate(system: str, user: str, *, timeout) -> LLMResult(text, model, latency_ms)`. Providers use `httpx.Client` with explicit timeouts (connect 5 s, read 30 s, total 45 s):
- **Gemini**: REST `generateContent` on `generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}`, key in `x-goog-api-key` header.
- **Groq**: OpenAI-compatible `POST https://api.groq.com/openai/v1/chat/completions`, `Authorization: Bearer`.
Both: temperature 0.2, `max output ≈ 2000 tokens`. If a provider's API shape differs from the above at build time, follow the current official docs and keep the interface unchanged.

`router.py` policy per `send`:
1. Providers in `LLM_PROVIDER_ORDER`. Skip any whose **circuit breaker** is open.
2. Per provider: up to **3 attempts**, exponential backoff 1 s, 2 s, 4 s + jitter (0–300 ms); honor `Retry-After` (cap 10 s). Retry on timeouts, connection errors, 429, 5xx. No retry on 400/401/403 (→ `LLM_AUTH_ERROR`, move on to the next provider).
3. **Circuit breaker** per provider: 5 consecutive failures within 60 s → open for 30 s → half-open (one trial).
4. **Output validation** (`validate.py`): non-empty, ≤ 20 000 chars, valid UTF-8, contains all required headings for the task (case-insensitive `## Heading`), no placeholder like "I cannot". On failure: one "repair" retry on the same provider (user message gets an extra line: "Return only the required Markdown headings"), then next provider.
5. All providers failed → status `LLM_FAILED`, `failure_code` = `LLM_UNAVAILABLE` / `LLM_TIMEOUT` / `LLM_MALFORMED_RESPONSE`. Nothing partial is stored. Doctor can press Retry.
6. Concurrency: global `threading.Semaphore(4)` for LLM calls; per-user limit 10/min (429 `RATE_LIMITED`).
7. Every attempt is recorded (provider, attempts, latency, error_code) in `llm_requests`; fallback use writes audit `DOC_LLM_FALLBACK`.
8. Payload sent: only the static system prompt + task instructions + `sanitized_text`. A unit test asserts no real value, filename, email, or id is in the outbound body.

Prompts (`prompts.py`):
- System: "You are a clinical documentation assistant. The text contains placeholders such as [PATIENT_A], [DOCTOR_1], [DAY_3]. Copy placeholders exactly as written. Never guess or invent identities, dates or numbers. [DAY_0] is the admission or first recorded date; [DAY_n] means n days after it. Write only what the text supports; write 'Not documented' otherwise. Output Markdown with exactly these headings."
- `discharge_summary`: `## Diagnosis`, `## Clinical course`, `## Key findings`, `## Medications at discharge`, `## Follow-up`.
- `case_summary`: `## Summary`, `## Key findings`, `## Concerns`.
- `treatment_plan`: `## Assessment`, `## Plan`, `## Monitoring`, `## Follow-up`.
The backend appends (not the LLM): "_AI-generated draft. Must be reviewed by a licensed clinician before use._"

## 17. Send, idempotency and concurrency (A05)

`POST /api/documents/{id}/send` with header `Idempotency-Key` (client-generated UUID; missing → 400 `IDEMPOTENCY_KEY_REQUIRED`).
In one transaction: `SELECT … FOR UPDATE` the document → if an `llm_requests` row with `(document_id, key)` exists → return it (200, same result, no new call) → else `transition(APPROVED → SENDING)` (atomic conditional update; a concurrent second request gets 409 `INVALID_STATE`) → insert `llm_requests(running)` → commit → submit job.
Retry (`POST …/retry`) from `LLM_FAILED` uses a fresh server-generated key. Retry from `FAILED` resumes the pipeline from the first non-succeeded step (needs Vault, else 409 `VAULT_EXPIRED`).
Approve: `REVIEW_REQUIRED → APPROVED` only if `safety_report.status == "PASS"` and the doctor's current sanitized-text hash equals the hash shown (client sends `sanitized_sha256`; mismatch → 409 `STALE_REVIEW`). This makes the approval apply to exactly what was reviewed.
Optimistic concurrency: `documents.version` increments on every change; manual mark requires `If-Match: <version>` (mismatch → 409 `VERSION_CONFLICT`).
Required concurrency tests: two simultaneous `send` → exactly one provider call; two simultaneous manual marks → no lost update; two simultaneous uploads of the same file → exactly one document (unique constraint → 409 `DUPLICATE_DOCUMENT`).

## 18. Re-hydration and export (`rehydrate.py`, `exporter.py`)

`GET /api/documents/{id}/result` (owner, status `COMPLETED`): get `llm_response_tokenized` from DB; if Vault alive → replace tokens using the Vault mapping; matching is case-insensitive on `[TYPE_ID]` and also bare `TYPE_ID` when the LLM dropped the brackets (word boundaries). Unknown tokens stay as written, plus a `warnings:[{code:"UNKNOWN_TOKEN", token}]`. Vault gone → return tokenized text with `rehydrated:false` and `vault_expired:true`. The re-hydrated text is **never stored**.
`GET /api/documents/{id}/export?format=txt|docx` → re-hydrated when possible (audit `DOC_EXPORT`, format only). `python-docx` for docx; headers/footers empty; filename `summary-{short_id}.{ext}`.

## 19. Error code catalog (HTTP status in parentheses)

Auth: `INVALID_CREDENTIALS`(401) `ACCOUNT_LOCKED`(423) `EMAIL_TAKEN`(409) `WEAK_PASSWORD`(422) `UNAUTHENTICATED`(401) `TOKEN_EXPIRED`(401) `SESSION_REVOKED`(401) `GOOGLE_TOKEN_INVALID`(401) `NO_PASSWORD_SET`(400) `CSRF_REJECTED`(403)
Access: `FORBIDDEN`(403) `ACCOUNT_RESTRICTED`(403) `ADMIN_NO_DOCUMENT_ACCESS`(403) `NOT_FOUND`(404)
Validation: `VALIDATION_ERROR`(422) `IDEMPOTENCY_KEY_REQUIRED`(400) `RATE_LIMITED`(429)
Upload: `FILE_TOO_LARGE`(413) `NOT_A_PDF`(415) `PDF_CORRUPT`(422) `PDF_ENCRYPTED`(422) `TOO_MANY_PAGES`(422) `EMPTY_DOCUMENT`(422) `DUPLICATE_DOCUMENT`(409)
Pipeline: `EXTRACTION_TIMEOUT` `OCR_FAILED` `DETECTION_FAILED` `SAFETY_BLOCKED` `SERVER_RESTART` (stored as failure_code; HTTP not applicable) `INVALID_STATE`(409) `VAULT_EXPIRED`(409) `STALE_REVIEW`(409) `VERSION_CONFLICT`(409) `MARK_NOT_FOUND`(422) `MARK_OVERLAPS_TOKEN`(422)
LLM: `LLM_UNAVAILABLE` `LLM_TIMEOUT` `LLM_MALFORMED_RESPONSE` `LLM_AUTH_ERROR` (stored as failure_code)
Admin: `CANNOT_MODIFY_SELF`(400) `CANNOT_MODIFY_ADMIN`(403) `INVALID_ROLE_CHANGE`(400)
Complaints: `COMPLAINT_CLOSED`(409) `INVALID_COMPLAINT_TRANSITION`(409)
Fallback: `INTERNAL_ERROR`(500) (generic message; details only in server log with `request_id`).

## 20. Audit log (A03)

`audit.record(action, resource_type, resource_id, outcome, actor, metadata)` called inside the same transaction. Hash chain: `hash = sha256(prev_hash || canonical_json(row_without_hash))`; inserts serialized with `pg_advisory_xact_lock(7001)`. `GET /api/audit/verify` (admin) recomputes the chain and returns `{ok, checked, first_broken_id}`.
Actions: `AUTH_SIGNUP AUTH_LOGIN_SUCCESS AUTH_LOGIN_FAILED AUTH_LOCKED AUTH_LOGOUT AUTH_REFRESH_REUSE_DETECTED AUTH_GOOGLE_LOGIN PASSWORD_CHANGED DOC_UPLOAD DOC_DUPLICATE DOC_PIPELINE_COMPLETED DOC_PIPELINE_FAILED DOC_SAFETY_BLOCK DOC_MANUAL_MARK DOC_APPROVE DOC_SEND DOC_LLM_FALLBACK DOC_COMPLETE DOC_EXPORT DOC_DELETE DOC_ACCESS_DENIED ADMIN_DOC_ACCESS_DENIED VAULT_WIPE USER_RESTRICT USER_RESTORE USER_ROLE_CHANGE COMPLAINT_CREATE COMPLAINT_REPLY COMPLAINT_STATUS`.
Metadata never contains values, filenames or text; only types, counts, codes, short ids.

## 21. Dynamic data (M05, A08-lite)

- `GET /api/documents?q=&status=&task_type=&date_from=&date_to=&sort=created_at|original_filename|status|entity_count&order=asc|desc&page=1&page_size=10` (owner only; `q` matches filename or id prefix; page_size ≤ 50) → `{items,total,page,page_size}`. `entity_count` is derived from `entity_summary`.
- `GET /api/dashboard` (doctor): counts by status, processed in last 7 days, blocked count, last 5 documents, top 5 entity types by total count, average pipeline seconds (from step timestamps).
- `GET /api/admin/analytics`: users by role/status, documents by status per day for the last 14 days (counts only), LLM provider usage and fallback count, average LLM latency, complaint counts by status, safety-block rate, entity type totals. SQL aggregation (`GROUP BY`), no per-document rows.
- `GET /api/audit?actor=&action=&outcome=&date_from=&date_to=&sort=&order=&page=&page_size=` (admin, auditor).
- `GET /api/admin/users?q=&role=&status=&sort=&order=&page=`; `GET /api/admin/complaints?status=&category=&q=&sort=&page=`.
- Indexes support these queries. Large-input handling: streaming upload size check, page cap, per-page OCR cap.

## 22. Complaints / Help workflow

User: `POST /api/complaints`, `GET /api/complaints` (own), `GET /api/complaints/{id}` (own, with messages), `POST /api/complaints/{id}/messages` (only while `open` or `in_progress`; resolved → 409 `COMPLAINT_CLOSED`). Allowed for restricted users. `document_id` optional, validated to belong to the user; admin sees the id only (cannot open it).
Admin: `GET /api/admin/complaints`, `GET /api/admin/complaints/{id}`, `POST …/messages` (first admin reply auto-moves `open → in_progress`), `PATCH …/status`. Transitions: `open→in_progress`, `in_progress→resolved`, `open→resolved`, `resolved→in_progress` (reopen by admin). Others → 409 `INVALID_COMPLAINT_TRANSITION`.

## 23. Admin user management

`GET /api/admin/users/{id}`; `PATCH /api/admin/users/{id}` `{status?: "active"|"restricted", restricted_reason?, role?: "doctor"|"auditor"}`.
Rules: not self (`CANNOT_MODIFY_SELF`), not another admin (`CANNOT_MODIFY_ADMIN`), role only doctor↔auditor (`INVALID_ROLE_CHANGE`).
Restrict effects (single transaction + post-commit): set status, reason, `restricted_at`; wipe the user's vaults; set the user's non-terminal documents to `FAILED` (`ACCOUNT_RESTRICTED`); audit `USER_RESTRICT`. Restore: status `active`, audit `USER_RESTORE`. Role change: bump `token_version`, revoke all sessions, audit `USER_ROLE_CHANGE`.

## 24. Tests that must exist (`backend/tests/`)

Auth: signup/login/duplicate/weak password; lockout after 5; refresh rotation; refresh-reuse revokes family; Google token mock (valid/invalid/unverified); logout wipes vault; CSRF header required.
Authorization (A03): doctor B reads/modifies/deletes doctor A's document → 404 + audit; admin and auditor on any document endpoint → 403 + audit; restricted user blocked from upload but allowed to create complaints; privilege escalation attempts (role in signup body ignored; self-promote; admin acting on admin); admin list/analytics responses contain no filenames or text; audit rows cannot be updated or deleted (trigger); hash chain verifies and detects tampering.
Upload/validation: non-PDF, corrupt, encrypted, oversize, too many pages, empty/scanned-only, duplicate (including concurrent).
Extraction: text PDF, scanned PDF (OCR), image header, annotations/form fields, metadata author used as hint and absent from outputs.
Detection/tokenization: each HIPAA row in §12 with a synthetic example; DOB→Age; age ≥ 90; DAY tokens with negatives; invalid date; same person same token; name components swept; stoplist (drug named like a person is kept); lab values untouched; overlap resolution.
Safety: seeded leak (name missed) → BLOCK; manual mark clears block; approval reset after mark; stale review rejected.
Pipeline (A07): failure injected at each step → status, failure_code, step rows correct; resume skips succeeded steps; server-restart simulation marks documents correctly.
LLM (A06): timeout → retry → success; 429 with Retry-After; all primary attempts fail → fallback provider used; both fail → `LLM_FAILED` and retry works; malformed response → repair then fallback; circuit breaker opens and recovers; outbound payload contains no real values; unknown token in output left as-is with warning.
Concurrency (A05): double send → one provider call; idempotency key replay; simultaneous manual marks (version conflict); atomic transitions.
Privacy (P1/T5): after a full run, no real value in DB tables, audit logs, captured logs, or LLM request body.
Data (M05): filters, sorting, pagination edge cases (page beyond range, page_size cap), dashboard and analytics numbers vs. known fixtures.
Complaints: create/reply/status transitions/closed rule/foreign document id rejected.
API: standard error shape on 401/403/404/422/429/500.

## 25. Deployment

- Backend `Dockerfile` (python:3.11-slim): `apt-get install -y tesseract-ocr tesseract-ocr-eng libgl1`, pip install, `python -m spacy download en_core_web_sm`, run `alembic upgrade head && python scripts/seed.py && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1`.
- Free-tier hosts sleep: document "open the app 1 minute before judging" and add `/api/health` for a keep-alive ping. Vault is lost on restart (documented, handled by §8 startup routine).
- Frontend on Vercel with `BACKEND_URL` env; `next.config.js` rewrites `/api/:path*` to `${BACKEND_URL}/api/:path*`. Cookies set by the backend pass through the rewrite and stay first-party.
- `docker-compose.yml`: `db` (postgres), `backend`, `frontend`. One command: `docker compose up --build`.
- `scripts/make_sample_pdfs.py`: three synthetic patients (text lab report; discharge summary with metadata author set; scanned/image-header report).
- Seed script creates admin, auditor and one demo doctor from env vars (never committed). Credentials go to judges privately.
- README sections: problem, track, architecture diagram (ASCII from §1), setup, env vars, run, tests, deploy, security model, known limitations (Python memory zeroing; detection is not perfect → human review; no password reset / email verification; free-tier cold starts), declared challenges A03 + A06 with where to look in the code.
