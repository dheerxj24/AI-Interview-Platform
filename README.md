# AI-Powered Technical Interview Platform

![Python](https://img.shields.io/badge/Python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-teal)
![React](https://img.shields.io/badge/React-18-61dafb)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791)
![Redis](https://img.shields.io/badge/Redis-7-red)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ed)
![CI](https://img.shields.io/badge/CI-GitHub%20Actions-black)

**Python · FastAPI · React · CodeMirror · Yjs · PostgreSQL · Redis · Docker · Ollama**

A live, collaborative coding interview tool. Candidates and interviewers share one editor that syncs in real time, candidate code runs in a locked-down sandbox against hidden tests, and an optional AI co-pilot helps interviewers ask better follow-up questions. It is built as a full-stack project: API design, real-time sync, container isolation, access control, and CI.

## Business Problem

*Remote coding interviews need three things: a shared place to write code live, a fair way to run it, and consistent notes for every candidate.*

This project covers all three. It also adds integrity signals so interviewers can see how a session went, and it uses an LLM only where it helps: suggesting questions, drafting scores for review, and drafting problems that are checked by running their own solution.

## Key Features

- **Live shared editor:** CodeMirror 6 with Yjs over WebSocket, live presence, and autosave every 2 seconds.
- **Sandboxed execution:** candidate code runs in a Docker container with no network, a 128 MB memory limit, half a CPU, a read-only filesystem, and a process limit.
- **Hidden tests:** "Run visible tests" shows per-test results. "Run all tests" returns pass counts only, so hidden test data never reaches the browser.
- **Role-based access:** separate candidate and interviewer tokens, plus an admin token for managing problems and sessions. Tokens are stored as hashes.
- **Integrity signals:** the candidate view logs when the tab is hidden, when the window loses focus, and the length of each paste. The summary lists them with timestamps.
- **Scorecards:** interviewers record correctness and communication scores with notes. Candidates see their scores after the session ends, but never the notes.
- **AI co-pilot:** suggests three follow-up questions from the problem and the candidate's code, and retries once if the reply is malformed.
- **AI scorecard draft:** fills in scores and notes for the interviewer to review. Nothing is saved until the interviewer submits the form.
- **AI problem generator:** drafts a problem from a topic. Its reference solution runs in the worker's sandbox, and the output becomes each expected output, so the tests come from running code, not from the model's guess.
- **Archiving:** deleting a problem hides it from new sessions but keeps it for past interviews.

## Tools Used

| Tool | Purpose |
|---|---|
| **FastAPI + SQLAlchemy** | REST API, WebSocket relay, role checks |
| **PostgreSQL** | Sessions, problems, tests, runs, events, scorecards |
| **Redis** | Real-time pub/sub between API processes, Celery broker and result backend |
| **Celery** | Runs candidate code and AI draft checks in the worker |
| **Docker** | Sandbox image for untrusted code; Docker Compose for the full stack |
| **React + Vite** | Interview room, problems page, summary page |
| **CodeMirror 6 + Yjs** | Collaborative editor with live cursors |
| **Ollama or Anthropic API** | Co-pilot model (local by default, hosted optional) |
| **GitHub Actions** | Backend tests and frontend build on every push |

## Architecture

```
Browser (React, CodeMirror, Yjs)
        │  REST                    │  WebSocket (Yjs updates, presence)
        ▼                          ▼
   FastAPI API ◄──── Redis pub/sub (shares rooms across API processes)
        │
        ├──► PostgreSQL (sessions, problems, runs, events, scorecards)
        │
        ├──► Redis queue ──► Celery worker ──► Docker sandbox (run candidate code)
        │
        └──► Ollama or Anthropic (co-pilot, scorecard draft, problem draft)
```

## How a Session Works

1. **Set up:** the admin creates a problem and its tests on the problems page, or generates a draft with AI and reviews it.
2. **Create:** the interviewer creates a session. The interviewer link opens the interviewer view, and the candidate link is in the header.
3. **Interview:** both people edit the same code. The candidate runs visible tests, and the interviewer can run all tests, ask the co-pilot for questions, and draft a scorecard.
4. **End:** the interview closes for both people. The summary shows the final code, run history, integrity events, and scorecard. The candidate sees their scores.

## Testing

The backend has 53 tests covering access control, judging, the realtime relay, the AI endpoints, and problem archiving. CI runs them on every push, along with a frontend build. The tests run on SQLite with fake Redis, so the Docker sandbox and the live Redis path still need a manual run.

## Run It

**Full stack (Docker Compose):**
```bash
cd infra
# PowerShell: $env:ADMIN_TOKEN = "choose-a-token"
# bash:       export ADMIN_TOKEN=choose-a-token
docker compose up --build
```
Open http://localhost:5173, sign in with the admin token, and create a problem. The API docs are at http://localhost:8000/docs.

**Backend only (no Docker):**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -q
# No Redis locally? Run submissions inline instead of through a worker:
CELERY_EAGER=true uvicorn app.main:app --reload
```

## Access and Roles

- **Admin token:** set `ADMIN_TOKEN` before running Compose. It opens the problems page, creating sessions, the sessions list, and any session as interviewer. The browser keeps it in session storage only.
- **Interviewer link:** included with each session. Opening a session with only the admin token also works.
- **Candidate link:** shown in the interviewer's session header. It opens the candidate view with the editor, runs, the problem prompt, and scores after the session ends.
- Sessions created before access tokens existed cannot be opened and need to be recreated.

## Co-Pilot

The AI features share one model connection. They use a local Ollama server when `OLLAMA_URL` is set (the default in Compose is `http://host.docker.internal:11434`). Otherwise they use Anthropic with `ANTHROPIC_API_KEY`.

- **Follow-up questions:** the co-pilot panel suggests three questions based on the problem and the candidate's code.
- **Scorecard draft:** "Draft with AI" fills in scores and notes for review.
- **Problem draft:** "Generate draft" writes a problem and a reference solution. The worker runs the solution, and its output becomes each expected output.

Local models sometimes produce a bad draft. When that happens, the page shows the reason, and you can try again.

## Integrity Events

The candidate view records when the window loses focus, when the tab is hidden, and the length of any paste. It never records what was pasted. The summary lists the events with their times. These are signals for the interviewer, not proof of cheating.

## Known Limits

- The local executor (`EXECUTOR=local`) is for development only. It is not a security boundary. Compose runs candidate code and the problem draft check in the worker with `EXECUTOR=docker`.
- The worker needs the Docker socket, which is root-equivalent on the host. Use rootless Docker or a separate host for anything beyond local demos.
- Everyone with the admin token has full access. There are no user accounts.
- Tokens appear in URLs, so share only the candidate link.
- Event logging cannot detect a second device or a window outside the browser.
- Postgres credentials in `docker-compose.yml` are demo defaults.
- There are no database migrations. Startup creates missing tables but does not add new columns to existing ones. After a schema change, add the column by hand or recreate the database volume.

## Repository Structure

```
AI-Interview-Platform/
│
├── backend/
│   ├── app/             FastAPI app: routers, models, auth, realtime, co-pilot, judging
│   ├── tests/           pytest suite (SQLite, fake Redis)
│   └── Dockerfile
│
├── frontend/
│   ├── src/             React app: session room, problems, summary, admin sign-in
│   └── Dockerfile
│
├── sandbox/             Image that runs candidate code (no network, non-root)
├── infra/               docker-compose.yml for the full stack
├── docs/                Build plan
└── .github/workflows/   CI: backend tests and frontend build
```

## Future Work

- Add database migrations (Alembic) so schema changes don't need manual SQL
- Add user accounts and per-interviewer history instead of shared admin access
- Add browser end-to-end tests for the interview room and the summary page
- Let the co-pilot read the candidate's run results, not just the code

## Skills Demonstrated

- Full-stack development with FastAPI and React
- Real-time collaboration with Yjs, WebSockets, and Redis pub/sub
- Container isolation and sandboxed code execution
- Role-based access control with hashed tokens
- Background jobs with Celery
- LLM integration with validation, retries, and grounded outputs
- Testing and CI with GitHub Actions
- Docker Compose for multi-service setups

## Author

**Dheeraj Paul**

GitHub: [https://github.com/dheerxj24](https://github.com/dheerxj24)

LinkedIn: [www.linkedin.com/in/dheeraj-paul-175515333](https://www.linkedin.com/in/dheeraj-paul-175515333)

---

⭐ If you found this project useful, consider giving it a star.
