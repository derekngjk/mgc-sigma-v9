# MGC PoC

Proof-of-concept web app that simulates being embedded in Epic EHR. Translates
synthetic FHIR clinical data into patient/family-friendly summaries via LLM,
with a clinician human-in-the-loop approval step before delivery.

## Repo layout

```
mgc/
├── backend/    FastAPI service — FHIR fetch, LLM call, approval state
└── frontend/   React + Vite + TS + Tailwind — Clinician + Family views
```

## Local dev

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate           # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Health check: <http://localhost:8000/health>

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open: <http://localhost:5173>

## Deploy

`render.yaml` defines two Render services (web app + API).

## Status

Task 1.1 — foundation scaffold. Health check + welcome screen only. No FHIR
or LLM wiring yet.
