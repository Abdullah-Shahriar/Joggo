# design.md — Frontend and UX specification

Goal: calm, clean, medical-grade simplicity. Flat, lots of white space, almost no decoration.
Stack: Next.js 14 (App Router), TypeScript strict, Tailwind, TanStack Query, react-hook-form + zod, lucide-react.

---

## 1. Principles

1. Simple over clever. If in doubt, remove it.
2. **No card grids.** Use plain sections, tables, lists and single-column forms. A bordered box is allowed only for: the review panes, the modal dialogs, the login form container, and the empty states.
3. **No 3D.** No tilt, perspective, glassmorphism, heavy shadows, gradients. Only exception: the landing hero may have one subtle flat illustration with light depth. Nothing else.
4. **No theme switcher, no dark mode.**
5. One accent color. Red only for errors and blocked states.
6. Every screen has loading, empty and error states.
7. Same component = same look everywhere.

## 2. Tokens

| Token | Value | Use |
|---|---|---|
| `bg` | `#FFFFFF` | page background |
| `bg-subtle` | `#F7F8F9` | table header, striped rows, input disabled |
| `border` | `#E5E7EB` | all borders and dividers |
| `text` | `#111827` | main text |
| `text-muted` | `#6B7280` | secondary text, labels |
| `accent` | `#0F766E` | buttons, links, active menu, focus ring |
| `accent-hover` | `#0D5F59` | hover |
| `accent-tint` | `#E6F4F1` | selected row, token highlight, update flash |
| `danger` | `#B91C1C` | errors, blocked, destructive text |
| `danger-tint` | `#FEF2F2` | error banner background |

Typography: Inter (`next/font/google`, with system-ui fallback) for UI copy, and IBM Plex Mono (`next/font/google`, weights 400/500, Tailwind `font-mono`) strictly for placeholders/tokens, document IDs, and small clinical header codes (e.g. `WARD 4`, `CLEAN`, `DE-IDENTIFIED`, `ON YOUR SCREEN ONLY`). Sizes: 14px body, 12px small, 16px inputs, 20px h2, 28px h1, 44px landing hero. Weights 400/500/600. Line height 1.5. Max content width 1120px (app), 720px (text pages), 640px (forms).
Spacing scale: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64. Radius 6px (inputs, buttons), 8px (modals). Hairline separation shadows (white-theme distinction with ~1px `#E5E7EB` borders): buttons `0 1px 2px rgba(17,24,39,.07)`, sections/panes `0 1px 3px rgba(17,24,39,.06), 0 1px 2px rgba(17,24,39,.04)`, sticky bars `0 1px 4px rgba(17,24,39,.08)`, dividers `0 1px 0 rgba(17,24,39,.04)`, modals `0 8px 24px rgba(0,0,0,.12)`.
Focus: 2px accent outline with 2px offset on every interactive element.

## 3. Components

- **Button**: primary (accent bg, white text), secondary (white, border, text), ghost (text only), destructive (white, danger text/border). Height 40px (32px small). Loading state = inline spinner + disabled + label kept.
- **Input / Select / Textarea / Checkbox / Radio**: 40px high, border `border`, label above, helper/error text below (error in `danger`, linked via `aria-describedby`).
- **Table**: header on `bg-subtle`, 1px row dividers, no vertical borders, hover `bg-subtle`, sortable headers with arrow, sticky header on scroll. Mobile: horizontal scroll inside the table container only.
- **Filters bar**: one row above the table: search input + selects; collapses to a stack on mobile.
- **Badge** (status): text-only pill, 12px, no strong colors: neutral gray for UPLOADED/PROCESSING/SENDING (with tiny spinner), accent text on tint for REVIEW_REQUIRED/APPROVED/COMPLETED, danger text on tint for BLOCKED/FAILED/LLM_FAILED. Always includes the text label.
- **Toast**: bottom-right, white, border, 1 line, check or alert icon, auto-dismiss 3 s (errors 6 s), `aria-live="polite"`.
- **Modal**: centered, 480px, focus trap, Esc to close, overlay `rgba(17,24,39,.4)`.
- **Pagination**: "Previous / Next" and "Page X of Y".
- **Empty state**: one sentence + one action button, centered.
- **Confirm dialog** for: delete document, restrict user, restore user, sign out other devices.
- **TokenChip**: monospace 12px (`font-mono`), `#E6F4F1` background, `#0F766E` text, `3px solid #0F766E` left border, `border-radius: 0 4px 4px 0`, `padding: 1px 6px`, `whitespace-nowrap`. Used for all placeholders/tokens in cleaned records and the hero clinical preview.
- **Clinical chart sheet**: flat 1px-bordered review pane (`#FFFFFF` surface) with a chart-sheet header (title left, mono code right such as `DE-IDENTIFIED` in teal or `ON YOUR SCREEN ONLY` muted, and a 2px divider below: `#0F766E` for Cleaned, `#E5E7EB` for Original), 11px uppercase tracked section labels separated by thin `#E5E7EB` rules, and a faint diagonal `DE-IDENTIFIED` mono watermark (~7% teal opacity, `pointer-events: none`, hidden from screen readers and print) on the Cleaned pane.
- **Clinical block alert**: square-cornered `#FEF2F2` banner with `4px solid #B91C1C` left border, warning-triangle icon, bold `"Hold: {n} identifiers still visible"` title, a muted line listing detected words with line numbers, and Jump / Auto-fix actions.
- **Sign-out checklist**: labeled `"Sign-out checklist"` (11px uppercase muted) beside `"Approve and generate"`, showing three items (`Identifiers replaced`, `Safety scan passed`, and interactive checkbox `I reviewed the cleaned text`). Gates `"Approve and generate"` until all three are ticked; resets the review checkbox on untick or any manual mark. The same review-confirmation checkbox pattern is reused in the external AI handoff confirmation modal.
- **Clinical icons**: `lucide-react` stroke `1.5`, `#0F766E` or `#6B7280` only — `Stethoscope` (doctor areas), `ClipboardList` (documents), `FileHeart` (drafts), `ShieldPlus` (privacy sections), `Activity` (analytics). Used sparingly where an icon already exists or a heading benefits.

## 4. Layout

**Public header** (before login): height 64px, white, bottom border. Left: logo (shield-with-cross mark + `APP_NAME` wordmark in text color; click → `/`). Center: **Home · About · FAQ** (active = accent text + 2px underline). Right: **Login** button (primary). Mobile: hamburger → slide-down list (Home, About, FAQ, Login).
**Public footer**: top border, white. Left: logo + one line "Privacy-first AI for clinical documents." Center/links: Home · About · FAQ. Right: "Demo environment — synthetic data only". Bottom line: © {year} {APP_NAME}.
**App header** (after login): logo left (→ role home), menu center, profile menu right (name + chevron → Profile, Sign out). Mobile: hamburger.
Menus:
- doctor: Dashboard · New document · My documents · Help
- admin: Overview · Users · Complaints · Audit logs · Analytics
- auditor: Audit logs
The landing, About, FAQ, Login and Signup pages are **never** shown to a logged-in user (redirect: doctor → `/dashboard`, admin → `/admin`, auditor → `/admin/audit`).
App footer: slim single line (demo notice + © year).

## 5. Routes and page specs

Public (logged-out only):
- `/` Landing. Sections in order, plain, centered, alternating white and `bg-subtle` bands:
  1. Hero: H1 "Use AI on patient records. Without exposing patients." Sub: "We remove identities locally before anything reaches an AI model, then restore them on your screen." Buttons: "Get started" (→ `/login`), "How it works" (scroll). Optional light flat illustration on the right.
  2. How it works (4 numbered steps as a simple list, not cards): 1 Upload a patient PDF. 2 Identities are found and replaced with safe placeholders. 3 You review the cleaned text, then approve. 4 The AI writes the draft; real details are restored only on your screen.
  3. Why it is safe (4 plain bullet lines): Identifiers never leave our server. Dates become relative days; birthdates become age. Real details are kept only in temporary memory and wiped when you sign out. Every action is recorded in a tamper-evident audit log.
  4. Final call to action: "Try it with synthetic data" + button.
- `/about` (720px text page): What it is (2 short paragraphs), The problem (hospitals ban AI or staff use it secretly; blunt redaction removes clinical meaning; PDFs hide identities in metadata and images), Our approach (local de-identify and re-hydrate, human review, audit), Limits (detection is not perfect, so a human always reviews; demo uses synthetic data).
- `/faq` — accordion (one open at a time), questions:
  1. Does patient data reach the AI? — No. Only placeholder text such as [PATIENT_A], "Age 58" and [DAY_0].
  2. What if something is missed? — A second scan blocks sending if it finds leftovers, and you can highlight any text to replace it.
  3. Where are real names stored? — Only in temporary encrypted memory during your session. They are wiped on sign out or after 30 minutes idle.
  4. Can administrators read my documents? — No. Admins can manage accounts and see activity logs, never document content.
  5. Which AI providers are used? — Gemini and Groq. If one fails, the other is used automatically.
  6. Is this ready for real patients? — This is a demo. Use synthetic data only.
- `/login`: simple centered 400px form container. **Back button** at top-left of the page ("← Back to home", ghost button → `/`). Title "Sign in". Email, Password (show/hide), "Sign in" primary, divider "or", Google button ("Continue with Google"), link "Create an account" → `/signup`. Inline errors; generic failure text; locked-account message with minutes left.
- `/signup`: same layout; Full name, Email, Password (rules shown live), Create account; Google button; link back to Login; also has the Back to home button.

Doctor:
- `/dashboard`: H1 "Welcome, {first name}". One plain row of three figures with small labels (Processed this week · Waiting for review · Blocked). Primary button "New document". H2 "Recent documents": table of last 5 (Document, Task, Status, Date) + link "View all". Empty state: "No documents yet. Upload a PDF to begin." If account restricted: danger banner at top: "Your account is restricted. You can contact support from Help." and the New document button is disabled.
- `/documents/new`: single column 640px. Task type (radio: Discharge summary · Case summary · Treatment plan). File drop zone (click or drag; text "PDF, up to 10 MB and 30 pages"). Notice line: "Demo environment — use synthetic data only". Submit "Upload and clean". After upload show a live step list (Reading file · Finding identifiers · Replacing with placeholders · Safety check), each with a dot/spinner/check, polling every 1.5 s, then redirect to `/documents/{id}`. Error mapping: show the API message inline (duplicate → link "Open existing document").
- `/documents` (My documents): H1, filters bar (search, status, task, date range), sortable table (Document, Task, Status, Entities, Created), pagination, row click → detail. Row action: Delete (confirm).
- `/documents/[id]` (review): header row: filename, status badge, "Why was this replaced?" toggle on the right. A thin step tracker (Extract · Detect · Tokenize · Safety · Review · Generate). Body:
  - Desktop: three columns with 1px borders and independent scroll: **Original** (tabs: Text | PDF preview; detected items softly highlighted in `accent-tint`) · **Cleaned text** (tokens shown as `accent` text on `accent-tint`) · **Result** (appears after generation; tabs not needed).
  - Mobile: tab bar (Original · Cleaned · Result).
  - **Highlight-to-tokenize**: selecting text in the Cleaned pane shows a small popover at the selection: "Mark as" + select (Name, Doctor, Person, Phone, Email, ID, Record number, Address, Facility, Other) + "Replace" button. On success the pane updates, toast "Marked and replaced everywhere".
  - Safety banner: PASS = plain accent text "Safety check passed". BLOCK = danger-tint banner listing findings with "Jump to" links and the instruction "Highlight the text and replace it to continue."
  - Actions (sticky bottom bar): "Approve and generate" (primary; disabled unless safety PASS; sends approve then send with a fresh `Idempotency-Key`), "Delete".
  - While SENDING: BrandLoader in the Result pane with text "Generating draft…" and provider fallback message if it happened ("Switched to backup provider").
  - COMPLETED: Result pane shows re-hydrated text with the AI disclaimer, buttons Copy · Download .txt · Download .docx. If `vault_expired`: note "Original details have expired, showing placeholders only."
  - LLM_FAILED: danger banner "Could not generate a draft." + "Try again".
  - "Why was this replaced?" opens a plain list: token, type, rule reason, occurrences (no values).
  - If the vault expired before approval: banner "Session data expired. Upload the file again." and the actions are disabled.
- `/help`: H1 "Help". Two parts: short form (Subject, Category, Message, optional "Related document" select from own documents) and "My complaints" table (Subject, Status, Updated). `/help/[id]`: thread (messages as plain list with author and time), reply box (hidden when resolved: "This complaint is resolved.").
- `/profile`: single column 640px, plain sections separated by dividers:
  1. **Account**: Full name (editable, Save), Email (read-only), Role (text), Member since, Sign-in method (Email / Google).
  2. **Password**: Current, New, Confirm, "Update password" — for Google-only accounts show "You sign in with Google, so there is no password to change."
  3. **Active sessions**: table (Device, IP, Last active, "This device" label), "Sign out" per row, and "Sign out all other devices" (confirm).
  Banner at top if restricted. Sign out lives in the header menu only.

Admin:
- `/admin` Overview: H1; plain definition-style list of counts (Open complaints, In progress, Restricted users, Documents processed today). Counts only.
- `/admin/users`: filters (search, role, status), table (Name, Email, Role, Status, Last login, Documents count) with row actions: Restrict / Restore (modal asks for a reason on restrict), Change role (select doctor/auditor). Self row and other admins show "—" for actions.
- `/admin/complaints`: filters (status, category, search), table (Subject, User, Category, Status, Updated). Detail page: thread + reply box + status select. The related document id is shown as plain text with the note "Admins cannot open documents".
- `/admin/audit` (also auditor): filters (actor, action, outcome, date range), table (Time, Actor, Action, Resource, Outcome), pagination, and an "Verify log integrity" button showing the result inline.
- `/admin/analytics`: plain tables and simple horizontal bars drawn with CSS widths (no chart library): users by role/status, documents per day (14 days), LLM provider usage and fallbacks, safety-block rate, entity type totals, complaints by status.

Other:
- **Custom 404** (`app/not-found.tsx`): centered; large "404" (text color) with a short accent underline; heading "This page doesn't exist"; one line "The link may be broken or the page was moved."; button "Go to home" (logged-out) or "Go to dashboard" (logged-in, role-aware). Uses the public or app layout accordingly.
- **403 view**: "You don't have access to this page." + back button.
- **Error boundary** (`error.tsx`): "Something went wrong." + "Try again".

## 6. Animations (subtle, purposeful)

All animations are disabled under `prefers-reduced-motion` (replace with static states).
- **BrandLoader** (full-page and big panes): the shield-cross logo mark outline with an accent ring (SVG stroke-dasharray) rotating once per 1.2 s, and a soft opacity pulse on the cross. Label below in muted text ("Loading…"). Used for first page load, route changes that fetch data, and LLM generation.
- **Route progress bar**: 2px accent bar at the very top that advances while a route/data loads.
- **Skeletons**: gray `bg-subtle` rows with a slow pulse for tables and the review panes.
- **Button/inline spinner**: 16px ring, 0.8 s.
- **Pipeline step list**: dot → spinner → check (check draws in 250 ms).
- **Admin update animation** (all admin mutations: restrict, restore, role change, complaint status/reply): after a successful response the affected row (or thread item) flashes from `accent-tint` to transparent over 1.2 s; the status text does a quick scale 1 → 1.08 → 1 over 200 ms; a toast appears with an animated check (stroke draw 300 ms) and a message like "User restricted". Failures: row shakes 2px × 2 (150 ms) and an error toast appears.
- **Toasts**: slide up 8px + fade, 150 ms.
- **FAQ accordion**: height transition 150 ms.
- Page transitions: none (keep fast).

## 7. Behavior and data rules (frontend)

- `lib/api.ts` is the only fetch layer: base `/api`, `credentials: "include"`, header `X-Requested-With: fetch`, JSON by default; on 401 call `/api/auth/refresh` once, retry once, else go to `/login?next=…`. Error toasts use the backend `error.message`; `request_id` shown small in the toast for support.
- `middleware.ts`: if the `refresh_token` cookie is present and the path is public (`/`, `/about`, `/faq`, `/login`, `/signup`) → redirect to the role home (resolved from a lightweight cookie-less `GET /api/me`, or default to `/dashboard` then let the layout redirect). If absent and the path is protected → `/login?next=…`. The app layout always verifies with `GET /api/me`.
- Server state with TanStack Query: polling `GET /api/documents/{id}` every 1.5 s while status ∈ {UPLOADED, PROCESSING, SENDING}, stop otherwise.
- Never persist documents or tokens in browser storage. Never log values to the console.
- Forms: zod schemas mirror backend limits (subject 3–120, message 10–4000, password ≥ 10 with a letter and a digit, name 2–80).
- Google sign-in: load `https://accounts.google.com/gsi/client` only on `/login` and `/signup`; send the credential to `/api/auth/google`.
- Date display: local timezone, format `12 Oct 2026, 14:05`.
- PDF preview: `GET /api/documents/{id}/original-pdf` → blob URL → `<iframe>` (only while the vault is alive; else show the expired note).
- Accessibility: landmarks (`header`, `nav`, `main`, `footer`), skip link, `aria-current="page"` on active menu, table captions or `aria-label`, color never the only signal (badges have text), min target 40px, form errors announced.
- Responsive breakpoints: 640 (sm), 1024 (lg). Review page columns only at ≥ 1024.

## 8. Copy rules

Plain, calm, short. No exclamation marks, no emojis, no marketing buzzwords. Error messages say what happened and what to do next.
