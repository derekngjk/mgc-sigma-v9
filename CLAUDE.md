# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## WHAT

MGC PoC is a two-service monorepo that simulates an Epic EHR-embedded application. Its core purpose is to demonstrate one end-to-end workflow:

1. Pull synthetic clinical data from the Epic Open FHIR Sandbox
2. Translate it into a patient/family-friendly summary via LLM (GPT-4o or Anthropic)
3. Gate delivery behind a clinician Human-in-the-Loop (HITL) approval step
4. Auto-deliver the approved summary to the patient's care circle: each person (patient / spouse / adult child / caregiver) self-registers a portal account (email + password), links to the patient via the patient's full name + NRIC, and sees only the summaries written for their role

There are no shared packages between the two services. The backend is the single source of truth for state; the frontend is purely a UI layer that calls the backend API.

**Data privacy constraint:** this PoC only ever touches synthetic data from Epic's Open Sandbox. Real PHI must never be used.

---

## WHERE

```text
mgc-sigma-v9/
├── backend/                    FastAPI service (Python 3.11)
│   ├── app/                    Application package (import root: `app`)
│   │   ├── main.py             create_app() factory, CORS, lifespan, router wiring; `app` ASGI entry
│   │   ├── config.py           Settings (env vars, read live) + path anchors (MOCK_DATA_DIR, SYNTHEA_DIR)
│   │   ├── schemas.py          Pydantic request/response models + validation sets
│   │   ├── dependencies.py     verify_clinician_token (Supabase Auth) + verify_patient_token (patient JWT)
│   │   ├── routers/            health.py · clinician.py (patient/generate/approve) · account.py (patient login/reports/audio)
│   │   ├── services/           fhir.py · images.py · image_brief.py · tts.py · summaries.py · prompts.py · identity.py (name+NRIC hash, password hash, portal JWT)
│   │   │   └── llm/            base.py (LLMProvider Protocol) · providers.py (Anthropic/OpenAI/Google) · get_provider()
│   │   └── db/                 client.py · schema.py · communications.py · accounts.py (patient lookup/delivery) · portal.py (users + role reports + reads) · storage.py · _helpers.py
│   ├── scripts/               Ops scripts — seed_healthx.py, synthea_to_fhir.py (run via `python -m scripts.<name>`)
│   ├── mock_data/
│   │   └── mock-oncology-123.json   Synthetic oncology fixture (bypasses Epic Sandbox)
│   ├── pyproject.toml          Deps ([project] + [dependency-groups] dev), pytest + ruff config — uv-managed
│   ├── uv.lock                 Pinned dependency lockfile (single source of truth)
│   ├── .python-version         Pins the Python version (read by uv; Render fallback)
│   ├── .env.example            SUPABASE_URL · SUPABASE_KEY · SUPABASE_DB_URL · FHIR_BASE_URL · LLM_PROVIDER · PATIENT_JWT_SECRET · PATIENT_ID_PEPPER
│   └── tests/                  pytest suite (imports the app via `app.*`; patches router/service module globals)
│
├── frontend/                   React 18 + Vite + TypeScript + Tailwind CSS
│   ├── src/
│   │   ├── main.tsx            React entry point — BrowserRouter + StrictMode wrapper
│   │   ├── App.tsx             Routes: / → Welcome, /login + /clinician (clinician), /patient/login + /patient + /patient/report/:commId (patient account)
│   │   ├── index.css           Tailwind base import
│   │   ├── lib/                supabase.ts (clinician auth) · patientSession.ts (patient JWT) · markdown.ts
│   │   ├── components/         AuthGate.tsx (clinician) · PatientAuthGate.tsx · ReportView.tsx (shared report viewer)
│   │   └── pages/              ClinicianPage · LoginPage · PatientRegisterPage · PatientLoginPage · PatientDashboardPage · PatientReportPage
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── .env.example            VITE_API_BASE_URL
│
└── render.yaml                 Render PaaS deployment (one web service + one static site)
```

### Frontend routes

| Route | Status | Purpose |
| --- | --- | --- |
| `/` | ✅ Live | Welcome screen — backend health check, link to `/clinician` |
| `/clinician` | ✅ Live | EHR-embedded tab (guarded by `AuthGate`/Supabase) — patient selector, side-by-side Raw FHIR vs. AI Draft, Approve button; success card confirms account delivery |
| `/login` | ✅ Live | Clinician sign-in — Supabase magic-link (passwordless email) |
| `/patient/register` | ✅ Live | Portal self-registration — email, password, role (patient/spouse/child/caregiver), + patient's full name & NRIC to link |
| `/patient/login` | ✅ Live | Portal sign-in — email + password |
| `/patient` | ✅ Live | Portal dashboard (guarded by `PatientAuthGate`) — the user's role-scoped reports as cards + per-user unread badge; "Signed in as {role}" |
| `/patient/report/:commId` | ✅ Live | Single report viewer (mobile-first `ReportView`) — translation, TTS, illustration, condition diff, print; authorized to the caller's patient + role |

### Backend API surface

| Endpoint | Status | Description |
| --- | --- | --- |
| `GET /health` | ✅ Live | Liveness check |
| `GET /api/patient/{id}` | ✅ Live | Fetch + parse FHIR data (Patient, Condition, CarePlan); falls back to mock JSON for `mock-oncology-123`; creates a Draft `Communications` record; computes three-way condition diff (added/removed/ongoing) vs. last approved record; returns `PatientResponse` with `condition_diff` |
| `POST /api/generate` | ✅ Live | Accepts `comm_id` + `target_audience` + optional `review`; calls LLM (`LLM_PROVIDER` env var selects Anthropic or OpenAI); when `review: true`, a second LLM (`REVIEWER_PROVIDER`) checks the draft against the source facts and the advisory `ReviewVerdict` is returned and persisted to `review_json`; stores summary in `Communications`; returns `GenerateResponse` |
| `POST /api/communications/{id}/approve` | ✅ Live | Saves edited `ai_summary_text`, flips status to `Approved`, auto-delivers to the patient's account (`set_delivered`); returns `id` + `approved_at` + `patient_name` + `delivered` (`false` when the patient has no NRIC → no account) |
| `POST /api/account/register` | ✅ Live | Portal registration — body `{email, password, role, patient_full_name, patient_nric}`; links via `identity_hash`; creates a `portal_users` row (PBKDF2-hashed password); returns a session JWT + `patient_name` + `role`. 404 unknown patient · 409 duplicate email · 400 bad role/short password |
| `POST /api/account/login` | ✅ Live | Portal login — body `{email, password}`; verifies against `portal_users`; returns JWT + `patient_name` + `role`, or 401 |
| `GET /api/account/reports` | ✅ Live | (portal JWT) The user's **role-scoped** delivered reports as cards + **per-user** unread count (from `portal_report_reads`) + `role` |
| `GET /api/account/reports/{comm_id}` | ✅ Live | (portal JWT) One report matching the caller's patient **and role**; `?lang=` translates; marks read for this user; 404 otherwise |
| `GET /api/account/reports/{comm_id}/audio` | ✅ Live | (portal JWT) TTS MP3 + sentences for a role-authorized report; `?lang=` selects language |

### Supabase schema (PostgreSQL)

#### `patients` table
- `id` (UUID PK): Internal unique identifier
- `epic_patient_id` (TEXT Unique): Patient.identifier from Epic Sandbox
- `patient_name` (TEXT): Full name
- `dob` (TEXT): Date of birth
- `gender` (TEXT): Gender
- `identity_hash` (TEXT Unique): Peppered HMAC of normalized full name + NRIC — the patient-account login key. Raw name+NRIC is never stored.
- `created_at` (TIMESTAMPTZ): Auto-set on creation

#### `care_plan_translations` table

- `id` (UUID PK): Unique identifier for this record
- `patient_id` (UUID FK): Reference to `patients.id`
- `fhir_source` (TEXT): `"sandbox"` or `"mock"`
- `raw_clinical_text` (TEXT): Serialised FHIR payload
- `target_audience` (TEXT): `"patient"` or `"family"`
- `ai_summary_text` (TEXT): Simplified analogy
- `status` (TEXT): `"Draft"` or `"Approved"`
- `created_at` (TIMESTAMPTZ): Auto-set on creation
- `approved_at` (TIMESTAMPTZ): Timestamp of clinician approval
- `conditions_json` (JSONB): Parsed active conditions
- `condition_diff` (JSONB): NEW/ONGOING/RESOLVED delta
- `translations_json` (JSONB): Cached per-language translations
- `audio_urls_json` (JSONB): Cached per-language TTS Storage URLs
- `image_url` (TEXT): Cached visual-aid Storage URL
- `approved_by_user_id` (UUID): Clinician (Supabase Auth) who approved — audit trail
- `delivered_to_patient_at` (TIMESTAMPTZ): Set on approval; a report appears in the portal only once delivered
- `viewed_by_patient_at` (TIMESTAMPTZ): **Deprecated** — read state is now per-user in `portal_report_reads`

#### `portal_users` table

- `id` (UUID PK): Portal account id — the JWT `sub`
- `email` (TEXT Unique): Login email
- `password_hash` / `password_salt` (TEXT): PBKDF2-HMAC-SHA256 hash + per-user salt (no plaintext)
- `role` (TEXT): One of `patient` / `spouse` / `child` / `caregiver` — matches report `target_audience`
- `patient_id` (UUID FK): The patient this account is linked to (set at registration via name+NRIC)
- `created_at` (TIMESTAMPTZ): Auto-set on creation

#### `portal_report_reads` table

- `id` (UUID PK): Row id
- `portal_user_id` (UUID FK): Reference to `portal_users.id`
- `comm_id` (UUID FK): Reference to `care_plan_translations.id`
- `viewed_at` (TIMESTAMPTZ): When this user first opened the report
- UNIQUE(`portal_user_id`, `comm_id`): One read-record per (user, report); `mark_report_read` upserts

#### `families` / `family_members` tables — **deprecated**

Left in existing databases but no longer read or written. The old `/family/:fid/member/:mid` magic-link model was replaced by per-user portal accounts (`portal_users`); a report is authorized by the caller's `patient_id` **and role**, not by a family/member pair.

---

## HOW

### Package manager

- **Frontend:** npm (Node). Use `npm ci` for reproducible installs.
- **Backend:** [uv](https://docs.astral.sh/uv/) (Python).

### Running locally

#### Backend

```bash
cd backend
uv sync
cp .env.example .env       # set SUPABASE_URL, SUPABASE_KEY, SUPABASE_DB_URL
uv run uvicorn app.main:app --reload --port 8000
```

#### Frontend (separate terminal)

```bash
cd frontend
npm install
cp .env.example .env       # set VITE_API_BASE_URL=http://localhost:8000 if not already
npm run dev
```

### Verify changes

| What to check | Where |
| --- | --- |
| Backend alive | [http://localhost:8000/health](http://localhost:8000/health) |
| Auto-generated API docs (Swagger UI) | [http://localhost:8000/docs](http://localhost:8000/docs) |
| Frontend dev server | [http://localhost:5173](http://localhost:5173) |
| Python linting & format | `cd backend && uv run ruff check . && uv run ruff format .` |
| TypeScript errors | `cd frontend && npm run lint` (runs `tsc --noEmit`) |
| Production frontend build | `cd frontend && npm run build` (output: `frontend/dist/`) |

### Deployment

`render.yaml` wires up two Render services. Set `FRONTEND_ORIGIN` on the backend service and `VITE_API_BASE_URL` on the frontend static site via the Render dashboard (both are marked `sync: false` — they must be set manually per environment).

### FHIR mock fallback

When adding any new FHIR-fetching code, always implement the hardcoded mock JSON path in parallel. Request the special Patient ID `mock-oncology-123` to exercise it locally without hitting the sandbox.

### LLM latency

LLM calls are synchronous. If response time exceeds ~5 seconds, use the LLM provider's streaming API and surface a skeleton/spinner in the frontend rather than waiting on a blocking HTTP response.

---

## Coding Preferences and Rules

### Code style

- **Python:** Always use explicit type hints on all function signatures and return types. No bare `Any` unless unavoidable.
- **TypeScript/React:** Always use named exports — no default wildcard re-exports. Prefer explicit `export { Foo }` over `export * from`.
- Keep functions small and single-purpose. Inline helpers only if they are used once and add no meaningful abstraction.

### Testing

- **Frontend:** [Vitest](https://vitest.dev/) is the test runner (not yet scaffolded).

  ```bash
  cd frontend && npm run test
  ```

- **Backend:** pytest is the test runner.

  ```bash
  cd backend && uv run pytest -v                          # run all tests
  cd backend && uv run pytest tests/test_task_3_1.py -v   # run a single file
  ```

- New features require at least one unit test covering the happy path and one covering the primary error/edge case.

### Response formatting

- Use XML tags (`<plan>`, `<code>`, `<explanation>`) to separate distinct sections in complex responses.
- Avoid dense walls of text — prefer short paragraphs or bullet lists.
- Minimize conversational filler before and after code blocks. State what the code does in one sentence, then show the code.

---

## Workflow

For complex or multi-feature requests, do not attempt to write the entire solution in one pass. Follow this process:

1. **Plan first.** Break the request into small, clearly scoped steps. Present the numbered plan and wait for confirmation before writing any code.
2. **Execute one step at a time.** Complete one step, show the diff or result, and stop.
3. **Wait for review.** Do not proceed to the next step until the user has reviewed and approved the current one.
4. **Flag blockers early.** If a step depends on a decision not yet made (e.g., schema design, API contract), surface it as a question before writing code that assumes an answer.
5. **Document work.** Once the feature has been completed, document the work in `implementation-notes.md` following the style of the document.

This applies to: adding new routes, building new UI views, integrating new external services, and any change that touches both `backend/` and `frontend/` in the same request.
