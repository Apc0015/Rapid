# RAPID — Startup Operating Workspace

RAPID is a governed startup operating workspace: one React product portal for product delivery, customer work, decisions, projects, operations, knowledge, and tenant administration, backed by configurable AI assistance and organization data services.

---

## What RAPID Does

RAPID is currently operated as an invite-only beta. A founder requests access at `/start`; an authorised RAPID reviewer approves or declines the request; approval creates an isolated synthetic startup workspace and displays a one-time account-activation link for the reviewer to send. No payment, customer data connection, or production database access is required during the beta. After activation, the founder can configure model providers, organization data, SSO, and supported integrations from the admin portal.

**Key capabilities:**

- **Unified workspace** — overview, meetings, actions, people, CRM, projects, tickets, reports, library, notifications, search, and settings
- **Persistent RAPID chat** — page-aware, tenant-isolated conversations that retain approved evidence, source context, and follow-up history
- **Startup-first setup** — a focused starting workspace for product, growth, customer, finance, delivery, and operations work; other operating models remain configurable for future expansion
- **Governed work areas** — Finance, People Ops, Legal, Sales, Marketing, Operations, IT, Procurement, R&D, and Customer Success can be enabled as the company grows
- **Project intelligence** — isolated project data spaces, scoped queries, skills, generated documents, portfolio analysis, and team membership
- **Organization knowledge** — document upload, extraction/OCR, PII handling, source sync jobs, permissions, lexical/vector retrieval, and optional Qdrant
- **Visible trust controls** — founders can inspect the data boundary, active runtime, connection state, evidence behavior, and approval requirement before connecting production data
- **Tenant administration** — invitations, roles, organization structure, model/provider configuration, integrations, branding, and operations visibility
- **AI deployment policy** — managed cloud, private, on-prem, or hybrid routing; private and on-prem policies block cloud providers and default to local Ollama

---

## Unified Product Architecture

RAPID has one supported product surface: the React portal in `frontend/src`. It covers the organization workspace, meetings, actions, people, CRM, projects, tickets, reports, search, notifications, tenant administration, and operations.

The FastAPI routers and agent services are the product backend, not a second application. They provide governed agent orchestration, RAG, task runs, integrations, skills, project intelligence, and tenant administration to the React portal. The retired standalone HTML entry points have been removed; integrations and OAuth callbacks return to React routes.

The local synthetic startup is the default product demo and test dataset. Customer databases, SSO, LLM providers, and live connectors are opt-in tenant configuration, not required to explore the product. RAPID never treats a configured secret reference as a live connection: provider and connector setup remain visibly pending until the customer's deployment has supplied and validated it.

Older direct OAuth connector routes are disabled by default. This prevents customer data from entering a legacy ingestion path while tenant-scoped, permission-aware adapters are completed. Set `RAPID_ENABLE_LEGACY_CLOUD_CONNECTORS=true` only for a controlled migration environment, never as the default customer deployment.

---

## Project Structure

```
RAPID/
├── frontend/                  React 19 + TypeScript product portal
│   ├── src/App.tsx            Product routing and authenticated shell
│   ├── src/pages/             Workspace, admin, operations, and login pages
│   ├── src/features/          Workspace, meeting, and intelligence flows
│   ├── src/lib/api.ts         Browser API client and authenticated downloads
│   └── Dockerfile             Builds the Vite production bundle for nginx
├── nginx/nginx.conf           Serves the SPA and proxies /api/* to FastAPI
│
├── main.py                    FastAPI application, lifespan, middleware, router registration
├── routers/                   Product API boundaries
│   ├── workspace.py           Common portal data: overview, meetings, records, notifications
│   ├── projects.py            Project lifecycle and membership
│   ├── project_query.py       Project-scoped intelligence
│   ├── skills.py              Skill execution, reviewed outputs, project documents
│   ├── actions.py             Human review queue and action decisions
│   ├── organization_data.py   Sources, uploads, RAG status, document permissions
│   ├── tenant_admin.py        Tenant configuration, invitations, entitlements, branding
│   ├── onboarding.py          Controlled organization provisioning service
│   ├── beta.py                Invite-only beta application, approval, and activation API
│   ├── organization_*.py      Structure, integrations, and organization operations
│   ├── intelligence.py        Portal intelligence and evidence-aware answers
│   ├── chat_sessions.py       Tenant-scoped RAPID conversation history
│   └── jobs.py / monitoring.py Durable job visibility, metrics, liveness, readiness
│
├── infrastructure/            Product services and storage adapters
│   ├── intelligence_gateway.py Shared intelligence scope, evidence, and specialist routing
│   ├── query_service.py       Backward-compatible organization-agent specialist
│   ├── organization_rag.py    Permission-aware organization retrieval
│   ├── document_extractor.py  Text extraction, OCR, PII handling
│   ├── embedding_service.py   Configurable embedding provider
│   ├── job_queue.py           Durable queue, retries, dead letters, worker heartbeats
│   ├── job_handlers.py        Indexing, sync, webhook, and connector job handlers
│   ├── organization_data_store.py Source/document metadata and access scopes
│   ├── integration_hub.py     Configured provider and connector registry
│   ├── tenant_admin_store.py  Tenant configuration and entitlement state
│   ├── organization_profiles.py Profile catalogue and AI deployment policies
│   └── tenant_provisioning.py Tenant, CEO, profile, and workspace provisioning
│
├── agents/                    Department agents, project intelligence, skills, and governance
├── workers/job_worker.py      Separate durable background worker process
├── data/                      Git-ignored runtime state: SQLite, queued jobs, documents, indexes, logs
├── tests/                     Python regression and integration coverage
├── scripts/                   Portal E2E and load-smoke validation
├── docker-compose.yml         nginx + API + worker + Ollama; optional Qdrant profile
├── .env.example               Configuration template for local or customer deployment
└── README.md                  Product, deployment, and architecture guide
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

To test the private-beta application journey, open `http://localhost:4173/start`. An authorised reviewer approves the request from **Administration → Users and access**, then sends the one-time link displayed there. The activated founder is provisioned as that tenant's CEO and can refine the operating profile under Administration.

`./start.sh` starts both FastAPI and the React portal with one command.

Default admin credentials are in `data/users.yaml`.

---

## Production Deployment — Docker (Recommended)

The full production stack (nginx + FastAPI + durable job worker + Ollama) is one command:

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
- **worker** (internal) — durable indexing, connector sync, webhook, and RAG processing
- **ollama** on port `11434` — local LLM inference (optional)

### 4. Pull an LLM model (if using Ollama)

```bash
docker exec rapid-ollama-1 ollama pull llama3.2
```

### 5. Access RAPID

Open `http://your-server-ip` in a browser. The nginx config routes:
- `/*` → React application with history fallback
- `/api/*` → FastAPI backend

### 6. Verify the deployment

```bash
curl -fsS http://your-server-ip/api/health/ready
```

Production compose requires an active `worker` heartbeat. The response includes a `job_worker` check and the portal Settings page shows the active worker count. This prevents accepting uploads or connector syncs into a deployment with no durable processor.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `JWT_SECRET_KEY` | **Yes** | — | Strong random secret ≥32 chars |
| `RAPID_ENV` | No | `development` | `production` disables debug mode |
| `RAPID_ENABLE_DEMO` | No | `false` | Enables the public synthetic demo session; keep `false` for invite-only beta |
| `RAPID_PORTAL_URL` | Yes for beta | — | Public portal URL used to create activation links, for example `https://beta.rapid.example` |
| `RAPID_BETA_REVIEWER_IDS` | Yes in production | — | Comma-separated account IDs permitted to approve beta applications |
| `RAPID_ALLOW_SELF_SERVICE_PROVISIONING` | No | `false` | Must remain `false` for invite-only beta |
| `RAPID_ALLOW_LEGACY_REGISTRATION` | No | `false` | Must remain `false` for invite-only beta |
| `RAPID_ORGANIZATION_AI_TIMEOUT_SECONDS` | No | `12` | Max seconds for an interactive organization-wide AI answer before approved-evidence fallback |
| `OPENROUTER_API_KEY` | No | — | OpenRouter (100+ models) |
| `ANTHROPIC_API_KEY` | No | — | Claude models |
| `OPENAI_API_KEY` | No | — | GPT models |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434/v1` | Local Ollama |
| `OLLAMA_DOCKER_BASE_URL` | No | `http://ollama:11434/v1` | Ollama endpoint used inside Docker Compose |
| `OLLAMA_MODEL` | No | `llama3.2` | Ollama model to use |
| `DATABASE_URL` | No | `sqlite:///data/db/rapid.db` | SQLite or PostgreSQL |
| `RAPID_REQUIRE_JOB_WORKER` | No | `false` | Require a live durable worker in `/health/ready`; enabled by Docker production compose |
| `RAPID_JOB_DB_PATH` | No | `data/db/jobs.db` | Durable queue and worker heartbeat database |
| `ALLOWED_ORIGINS` | No | `http://localhost` | CORS allowed origins |
| `LOG_LEVEL` | No | `INFO` | Logging level |

See `.env.example` for the full list.

---

## Invite-Only Beta Launch

Set the following values in the deployed environment before exposing the public URL. Do not use the local development `.env` as a production secret source.

```bash
RAPID_ENV=production
RAPID_PORTAL_URL=https://beta.your-domain.com
RAPID_ENABLE_DEMO=false
RAPID_ALLOW_SELF_SERVICE_PROVISIONING=false
RAPID_ALLOW_LEGACY_REGISTRATION=false
RAPID_BETA_REVIEWER_IDS=your_existing_admin_account_id
JWT_SECRET_KEY=<a-new-random-secret-of-at-least-32-characters>
RAPID_ENCRYPTION_KEY=<a-new-fernet-key>
ALLOWED_HOSTS=beta.your-domain.com
ALLOWED_ORIGINS=https://beta.your-domain.com
```

Launch sequence:

1. Sign in as the configured reviewer and open **Administration → Users and access**.
2. A founder requests access at `/start`; no tenant or password is created at that point.
3. Review the request, approve it, copy the one-time activation link immediately, and send it through your chosen email or support channel.
4. The founder activates their account, then works only in an isolated synthetic tenant until they intentionally configure data, AI providers, or integrations.
5. Verify `/api/health/ready` and the beta application/activation flow on the deployed domain before inviting external testers.

There is deliberately no payment or automatic outbound email in this beta flow. Billing and transactional email should be added only when the relevant provider accounts and product policy are ready.

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

- **Tenant and project scoping** — tenant identity and project membership gate project queries, skills, and generated outputs
- **Data controls** — classification, PII handling, source permissions, and governance filters are applied in the organization data/RAG path
- **Audit trail** — operational events and agent activity are recorded for review
- **Human-in-the-loop** — generated skill outputs are queued for reviewer approval before download or distribution
- **bcrypt passwords** — no plaintext credentials anywhere in the codebase
- **JWT hard-fail** — docker-compose refuses to start without `JWT_SECRET_KEY`

---

## Architecture

```
Browser
  │
  ▼
nginx (:80)
  ├── React product portal (Vite build)
  │     workspace · admin · operations · project intelligence
  │
  └── /api/* → FastAPI product API (:8000)
        ├── Workspace API: meetings, CRM, reports, search, notifications
        ├── Tenant/Admin API: users, configuration, organization structure, integrations
        ├── Project API: scoped queries, skills, approvals, generated documents
        └── Unified intelligence gateway
              shared scope · permissions · evidence · audit contract
                   ├── organization agent specialist
                   ├── project and portfolio specialists
                   └── governed data and retrieval services
                         RAG · search · extraction/OCR · PII rules
                   ├── SQLite + files: tenant/project metadata and documents
                   ├── FAISS or Qdrant: vector retrieval and embeddings
                   ├── OpenRouter/Ollama: configured tenant model providers
                   └── Durable job queue + worker
                         indexing · source sync · webhooks · retry/dead letter
```

---

## Testing

```bash
make test
# or directly:
pytest tests/ -v --tb=short
```

The suite covers authentication, tenant isolation, workspace flows, project/RAG behavior, governance, durable jobs, configuration, and security middleware. The CI workflow also builds the React portal, runs browser E2E coverage, and performs a load smoke test.

---

## License

Proprietary — © Ayush Chhoker. All rights reserved.
