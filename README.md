# SetRescue AI — Local hackathon MVP

A local-first production readiness and adaptive recovery web app for the **Production Manager**. The product connects shot/scene readiness, confirmed production dependencies, active schedules, incidents and recovery options. No login or hosted application is required.

The architecture follows the supplied `2026-10-09-setrescue-ai-mvp-design.md`: React + Vite + TypeScript, FastAPI + SQLite, and OR-Tools CP-SAT. **AI interprets and explains; SetRescue calculates and validates.**

## Windows setup

**Prerequisites:** Windows 10/11, **Python 3.12 (64-bit)** recommended, **Node.js 20+**, internet connectivity for the first installation. Python 3.13 may work with recent packages but is not the tested target. Ensure `py`, `python` and `npm` commands are available.

1. Extract the ZIP to a writable folder, not inside another ZIP.
2. Double-click **`setup.bat`** in the root folder (or run it in PowerShell with `./setup.bat`). It installs Python requirements, generates a local encryption key once, migrates SQLite, and installs the frontend packages.
3. Double-click **`start.bat`** (or run `./start.bat`). Leave **both** terminal windows open.
4. Visit **http://localhost:5173**. The API docs are at **http://localhost:8000/docs**.
5. Open **Projects → Load Realistic Demo** and follow the demo flow below.

**Manual startup (if preferred):** from `backend`, run `.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`; from `frontend`, run `npm run dev -- --host 127.0.0.1`.

> Do not delete `backend/.env` after saving an AI key: it contains the local encryption key. Keep it private. The local application serves its API on localhost only.

## Live hackathon demo

1. **Projects:** Load Realistic Demo to create *Project Rainfall*, 2 shooting days, 8 scenes, and 20 shots.
2. **Documents:** Review Script, Shot List, Call Sheet and the editable structured production data. For a new project, upload a tabular XLSX file, choose **Preview structured import**, then explicitly **Confirm & import** its supported rows.
3. **PREVENT:** Run the readiness analysis, review/confirm a suggested contingency requirement and resolve one finding.
4. **Schedule:** Generate an initial schedule. This is the version 1 baseline.
5. **Live Production:** Start a scene and compare actual/planned time.
6. **Incidents:** Report unexpected rain affecting an outdoor scene (or use the manual weather report).
7. **Recovery:** Choose TIME, COST or STABILITY priority, generate Fastest / Cheapest / Minimum Change, inspect verified scene sequence, cost and unresolved blockers.
8. **Approve** a valid plan. It becomes **schedule V2**, replacing the active baseline while retaining the earlier schedule.
9. **Reports:** Export PREVENT report, Recovery Comparison, and Updated Call Sheet PDF. **Crew Updates:** Preview notifications; demo-email mode avoids sending real email.

## AI provider setup (optional for deterministic demo)

In **Settings → AI Provider**, provide your OpenAI-compatible HTTPS **base URL**, **model identifier** and **API key**. For example, use the actual values supplied by your `siaptuan.my.id` provider account. We do not assume the provider's endpoint/model name; consult its API documentation. Save and select **Test Connection**. Keep the URL pointing to the `/v1` API root when that is what your provider specifies (not directly to `/chat/completions`).

The API key is Fernet-encrypted in SQLite; encryption key lives in `backend/.env` and is not returned to the browser. Uploaded documents stay on the laptop; selected document text is sent to the provider **only if the user runs AI analysis**. The main rule-based PREVENT and CP-SAT RECOVER workflows do **not** require AI connectivity.

## Boundaries and known MVP limitations

- Text-based PDFs and XLSX spreadsheets are accepted. Scanned images/OCR are **not** supported.
- Structured scenes, shots, resources and confirmed requirements form the solver's source of truth. Document upload alone does not imply verified constraints. Tabular XLSX Script, Shot List and Resource Sheet files support preview-first imports, idempotent imports and version checks. Call Sheets are preview-only; PDF text extraction provides AI analysis context. Automatic full screenplay/shot/call-sheet reconstruction from arbitrary PDF layouts remains incomplete.
- The CP-SAT solver models a single shooting unit and 15-minute time slots over a maximum of 14 days. Advanced travel-time, inter-scene precedence and imported Call Sheet → active schedule mapping remain outside the current verified constraint implementation. Inspect any generated plan before approval.
- Recovery costs cover incremental overtime and changed-location transport from known project defaults. Detailed rental and extra-shoot billing is not yet implemented; estimates are **not** final quotes.
- EN/ID navigation is available; some longer detail-screen copy remains English.
- Optional live weather lookup and live email need connectivity/valid provider settings. Manual weather and demo-email preview work without those third parties.

## Tests

From `backend` using the virtualenv:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

For the frontend, after `npm install`:

```powershell
npm run build
```

The tests exercise demo data, PREVENT, initial schedule, recovery, stale-plan rejection, failed/unavailable resource cases, secrets and document validation. Source files are excluded from ZIP caches and binary build artifacts.
