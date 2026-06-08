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

## Cross-cutting decisions

### Dependency management

`requirements.txt` is production-only. `requirements-dev.txt` starts with `-r requirements.txt` so a single `pip install -r requirements-dev.txt` sets up a complete development environment. This means production and development dependency trees are always in sync.

### Environment variables

All environment-specific values are read at module load time via `os.getenv` with safe local defaults. No value is hardcoded in logic. The pattern is:

```python
SOME_VALUE = os.getenv("SOME_VAR", "safe-local-default")
```

This makes the codebase portable between local dev, CI, and Render without any code changes.

### No async in business logic

`db.py` and `fhir.py` are fully synchronous. FastAPI supports sync route handlers natively (it runs them in a thread pool). The PoC has no concurrency requirements that would justify async DB or HTTP calls at this stage. Mixing sync and async code in a PoC adds cognitive overhead with no benefit.
