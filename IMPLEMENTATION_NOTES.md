# SetRescue MVP — changes relative to uploaded ZIP

Implementation reference: `docs/2026-10-09-setrescue-ai-mvp-design.md`.

## Completed in this pass

- Added Windows `setup.bat`, `start.bat`, local encryption-key initialization, migrations, `README.md`, and `.gitignore`.
- Fixed comma-separated CORS settings parsing under Pydantic Settings; the example `.env` now uses the correct `SETRESCUE_` prefix for Resend.
- Improved CP-SAT modeling by replacing quadratic overlap pairs with optional-interval `NoOverlap`; fixed resource-unavailable precedence, including resource status, and added shot-level requirements to scene-level scheduling checks.
- Tightened enforcement: confirmed hard requirements with UNKNOWN/FAILED fulfillment cannot silently become shootable; completed/in-progress scene locks and stale-plan approval checks are retained.
- Cost projection now charges positive incremental overtime (above the baseline scene commitment) rather than billing all day-2 scenes as extra costs; recovery cost entries are itemized.
- Added preview/confirm workflow for simple XLSX Script, Shot List, Resource Sheet formats, with project isolation, idempotent imports, version checking and errors for unknown scene references. Call Sheet preview is informational only.
- Improved AI cache key separation across providers/models and retained valid cache entries across unchanged document reuploads.
- Fixed live scene timer to show elapsed time since the actual start recorded by FastAPI (instead of the planned wall-clock time); guarded completion of scenes not in progress.
- Made manual actual weather override forecasts for the same local filming day; corrected date handling and project creation date defaults for local time.
- Removed an assumed siaptuan.my.id endpoint from Settings, so users supply the real provider URL/model from their account. AI header indicates 'configured', not 'connected', until verified.
- Added import-focused API tests.

## Requires future implementation / external verification

1. Arbitrary PDF → verified scene/shot/call-sheet structured extraction with user review.
2. Automatic valid Call Sheet import to schedule; currently generate an initial CP-SAT schedule.
3. Inter-scene travel/precedence constraints and more complete crew/rental/location cost models. The current solver uses a single shooting unit.
4. Complete translation of all descriptive UI copy to Bahasa Indonesia.
5. Provider-specific compatibility (OpenAI-style `/models` / chat-completions) and live Open-Meteo/Resend integrations require network access and real credentials.

## Verification performed in this environment

- Python modules compile successfully.
- 21 TypeScript/TSX files pass syntax/transpilation checks (not a complete bundler build).
- 7 targeted non-solver API tests passed, including XLSX preview, apply, duplicate protection, stale-version rejection, credential secrecy, input validation, shot-level hard blockers, overlapping outage precedence, and project-scoped references.
- The complete CP-SAT scenario suite and the full React production build could not be run because the execution environment has no network package-registry access and OR-Tools / frontend node dependencies were not installed. Execute `setup.bat`, the Python test suite and `npm run build` on a networked Windows development machine.
