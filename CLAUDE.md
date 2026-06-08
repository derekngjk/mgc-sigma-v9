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
│   ├── db.py                   SQLite CRUD — init_db, create_communication, get_communication, update_communication
│   ├── fhir.py                 FHIR fetch + parse — fetch_patient_data, _fetch_from_sandbox, _parse_fhir_bundle
│   ├── llm.py                  LLM translation — generate_summary, _call_llm (Anthropic + OpenAI)
│   ├── mock_data/
│   │   └── mock-oncology-123.json   Synthetic oncology fixture (bypasses Epic Sandbox)
│   ├── requirements.txt        Production deps (fastapi, uvicorn, pydantic, httpx, python-dotenv, anthropic, openai)
│   ├── requirements-dev.txt    Test deps (-r requirements.txt + pytest)
│   ├── pytest.ini              testpaths = tests, pythonpath = .
│   ├── runtime.txt             Pins Python version for Render
│   ├── .env.example            FRONTEND_ORIGIN · DB_PATH · FHIR_BASE_URL · LLM_PROVIDER · ANTHROPIC_API_KEY · OPENAI_API_KEY
│   └── tests/
│       ├── conftest.py         Shared TestClient fixture
│       ├── test_task_1_1.py    Health check + root endpoint (4 tests)
│       ├── test_task_1_2.py    SQLite CRUD (14 tests)
│       ├── test_task_2_1.py    FHIR fetcher + mock fallback (22 tests)
│       └── test_task_3_1.py    LLM translation — happy path, audience, errors, unit (14 tests)
│
├── frontend/                   React 18 + Vite + TypeScript + Tailwind CSS
│   ├── src/
│   │   ├── main.tsx            React entry point, router bootstrap
│   │   ├── App.tsx             Root component (welcome screen / health check)
│   │   └── index.css           Tailwind base import
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── .env.example            VITE_API_BASE_URL
│
└── render.yaml                 Render PaaS deployment (one web service + one static site)
```

### Frontend route namespaces (planned)

| Route | Purpose |
| --- | --- |
| `/clinician` | Mock EHR tab — patient selector, side-by-side Raw FHIR vs. AI Draft, Approve button |
| `/family/:id` | Mobile-first patient/family viewer — fetches approved summary by UUID; 404 on unknown ID |

### Backend API surface

| Endpoint | Status | Description |
| --- | --- | --- |
| `GET /health` | ✅ Live | Liveness check |
| `GET /api/patient/{id}` | ✅ Live | Fetch + parse FHIR data (Patient, Condition, CarePlan); falls back to mock JSON for `mock-oncology-123`; creates a Draft `Communications` record; returns `PatientResponse` |
| `POST /api/generate` | ✅ Live | Accepts `comm_id` + `target_audience`; calls LLM (`LLM_PROVIDER` env var selects Anthropic or OpenAI); stores summary in `Communications`; returns `GenerateResponse` |
| `POST /api/communications/{id}/approve` | ⏳ Pending | Save approved text to SQLite, flip status to Approved |
| `GET /api/communications/{id}` | ⏳ Pending | Return approved summary for the family viewer |

### SQLite schema (`Communications` table)

| Column | Type | Notes |
| --- | --- | --- |
| `id` | TEXT PK | UUID v4 |
| `epic_patient_id` | TEXT NOT NULL | Patient.identifier from Epic Sandbox (Base64-encoded string, e.g. `eovIMNNn7tHB…`). Use `mock-oncology-123` to trigger the mock fallback. |
| `fhir_source` | TEXT NOT NULL | `"sandbox"` or `"mock"` — records which data path produced the raw clinical text |
| `patient_name` | TEXT NOT NULL | Patient.name from FHIR |
| `raw_clinical_text` | TEXT NOT NULL | Serialised FHIR payload (Condition + CarePlan) sent to the LLM |
| `target_audience` | TEXT NOT NULL | LLM prompt parameter — `"patient"` or `"family"` (default `"family"`) |
| `ai_summary_text` | TEXT | NULL until LLM generates a draft |
| `status` | TEXT NOT NULL | `"Draft"` → `"Approved"` |
| `created_at` | TEXT NOT NULL | ISO-8601 UTC timestamp |
| `approved_at` | TEXT | NULL until clinician approves; ISO-8601 UTC timestamp |

---

## HOW

### Package manager

- **Frontend:** npm (Node). Use `npm ci` for reproducible installs. There is no Bun or Yarn config — stay with npm.
- **Backend:** pip inside a virtualenv.

### Running locally

#### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
cp .env.example .env       # fill in any API keys
uvicorn main:app --reload --port 8000
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

- **Frontend:** [Vitest](https://vitest.dev/) is the test runner (not yet scaffolded — add it when writing the first test).

  ```bash
  cd frontend && npm run test          # run all tests
  cd frontend && npm run test -- path/to/file.test.tsx   # run a single file
  ```

- **Backend:** pytest is the test runner. Always use the venv's pytest binary.

  ```bash
  cd backend && .venv/bin/pytest -v                          # run all tests
  cd backend && .venv/bin/pytest tests/test_task_3_1.py -v   # run a single file
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

This applies to: adding new routes, building new UI views, integrating new external services, and any change that touches both `backend/` and `frontend/` in the same request.
