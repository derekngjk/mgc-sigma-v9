# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## WHAT

MGC PoC is a two-service monorepo that simulates an Epic EHR-embedded application. Its core purpose is to demonstrate one end-to-end workflow:

1. Pull synthetic clinical data from the Epic Open FHIR Sandbox
2. Translate it into a patient/family-friendly summary via LLM (GPT-4o or Anthropic)
3. Gate delivery behind a clinician Human-in-the-Loop (HITL) approval step
4. Surface the approved summary to the patient/family via a one-time magic link

There are no shared packages between the two services. The backend is the single source of truth for state; the frontend is purely a UI layer that calls the backend API.

**Data privacy constraint:** this PoC only ever touches synthetic data from Epic's Open Sandbox. Real PHI must never be used.

---

## WHERE

```text
mgc-sigma-v9/
├── backend/                    FastAPI service (Python 3.11)
│   ├── main.py                 Routes, CORS config, Pydantic response models, app bootstrap
│   ├── db.py                   Supabase CRUD (PostgreSQL) — init_db, create_communication, get_communication, update_communication, get_or_create_family, get_or_create_primary_member, get_family_summary
│   ├── fhir.py                 FHIR fetch + parse — fetch_patient_data, _fetch_from_sandbox, _parse_fhir_bundle
│   ├── llm.py                  LLM translation — generate_summary, _call_llm (Anthropic + OpenAI)
│   ├── mock_data/
│   │   └── mock-oncology-123.json   Synthetic oncology fixture (bypasses Epic Sandbox)
│   ├── pyproject.toml          Dependencies and tool configuration (uv, ruff)
│   ├── requirements.txt        Production deps (fastapi, uvicorn, pydantic, httpx, supabase, psycopg)
│   ├── requirements-dev.txt    Test deps (-r requirements.txt + pytest, pytest-mock)
│   ├── pytest.ini              testpaths = tests, pythonpath = ., filterwarnings
│   ├── runtime.txt             Pins Python version for Render
│   ├── .env.example            SUPABASE_URL · SUPABASE_KEY · SUPABASE_DB_URL · FHIR_BASE_URL · LLM_PROVIDER
│   └── tests/
│       ├── conftest.py         Mocks for Supabase and psycopg3
│       ├── test_task_1_1.py    Health check + root endpoint (4 tests)
│       ├── test_task_1_2.py    Supabase CRUD (5 tests)
│       ├── test_task_2_1.py    FHIR fetcher + mock fallback (4 tests)
│       ├── test_task_3_1.py    LLM translation (2 tests)
│       ├── test_task_4_2.py    Approval + magic link (1 test)
│       ├── test_task_4_3.py    Patient/family mobile viewer (2 tests)
│       ├── test_change_tracking.py Condition change tracking (3 tests)
│       └── test_family_route.py    Family member access route (3 tests)
│
├── frontend/                   React 18 + Vite + TypeScript + Tailwind CSS
│   ├── src/
│   │   ├── main.tsx            React entry point — BrowserRouter + StrictMode wrapper
│   │   ├── App.tsx             Routes: / → WelcomeScreen, /clinician → ClinicianPage, /family/:fid/member/:mid → FamilyPage
│   │   ├── index.css           Tailwind base import
│   │   └── pages/
│   │       └── ClinicianPage.tsx   Full clinician workflow — patient selector, FHIR data panel,
│   │                               AI draft panel (editable textarea), Approve button
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
| `/clinician` | ✅ Live | EHR-embedded tab — patient selector, side-by-side Raw FHIR vs. AI Draft, Approve button |
| `/family/:fid/member/:mid` | ✅ Live | Mobile-first patient/family viewer — validates family+member pair; fetches latest approved summary for the patient; shows condition diff (new/resolved) if changes exist; 404 on invalid pair or no approved summary |

### Backend API surface

| Endpoint | Status | Description |
| --- | --- | --- |
| `GET /health` | ✅ Live | Liveness check |
| `GET /api/patient/{id}` | ✅ Live | Fetch + parse FHIR data (Patient, Condition, CarePlan); falls back to mock JSON for `mock-oncology-123`; creates a Draft `Communications` record; computes three-way condition diff (added/removed/ongoing) vs. last approved record; returns `PatientResponse` with `condition_diff` |
| `POST /api/generate` | ✅ Live | Accepts `comm_id` + `target_audience`; calls LLM (`LLM_PROVIDER` env var selects Anthropic or OpenAI); stores summary in `Communications`; returns `GenerateResponse` |
| `POST /api/communications/{id}/approve` | ✅ Live | Saves edited `ai_summary_text`, flips status to `Approved`; creates/reuses the patient's `families` + `family_members` records; returns `id` + `approved_at` + `family_link` in new `/family/{fid}/member/{mid}` format |
| `GET /api/communications/{id}` | ✅ Live | Legacy family viewer endpoint — return approved summary by comm_id; 404 if unknown or status != Approved |
| `GET /api/family/{fid}/member/{mid}` | ✅ Live | Family member access endpoint — validates both IDs belong together; returns latest approved summary for the patient; 404 if pair is invalid or no approved summary exists |

### Supabase schema (PostgreSQL)

#### `patients` table
- `id` (UUID PK): Internal unique identifier
- `epic_patient_id` (TEXT Unique): Patient.identifier from Epic Sandbox
- `patient_name` (TEXT): Full name
- `dob` (TEXT): Date of birth
- `gender` (TEXT): Gender
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

#### `families` table

- `id` (UUID PK): Family group identifier — the `:fid` in the magic link
- `patient_id` (UUID FK, UNIQUE): Reference to `patients.id` — one family group per patient, stable across approvals
- `created_at` (TIMESTAMPTZ): Auto-set on creation

#### `family_members` table

- `id` (UUID PK): Family member identifier — the `:mid` in the magic link
- `family_id` (UUID FK): Reference to `families.id`
- `name` (TEXT): Display name of the member
- `relationship` (TEXT): Role within the family, e.g. `"patient"`, `"spouse"`, `"child"`
- `created_at` (TIMESTAMPTZ): Auto-set on creation

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
uv run uvicorn main:app --reload --port 8000
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
