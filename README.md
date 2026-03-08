# AI QA Copilot

AI QA Copilot is a full-stack demo app for generating, running, and scheduling QA test cases against a mock Vessel Connect domain.

It includes:
- A React dashboard to create and run AI-generated test cases
- A FastAPI backend with test orchestration APIs
- Mock Vessel Connect APIs used as test targets
- Local audit logging of AI operations
- Optional OpenAI integration (falls back to deterministic mock AI when no key is provided)

## What this app does

- Discovers target APIs/pages from a catalog
- Creates test cases with AI metadata (`name`, `description`, `assertions`, scripts)
- Supports 2 runners:
  - `python_api`
  - `playwright_ui`
- Runs single or all test cases and stores run history
- Schedules recurring test runs with cron-like modes
- Shows pass/fail status and logs in the dashboard
- Provides a Vessel Connect simulator page for UI workflow testing

## Tech stack

- Frontend: React 18 + TypeScript + Vite
- Backend: FastAPI + Pydantic + APScheduler
- Database: SQLite (`backend/data/app.db`)
- Test tooling: Pytest + Playwright
- AI integration: OpenAI API (optional)

## Project structure

```text
backend/
  app/
    main.py            # FastAPI app + QA APIs + scheduler
    vc_api.py          # Mock Vessel Connect endpoints
    db.py              # SQLite setup
    ai/                # AI service, schemas, RAG utilities
  data/
    app.db             # SQLite database (created automatically)
  generated_tests/
    tests/api/
    tests/ui/
frontend/
  src/pages/
    QADashboard.tsx
    VesselConnectSim.tsx
  tests/
Makefile
docker-compose.yml
```

## Prerequisites

- Python 3.11+ (3.10 may work, 3.11 is recommended)
- Node.js 20+
- npm
- `npx` (comes with npm)

Optional:
- `OPENAI_API_KEY` for real AI mode

## Install and run (local)

### 1) Clone and enter project

```bash
cd /path/to/your/workspace
cd your-project-folder
```

### 2) Set up backend dependencies

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3) Set up frontend dependencies

```bash
cd ../frontend
npm install
```

### 4) Start both backend and frontend

From project root:

```bash
cd ..
export PATH="$PWD/backend/.venv/bin:$PATH"
make dev
```

`make dev` starts:
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173`

### 5) Open the app

- UI: `http://localhost:5173`
- API docs (Swagger): `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

### Stop the app

Press `Ctrl + C` in the terminal running `make dev`.

## Run with real OpenAI model

By default, the app uses mock AI outputs if `OPENAI_API_KEY` is not set.

To use real OpenAI responses:

```bash
export OPENAI_API_KEY="your_api_key"
export OPENAI_MODEL="gpt-4.1-mini"   # optional (default is gpt-4.1-mini)
export PATH="$PWD/backend/.venv/bin:$PATH"
make dev
```

## Run with Docker Compose

```bash
cd /path/to/your-project-folder
export OPENAI_API_KEY="your_api_key"   # optional
docker compose up --build
```

Services:
- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`

Stop:

```bash
docker compose down
```

## How to use the app

### QA Dashboard (`/`)

1. Click `Create New Test Case`.
2. Select `Runner` and target (`API Endpoint` or `Page`).
3. Add optional `AI Prompt`.
4. Click `Create`.
5. Run tests with `Run` or `Run All Test Cases`.
6. Configure recurring runs using `Auto Cron`.
7. Review logs in `Execution Results`.

### Vessel Connect Simulator (`/vessel-connect`)

Use this page to simulate end-user workflow:
- Submit nomination
- Update schedule
- Verify calendar event count/status

## API overview

### Health

- `GET /health`

### QA catalog and cases

- `GET /api/endpoints`
- `GET /api/pages`
- `GET /api/test-cases`
- `GET /api/test-runs?limit=40`
- `POST /api/test-cases/auto-create`
- `POST /api/test-cases/{case_id}/run`
- `POST /api/test-cases/run-all`
- `POST /api/test-cases/{case_id}/schedule`
- `DELETE /api/test-cases/{case_id}`

### AI/RAG workflow

- `POST /api/ai/index_doc`
- `POST /api/ai/generate_tests`
- `POST /api/tests/run`
- `POST /api/ai/propose_fix`
- `POST /api/fix/apply`

### Vessel Connect mock APIs

- `POST /vc/nominations`
- `GET /vc/nominations/{nomination_id}`
- `PATCH /vc/nominations/{nomination_id}/readiness`
- `PATCH /vc/nominations/{nomination_id}/schedule`
- `POST /vc/nominations/{nomination_id}/link-cq`
- `POST /vc/cq/{cq_id}/sign`
- `GET /vc/nominations/{nomination_id}/messages`
- `GET /vc/nominations/{nomination_id}/calendar`

## Environment variables

### Backend

- `OPENAI_API_KEY` (optional): enables real AI calls
- `OPENAI_MODEL` (optional): default `gpt-4.1-mini`
- `BASE_URL` (optional): frontend URL used by Playwright run endpoints, default `http://localhost:5173`
- `PLAYWRIGHT_HEADED` (optional): `1` for headed mode
- `PLAYWRIGHT_SLOW_MO` (optional): slow motion ms delay
- `PLAYWRIGHT_STEP_MS` (optional): script step delay in generated UI scripts
- `PLAYWRIGHT_HOLD_MS` (optional): wait time at end of generated UI script

### Frontend

- `VITE_API_BASE` (optional): backend base URL, default `http://localhost:8000`

## Testing

From project root:

```bash
export PATH="$PWD/backend/.venv/bin:$PATH"
make test
```

This runs:
- Pytest for generated API tests
- Playwright for generated UI tests

You can also run frontend e2e directly:

```bash
cd frontend
npm run test:e2e
```

## Data, generated files, and reset

- SQLite DB: `backend/data/app.db`
- Dynamic scripts generated at runtime:
  - `backend/generated_tests/dynamic/`
  - `frontend/tests/generated/`
- Seed generated tests:
  - `backend/generated_tests/tests/api/test_vc_api.py`
  - `backend/generated_tests/tests/ui/vc.spec.ts`

To reset local app data:

```bash
rm -f backend/data/app.db
```

Restart backend after removing DB.

## Troubleshooting

### API Endpoint/Page dropdown is blank

Cause: backend is not running.

Fix:
- Ensure backend is up on `http://localhost:8000`
- Open `http://localhost:8000/health` and confirm `{"status":"ok"}`

### Frontend shows `Failed to fetch`

Cause: frontend cannot reach backend.

Fix:
- Verify `VITE_API_BASE` value
- Verify backend port 8000 is available

### Port already in use

Fix:
- Stop old processes using ports 5173 or 8000
- Re-run `make dev`

### Playwright errors on first run

Fix:

```bash
cd frontend
npx playwright install
```

## Security notes

- Keep `OPENAI_API_KEY` in backend env only
- AI outputs are validated with Pydantic schemas
- AI operations are logged in `ai_audit_logs` table for traceability
- Demo patch application endpoint should not be exposed publicly in production

## License

Internal/demo project. Add your preferred license before external distribution.
