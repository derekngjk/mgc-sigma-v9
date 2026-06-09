<!-- markdownlint-disable MD024 -->
# MGC PoC — Implementation Notes

This document records the actual technical decisions made during implementation, the reasoning behind each, and where they diverged from the original architecture plan. It is a living record — updated as each task completes.

---

## Task 1.1 — Foundation Scaffold

**Files:** `backend/main.py`, `frontend/src/App.tsx`, `render.yaml`

### What was built

A minimal FastAPI backend with two routes (`GET /health`, `GET /`) and a React frontend that calls the health endpoint on load and displays the result. Deployment config (`render.yaml`) was wired for two Render services from the start.

### Decisions

**Single-file backend (`main.py`):** All routes live in one file for now. At PoC scale (5–6 routes total), a module-per-route structure would be premature. When the file grows past ~150 lines of route logic, splitting becomes worthwhile.

**CORS configured from env var (`FRONTEND_ORIGIN`):** Rather than hardcoding `localhost:5173`, the allowed origin is read from an env var with a local default. This means the same backend binary works for local dev and on Render without a code change — only the env var differs.

**FastAPI lifespan (not `@app.on_event`):** The `@app.on_event("startup")` decorator is deprecated in FastAPI 0.93+. The `@asynccontextmanager` lifespan pattern was used from the start to avoid having to migrate it later.

---

## Task 1.2 — SQLite State Store

**Files:** `backend/db.py`, `backend/main.py`, `backend/tests/test_task_1_2.py`

### What was built

A `db.py` module with four functions (`init_db`, `create_communication`, `get_communication`, `update_communication`) backed by stdlib `sqlite3`. `main.py` calls `init_db` in its lifespan handler so the table exists before any request is served.

### Schema decisions

The original architecture spec defined six columns. After reviewing the Epic Open FHIR R4 API, four were added:

| Column added | Reason |
| --- | --- |
| `epic_patient_id` | Every record must trace back to the patient ID that was fetched. Without this, you cannot correlate a `Communications` row with the FHIR data that produced it. Epic Sandbox patient IDs are Base64-encoded strings (e.g. `eovIMNNn7tHBQwLGAXNRRw3`). |
| `fhir_source` | The PoC has two data paths — live Epic Sandbox and a hardcoded mock fixture. Storing which path was used makes the record self-describing and avoids ambiguity during demos or debugging. Values: `"sandbox"` or `"mock"`. |
| `target_audience` | The LLM prompt in Task 3.1 takes a `target_audience` parameter (`"patient"` or `"family"`). Storing it alongside the output ties the summary to the prompt that generated it, making the record reproducible and auditable. |
| `approved_at` | The HITL approval step is the core product differentiator. A separate timestamp for the approval event (vs. `created_at` for record creation) gives a minimal but meaningful audit trail. `update_communication` sets this automatically when `status` is flipped to `"Approved"`. |

### Implementation decisions

**No ORM:** `sqlite3` from stdlib is used directly. An ORM (SQLAlchemy, Tortoise) would add a dependency and configuration overhead that isn't justified for a single table. Raw SQL is readable at this scale.

**`_UPDATABLE_FIELDS` whitelist:** `update_communication` accepts `**kwargs` but silently drops any key not in the whitelist set. This prevents callers from accidentally overwriting `id`, `created_at`, or `epic_patient_id` through a typo. The f-string SQL is safe because field names are constrained to the whitelist, not derived from user input — annotated with `# noqa: S608` to suppress the linter warning.

**`db_path` as a parameter (not a global):** Each function takes `db_path: str` explicitly rather than reading a module-level global. This makes the DB path injectable in tests via `tmp_path`, with no monkeypatching of module state required. The module-level `DB_PATH` lives only in `main.py`, which owns the app lifecycle.

**`approved_at` auto-set in `update_communication`:** When `status="Approved"` is passed and `approved_at` is not explicitly provided, the function sets it automatically. This keeps the approval logic in one place and prevents callers from forgetting to set the timestamp.

### Testing decisions

**TDD (red → green):** Tests were written before `db.py` existed. They failed with `ImportError` on the first run, confirming the contract before any implementation. This pattern is carried through all subsequent tasks.

**`tmp_path` fixture for DB isolation:** Each test gets its own temporary SQLite file via pytest's `tmp_path` fixture. Tests never share state across runs. No mocking of sqlite3 — the tests run against a real (temporary) database, which catches schema issues that mocks would silently hide.

**ISO-8601 regex validation:** `created_at` and `approved_at` are stored as strings. Tests use a regex (`r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+\d{2}:\d{2}$"`) to verify format rather than just asserting non-null. This caught an earlier version that was storing UTC timestamps without timezone info.

---

## Tasks 2.1 + 2.2 — FHIR Sandbox Fetcher + Mock Fallback

**Files:** `backend/fhir.py`, `backend/mock_data/mock-oncology-123.json`, `backend/main.py`, `backend/tests/test_task_2_1.py`

Tasks 2.1 and 2.2 were implemented together. The mock fallback is not a separate code path bolted on afterward — it shares the same parser as the live path, so both are tested by the same suite.

### What was built

`fhir.py` is a self-contained module with one public entry point (`fetch_patient_data`) and two internal helpers (`_fetch_from_sandbox`, `_parse_fhir_bundle`). `main.py` imports only `fetch_patient_data` plus the two exception classes. The `GET /api/patient/{epic_patient_id}` route calls `fetch_patient_data`, creates a Draft `Communications` record, and returns a `PatientResponse`.

### FHIR resource decisions

The original spec listed `Patient.Read` and `Condition.Read`. `CarePlan.Read` was added after reviewing the Epic FHIR R4 API because:

- `CarePlan` contains the treatment activities and goals that are the richest source material for the LLM to generate an analogy from.
- A summary built only from `Condition` would describe *what is wrong* but not *what is being done about it* — which is exactly what a patient/family most wants to understand.
- The Epic Open Sandbox has CarePlan data for the same synthetic patients that have Condition data, so there is no additional availability risk.

### Module structure decisions

**`fhir.py` separated from `main.py`:** All FHIR logic — HTTP calls, parsing, mock loading, exceptions — lives in `fhir.py`. `main.py` contains only route wiring and Pydantic models. This keeps the boundary clear: `main.py` owns HTTP concerns, `fhir.py` owns FHIR concerns. When Task 3.1 adds an LLM module, the same pattern will apply (`llm.py` separate from `main.py`).

**`_parse_fhir_bundle` is pure (no I/O):** The parser takes a dict and returns a dict. It never reads files or makes network calls. This makes it independently unit-testable (Group D tests) without any HTTP mocking or fixture setup. The same function parses both live sandbox responses and the mock JSON, ensuring both paths produce identical output shapes.

**Single public entry point:** `main.py` imports only `fetch_patient_data` from `fhir.py` (plus the two exception classes for error mapping). The internal helpers (`_fetch_from_sandbox`, `_parse_fhir_bundle`) are prefixed with `_` — they are imported directly in tests only, which is an accepted pattern for testing private helpers without exposing them to the wider application.

**Custom exception hierarchy (`FHIRError` → `PatientNotFoundError`):** Two exception classes rather than returning sentinel values or HTTP status codes from `fhir.py`. This keeps `fhir.py` HTTP-agnostic — it raises domain exceptions, and `main.py` maps them to HTTP status codes (`PatientNotFoundError` → 404, `FHIRError` → 502). If `fhir.py` were reused in a non-HTTP context (CLI, background job), it would still behave correctly.

**`httpx` moved to `requirements.txt`:** `httpx` was previously only in `requirements-dev.txt` because it was only needed by `TestClient`. Once `_fetch_from_sandbox` uses it at runtime, it becomes a production dependency.

**`PatientNotFoundError` raised inside the `try/except` block:** The `except` only catches `httpx.TimeoutException` and `httpx.NetworkError`. `PatientNotFoundError` (which inherits from `FHIRError`, not from any `httpx` exception) propagates through untouched. This is intentional — a 404 from the sandbox is not a network failure; it is a valid response that means the patient does not exist.

### Mock data decisions

**`mock-oncology-123.json` stores the same three-key bundle shape as the live fetcher returns:** Both paths (`load_mock_patient` and `_fetch_from_sandbox`) return `{"patient": ..., "conditions": ..., "care_plans": ...}`, which is then passed to `_parse_fhir_bundle`. This means there is exactly one parser to maintain and test, and the mock data is structurally validated by the same parser that runs against the live sandbox.

**Resolved condition included intentionally:** The mock fixture includes "Iron deficiency anaemia" with `clinicalStatus.coding[0].code == "resolved"`. This condition must *not* appear in the response — it is present specifically to test that `_parse_fhir_bundle` filters correctly. A fixture with only active conditions would not catch a regression in the filter logic.

**Oncology scenario chosen over a simpler one:** The HITL value proposition is clearest when the clinical language is most opaque. Oncology jargon ("invasive ductal carcinoma", "neoadjuvant chemotherapy", "ddAC-T regimen") is significantly harder for a layperson to understand than, say, hypertension or a broken arm. This makes the LLM translation in Task 3.1 demonstrably valuable during a demo.

### Testing decisions

**`monkeypatch.setattr("fhir._fetch_from_sandbox", ...)` instead of `respx`:** The sandbox tests patch `_fetch_from_sandbox` directly rather than intercepting HTTP at the transport layer. This avoids adding `respx` as a dependency and keeps the mock surface minimal — exactly one function is replaced, leaving all other logic (parsing, DB writes, response serialisation) exercised for real. `respx` would be worth adding if we needed to test redirect handling, streaming, or header inspection, but none of those apply here.

**Function-scoped isolated DB in Task 2.1 tests:** Unlike the module-scoped `TestClient` in `conftest.py` (used by Task 1.1 health tests), Task 2.1 tests use a function-scoped `client` fixture that patches `main.DB_PATH` to a `tmp_path`-isolated DB. Each test gets a clean database, preventing state leakage between tests that write `Communications` records. The Task 1.1 tests don't write to the DB so module scope is appropriate there; the Task 2.1 tests do, so function scope is required.

---

## Task 3.1 — LLM Translation

**Files:** `backend/llm.py`, `backend/main.py`, `backend/tests/test_task_3_1.py`

### What was built

A `llm.py` module with two functions (`generate_summary`, `_call_llm`) that translate a stored FHIR clinical JSON payload into a patient/family-friendly summary via an LLM. `main.py` exposes this as `POST /api/generate`, which fetches the existing `Communications` record, calls the LLM, stores the result, and returns it. Both Anthropic and OpenAI are supported; `LLM_PROVIDER` env var selects at runtime.

### Provider decisions

**Dual-provider via env var (`LLM_PROVIDER`):** Rather than picking one provider, a `LLM_PROVIDER=anthropic|openai` env var selects the active SDK. This lets the same codebase work with whichever key is available in a given environment — useful during development when one key may not be available, and during demos where the operator may have a preference.

**Lazy SDK imports inside `_call_llm`:** Both `anthropic` and `openai` are in `requirements.txt`, but neither is imported at module top level. The import happens inside `_call_llm` only when that provider is active. This avoids import errors in environments where only one API key is set, and prevents both SDKs from initialising when only one is needed.

**`LLMConfigError` (503) vs `LLMError` (502):** Two exception classes mirror the `fhir.py` pattern. `LLMConfigError` indicates a misconfigured environment (missing API key, unknown provider) — a 503 tells the caller the service isn't ready, distinct from a 502 which indicates the upstream LLM API itself failed. Callers can handle these differently: a 503 means fix the deployment config; a 502 means retry or surface a fallback.

### Module structure decisions

**`llm.py` separated from `main.py`:** All LLM logic — prompt construction, provider dispatch, exceptions — lives in `llm.py`. `main.py` only handles request/response wiring and error mapping. This mirrors the `fhir.py` separation established in Tasks 2.1/2.2.

**Single public entry point (`generate_summary`):** `main.py` imports only `generate_summary` and the two exception classes. `_call_llm` is private (prefixed `_`) and imported directly only in tests — the same pattern used for `_fetch_from_sandbox` in `fhir.py`.

**Prompt contains both raw text and audience inline:** The full prompt is constructed in `generate_summary` and passed as a single string to `_call_llm`. This keeps `_call_llm` provider-agnostic — it receives only a string and returns a string, with no knowledge of the prompt's structure. This makes it straightforward to swap provider implementations without changing prompt logic.

### DB decisions

**`target_audience` added to `_UPDATABLE_FIELDS`:** The initial FHIR fetch creates a record with `target_audience="family"` as a default. When `/api/generate` is called with a different audience (e.g. `"patient"`), the record is updated to reflect the audience that was actually used to generate the summary. Without this update, the stored record would not accurately represent the prompt that produced the `ai_summary_text`.

### Testing decisions

**`seeded_comm_id` fixture creates a real DB record:** Rather than posting to `/api/patient/...` first, the generate tests seed a `Communications` record directly via `db.create_communication`. This keeps each test focused on the generate path, avoids dependencies on the FHIR module, and is faster (no route call overhead).

**`_call_llm` monkeypatched, not the SDK:** Tests patch `llm._call_llm` directly rather than mocking Anthropic or OpenAI HTTP transport. This avoids adding a transport-mocking library and keeps the mock surface minimal — only the final SDK call is replaced. All prompt construction and exception mapping is exercised for real.

**Group D tests capture the prompt string:** `test_generate_summary_passes_raw_text_in_prompt` and `test_generate_summary_passes_audience_in_prompt` use a capturing lambda that appends the prompt to a list before returning the mock summary. This verifies that `generate_summary` correctly embeds both inputs into the prompt without inspecting implementation internals beyond what the function contract requires.

---

## Cross-cutting decisions

### Dependency management

`requirements.txt` is production-only. `requirements-dev.txt` starts with `-r requirements.txt` so a single `pip install -r requirements-dev.txt` sets up a complete development environment. This means production and development dependency trees are always in sync.

### Environment variables

All environment-specific values are read at module load time via `os.getenv` with safe local defaults. No value is hardcoded in logic. The pattern is:

```python
SOME_VALUE = os.getenv("SOME_VAR", "safe-local-default")
```

This makes the codebase portable between local dev, CI, and Render without any code changes.

---

## Task 4.2 — Approval + Magic Link Flow

**Files:** `backend/main.py`, `backend/tests/test_task_4_2.py`, `frontend/src/pages/ClinicianPage.tsx`

### What was built

A `POST /api/communications/{id}/approve` endpoint that persists the clinician's final edited text, flips the record to `"Approved"` (auto-setting `approved_at` via the existing `update_communication` logic), and returns a `family_link` URL pointing to the `/family/:id` route. The frontend `handleApprove` stub was replaced with a real async fetch; on success the two-column layout gives way to a success card showing the copyable link and a "Start New Patient" reset.

### Backend decisions

**`family_link` constructed from `frontend_origin`:** The backend already holds `frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")` for CORS configuration. Reusing it to build the magic link keeps the URL consistent with the actual frontend origin in every environment (local, Render) without adding a new env var.

**Two `get_communication` calls:** The route calls `get_communication` before the update (to check existence) and again after (to read the auto-set `approved_at` timestamp). The alternative — returning a hardcoded `datetime.now()` — would risk a small clock skew between what's returned and what's stored. Reading from DB after write guarantees the response reflects the exact value persisted.

**No 409 on re-approval:** The endpoint allows approving an already-approved record. At PoC scale there is no business rule against re-approving a revised draft, and adding a guard would complicate the demo flow. If idempotency becomes a concern, a 409 check is a one-line addition.

### Frontend decisions

**`approveError` surfaced via existing `generateError` prop slot:** Rather than adding a new prop to `AiDraftPanel`, approve errors are passed as `generateError={generateError ?? approveError}`. Both are "right-panel action errors" and display identically — no UI distinction is needed between "generate failed" and "approve failed".

**Success card replaces the two-column grid:** When `stage === 'approved'`, the grid is conditionally hidden (`stage !== 'approved'` guard) and the success card is shown instead. This avoids a layout flash and makes the approved state feel conclusive rather than additive.

**"Start New Patient" resets all state:** The reset clears all fourteen state variables back to initial values, returning to `'idle'`. This is preferable to a page reload (which would lose the patient selector state) and avoids stale `commId`/`draftText` values leaking into a new session.

---

## Cross-cutting decisions

### No async in business logic

`db.py` and `fhir.py` are fully synchronous. FastAPI supports sync route handlers natively (it runs them in a thread pool). The PoC has no concurrency requirements that would justify async DB or HTTP calls at this stage. Mixing sync and async code in a PoC adds cognitive overhead with no benefit.

---

## Task 4.1 — Clinician Dashboard UI

**Files:** `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/pages/ClinicianPage.tsx`

### What was built

A `/clinician` React route that implements the full clinician workflow: patient selection, FHIR data fetch, AI summary generation, inline editing, and an Approve button (wired to `console.log` placeholder; real endpoint in Task 4.2). Routing was added to `main.tsx` (`BrowserRouter`) and `App.tsx` (`Routes`). The welcome screen at `/` was preserved and gained a "Open Clinician View →" link.

### Design research and rationale

UI design decisions were grounded in three reference points:

**1. Epic Hyperspace embedded app conventions** — Epic's Hyperspace uses a dark-navy top chrome (`bg-slate-800`), with content panels on neutral backgrounds. The top bar and PHI warning banner replicate this pattern to make the PoC feel contextually embedded rather than like a generic web app. Source: [Embed AI Inside Epic via SMART on FHIR (Taction)](https://www.tactionsoft.com/blog/embed-ai-inside-epic-smart-on-fhir/), [Healthcare UX Done Right: Epic Systems (Medium)](https://medium.com/@blessingokpala/healthcare-ux-done-right-epic-systems-and-the-future-of-patient-centered-design-b943966a63f7).

**2. Nabla Copilot / ambient AI scribe layout** — Nabla and Abridge both use a side-by-side layout where source data (transcript or chart) sits left, and the AI-generated draft sits right. The clinician edits the draft in place before finalising. This directly maps to our two-column grid: raw FHIR data left, editable textarea right. Source: [Nabla: AI Copilot for Clinicians](https://www.nabla.com/).

**3. JAMIA study on AI-drafted patient portal messages** — Research on real clinician usage found that reviewing AI drafts adds ~135% time overhead per message compared to writing from scratch. The design implication: minimise clicks between "see draft" and "approve". The layout puts Generate and Approve as the only two actions in the right panel, with no modals or confirmation dialogs in the way. Source: [Utilization of Generative AI-drafted Responses — npj Digital Medicine](https://www.nature.com/articles/s41746-025-01972-w).

### Lo-fi wireframe

```txt
┌──────────────────────────────────────────────────────────────────────────┐
│ ■ Sigma Tech v9  /  Clinician View          ⚠ PoC · Synthetic Data Only │
├──────────────────────────────────────────────────────────────────────────┤
│  Patient  [mock-oncology-123 — Elena Vasquez (Mock Oncology)  ▾]         │
│           [Fetch Patient Data ▶]                                         │
├─────────────────────────────┬────────────────────────────────────────────┤
│ CLINICAL DATA               │ AI DRAFT                                   │
│ Elena Vasquez, 57 F         │  Audience  [Family ▾]   [Generate ▶]      │
│ Active Conditions           │  ┌──────────────────────────────────────┐  │
│  • Invasive ductal          │  │ Think of cancer cells like weeds...  │  │
│    carcinoma, stage III     │  │ (editable textarea)                  │  │
│  • Chemo-induced nausea     │  └──────────────────────────────────────┘  │
│ Care Plan                   │         [✓ Approve & Generate Link]       │
└─────────────────────────────┴────────────────────────────────────────────┘
```

### Component structure decisions

**Single-file page component:** All sub-components (`Spinner`, `ErrorBanner`, `ClinicalDataPanel`, `AiDraftPanel`) are defined in `ClinicianPage.tsx` as non-exported helpers. At PoC scale with one page, splitting into separate files would add indirection without benefit.

**`Stage` enum drives all conditional rendering:** A single `type Stage = 'idle' | 'fetching' | 'ready' | 'generating' | 'generated'` string union controls which UI elements are enabled or visible. This makes the state machine explicit and ensures buttons can never be in an inconsistent enabled/disabled state.

**`fetchError` shown in the selector bar, not the draft panel:** When a fetch fails (e.g. sandbox unreachable → 502), the error appears inline next to the Fetch button, not inside the two-column layout that hasn't rendered yet. This avoids a layout jump where an empty panel appears just to show an error.

**Approve button fires `console.log` placeholder:** The full approval flow (Task 4.2) requires a `POST /api/communications/{id}/approve` endpoint that doesn't exist yet. The button is present and visually correct (`emerald-600`, enabled only when a generated summary exists) so Task 4.2 is a one-line change — swap the `console.log` for an `await fetch(...)`.

**Color palette: all Tailwind defaults, no custom config:** The dark top bar (`slate-800`), neutral backgrounds (`slate-50`/`slate-100`), indigo action buttons, emerald approve button, and amber warning banner are all from Tailwind's default palette. No theme extensions were needed, keeping `tailwind.config.js` unchanged.
