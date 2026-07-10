# MGC PoC

Proof-of-concept embedded EHR application for the **Medical Grand Challenge 2026 (NUS)**. It pulls synthetic FHIR clinical data from the Synapxe HealthX sandbox, translates it into a patient/family-friendly summary via LLM, gates delivery behind a clinician Human-in-the-Loop (HITL) approval step, and surfaces the approved summary to the patient's family via a secure magic link.

---

## What you need before starting

| Requirement | Notes |
| --- | --- |
| **Node.js ≥ 18** | For the frontend |
| **Python 3.11+** | For the backend |
| **uv** | Python package manager — `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Supabase account** | Free tier works — [supabase.com](https://supabase.com) |
| **LLM API key** | One of: Anthropic, OpenAI, or Gemini |
| **Synapxe HealthX credentials** *(optional)* | For live FHIR data — register at [innovation.healthx.sg](https://innovation.healthx.sg). The mock patient (`mock-oncology-123`) works without this. |

---

## 1 — Supabase setup

### 1.1 Create a project

Go to [supabase.com](https://supabase.com), create a new project, and wait for it to provision.

### 1.2 Collect your keys

In the Supabase dashboard go to **Settings → API**. You need three values:

| Variable | Where to find it |
| --- | --- |
| `SUPABASE_URL` / `VITE_SUPABASE_URL` | **Project URL** field |
| `SUPABASE_KEY` / `VITE_SUPABASE_ANON_KEY` | **Project API keys → anon public** |
| `SUPABASE_JWT_SECRET` | **JWT Settings → JWT Secret** (scroll down) |

For `SUPABASE_DB_URL`, go to **Settings → Database → Connection string** and select the **URI** tab. Switch the connection mode to **Transaction pooler** (port 6543) to ensure IPv4 compatibility:

```text
postgresql://postgres.[project-id]:[password]@[pooler-host].pooler.supabase.com:6543/postgres
```

### 1.3 Enable email auth

Go to **Authentication → Providers → Email** and make sure it is enabled.

### 1.4 Add the redirect URL

Go to **Authentication → URL Configuration** and add the following to **Redirect URLs**:

- Local dev: `http://localhost:5173/clinician`
- Production (if deploying): `https://your-frontend-domain.com/clinician`

> This is required for magic link emails to redirect back to the app correctly.

### 1.5 Create your first clinician account

The login flow is self-registering — entering any email on the `/login` page and clicking the magic link will create the account automatically. No manual setup needed.

---

## 2 — Backend setup

```bash
cd backend
uv sync
cp .env.example .env
```

Open `backend/.env` and fill in the values:

```env
FRONTEND_ORIGIN=http://localhost:5173

# Supabase (from step 1.2)
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_DB_URL=postgresql://postgres.[project-id]:[password]@[pooler].supabase.com:6543/postgres
SUPABASE_JWT_SECRET=your-jwt-secret

# FHIR — leave defaults for local dev (mock data bypasses this)
FHIR_BASE_URL=https://sandbox.healthx.gov.sg/api/FHIR/R4/
FHIR_ACCESS_TOKEN=your-healthx-token   # only needed for live sandbox

# LLM — set provider and the matching key
LLM_PROVIDER=anthropic                 # or: openai / gemini
ANTHROPIC_API_KEY=your-key
OPENAI_API_KEY=your-key
GEMINI_API_KEY=your-key
```

Start the backend:

```bash
uv run uvicorn app.main:app --reload --port 8000
```

Verify it's running:

- Health check: <http://localhost:8000/health>
- API docs: <http://localhost:8000/docs>

The database tables (`patients`, `care_plan_translations`, `families`, `family_members`) are created automatically on startup via `init_db`.

---

## 3 — Frontend setup

```bash
cd frontend
npm install
cp .env.example .env
```

Open `frontend/.env` and fill in:

```env
VITE_API_BASE_URL=http://localhost:8000

# Supabase (same project as backend — from step 1.2)
VITE_SUPABASE_URL=https://your-project-id.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
```

Start the frontend:

```bash
npm run dev
```

Open <http://localhost:5173>.

---

## 4 — End-to-end walkthrough

1. Go to <http://localhost:5173/login>
2. Enter your email and click **Send magic link**
3. Click the link in the email — you'll be redirected to `/clinician`
4. Select a patient (use `mock-oncology-123` for local dev — no FHIR credentials needed)
5. Click **Fetch Patient Data**
6. Choose an audience (Family or Patient) and click **Generate Summary**
7. Edit the AI draft if needed, then click **Approve & Generate Link**
8. Copy the family link and open it in a new tab — this is the patient/family view at `/family/:fid/member/:mid`

---

## 5 — Tests & linting

```bash
cd backend
uv run pytest -v          # full suite, all mocked — no live DB or LLM needed
uv run ruff check .       # lint
uv run ruff format .      # format
```

```bash
cd frontend
npm run lint              # tsc --noEmit
```

---

## 6 — Deployment (Render)

`render.yaml` defines two services. Set the following environment variables on the Render dashboard for each service.

### Backend service

| Variable | Value |
| --- | --- |
| `FRONTEND_ORIGIN` | Your frontend URL, e.g. `https://mgc-frontend.onrender.com` |
| `SUPABASE_URL` | From Supabase dashboard |
| `SUPABASE_KEY` | From Supabase dashboard |
| `SUPABASE_DB_URL` | Transaction pooler connection string (port 6543) |
| `SUPABASE_JWT_SECRET` | From Supabase dashboard → Settings → API → JWT Secret |
| `LLM_PROVIDER` | `anthropic`, `openai`, or `gemini` |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` | Whichever provider you chose |
| `FHIR_BASE_URL` | Synapxe sandbox URL (or leave default) |
| `FHIR_ACCESS_TOKEN` | Your HealthX bearer token |

### Frontend static site

| Variable | Value |
| --- | --- |
| `VITE_API_BASE_URL` | Your backend URL, e.g. `https://mgc-backend.onrender.com` |
| `VITE_SUPABASE_URL` | From Supabase dashboard |
| `VITE_SUPABASE_ANON_KEY` | From Supabase dashboard |

After deploying, add your production frontend URL to the Supabase redirect URLs list (Authentication → URL Configuration).

---

## Repo layout

```text
mgc-sigma-v9/
├── backend/
│   ├── app/
│   │   ├── main.py           create_app() factory + `app` ASGI entry
│   │   ├── config.py         Settings (env) + path anchors
│   │   ├── schemas.py        Pydantic models + validation sets
│   │   ├── dependencies.py   JWT verification dependency (Supabase-issued tokens)
│   │   ├── routers/          health, clinician, family
│   │   ├── services/         fhir · images · tts · summaries · prompts · llm/ (provider abstraction)
│   │   └── db/               Supabase CRUD — patients, care_plan_translations, families, family_members
│   ├── scripts/              Ops scripts — seed_healthx, synthea_to_fhir
│   ├── mock_data/            Synthetic FHIR fixture — Tan Mei Ling, NCCS oncology
│   └── tests/                pytest suite (fully mocked)
└── frontend/
    └── src/
        ├── lib/supabase.ts   Supabase client singleton
        ├── components/
        │   └── AuthGate.tsx  Session check + redirect-to-login guard
        └── pages/
            ├── LoginPage.tsx     Magic link email form
            ├── ClinicianPage.tsx Clinician dashboard
            └── FamilyPage.tsx    Patient/family summary viewer
```

## Routes

| URL | Auth | Description |
| --- | --- | --- |
| `/` | Public | Welcome screen + backend health check |
| `/login` | Public | Magic link email form |
| `/clinician` | Clinician (JWT) | Patient selector, FHIR data, AI draft, Approve |
| `/family/:fid/member/:mid` | Public (two-part URL token) | Patient/family summary viewer |
