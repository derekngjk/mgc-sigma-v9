# summary document for synapxe endpoint

## How the PoC works

1. Clinician opens the app
The clinician navigates to /clinician — an Epic Hyperspace-styled dashboard embedded in the EHR. A patient selector dropdown lists available patients (currently mock-oncology-123 — Tan Mei Ling).

2. Fetch patient data
The clinician clicks Fetch Patient Data. The frontend calls GET /api/patient/{id}.

The backend checks if a mock fixture exists at backend/mock_data/{id}.json. For mock-oncology-123 it does, so it loads Tan Mei Ling's synthetic Singapore record (NRIC S6712345A, NCCS oncology patient) instead of hitting the live Synapxe HealthX sandbox. For any real NRIC/patient ID, it calls the Synapxe NGEMR FHIR R4 endpoint with a bearer token, fetching Patient, Condition, and CarePlan resources.

The backend also checks if Tan Mei Ling has a previous approved summary on record. If she does, it computes a three-way condition diff (NEW / ONGOING / RESOLVED) against that baseline. On first visit, all conditions land in ONGOING.

A draft care_plan_translations record is created in Supabase and a comm_id UUID is returned to the frontend alongside the parsed clinical data.

3. Review raw FHIR data
The left panel of the dashboard shows the raw clinical output — active conditions with change badges (green NEW, grey ONGOING, strikethrough RESOLVED) and the active care plan. The clinician reviews this to orient themselves before generating the summary.

4. Generate AI summary
The clinician picks a target audience (Patient or Family) and clicks Generate. The frontend calls POST /api/generate with the comm_id.

The backend fetches the stored FHIR text, constructs a prompt that includes the condition list, care plan, and (if there are changes) a "Changes since last report" section. It calls the configured LLM (Anthropic Claude or OpenAI GPT-4o, selected by LLM_PROVIDER) and stores the resulting plain-language summary back in Supabase.

5. Human-in-the-loop review & approval
The AI summary appears in the right panel as an editable textarea. The clinician reads it, edits any phrasing they want to adjust, then clicks Approve & Generate Link.

The frontend calls POST /api/communications/{id}/approve with the final text. The backend flips the record's status to Approved, timestamps it, and returns a magic link: {FRONTEND_ORIGIN}/family/{comm_id}.

A success card replaces the two-column layout showing the copyable link.

6. Patient/family receives the link
The clinician shares the magic link (e.g. via printout or QR code — QR generation is a planned feature). The patient or family member opens it on their phone.

/family/{comm_id} fetches GET /api/communications/{id}. The backend returns the record only if status is Approved — any other ID gets a 404. The mobile-first viewer displays:

The plain-language summary split into readable paragraphs
A "What's changed since your last visit" section (hidden if nothing changed)
A lock-icon 404 page if the link is invalid
What's gated by pending credentials
The Synapxe HealthX bearer token (FHIR_ACCESS_TOKEN) and the confirmed sandbox URL are still pending HX-IS registration. Until then, all development and demo runs use the mock-oncology-123 fixture — the rest of the pipeline (LLM, Supabase, approval, family viewer) is fully live.

## Who is on Synapxe (and is going to be - argue for future use ig)

Institutions live on NGEMR (accessible via HealthX FHIR today)
NHG — National Healthcare Group (fully live as of 2022–2024)

Tan Tock Seng Hospital (TTSH) — first to go live, July 2022
National Neuroscience Institute (NNI)
Ren Ci Hospital
Ang Mo Kio-Thye Hua Kwan Hospital (AMK-THK)
6 NHG polyclinics
NUHS — National University Health System (fully live as of 2024)

National University Hospital (NUH)
Alexandra Hospital
St Luke's Hospital
National University Polyclinics
Not yet on NGEMR — rolling out 2026–2028
SingHealth is in a phased rollout starting late 2026:

Singapore General Hospital (SGH)
Changi General Hospital (CGH)
KK Women's and Children's Hospital (KKH)
National Cancer Centre Singapore (NCCS) ← where our mock patient Tan Mei Ling is treated
Other SingHealth institutions
SAF medical records integration expected by 2028.

Implication for the PoC
Our mock patient is set at NCCS (a SingHealth institution), which won't be on NGEMR until 2026–2028. For the demo and hackathon, this is fine since we're using synthetic data. But if you want the mock to reference an institution that's already live on the sandbox, TTSH or NUH would be the more accurate choices. Worth considering for the pitch if judges ask.

## Endpoints used

### Backend API endpoints (FastAPI server)

| Method | Path | Called when |
| --- | --- | --- |
| `GET` | `/health` | Welcome screen loads — confirms backend is alive |
| `GET` | `/api/patient/{id}` | Clinician clicks Fetch Patient Data |
| `POST` | `/api/generate` | Clinician clicks Generate |
| `POST` | `/api/communications/{id}/approve` | Clinician clicks Approve & Generate Link |
| `GET` | `/api/communications/{id}` | Family member opens the magic link |

### External endpoints called by the backend

#### Synapxe HealthX NGEMR (FHIR R4)

Three sequential calls are made inside `GET /api/patient/{id}`:

| Method | FHIR endpoint | What it returns |
| --- | --- | --- |
| `GET` | `{FHIR_BASE_URL}/Patient/{id}` | Patient demographics — name, DOB, gender, NRIC identifier |
| `GET` | `{FHIR_BASE_URL}/Condition?patient={id}&clinical-status=active` | Active problem list — conditions the patient currently has |
| `GET` | `{FHIR_BASE_URL}/CarePlan?patient={id}&status=active` | Active treatment plan — activities, goals, medications |

All three carry `Authorization: Bearer {FHIR_ACCESS_TOKEN}` when the token is configured. For the mock patient (`mock-oncology-123`) these calls are bypassed entirely — the fixture is loaded from disk instead.

#### LLM provider

One call is made inside `POST /api/generate`:

| Provider | Endpoint |
| --- | --- |
| Anthropic | `https://api.anthropic.com/v1/messages` |
| OpenAI | `https://api.openai.com/v1/chat/completions` |

Selected by `LLM_PROVIDER` env var.

#### Supabase (PostgreSQL)

Called at every step:

| Operation | Triggered by |
| --- | --- |
| Upsert `patients` row | `GET /api/patient/{id}` |
| Insert `care_plan_translations` row (Draft) | `GET /api/patient/{id}` |
| Update row — write `ai_summary_text` | `POST /api/generate` |
| Update row — set status=Approved, stamp `approved_at` | `POST /api/communications/{id}/approve` |
| Read row — gate on status=Approved | `GET /api/communications/{id}` |

### One-line summary for judges

> The clinician view calls three Synapxe NGEMR FHIR R4 endpoints to pull patient data, passes it to an LLM, and gates delivery of the plain-language summary behind a human approval step before the family can access it via a one-time link.

---

### sources

The sources came from the Explore subagent I spawned to research the question — it searched the web and cited these specific pages:

- [Synapxe NGEMR overview](https://www.synapxe.sg/healthtech/national-programmes/next-generation-electronic-medical-record-ngemr)
- [Synapxe blog: first cluster to onboard NGEMR](https://www.synapxe.sg/blog/national-programmes/first-healthcare-cluster-to-onboard-the-next-generation-electronic-medical-record-ngemr)
- [TTSH NGEMR page](https://www.ttsh.com.sg/About-TTSH/Pages/NGEMR.aspx)
- [Healthcare IT News: NUH, St Luke's, Alexandra Hospital implementation](https://www.healthcareitnews.com/news/asia/nuh-st-lukes-hospital-and-alexandra-hospital-implement-next-gen-emr)
- [Ministry of Defence: SingHealth and SAF NGEMR partnership](https://www.mindef.gov.sg/news-and-events/latest-releases/24oct25-nr/)
- [Synapxe: Centralised SAF and public healthcare records by 2028](https://www.synapxe.sg/news/national-programmes/centralised-saf-public-healthcare-medical-records)
- [HealthX Innovation Sandbox APIs](https://innovation.healthx.sg/apis/)
- [Synapxe: New HealthX Sandbox 2.0](https://www.synapxe.sg/media-releases/innovation/new-healthx-sandbox)
