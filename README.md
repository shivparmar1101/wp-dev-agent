# WP Dev Agent

A GitHub-based AI development agent for **WordPress** and **Elementor** repositories.
Sign in with GitHub, pick a repository, scan it, and ask questions about the code —
the agent answers with grounded analysis: relevant files, line ranges, cause, and a
suggested fix.

**Read-only by design.** The agent never commits, pushes, creates branches, opens pull
requests, or modifies your repositories.

## Features

- **GitHub OAuth login** — public and private repositories, tokens encrypted at rest.
- **Background repository scanning** — staged pipeline: tree reading → WordPress /
  theme / plugin / Elementor detection → language-group indexing → search index.
- **Code search** — hybrid, keyword (BM25), exact-phrase, file-path, and semantic
  modes (semantic re-ranking falls back to lexical when embeddings are unavailable).
- **AI chat analysis** — provider abstraction for OpenAI / OpenAI-compatible, Anthropic,
  Gemini, plus an offline `mock` provider for development without API keys.
- **Workspace UI** — AI chat, project overview, file explorer with syntax highlighting,
  WordPress / themes / plugins / Elementor panels, and a dedicated search view.

## Architecture

```
agent/
├── backend/           Python FastAPI API
│   ├── api/           HTTP routes (auth, repositories, scan, projects, search, chat)
│   ├── github/        OAuth flow + GitHub REST client
│   ├── scanner/       Background scan jobs and staged pipeline
│   ├── wordpress/     WordPress / theme / plugin / Elementor detection
│   ├── indexing/      Chunker, BM25 index, embeddings, search service
│   ├── ai/            Provider abstraction, prompts, analyzer
│   ├── storage/       SQLite persistence (sessions, scans, chat history)
│   └── utils/         Security, redaction, rate limiting, logging
├── frontend/          Next.js 15 (App Router) + Tailwind UI
├── tests/             Backend + scanner/indexing/AI test suites (pytest)
└── data/              SQLite DB and secret key (created at runtime, gitignored)
```

## Prerequisites

- Python 3.11+ (tested on 3.12)
- Node.js 20+ (tested on 24)
- A GitHub OAuth App (for sign-in)
- An AI provider API key (optional — a `mock` provider works offline)

## Setup

### 1. Backend

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
Copy-Item .env.example .env         # then edit values
```

Create an OAuth app at <https://github.com/settings/developers>:

- **Homepage URL:** `http://localhost:3000`
- **Authorization callback URL:** `http://localhost:8000/api/auth/callback`

Set `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` in `.env`.

For AI answers set `AI_PROVIDER` (`openai` | `anthropic` | `gemini` | `mock`) and
`AI_API_KEY`. `AI_PROVIDER=openai` also works with any OpenAI-compatible endpoint via
`AI_BASE_URL` (OpenRouter, Ollama, Groq, …).

### 2. Frontend

```powershell
npm --prefix frontend install
Copy-Item frontend\.env.example frontend\.env.local   # optional; default API URL works
```

### 3. Run

```powershell
# Terminal 1 — API on :8000
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000

# Terminal 2 — UI on :3000
npm --prefix frontend run dev
```

Or use the root convenience scripts (Windows; POSIX users run the two commands above):

```powershell
npm run dev            # runs both with concurrently
npm run test:backend
npm run test:frontend
```

Open <http://localhost:3000>.

### Docker

```bash
docker compose up --build
```

UI on `http://localhost:3000`, API on `http://localhost:8000`. Put your `.env` next to
`docker-compose.yml` first.

## Tests, lint, typecheck

```powershell
# Backend (pytest, from repo root)
python -m pytest tests -q

# Frontend
npm --prefix frontend run test        # vitest
npm --prefix frontend run typecheck   # tsc --noEmit
npm --prefix frontend run lint        # eslint --max-warnings=0
npm --prefix frontend run build       # next build
```

## API surface

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Service + configuration status |
| GET | `/api/auth/login` | Start GitHub OAuth (redirects to GitHub) |
| GET | `/api/auth/callback` | OAuth callback (sets session cookie) |
| GET | `/api/auth/me` | Current session / user |
| POST | `/api/auth/logout` | Clear session |
| GET | `/api/repositories` | List repositories (search, pagination) |
| POST | `/api/scan/{owner}/{repo}` | Start a background scan |
| GET | `/api/scan/{owner}/{repo}/status` | Scan progress (stages, 0–100%) |
| GET | `/api/projects` | List analyzed projects |
| GET | `/api/projects/{owner}/{repo}` | Project summary (detection + index stats) |
| GET | `/api/projects/{owner}/{repo}/tree` | Repository file tree |
| GET | `/api/projects/{owner}/{repo}/file` | File contents (blocked paths rejected, secrets redacted) |
| POST | `/api/search/{owner}/{repo}` | Code search (`hybrid\|keyword\|exact\|file\|semantic`) |
| POST | `/api/chat/{owner}/{repo}` | AI analysis of a question |

## Security notes

- Session is an opaque **httpOnly** cookie; sessions live in SQLite, not in the browser.
- GitHub access tokens are encrypted at rest (Fernet / `SECRET_KEY`).
- Blocked paths (`.env*`, private keys, `secrets.*`, …) can never be read through the API.
- `wp-config.php` is readable in the UI but aggressively redacted before any AI prompt.
- All retrieved code is treated as untrusted data — prompt-injection style content is
  fenced inside delimiters and never followed as instructions.
- Rate limits apply per session/IP to search, chat, and scan endpoints.

## Notes

- Backend settings are read from `backend/config.py` (pydantic-settings, `.env` aware).
- `DATABASE_URL=sqlite:///./data/wp_dev_agent.db` is the default; other schemes are
  reserved for later phases.
- If no AI key is configured the API uses the `mock` provider and flags the answer with
  an explicit warning — useful for UI development.
