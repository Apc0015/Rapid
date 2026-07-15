# RAPID — Departmental Intelligence OS

An enterprise-grade, privacy-first AI platform that gives every department its own intelligent agent — trained on your data, governed by your rules, and ready to act on your behalf.

---

## What RAPID Does

RAPID connects your organization's documents, databases, and workflows to a team of AI agents that understand role-based access. A Finance analyst asking "What was our Q3 margin?" gets a different view than the CFO asking the same question — because RAPID enforces column-level governance rules before any data reaches the LLM.

**Key capabilities:**

- **Multi-agent orchestration** — 10 specialized department agents (Finance, HR, Legal, Sales, IT, etc.) plus C-Suite agents for escalations
- **Role-based intelligence** — column-level governance via `constitution.yaml`; raw data never reaches the LLM
- **Pluggable LLM** — Anthropic, OpenAI, Azure, OpenRouter, Ollama (local), Google
- **Human-in-the-loop** — 3-stage approval workflow before any consequential AI action
- **Industry packs** — pre-configured templates for 8 verticals
- **Full audit trail** — every query logged immutably for compliance

---

## Unified Product Architecture

RAPID has one supported product surface: the React portal in `frontend/src`. It covers the organization workspace, meetings, actions, people, CRM, projects, tickets, reports, search, notifications, tenant administration, and operations.

The FastAPI routers and agent services are the product backend, not a second application. They provide governed agent orchestration, RAG, task runs, integrations, skills, project intelligence, and tenant administration to the React portal. The retired standalone HTML entry points have been removed; integrations and OAuth callbacks return to React routes.

The local synthetic organization is the default product demo and test dataset. Customer databases, SSO, LLM providers, and live connectors are opt-in tenant configuration, not required to explore the product.

---

## Project Structure

```
RAPID/
├── main.py                    FastAPI app entry-point; registers all routers
├── config.py                  Tunable parameters (thresholds, paths, model names)
├── shared.py                  Agent singletons (imported by main + routers)
├── constitution.yaml          Column-level governance rules (Allow/Anonymize/Block)
│
├── frontend/                  React 19 + TypeScript product portal
│   ├── src/                   Routes, pages, components, API client, and tests
│   ├── package.json           Vite build, test, preview, and typecheck scripts
│   ├── rapid-design.css       RAPID design tokens
│   ├── product-shell.css      Shared product component styles
│   └── Dockerfile             Builds the production React artifact for nginx
│
├── nginx/
│   └── nginx.conf             Serves frontend, proxies /api/* → FastAPI
│
├── routers/                   FastAPI route handlers (one file per concern)
│   ├── deps.py                Auth dependencies (auth_user, require_role)
│   ├── auth.py                /auth/login, /auth/register
│   ├── admin.py               /admin/* — department and division management
│   ├── users.py               /users/* — user management + approval workflow
│   ├── documents.py           /ingest, /upload — document ingestion
│   ├── database.py            /db/connect — database connections
│   ├── llm.py                 /llm/configure, /llm/models, /llm/status
│   ├── monitoring.py          /audit, /agents/stats, /health
│   ├── chat_sessions.py       /sessions/* — chat history persistence
│   ├── projects.py            /projects/* — project management
│   ├── project_query.py       /projects/{id}/query — project-scoped intelligence
│   ├── actions.py             /actions/* — human-in-the-loop approval queue
│   ├── packs.py               /packs/* — industry pack management
│   ├── backup.py              /backup/* — backup and restore
│   ├── cloud_onedrive.py      /cloud/onedrive/* — OneDrive OAuth + import
│   └── cloud_gmail.py         /cloud/gmail/* — Gmail OAuth + import
│
├── agents/                    Multi-agent orchestration layer
│   ├── system/                Orchestration agents
│   │   ├── spokesperson.py    Intent classification + final answer composition
│   │   ├── master_planner.py  Query decomposition + bidding + dispatch
│   │   └── fusion_agent.py    Merge dept results + confidence scoring
│   └── departments/           10 specialized dept agents
│
├── infrastructure/            Core integrations
│   ├── llm_client.py          Multi-provider LLM client
│   ├── db_master.py           SQL execution + governance firewall
│   ├── doc_master.py          Document management + RAG indexing
│   ├── user_registry.py       User auth, roles, dept/division assignment
│   └── chat_history.py        SQLite-backed session store
│
├── pipelines/
│   ├── rag_pipeline.py        Chunk → embed → hybrid search (vector + BM25)
│   └── db_pipeline.py         SQL generation → execution → governance filter
│
├── industry_packs/            8 pre-configured industry templates
├── departments/               Per-department configs
├── governance/                Org governance rules
├── models/                    Internal data objects
├── tests/                     Test suite
│
├── data/                      Runtime data (git-ignored)
│   ├── users.yaml             User accounts + bcrypt-hashed passwords
│   ├── db/rapid.db            SQLite — users, chat sessions, messages
│   ├── faiss/                 FAISS vector index
│   ├── chroma/                ChromaDB embeddings
│   ├── documents/             Ingested documents
│   └── backups/               Automated backups
│
├── Dockerfile                 Production image (gunicorn + uvicorn workers)
├── docker-compose.yml         Full stack: nginx + rapid + ollama
├── .env.example               Environment variable template
├── requirements.txt           Python dependencies
├── Makefile                   Developer shortcuts
└── pytest.ini                 Test configuration
```

---

## Quick Start — Local Development

### Prerequisites
- Python 3.11+
- (Optional) Ollama for local LLM: https://ollama.ai

### 1. Clone and configure

```bash
git clone <repo-url>
cd RAPID
cp .env.example .env
```

Edit `.env` — minimum required:

```env
JWT_SECRET_KEY=your-strong-random-secret-minimum-32-characters
```

For local LLM (no API key needed):
```env
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=llama3.2
```

### 2. Install and run

```bash
make install
make dev
```

API available at: `http://localhost:8000`
API docs at: `http://localhost:8000/docs`

### 3. Run the React frontend

```bash
npm ci --prefix frontend
npm run dev --prefix frontend
```

Then navigate to `http://localhost:4173/login`.

`./start.sh` starts both FastAPI and the React portal with one command.

Default admin credentials are in `data/users.yaml`.

---

## Production Deployment — Docker (Recommended)

The full production stack (nginx + FastAPI + Ollama) is one command:

### 1. Generate a strong JWT secret

```bash
export JWT_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

### 2. Configure your environment

```bash
cp .env.example .env
# Edit .env — set JWT_SECRET_KEY, LLM credentials, ALLOWED_ORIGINS
```

### 3. Launch

```bash
docker-compose up -d
```

This starts:
- **nginx** on port `80` — serves the compiled React portal and proxies `/api/*` to the backend
- **rapid** (internal) — FastAPI with 2 gunicorn workers
- **ollama** on port `11434` — local LLM inference (optional)

### 4. Pull an LLM model (if using Ollama)

```bash
docker exec rapid-ollama-1 ollama pull llama3.2
```

### 5. Access RAPID

Open `http://your-server-ip` in a browser. The nginx config routes:
- `/*` → React application with history fallback
- `/api/*` → FastAPI backend

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `JWT_SECRET_KEY` | **Yes** | — | Strong random secret ≥32 chars |
| `RAPID_ENV` | No | `development` | `production` disables debug mode |
| `OPENROUTER_API_KEY` | No | — | OpenRouter (100+ models) |
| `ANTHROPIC_API_KEY` | No | — | Claude models |
| `OPENAI_API_KEY` | No | — | GPT models |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434/v1` | Local Ollama |
| `OLLAMA_MODEL` | No | `llama3.2` | Ollama model to use |
| `DATABASE_URL` | No | `sqlite:///data/db/rapid.db` | SQLite or PostgreSQL |
| `ALLOWED_ORIGINS` | No | `http://localhost` | CORS allowed origins |
| `LOG_LEVEL` | No | `INFO` | Logging level |

See `.env.example` for the full list.

---

## Makefile Commands

```bash
make help          # Show all available commands
make install       # Install Python dependencies
make dev           # Run with auto-reload (development)
make run           # Run in production mode (2 workers)
make test          # Run test suite
make test-fast     # Run tests, stop on first failure
make lint          # Lint with ruff
make docker-build  # Build Docker image
make docker-up     # Start with Docker Compose
make docker-down   # Stop Docker Compose
make clean         # Remove Python cache files
make dirs          # Create required runtime directories
```

---

## Role Hierarchy

| Role | Access |
|---|---|
| `employee` | Own department data only |
| `manager` | Department + team data |
| `dept_head` | Full department + approval queue |
| `division_head` | Multi-department view |
| `c_suite` / `ceo` | Cross-division executive view |
| `admin` | Full platform administration |

---

## Privacy & Governance

- **RAW DATA NEVER REACHES THE LLM** — documents and DB rows are converted to plain-English summaries before the LLM sees them
- **Column-level rules** in `constitution.yaml` — ALLOW / ANONYMIZE / BLOCK per role and department
- **Audit trail** — every query logged immutably to `data/audit.log`
- **Human-in-the-loop** — 3-stage approval (dept → division → admin) before any AI action executes
- **bcrypt passwords** — no plaintext credentials anywhere in the codebase
- **JWT hard-fail** — docker-compose refuses to start without `JWT_SECRET_KEY`

---

## Architecture

```
Browser → nginx (:80)
            │
            ├── /* → React/Vite build   (TypeScript SPA)
            └── /api/* → rapid (:8000)  (FastAPI)
                              │
                    Intent Classification
                              │
                    ┌─────────┴──────────┐
                    │  MasterPlanner      │
                    │  (decompose + bid)  │
                    └─────────┬──────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
          HR Agent      Finance Agent    Legal Agent  …
          RAG + DB       RAG + DB        RAG + DB
              │               │               │
              └───────────────┼───────────────┘
                              ▼
                        FusionAgent
                    (merge + confidence)
                              │
                        Spokesperson
                    (compose final answer)
                              │
                        AuditLogger
```

---

## Testing

```bash
make test
# or directly:
pytest tests/ -v --tb=short
```

Tests cover: JWT auth, SQL governance, RAG pipeline, escalation logic, intent classification.

---

## License

Proprietary — © Ayush Chhoker. All rights reserved.
