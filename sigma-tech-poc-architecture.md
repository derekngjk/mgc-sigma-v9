# Sigma Tech v9 – Proof of Concept Technical Architecture & Engineering Execution Plan

This document outlines the revised technical architecture and itemized engineering execution plan for a Proof of Concept (PoC) of Sigma Tech v9.

The objective of this PoC is to demonstrate the core value proposition—extracting FHIR data, translating it into empathetic analogies via AI, and validating the Human-in-the-Loop (HITL) workflow—without the overhead of enterprise security, real SMART on FHIR SSO, or production infrastructure.

---

## 1. Executive Architecture Summary (PoC Edition)

### High-Level Overview

The PoC will operate as a standalone web application that visually simulates being embedded inside the Epic EHR. It will connect to the Epic Open FHIR Sandbox (using synthetic patient data) rather than a live hospital environment. Background workers and proactive monitoring are replaced with user-triggered actions to simplify the architecture while proving the core AI translation capability.

### Core Technologies & Architectural Patterns

| Component | Technology |
|-----------|-----------|
| **Architecture Pattern** | Monolithic frontend with a lightweight synchronous API backend |
| **Integration Standard** | Epic Open FHIR R4 Sandbox (unauthenticated/open endpoints for synthetic data) |
| **Backend Framework** | Python (FastAPI) – lightweight and ideal for rapid API development and LLM integration |
| **Frontend Framework** | React.js / TypeScript with TailwindCSS – deployed as a single application with two routing namespaces (one simulating the Clinician View, one simulating the Family View) |
| **AI/NLP Engine** | Standard OpenAI API (GPT-4o), Anthropic API (Claude), or Google Gemini API (gemini-3.5-flash). Constraint: Strictly utilizing synthetic Sandbox data, meaning HIPAA compliance is not required for this phase |
| **Database** | Supabase (PostgreSQL) – normalized schema with `patients` and `care_plan_translations` tables |
| **Infrastructure** | PaaS deployment (e.g., Render, Heroku, or Vercel) for rapid iteration and zero DevOps overhead |

---

## 2. System Design & Data Flow (PoC Edition)

### Component Interaction & Data Flow

1. **Simulated Launch**: The user opens the React web app and selects a synthetic "Patient ID" from a dropdown. This simulates the context-aware launch of a SMART on FHIR app.

2. **Data Ingestion**: The frontend requests data for this Patient ID from the FastAPI backend. The backend executes a synchronous HTTP GET request to `https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4/` (Epic Open Sandbox) fetching Condition.Read, CarePlan.Read, and DocumentReference.Read.

3. **On-Demand NLP**: The backend parses the raw FHIR JSON, constructs a prompt containing the clinical data and the target audience parameter, and synchronously calls the LLM API.

4. **HITL Mock UI**: The React app displays the raw clinical data on the left and the AI-generated draft on the right. The user (acting as the clinician) edits and clicks "Approve".

5. **State Management**: The backend saves the approved text and metadata into a normalized Supabase database.

6. **Simulated Delivery**: The Clinician UI displays a "Magic Link" URL containing the translation record's UUID.

7. **Patient Viewer Mock**: Opening the Magic Link navigates to the Patient Viewer route in the React app, which fetches the approved text from Supabase and displays it in a mobile-friendly layout.

---

## 3. Technical Constraints & Considerations (PoC Edition)

### Constraint 1: Epic Sandbox Limitations

**Bottleneck**: The Epic Open Sandbox contains limited, read-only synthetic data. Not all patients have complex clinical notes or care plans. Writeback (DocumentReference.Create) is not supported in the open sandbox.

**Mitigation**: 
- Pre-select 3-5 specific synthetic Patient IDs from the sandbox that have rich data
- Hardcode fallback mock JSON data in the backend if the sandbox fails or returns empty responses
- Omit the writeback feature; mock the UI success state instead

### Constraint 2: Synchronous LLM Latency

**Bottleneck**: Waiting 5-10 seconds for an LLM to generate text during a synchronous API call can result in a poor demo experience or HTTP timeouts.

**Mitigation**: 
- Implement a skeleton loading state/spinner in the React UI while the API request is pending
- Use a streaming response from the LLM if latency exceeds 5 seconds

### Constraint 3: Data Privacy (Strict Enforcement)

**Bottleneck**: Connecting a public LLM API to healthcare data.

**Mitigation**: 
- Explicitly hardcode guardrails to ensure only sandbox API endpoints (`fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4`) are used
- Add a banner to the UI stating: "PoC Environment: Synthetic Data Only. Do not input Real PHI."

---

## 4. Itemized Engineering Task Breakdown

### Epic 1: PoC Foundation & Setup

#### Task 1.1: Initialize Mono-Repo & Cloud PaaS

**Technical Details**: Scaffold a Git repository containing a `frontend/` (React/Vite) and `backend/` (FastAPI). Configure deployment pipelines to a PaaS (e.g., Render or Railway) for quick public URL access.

**Dependencies**: None

**Acceptance Criteria**: Both backend API (returning a 200 OK health check) and frontend (displaying a basic welcome screen) are live on public URLs.

#### Task 1.2: Setup Supabase State Store

**Technical Details**: Implement a normalized schema in Supabase (PostgreSQL) consisting of `patients` and `care_plan_translations` tables. Use `psycopg3` for idempotent schema auto-initialization on startup.

**Dependencies**: Task 1.1

**Acceptance Criteria**: Backend can successfully create, read, and update records in the Supabase database.

### Epic 2: Epic Open Sandbox Integration

#### Task 2.1: Implement FHIR Sandbox Fetcher

**Technical Details**: Create a Python service to query the Epic Open Sandbox. Implement Patient.Read and Condition.Read. Map the JSON response to extract patient demographics and problem lists.

**Dependencies**: Task 1.1

**Acceptance Criteria**: Sending a GET request to the FastAPI endpoint `/api/patient/{epic_patient_id}` returns a cleaned JSON object containing demographics and a list of active conditions extracted from the Epic Sandbox.

#### Task 2.2: Mock Data Fallback Mechanism

**Technical Details**: Because Sandbox data can be sparse, create a static JSON file containing a rich, complex clinical scenario (e.g., an Oncology care plan with complex jargon). If the Sandbox fetch fails or returns insufficient data, fallback to this JSON.

**Dependencies**: Task 2.1

**Acceptance Criteria**: System successfully injects the hardcoded complex clinical scenario when a specific test Patient ID (e.g., `mock-oncology-123`) is requested.

### Epic 3: AI Prompt Engineering

#### Task 3.1: Develop Translation & Analogy Prompt

**Technical Details**: Integrate the OpenAI Python SDK. Write a system prompt that enforces strict guidelines:

> "You are a medical translator. Translate the following clinical text for a [target_audience]. Use a relatable analogy based on the condition."

Expose this as an endpoint `/api/generate`.

**Dependencies**: Task 2.1

**Acceptance Criteria**: Endpoint accepts clinical text and returns a JSON payload containing the simplified text and the identified analogy.

### Epic 4: Frontend Development (Mock UIs)

#### Task 4.1: Build Clinician Dashboard (Mock EHR UI)

**Technical Details**: Build a React route (`/clinician`). Design the UI to look like an embedded EHR tab. Create a dropdown to select a "Test Patient", a "Fetch Data" button, and a side-by-side view showing Raw Data vs. AI Draft.

**Dependencies**: Tasks 1.1, 2.1, 3.1

**Acceptance Criteria**: User can select a patient, view loading states, see the generated AI text next to the raw FHIR data, edit the text in a text box, and click "Approve."

#### Task 4.2: Build Approval & Link Generation Flow

**Technical Details**: When "Approve" is clicked in the UI, send the final text to the backend to update the Supabase record status to "Approved". The backend returns the `id` (UUID). The frontend displays a mock modal: "Message Sent! Family Link: `[baseUrl]/family/{uuid}`".

**Dependencies**: Task 1.2, Task 4.1

**Acceptance Criteria**: Approving the text successfully updates the DB and surfaces a clickable URL for the family view.

#### Task 4.3: Build Patient/Family Mobile Viewer

**Technical Details**: Build a React route (`/family/:id`). Design it with a mobile-first CSS approach. On load, it fetches the summary from `/api/communications/{id}`.

**Dependencies**: Task 4.2

**Acceptance Criteria**: Navigating to the generated link displays a clean, consumer-friendly interface showing the approved medical analogy and simplified text. It must display a 404 if an invalid UUID is provided.
