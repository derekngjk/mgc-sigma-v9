# MGC PoC

Proof-of-concept web app that simulates being embedded in Epic EHR. Translates
synthetic FHIR clinical data into patient/family-friendly summaries via LLM,
with a clinician human-in-the-loop approval step before delivery.
## Repo layout

```text
mgc-sigma-v9/
├── backend/    FastAPI service — FHIR fetch, Supabase state, LLM call, approval flow
│   ├── main.py             Routes + Pydantic models
│   ├── db.py               Supabase CRUD layer (PostgreSQL)
│   ├── fhir.py             Epic FHIR R4 fetcher + parser
│   ├── llm.py              LLM translation — Anthropic + OpenAI, env-var selected
│   ├── mock_data/          Static FHIR fixtures (bypasses live sandbox)
│   └── tests/              pytest suite (21 tests using mocked Supabase client)
└── frontend/   React + Vite + TS + Tailwind — Clinician + Family views
```

    └── src/
        ├── App.tsx             Root component — BrowserRouter routes (/ and /clinician)
        └── pages/
            └── ClinicianPage.tsx   Clinician dashboard — patient selector, FHIR panel, AI draft, Approve
```

## Local dev

### Backend

```bash
cd backend
# Install uv if you haven't: https://docs.astral.sh/uv/getting-started/installation/
uv sync
cp .env.example .env               # set SUPABASE_URL, SUPABASE_KEY, SUPABASE_DB_URL
uv run uvicorn main:app --reload --port 8000
```

Health check: <http://localhost:8000/health>  
API docs (Swagger): <http://localhost:8000/docs>

### Frontend

```bash
cd frontend
npm install
cp .env.example .env               # set VITE_API_BASE_URL=http://localhost:8000
npm run dev
```

Open: <http://localhost:5173> (welcome screen) or <http://localhost:5173/clinician> (clinician view)

### Running tests & Linting

```bash
cd backend
uv run pytest                        # run full suite
uv run ruff check .                  # lint check
uv run ruff format .                 # apply formatting
```

## Deploy

`render.yaml` defines two Render services (web app + API). Set `FRONTEND_ORIGIN`,
`SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_DB_URL`, `FHIR_BASE_URL`, `LLM_PROVIDER`, 
and the relevant API key as env vars on the Render dashboard.

## Status

| Task | Description | Status |
| --- | --- | --- |
| 1.1 | Foundation scaffold — health check + welcome screen | ✅ Done |
| 1.2 | SQLite state store — `Communications` table + CRUD | ✅ Done |
| 2.1 | FHIR Sandbox Fetcher — `GET /api/patient/{id}` | ✅ Done |
| 2.2 | Mock data fallback — `mock-oncology-123` fixture | ✅ Done |
| 3.1 | LLM translation — `POST /api/generate` | ✅ Done |
| 4.1 | Clinician dashboard UI (`/clinician`) | ✅ Done |
| 4.2 | Approval + magic link flow | ✅ Done |
| 4.3 | Patient/family mobile viewer (`/family/:id`) | ✅ Done |
| CT | Condition change tracking — NEW/ONGOING/RESOLVED diff across visits | ✅ Done |
