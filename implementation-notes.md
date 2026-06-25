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

---

## Task 4.3 — Patient/Family Mobile Viewer

**Files:** `backend/main.py`, `backend/tests/test_task_4_3.py`, `frontend/src/pages/FamilyPage.tsx`, `frontend/src/App.tsx`

### What was built

A `/family/:id` React route that the magic link (generated at approval) resolves to. It fetches `GET /api/communications/{id}` and renders the approved AI summary in a mobile-first, patient-facing layout. A matching backend endpoint was added that returns the record only when `status = "Approved"` — unapproved or unknown IDs both return 404.

### Backend decisions

**Single endpoint for two error cases (not found + not approved → 404):** From the family's perspective both cases are the same: "this link doesn't work." Returning 403 for a Draft record would leak information about the record's existence. A uniform 404 with a non-specific detail message (`"Summary not found or not yet approved"`) is the correct behaviour for a public-facing link.

**`condition_diff` defaults to empty categories if NULL:** Records created before the condition tracking feature was added may have a NULL `condition_diff`. The route handles this with a safe default (`{"added": [], "removed": [], "ongoing": []}`) rather than failing with a parse error.

**`FamilyViewResponse` reuses `ConditionDiff`:** The same Pydantic model defined for `PatientResponse` is reused here — no duplication. `ai_summary_text` is `str` (not `Optional[str]`) because the route only returns when status is Approved, and approval requires a non-empty summary text.

### Frontend decisions

**No clinician chrome:** The family page has no dark header bar, no PHI warning banner, and no "PoC" badge. Those elements are appropriate for a clinician tool embedded in Epic; they'd be alarming on a page a patient opens on their phone. The header is minimal: brand name + page title in a light border-bottom bar.

**Changes section hidden on first visit / no changes:** The `ChangesSection` component returns `null` when both `added` and `removed` are empty. On a first visit (all conditions in `ongoing`) or when nothing has changed, there is simply no "What's changed" section — patients don't need to read "nothing changed."

**Paragraphs split on double newline:** The AI summary is split on `\n\n` and each fragment rendered as a `<p>`. This preserves the paragraph structure the LLM naturally produces (it writes 3–4 short paragraphs) without requiring any markdown parser dependency.

**`not_found` state uses a lock emoji and plain language:** A 404 page for a patient should be reassuring, not technical. "This summary isn't available. Please check with your care team." is more useful than a raw 404 message.

---

## Cross-cutting — Condition Change Tracking

**Files:** `backend/db.py`, `backend/main.py`, `backend/llm.py`, `backend/tests/test_change_tracking.py`, `frontend/src/pages/ClinicianPage.tsx`

### What was built

When a clinician fetches a patient who has a previous approved `Communications` record, the system now computes a three-category diff of active conditions compared to that last approved report:

- **added** — conditions present now that were not present at the last approved report
- **removed** — conditions from the last approved report that are no longer active
- **ongoing** — conditions present in both

On a patient's first visit (no prior approved record), all conditions are placed in `ongoing` with `added=[], removed=[]` — semantically correct because there is no previous state to compare against.

The diff is stored in the DB alongside the new record and propagated to both the LLM prompt and the clinician UI.

### Schema decisions

**Two new columns rather than re-parsing FHIR:** The diff is computed at fetch time from the current conditions list and the `conditions_json` stored in the previous approved record. This avoids re-parsing the raw FHIR JSON (which is stored as a serialised string) and keeps the diff logic in one place (`main.py`). The `conditions_json` column stores the parsed, normalised list; `condition_diff` stores the computed three-way result as JSON.

**Migration via `ALTER TABLE ADD COLUMN` with try/except:** `init_db` first runs `CREATE TABLE IF NOT EXISTS` (which defines all columns for a fresh DB), then attempts `ALTER TABLE ADD COLUMN` for the two new columns. SQLite raises `OperationalError` if a column already exists; this is caught and ignored. This gives zero-downtime migration for existing databases without a separate migration tool.

**`condition_diff` is always populated (never NULL):** Unlike an earlier plan variant where only diffs with changes would be stored, every record stores the full three-category object. This simplifies downstream code (family viewer, LLM prompt) — they never need to handle a NULL case.

### Route logic decisions

**Diff computed from set arithmetic:** `added = new - old`, `removed = old - new`, `ongoing = new ∩ old`. Using Python `set` operations ensures correctness even if conditions appear in different orders between visits. Both input lists are normalised (sorted JSON) before storage.

**`get_latest_approved_communication` queries by `approved_at DESC LIMIT 1`:** The most recent approved record is the relevant baseline, not the most recently *created* record. If a clinician fetches a patient, abandons the draft, and then fetches again, only the previously *approved* report is used as the diff baseline.

### LLM prompt decisions

**Condition summary section always injected, "Changes since last report" only when there are changes:** The prompt always includes an `ongoing` list so the LLM has full condition context regardless of whether anything changed. The "Changes since last report" sentence is only appended when `added` or `removed` is non-empty — this prevents the model from mentioning "no changes" on first visits or stable visits, which would be confusing to patients.

### Clinician UI decisions

**Three visual states for conditions:** Green NEW badge (emerald), neutral ONGOING badge (slate, only shown when there is at least one change), and a separate "Resolved since last report" section below the active list with strikethrough text. The ONGOING badge is hidden on first visits (where all conditions are ongoing with no changes) to avoid annotating every condition as "Ongoing" on the very first fetch — the badge only has meaning in comparison to a prior report.

**Resolved conditions shown below active conditions:** Resolved items are not part of the active condition list, so they live in a visually demoted section below. This matches the reading order clinicians would expect: active concerns first, resolved context second.

---

## Task 5.1 — Supabase Migration (Production Standards)

**Files:** `backend/db.py`, `backend/main.py`, `backend/pyproject.toml`, `backend/tests/conftest.py`

### What was built

Migrated the local SQLite database to Supabase (PostgreSQL). The monolithic `Communications` table was normalized into `patients` and `care_plan_translations` tables. Dependency management was moved to `uv`, and `ruff` was introduced for linting and formatting.

### Schema decisions

**Normalized tables:** Rather than one large table, clinical data is now split. `patients` stores demographics (keyed by `epic_patient_id`), while `care_plan_translations` stores the AI summaries and raw text. This aligns with standard RDBMS practices and enables easier scaling (e.g., multiple visits per patient).

**`TIMESTAMPTZ` for all timestamps:** SQLite stored timestamps as strings. Postgres uses `TIMESTAMPTZ` to ensure timezone-aware sorting and auditing.

**Idempotent DDL via `psycopg3`:** `init_db` now uses `psycopg3` to execute a `CREATE TABLE IF NOT EXISTS` script on application startup. This ensures the Supabase instance is correctly configured automatically without manual dashboard intervention.

### Implementation decisions

**Supabase Python Client for transactions:** While `psycopg3` handles the schema initialization, the higher-level `supabase-py` client is used for CRUD operations. This provides a cleaner API and prepares the app for using Supabase Auth/Realtime in the future.

**`db_path` removed from signatures:** The database configuration is now purely environment-driven (`SUPABASE_DB_URL`). Function signatures in `db.py` were cleaned up to remove the legacy `db_path` parameter.

**IPv4/IPv6 compatibility:** Since Supabase direct connections are IPv6-only, the connection string defaults to the **Connection Pooler (port 6543)**, which supports IPv4 environments and prevents "Network is unreachable" errors.

**`uv` and `ruff` adoption:** Moved from `pip` and manual formatting to `uv` for reproducible builds and `ruff` for automated linting and code style enforcement.

### Testing decisions

**Mocked Supabase Architecture:** Real database connections are disabled in tests via a session-scoped `psycopg.connect` mock. The `mock_supabase` fixture uses table-specific side effects to simulate complex CRUD flows (e.g., upserting a patient followed by inserting a translation).

**Regression testing:** The public API response shapes were strictly preserved during the migration. Unit tests confirm that the joined data from multiple tables is correctly flattened into the legacy JSON structure.

---

## Synapxe HealthX Sandbox Migration

**Files:** `backend/fhir.py`, `backend/mock_data/mock-oncology-123.json`, `backend/.env.example`

### What was changed

The project was aligned with the Synapxe HealthX Innovation Sandbox (HX-IS) — Singapore's national NGEMR FHIR R4 sandbox — replacing the generic Epic Open FHIR Sandbox. The FHIR client now targets the Synapxe endpoint and authenticates with a bearer token. The mock patient fixture was updated to reflect Singapore demographics, identifiers, and hospital context.

**Context:** MGC is being submitted to the Medical Grand Challenge 2026 (NUS). Synapxe (Singapore's national HealthTech agency) operates the HealthX Innovation Sandbox, which provides access to NGEMR — Singapore's Epic-based national EMR. The PoC must use Singapore-relevant synthetic data to be credible to local evaluators. API credentials are pending HX-IS registration.

### FHIR endpoint decisions

**Synapxe HealthX as the new default:** `FHIR_BASE_URL` defaults to `https://sandbox.healthx.gov.sg/api/FHIR/R4/`. This is the NGEMR FHIR R4 sandbox endpoint. Because NGEMR is built on Epic, the resource structure (`Patient.Read`, `Condition.Search`, `CarePlan.Search`) and URL path conventions are identical to the Epic FHIR R4 spec — no changes were needed to the request logic itself.

**Bearer token authentication added:** Synapxe's HealthX APIs are gated behind OAuth2. A new `FHIR_ACCESS_TOKEN` env var is read at module load time. When set, `Authorization: Bearer <token>` is injected as a default header on every `httpx.Client` request. When empty (local dev using the mock path), no auth header is sent — the mock fallback triggers before any network call, so the absence of a token does not cause failures during development.

**Parameter renamed `patient_id`:** The internal parameter in `_fetch_from_sandbox` was renamed from `epic_patient_id` to `patient_id`. In the Singapore context the identifier is an NRIC or FIN (e.g. `S6712345A`), not an Epic-format Base64 ID. The public-facing route path (`/api/patient/{epic_patient_id}`) was not renamed to avoid breaking the DB schema and tests — that rename belongs in a dedicated schema migration.

### Mock data decisions

**Patient re-skinned to Singapore context:** Elena Vasquez was replaced with **Tan Mei Ling** (NRIC `S6712345A`, DOB 1967-08-22, female), a realistic Singapore demographic profile. The NRIC uses the standard `S`-prefix format and conforms to the Synapxe FHIR identifier system URI (`https://fhir.synapxe.sg/identifier/nric-fin`).

**Full FHIR `identifier` block added:** The mock patient now carries an `identifier` array with `use: "official"`, a type coding of `NRIC` from `http://terminology.hl7.org/CodeSystem/v2-0203`, and the Synapxe system URI. This mirrors what a real NGEMR patient record returns, ensuring the mock is structurally representative.

**SNOMED CT codes added to conditions:** Each condition entry now includes a `system` and `code` from `http://snomed.info/sct` alongside the display text. This matches NGEMR's coding practice and makes the fixture more realistic for demo purposes. The parser ignores these codes today (`_parse_fhir_bundle` only reads `code.coding[0].display`), but they are present for future use.

**Managing organisation set to NCCS:** `managingOrganization.display` is set to "National Cancer Centre Singapore (NCCS)". Care plan activities and notes reference NCCS/SGH context (NCCS Chemotherapy Suite, SGH Radiology). The oncology scenario itself (ddAC-T neoadjuvant chemotherapy, invasive ductal carcinoma stage III) is unchanged — it remains the strongest demo case for the HITL value proposition.

**Resolved condition preserved:** "Iron deficiency anaemia" with `clinicalStatus.code = "resolved"` is still present in the fixture. This entry exists specifically to test that `_parse_fhir_bundle` correctly filters it out. Removing it would silently eliminate a regression guard.

### Configuration decisions

**`FHIR_ACCESS_TOKEN` documented in `.env.example`:** The new variable is added with a clear comment pointing to `https://innovation.healthx.sg/` for registration. The mock fallback path (`mock-oncology-123`) continues to work with no credentials set, so the local development experience is unchanged.

---

## Family Access Route Refactor

**Files:** `backend/db.py`, `backend/main.py`, `backend/tests/test_task_4_2.py`, `backend/tests/test_family_route.py`, `frontend/src/App.tsx`, `frontend/src/pages/FamilyPage.tsx`

### What was built

The family viewer URL was restructured from `/family/{comm_id}` (a single opaque UUID) to `/family/{fid}/member/{mid}` — a two-part URL where both IDs must match a valid record before the summary is returned. Two new Supabase tables (`families`, `family_members`) underpin the access model.

### Schema decisions

**One `families` row per patient, not per approval:** The `patient_id` column on `families` has a UNIQUE constraint. This means the family group is a stable identity for the patient — the magic link URL never changes across re-approvals. The viewer always resolves to the *latest* approved `care_plan_translations` row for that patient. If this constraint were instead on `care_plan_translation_id`, each approval would generate a new link that families would need to be re-issued.

**`relationship` column on `family_members`:** Currently only `"patient"` is used for the auto-created primary member. The column exists to support additional members (spouse, child) without a schema change — they can be inserted with `relationship="spouse"` etc. This is deliberate future-proofing at zero schema cost.

**No separate access token:** The two-part URL acts as the token. Both `fid` and `mid` are UUIDs (122 bits of entropy combined). A third token parameter would add friction (harder to share as a link or QR code) with negligible additional security at this PoC stage.

### DB function decisions

**`get_or_create_family` and `get_or_create_primary_member` are idempotent:** Both functions check for an existing record before inserting. This makes repeated calls to `approve_communication` safe — re-approving a record returns the same `fid` and `mid`, preserving the stable link.

**`get_family_summary` validates membership before resolving the patient:** The validation query (`family_members` where `id=mid AND family_id=fid`) is the first thing the function does. If it returns empty, the function returns `None` immediately without touching `families` or `care_plan_translations`. This prevents any information leakage — an invalid `mid` reveals nothing about whether `fid` exists.

### Backend route decisions

**`approve_communication` reads `patient_id` from the post-update `get_communication` result:** The `care_plan_translations` record already contains `patient_id` as a FK column; no extra query is needed to resolve the patient. `get_or_create_family` receives it directly.

**Legacy `GET /api/communications/{id}` preserved:** The old endpoint is retained for backward compatibility with `test_task_4_3.py` and any tooling that may call it. The frontend no longer uses it (all family traffic goes through the new endpoint), but removing it would break the existing test suite without a corresponding gain.

### Testing decisions

**`test_family_route.py` covers three distinct 404 causes:** The new test file has separate cases for (1) invalid `fid+mid` pair, and (2) valid pair but no approved summary. These are operationally different failures — the first means the link was forged or corrupted; the second means a clinician hasn't approved yet. Both correctly return 404 with the same message (no information leakage).

**`test_task_4_2.py` updated to assert link format:** The approval test now checks that `family_link` contains both `/family/` and `/member/` substrings rather than asserting the full URL (which would embed generated UUIDs). This is the right level of specificity — the format is contractual, the exact IDs are not.

**Three `side_effect` entries for `care_plan_translations`:** The mock's `execute` method is shared across all chained calls on the same table mock (select, update, insert all return the same mock object). The update call in `update_communication` consumes one entry from the side_effect list. The entries map to: (1) pre-update existence check, (2) the update call itself, (3) post-update read for `approved_at` and `patient_id`.

---

## Feature 3 — Multilingual Translation (EN / ZH / MS / TA)

**Files:** `backend/llm.py`, `backend/db.py`, `backend/main.py`, `backend/tests/test_translation.py`, `backend/tests/test_translation_db.py`, `backend/tests/test_translation_routes.py`, `frontend/src/pages/FamilyPage.tsx`

### What was built

Approved English summaries can now be read in Singapore's four official languages. A language toggle (`EN` / `中文` / `BM` / `தமிழ்`) appears on the family viewer page. Translations are generated on first request (lazy) and cached in a new `translations_json` JSONB column so subsequent requests for the same language are instant. The same `?lang=` query parameter works on both `GET /api/family/{fid}/member/{mid}` and the legacy `GET /api/communications/{id}` endpoint.

### Translation provider decision

**LLM instead of a dedicated translation API:** Azure AI Translator and Google Cloud Translation were both evaluated. Azure was preferred on cost ($10/M chars vs $20/M chars) and simpler auth (single API key vs Service Account JSON). However, both require additional billing credentials. Since the project already has LLM API keys wired up, `translate_summary` reuses the existing `_call_llm` dispatch — no new credentials or services are needed. The LLM also produces more natural-sounding output than a statistical translation model, which matters for patient-facing prose that must preserve a warm, empathetic tone.

**Rejected: Azure Dynamic Dictionary for glossary injection:** Azure's per-request glossary mechanism requires embedding `<mstrans:dictionary>` XML markup in the source text and sending `textType=html`. This is documented as "safe for proper nouns only" and does not work reliably for common medical nouns. The LLM prompt approach is more flexible: the glossary is injected as plain text and the model applies it contextually, handling plurals, case, and sentence position correctly.

### Glossary decisions

**Source: HealthHub A–Z Medications Glossary + Cambridge Dictionary.** HealthHub (healthhub.sg) is the MOH Singapore patient portal and publishes health content in all four official languages. The Cambridge Dictionary bilingual entries for English→Chinese Simplified, English→Malaysian, and English→Tamil were used as a secondary verification source for common clinical terms. Official institution names (NCCS, SGH) were sourced from their respective websites. Every entry in `_CLINICAL_GLOSSARY` in `llm.py` is annotated with which source it came from.

**13 terms × 3 languages, injected into the prompt:** The glossary is formatted as a plain-text reference block (`en_term → target_term`) and embedded in the translation prompt under a "Medical term reference (use these translations)" heading. This ensures the LLM uses the Singapore-specific translation (e.g. `palliative care → 舒缓治疗` per MOH/SingHealth, not `姑息治疗` as used in mainland China) rather than its training-data default. The glossary covers the most likely terms to appear in any of the five mock patient scenarios.

**Condition diff section not translated:** The condition names in `ChangesSection` on the family viewer come directly from FHIR and are stored as English strings. Translating them would require a separate pass and risk inconsistency with clinical identifiers. They are left in English — clinically meaningful to care teams and recognisable to most patients by name.

### Schema decisions

**`translations_json JSONB DEFAULT '{}'` column on `care_plan_translations`:** A single JSONB column stores all language translations for a record as `{"zh": "...", "ms": "...", "ta": "..."}`. Alternatives considered:

| Option | Verdict |
| --- | --- |
| Separate `translations` table with `(comm_id, lang, text)` rows | Overkill for 3 languages; adds a join to every family-viewer request |
| One column per language (`ai_summary_zh`, `ai_summary_ms`, `ai_summary_ta`) | Rigid schema; adding a language requires a migration |
| Single JSONB column | Zero joins, arbitrary languages without schema changes, easy to inspect |

**Idempotent migration via `ADD COLUMN IF NOT EXISTS`:** `init_db` adds the column to the `CREATE TABLE` definition (for fresh databases) and also runs `ALTER TABLE care_plan_translations ADD COLUMN IF NOT EXISTS translations_json JSONB DEFAULT '{}'` (a no-op on fresh databases, a live migration on existing ones). This follows the same migration pattern established in the condition-change-tracking cross-cutting section.

### API design decisions

**Lazy translation via `?lang=` query parameter:** Translation is triggered on the first family-viewer request for a given language, not at approval time. This keeps the approval step fast (no LLM calls beyond the summary itself) and means unused languages never incur a cost. The same endpoint is used for all languages — the frontend just appends `?lang=zh` etc. on language switch.

**Cache check before LLM call:** `get_translation(comm_id, lang)` is a lightweight single-column Supabase query. On a cache hit it returns immediately. On a miss, `translate_summary` is called, then `set_translation` writes the result back. Subsequent requests for the same language are served from the cache.

**Invalid lang → 400, LLM failure → 502/503:** `_VALID_LANGS = {"en", "zh", "ms", "ta"}` is checked at route entry before touching the DB. An unrecognised lang code (e.g. `?lang=fr`) returns 400 immediately. LLM errors map to the same 502/503 pattern used by `POST /api/generate`.

**`lang="en"` short-circuits entirely:** When `lang="en"` (the default), neither `get_translation` nor `set_translation` are called. The English `ai_summary_text` is returned directly. This avoids a Supabase round-trip on every standard (English) family-viewer load.

### Frontend decisions

**`summaryText` decoupled from `data.ai_summary_text`:** `data` is set once on initial load and holds all metadata (patient name, approved date, condition diff). `summaryText` is a separate state string that starts as `data.ai_summary_text` and is updated independently on each language switch. This avoids mutating `data` and keeps the metadata (patient name, condition diff) visible and stable while the summary text swaps.

**`lang` committed on success only:** `setLang(newLang)` is called only after the fetch succeeds. If the translation request fails, `lang` stays pointing at the last successfully displayed language, so the active button remains correct.

**Opacity fade during translation:** The summary container's opacity drops to 40% while `translating` is true, giving the user a clear signal that the current text is being replaced. A spinner appears inline in the button row — not a full-screen overlay — so the patient name, date, and condition diff remain readable while waiting.

**`translating` guard prevents concurrent requests:** `handleLangChange` returns early if `translating` is already true. This prevents double-tapping or rapid switching from firing multiple in-flight LLM calls.

### Testing decisions

**Three test files for three layers:** `test_translation.py` tests the LLM prompt logic in `llm.py` (mocking `_call_llm`); `test_translation_db.py` tests `get_translation` and `set_translation` against the Supabase mock; `test_translation_routes.py` tests the route-level behaviour (lang validation, cache hit, cache miss, error mapping) by monkeypatching `main.*` functions directly.

**Route tests monkeypatch `main.*`, not the Supabase chain:** The route tests patch `main.get_family_summary`, `main.get_translation`, `main.translate_summary`, and `main.set_translation` at the `main` module's namespace (not the source modules). This is necessary because `main.py` uses `from db import ...` and `from llm import ...` — the name bindings in `main` are fixed at import time, so patching the source module would not affect `main`'s references.

**`lang` committed on success tested explicitly:** `test_family_member_cache_miss_translates_and_caches` asserts that `set_translation` is called with exactly `("comm-001", "zh", ZH_TEXT)` — verifying both that the result is cached and that the correct comm_id and lang code are written.

---

## Feature 8 — Delivery Stub (QR Code + Print Handout)

**Files:** `frontend/src/pages/ClinicianPage.tsx`, `frontend/src/pages/FamilyPage.tsx`, `frontend/src/lib/markdown.ts`, `frontend/src/index.css`

### What was built

After a clinician approves a summary, the success card on the clinician dashboard now shows a QR code of the family magic link alongside the existing copy-to-clipboard URL. Both the clinician dashboard and the family/patient viewer gained a **Print Handout** / **Print summary** button that opens a dedicated print window containing the formatted summary text (headings, bold, lists preserved), the patient name, and a footer. The family viewer also gained A−/A+ font size controls that carry through into the print output.

### Clinician success card decisions

**QR code via `react-qr-code`:** The library renders a pure SVG — no canvas, no network call, no server-side generation. The SVG is injected directly into the print window so the printed QR code is a vector graphic at full resolution, not a rasterised screenshot.

**Print shows the summary text, not the QR:** The clinician handout is intended as a paper copy of the care summary to give to the patient at the point of care. The QR code is shown on-screen for point-of-care handoff; the printout contains the approved draft text so the clinician has a readable record.

### Family viewer decisions

**Print button placement:** The "Print summary" button is placed below the condition-changes section — after the patient has read the full summary — rather than at the top. This matches the reading order and avoids the button being the first thing a patient sees.

**Font size controls (A− / A+):** Font size steps from 14px to 26px in 2px increments, defaulting to 18px (slightly above browser default for accessibility). The controls sit inline at the right of the language toggle row so they are discoverable without occupying a separate row. The chosen size is passed directly into the print window CSS so the printed PDF reflects exactly what the patient was reading on screen.

### Print window implementation decisions

**`Blob` + `URL.createObjectURL` instead of `document.write`:** `document.write` ignores `<meta charset="utf-8">` because that tag only instructs the browser how to decode bytes from a URL — `document.write` passes an already-decoded JS string and uses a legacy code path that does not respect the charset hint. Creating a `Blob` with `{ type: 'text/html;charset=utf-8' }` forces the browser to decode the blob's bytes as UTF-8 from the start, which correctly renders Chinese, Tamil, and Malay characters.

**Print triggered from inside the document via `window.onload`:** `win.addEventListener('load', ...)` on a cross-origin popup is unreliable — the event may fire before the listener is registered. Injecting `<script>window.onload=function(){window.print()}<\/script>` into the HTML body means the print dialog is triggered from within the document's own execution context, which is universally reliable.

**CJK font fallbacks:** `system-ui` alone dropped Chinese and Tamil glyphs on some systems (particularly Windows, where `system-ui` maps to Segoe UI). The print font stack explicitly includes `'PingFang SC'`, `'Hiragino Sans GB'`, `'Microsoft YaHei'`, and `'Noto Sans CJK SC'` as fallbacks. The same stack is exported from `lib/markdown.ts` as `PRINT_FONT` and shared by both print handlers.

**Shared `lib/markdown.ts`:** `markdownToHtml`, `openPrintWindow`, `PRINT_FONT`, and `stripMarkdown` live in a single shared module imported by both `ClinicianPage` and `FamilyPage`. This ensures both print handlers stay in sync and eliminates the duplicated strip-and-split logic that previously lived inline in each component.

### Markdown rendering decisions

**`dangerouslySetInnerHTML` + `markdownToHtml` for the web view:** An earlier implementation maintained parallel JSX rendering functions (`renderMarkdown`, `renderInline`) alongside the HTML-string `markdownToHtml` used by the print window. This meant two separate renderers had to be kept in sync. Replacing them with a single `markdownToHtml` call and `dangerouslySetInnerHTML` gives both the web view and the print window a single rendering path. The LLM-generated content is not user-supplied input, so the XSS risk is low for a PoC; a production deployment would add DOMPurify sanitisation.

**Headings use `em` units in both web and print CSS:** Absolute `px`/`rem` heading sizes would not scale with the A−/A+ font size control. Switching to `font-size: 1.2em` / `1.1em` means headings always stay proportionally larger than body text regardless of the chosen base size.

**Translation prompt preserves Markdown markers:** The translation prompt instructs the LLM to "preserve all Markdown formatting markers exactly as they appear (`**bold**`, `*italic*`, `## headings`, `- list items`)". Without this, translations stripped all formatting, making the Chinese/Tamil/Malay output visually flat compared to the bolded English original. Keeping the markers ensures `markdownToHtml` produces consistent HTML structure across all languages.

**`max_tokens=4096` for translation calls:** Tamil Unicode characters cost 2–4 tokens each in most LLM tokenizers, and Malay has longer average word lengths than English. The default `max_tokens=1024` caused Malay and Tamil translations to be cut off mid-sentence. Translation calls now pass `max_tokens=4096` to `_call_llm` while summary generation retains the `1024` default. The `_call_llm` signature was updated to accept `max_tokens` as a keyword argument; test mocks were updated to accept `**kwargs` accordingly.

---

## Feature 9 — Audience-Specific Reports

**Files:** `backend/llm.py`, `backend/db.py`, `backend/main.py`, `frontend/src/pages/ClinicianPage.tsx`, `backend/tests/test_task_3_1.py`

### What was built

The `target_audience` field was expanded from a binary `"patient" | "family"` toggle to four specific recipient types: `"patient"`, `"spouse"`, `"child"`, `"caregiver"`. Each type has a distinct LLM prompt instruction block that shapes tone, framing, and content focus. The clinician selects the intended recipient before generating — the resulting summary and approval link are specific to that person. Running the flow twice for the same patient (once for `"patient"`, once for `"spouse"`) produces two separately written summaries, each with their own unique `/family/:fid/member/:mid` link.

### Why audience-specific, not just "family"

The original `"family"` option was too broad. A spouse supporting a partner through chemotherapy needs different information than an adult child managing a parent's care from a distance, which is again different from a hired caregiver monitoring daily symptoms. Collapsing these into one prompt produced generic text that was neither emotionally appropriate nor practically useful for any specific reader. The audience-specific model lets the LLM tune:

- **patient** — second-person ("you"), empowering, focuses on what the patient is experiencing and what their team is doing
- **spouse** — third-person about the patient, emphasises shared emotional burden, practical caregiving tips, and when to call the team
- **child** — acknowledges the parent-child role reversal, balances practical support with emotional reassurance
- **caregiver** — most clinical of the four; prioritises symptoms to monitor, red-flag signs, and actionable daily guidance over emotional framing

### LLM prompt decisions

**`_SYSTEM_PROMPT_BASE` + `_AUDIENCE_INSTRUCTIONS` dict:** The previous single `_SYSTEM_PROMPT` string used `.format(target_audience=target_audience)` to interpolate the audience label. This produced text like "empathetic language that a family can understand" — a weak instruction that the model largely ignored. Replacing it with a dedicated `_AUDIENCE_INSTRUCTIONS` dict gives each audience type a full paragraph of specific framing guidance, which produces measurably more differentiated output.

**`VALID_AUDIENCES` exported from `llm.py`:** The set of valid audience values lives in `llm.py` alongside the prompt logic that depends on it — not duplicated in `main.py`. `main.py` imports and uses it for route validation. This means adding a new audience type in the future requires one change (adding an entry to `_AUDIENCE_INSTRUCTIONS`) rather than two.

**Markdown formatting enabled in base prompt:** The old `_SYSTEM_PROMPT` ended with "Return plain text only — do not use Markdown". This was a holdover from before `markdownToHtml` and the print window existed. It was removed; the base prompt now explicitly asks for `**bold**`, `## headings`, and `- lists`, consistent with how the family viewer already renders output.

### DB and route decisions

**`create_family_member` is non-idempotent; `get_or_create_primary_member` stays idempotent:** The `"patient"` audience maps to the existing idempotent primary-member creation — re-approving a patient-targeted summary reuses the same stable link. All other audience types call the new `create_family_member`, which always inserts a fresh row. This is intentional: a family might have two adult children who each need their own link, and idempotency on `relationship="child"` would incorrectly collapse them. The clinician runs the full generate-and-approve flow once per intended recipient.

**`_AUDIENCE_MEMBER_NAMES` inline in the route:** The mapping from audience value to display name (`"spouse" → "Spouse / Partner"` etc.) lives inline in `approve_communication` rather than in `db.py`. It is presentation logic (what name appears on the `family_members` row for identification) and does not belong in the data layer.

**`GenerateRequest.target_audience` default changed to `"patient"`:** The old default of `"family"` became invalid. `"patient"` is the most common clinical use-case and the safest default — a summary written for the patient is appropriate for the patient to also share with family if they choose.

### Testing decisions

**Existing `test_task_3_1.py` tests updated:** Both generate tests previously omitted `target_audience`, relying on the `"family"` default. They were updated to pass `"patient"` explicitly. This is the right level of precision — the tests are verifying generate-path behaviour, not audience logic, so a valid concrete value is better than relying on a default.

**No new prompt-content tests for audience framing:** The audience instruction strings are long-form prose injected into the prompt. Testing that a specific word appears in the prompt (as done for `condition_diff` injection) would be brittle — any wording change would break the test. The correct validation of audience-specific output is a human judgement call during demo review, not an assertion over prompt text.

---

## Feature 11 — Audit Trail

**Files:** `backend/db.py`, `backend/main.py`, `backend/tests/conftest.py`, `backend/tests/test_task_4_2.py`

### What was built

A single nullable UUID column, `approved_by_user_id`, was added to `care_plan_translations`. It is populated from the Supabase Auth user ID present in the validated JWT whenever a clinician approves a communication. The column records which clinician account triggered each approval, without changing any existing fields or response shapes.

### Why only `approved_by_user_id`

The roadmap noted three audit gaps: who approved, which patient, and when. `patient_id` was already a FK on every row. `approved_at` was already set on approval. The only missing field was the clinician's identity. One additive column closes the gap without a schema rework.

### Implementation decisions

**Idempotent `ALTER TABLE` migration rather than a schema change to `CREATE TABLE`:** The `CREATE TABLE IF NOT EXISTS` block is the original schema; it is not edited. A separate `ADD COLUMN IF NOT EXISTS` statement runs after it. This pattern, already used for `translations_json`, means the migration is safe to run against both a fresh database (where the column is created as part of the initial table) and any existing database (where Postgres silently skips the `ALTER` if the column is already present).

**`_UPDATABLE_FIELDS` whitelist extended:** `update_communication` filters kwargs through `_UPDATABLE_FIELDS` before passing them to Supabase. Adding `"approved_by_user_id"` to the set is sufficient to allow the approve route to write the value — no new DB function is needed.

**`user.get("id", "")` over `user["id"]`:** The Supabase Auth `/auth/v1/user` response always includes `id`, but `.get` with a fallback guards against malformed or unexpected token shapes without raising a `KeyError` mid-request. The empty string fallback is safe: a UUID column storing `""` would fail Postgres type validation and be caught at the DB layer, making the failure visible rather than silent.

**No response shape change:** `ApproveResponse` still returns `id`, `approved_at`, and `family_link`. `approved_by_user_id` is an internal audit field — it is not part of the clinician-facing response and does not need to be exposed to the frontend.

### Testing decisions

**`conftest.py` mock user updated to include `"id"`:** The session-scoped `override_auth` fixture previously returned `{"sub": "test-user"}`. The Supabase user object always includes both `sub` and `id`; the mock now returns `{"id": "test-user-id", "sub": "test-user"}` to match the real shape and prevent `user.get("id")` from silently returning `None` in tests.

**`test_approve_stores_clinician_id` patches `main.update_communication`:** The test overrides the auth dependency to inject a known user ID (`"clinician-uuid-42"`), then patches `main.update_communication` with `wraps=` so the real function still executes. After the request completes, `call_args.kwargs` is inspected to assert `approved_by_user_id == "clinician-uuid-42"`. This approach tests the route-level wiring (that the user ID is extracted from the token and forwarded) without requiring a live database.

### Verifying the change in a live environment

#### 1. Confirm the column exists after startup

Start the backend and check the schema directly:

```bash
cd backend
source .env
psql "$SUPABASE_DB_URL" -c "\d care_plan_translations" | grep approved
```

Expected output:

```text
 approved_at            | timestamp with time zone |
 approved_by_user_id    | uuid                     |
```

If `approved_by_user_id` is not listed, the migration did not run — check that `SUPABASE_DB_URL` is set and that the backend started without errors.

#### 2. Run an approval and confirm the column is populated

Complete a full flow in the clinician UI (fetch patient → generate → approve). Then query the latest approved row:

```bash
psql "$SUPABASE_DB_URL" -c \
  "SELECT id, approved_at, approved_by_user_id
   FROM care_plan_translations
   WHERE status = 'Approved'
   ORDER BY approved_at DESC
   LIMIT 1;"
```

`approved_by_user_id` should contain your Supabase Auth user UUID. It matches the value in **Authentication → Users** in the Supabase dashboard.

---

## Feature Roadmap & TODOs

The following core features are required to align the current proof-of-concept with the target functional architecture:

1. **Database Migration to Supabase (HIPAA Compliant)** ✅
   - Migrate the local SQLite schema to Supabase (Postgres).
   - Establish tables for `patients` and `care_plan_translations`. (Next: `profiles`, `clinics`, `families`).

2. **Update Family Access Route** ✅
   - Refactor the frontend router and backend endpoints to use the secure, structured `/family/:fid/member/:mid` path.
   - Implement token-based validation for family member access.

3. **Multilingual Translation** ✅
   - Integrate translation services to translate approved summaries into Singapore's official languages: English (EN), Chinese (ZH), Malay (MS), and Tamil (TA).
   - Incorporate a clinical glossary to ensure translation accuracy of medical terms.

4. **Text-to-Speech (TTS) Generation**
    - Integrate a TTS engine (e.g. OpenAI `tts-1`, ElevenLabs, or Azure Neural TTS) to synthesise audio (MP3) of the approved summary in each supported language.
    - Store generated audio in Supabase Storage (or S3); cache like translations — generate on first request, serve from cache thereafter.
    - Expose via a new `GET /api/family/{fid}/member/{mid}/audio?lang=` endpoint that returns a signed URL to the audio file.

5. **Visual Aid Generation (Nano Banana)**
    - Integrate an image generation model (e.g. Gemini 2.5 Flash Image, DALL-E 3) to produce a supportive illustration for the care plan.
    - Store and serve images alongside summaries. Consider one image per summary (generated at approval time, not lazily) to avoid UX delay on the family viewer.

6. **Audio Playback & Visuals in Family Viewer**
    - Add an audio player component (`<audio>` element or a custom play/pause bar) in `FamilyPage.tsx` below the summary text, conditionally rendered when a TTS audio URL is available.
    - Add an image viewer component (lightbox or inline) for the visual aid.
    - Both should respect the current language selection (TTS audio must match the displayed language).

7. **Clinician Authentication (AuthGate)** ✅
   - Supabase magic-link (passwordless email) auth on the frontend.
   - `AuthGate` component guards the `/clinician` route, redirecting unauthenticated users to `/login`.
   - `verify_clinician_token` FastAPI dependency validates the Supabase JWT on all clinician-only endpoints (`/api/patient/*`, `/api/generate`, `/api/communications/*/approve`).

8. **Delivery Stub** ✅
   - QR code on the clinician approval success card for point-of-care handoff.
   - Print Handout on the clinician dashboard and Print Summary on the family viewer, both using a Blob-based print window with UTF-8 encoding for CJK support.
   - A−/A+ font size controls on the family viewer; chosen size is preserved in the print output.

9. **Audience-Specific Reports (Multi-Member Family Access)** ✅
   - Expanded `target_audience` from `"patient" | "family"` to four specific recipient types: `"patient"`, `"spouse"`, `"child"`, `"caregiver"`.
   - Each audience type has a distinct LLM prompt instruction block. Each approval produces a separately written summary with its own unique family member link.

10. **Audit Trail** ✅
    - Currently `approved_at` is the only audit field. A production deployment requires: which clinician approved (Supabase Auth `user_id`), which patient, and timestamps for each LLM generation call.
    - Add `approved_by_user_id` (UUID FK to Supabase Auth `auth.users`) to `care_plan_translations`, populated from the verified JWT in the approve route.
    - No changes to existing behaviour — purely additive columns.

---

## Known Test Gaps

The following areas lack automated test coverage and carry regression risk:

| Area | Gap | Risk |
| --- | --- | --- |
| `frontend/src/lib/markdown.ts` | No unit tests. Edge cases (nested bold/italic, mixed heading levels, empty input) are untested. | Markdown regressions in web view and print output are invisible until a demo. |
| Frontend integration (E2E) | No Playwright / Cypress tests. `ClinicianPage` and `FamilyPage` flow logic is exercised only by manual testing. | A backend API contract change could silently break the UI. |
| Auth edge cases | No tests for session expiry mid-workflow, double-tap Approve, or token refresh. | A clinician could lose work or trigger a duplicate approval if their session expires mid-flow. |
| Translation glossary injection | The `_CLINICAL_GLOSSARY` entries in `llm.py` are present but not asserted to appear in the translation prompt string. | A refactor of `translate_summary` could silently drop the glossary without any test failing. |
| Print window | No test for QR code SVG generation, print window DOM structure, or CJK font fallback stack. | Print regressions only surface at demo time on a real device. |
