# RAPID — RAG Application for Private Instant Deployment

An enterprise-grade, privacy-first AI assistant that routes queries across 10 specialised department agents, enforces column-level governance, and never exposes raw data to the LLM.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Flutter Web UI (rapid_ui/)                                     │
│  Login · Chat · Cloud · Audit · Admin · User Management        │
└────────────────────────┬────────────────────────────────────────┘
                         │  HTTP / REST
┌────────────────────────▼────────────────────────────────────────┐
│  FastAPI (rapid/)                                               │
│                                                                 │
│  POST /query ──► Spokesperson (intent classify)                 │
│                     │ escalation                                │
│                     ▼                                           │
│              MasterPlanner (decompose + bid)                    │
│                     │                                           │
│          ┌──────────┼──────────┐                                │
│          ▼          ▼          ▼  (parallel)                    │
│       HR Agent  Finance  Legal … (10 dept agents)              │
│          │  RAG pipeline + DB pipeline                          │
│          └──────────┬──────────┘                                │
│                     ▼                                           │
│              FusionAgent (merge + score)                        │
│                     │                                           │
│                     ▼                                           │
│              Spokesperson (compose answer)                      │
│                     │                                           │
│              AuditLogger + ChatHistory                          │
└─────────────────────────────────────────────────────────────────┘
```

### Privacy guarantees
- The LLM **never** sees raw database rows or raw document chunks — only natural-language summaries produced by R4 (RAG firewall) and D5 (DB firewall).
- Column-level governance rules (`constitution.yaml`) enforce Allow / Anonymise / Block per role and department.
- Every query is immutably logged to `data/audit.log`.

---

## Project structure

```
RAPID/
├── rapid/                      Backend (FastAPI + Python)
│   ├── main.py                 Thin app entry-point — registers routers, /query endpoint
│   ├── shared.py               Agent singletons (imported by main + routers)
│   ├── config.py               All tunable parameters (thresholds, paths, model names)
│   ├── constitution.yaml       Governance rules loaded at startup
│   ├── requirements.txt
│   ├── seed_db.py              One-time database seeding script
│   │
│   ├── agents/                 Multi-agent layer
│   │   ├── spokesperson.py     Tier-1: intent classification + answer composition
│   │   ├── master_planner.py   Tier-2: query decomposition + agent bidding
│   │   ├── fusion_agent.py     Merge dept results into a single answer
│   │   ├── governance_filter.py  Column-level ALLOW / ANONYMISE / BLOCK
│   │   ├── web_agent.py        Optional web search augmentation
│   │   ├── audit_logger.py     Immutable query + event log
│   │   ├── agent_supervisor.py Gap detection + agent rating
│   │   └── departments/        10 specialised dept agents
│   │       ├── hr_agent.py
│   │       ├── finance_agent.py
│   │       ├── legal_agent.py
│   │       ├── sales_agent.py
│   │       ├── marketing_agent.py
│   │       ├── operations_agent.py
│   │       ├── it_agent.py
│   │       ├── procurement_agent.py
│   │       ├── rd_agent.py
│   │       └── customer_success_agent.py
│   │
│   ├── routers/                One file per API concern
│   │   ├── deps.py             Shared auth helper (auth_user, require_admin)
│   │   ├── auth.py             /auth/login, /auth/register, password, my-access
│   │   ├── users.py            /users/* — dept/division/admin approval workflow
│   │   ├── admin.py            /admin/* — dept heads + division assignments
│   │   ├── documents.py        /ingest, /upload
│   │   ├── database.py         /db/connect, /db/connections
│   │   ├── llm.py              /llm/configure, /llm/models, /llm/status
│   │   ├── monitoring.py       /audit, /agents/stats, /health
│   │   ├── chat_sessions.py    /sessions/* — chat history persistence
│   │   ├── cloud_onedrive.py   /cloud/onedrive/* — OneDrive OAuth + import
│   │   └── cloud_gmail.py      /cloud/gmail/* — Gmail OAuth + import
│   │
│   ├── infrastructure/         Core integrations
│   │   ├── llm_client.py       Multi-provider LLM client (OpenRouter / Ollama / OpenAI)
│   │   ├── db_master.py        SQL execution + governance firewall
│   │   ├── doc_master.py       Document management + RAG indexing (ChromaDB)
│   │   ├── user_registry.py    User auth, roles, dept/division assignment
│   │   ├── chat_history.py     SQLite-backed session + message store
│   │   ├── cloud_tokens.py     Atomic OAuth token storage (data/cloud_tokens.json)
│   │   ├── onedrive_connector.py  OAuth2 PKCE + Graph API
│   │   └── gmail_connector.py     OAuth2 + Gmail API
│   │
│   ├── pipelines/
│   │   ├── rag_pipeline.py     Chunk → embed → hybrid search (vector + BM25) → rank
│   │   └── db_pipeline.py      SQL generation → execution → governance filter
│   │
│   ├── models/                 Internal data objects
│   │   ├── intent_object.py
│   │   ├── bid_object.py
│   │   ├── nl_result.py
│   │   └── query_event.py
│   │
│   └── data/                   Runtime data (git-ignored except schema/)
│       ├── db/rapid.db         SQLite — users, chat sessions, messages
│       ├── chroma/             ChromaDB vector store
│       ├── schema/             JSON table schemas (10 depts)
│       ├── documents/          Department document folders
│       ├── users.yaml          User accounts + roles
│       └── cloud_tokens.json   OAuth tokens (OneDrive + Gmail)
│
├── rapid_ui/                   Frontend (Flutter Web)
│   └── lib/
│       ├── main.dart
│       ├── theme.dart
│       ├── models/             query_response, audit_entry, chat_session, cloud_models
│       ├── providers/          auth, chat, sessions, cloud
│       ├── screens/            login, register, chat, audit, admin, users, access, cloud
│       ├── widgets/            answer_bubble, confidence_bar, dept_badge
│       └── services/api_service.dart
│
├── .env                        API keys and secrets (never commit)
├── .env.example                Template for .env
└── README.md                   This file
```

---

## Quick start

### Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.9+ |
| pip | latest |
| Flutter | 3.x |
| Ollama (local LLM) | latest |

### 1 — Clone and configure

```bash
git clone <repo-url>
cd RAPID
cp .env.example .env        # edit with your values
```

Minimum `.env` for local development (Ollama):

```env
# No external keys needed — Ollama runs locally
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=llama3.1:8b

# Optional — enable OneDrive / Gmail integration
MICROSOFT_CLIENT_ID=
MICROSOFT_REDIRECT_URI=http://localhost:8000/cloud/onedrive/callback

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/cloud/gmail/callback

# Base URL Flutter is served from (for OAuth redirects)
FLUTTER_BASE_URL=http://localhost:3000
```

### 2 — Start the backend

```bash
cd rapid
pip install -r requirements.txt
python seed_db.py            # first run only — creates tables + default admin
python3 -m uvicorn main:app --reload --port 8000
```

API docs available at: http://localhost:8000/docs

### 3 — Start the Flutter UI

```bash
cd rapid_ui
flutter pub get
flutter run -d chrome --web-port 3000
```

### 4 — Log in

Default admin credentials (set by `seed_db.py`):

| Field | Value |
|-------|-------|
| User ID | `rapid_admin` |
| Password | `admin123` ← **change immediately** |

---

## API reference

### Authentication
All endpoints (except `/auth/login`, `/auth/register`, `/users/meta`, `/health`) require `user_id` + `password` (or `token` for legacy `/query`).

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/auth/register` | — | Self-registration request |
| `POST` | `/auth/login` | — | Returns user profile |
| `GET`  | `/users/my-access` | user | View own access profile |
| `POST` | `/users/change-password` | user | Change own password |

### Query
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/query` | Full AI pipeline — returns answer, confidence, sources |

Request body:
```json
{
  "user_id": "rapid_john",
  "token": "password",
  "query": "What is our headcount in the London office?",
  "use_web": false,
  "session_id": "uuid-of-existing-session"
}
```

### Chat history
| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/sessions` | List sessions (newest first) |
| `POST` | `/sessions` | Create new session |
| `GET`  | `/sessions/{id}/messages` | Load session messages |
| `DELETE` | `/sessions/{id}` | Delete session |

### Documents
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/upload` | admin/manager | Multipart file upload → RAG ingest |
| `POST` | `/ingest` | admin/manager | Ingest by server-side path |

Supported file types: `.txt` `.pdf` `.md` `.csv` `.json` `.docx`

### Cloud integrations
| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/cloud/onedrive/connect` | Get OAuth URL |
| `GET`  | `/cloud/onedrive/status` | Connection status |
| `GET`  | `/cloud/onedrive/files` | Browse files |
| `POST` | `/cloud/onedrive/import` | Import file into RAG |
| `DELETE` | `/cloud/onedrive/disconnect` | Revoke connection |
| `GET`  | `/cloud/gmail/connect` | Get OAuth URL |
| `GET`  | `/cloud/gmail/status` | Connection status |
| `GET`  | `/cloud/gmail/labels` | Gmail label list |
| `GET`  | `/cloud/gmail/messages` | Messages for a label |
| `POST` | `/cloud/gmail/import/message` | Import email body |
| `DELETE` | `/cloud/gmail/disconnect` | Revoke connection |

### Admin
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/admin/dept-heads` | admin | List dept head assignments |
| `POST` | `/admin/dept-heads` | admin | Assign dept head |
| `DELETE` | `/admin/dept-heads/{dept}` | admin | Remove dept head |
| `GET`  | `/admin/divisions` | admin | List division assignments |
| `POST` | `/admin/divisions` | admin | Assign division head / C-Suite |
| `DELETE` | `/admin/divisions/{division}` | admin | Remove division head |

### Monitoring
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/audit` | admin/manager | Immutable audit trail |
| `GET`  | `/agents/stats` | admin/manager | Per-agent performance |
| `GET`  | `/health` | — | System health check |

### LLM configuration (admin)
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/llm/configure` | Switch provider at runtime |
| `GET`  | `/llm/models` | List models for a provider |
| `GET`  | `/llm/status` | Active provider status |

---

## Org hierarchy and access flow

```
CEO / Board
  └─ C-Suite (division heads)
       ├─ Commercial Division  →  sales, marketing, customer_success
       ├─ Finance Division     →  finance, procurement
       ├─ People Division      →  hr, legal
       ├─ Technology Division  →  it, rd
       └─ Operations Division  →  ops
```

### Access request flow (3-stage approval)

```
Employee self-registers
       ↓
  dept_review   ← dept head approves/rejects each requested dept
       ↓
division_review ← division head reviews cross-dept patterns
       ↓
 admin_review   ← admin creates account + issues login_key
```

### Role hierarchy

| Role | Can see data from |
|------|------------------|
| `employee` | Own permitted depts only |
| `manager` | Own permitted depts |
| `dept_head` | Their dept + subordinates |
| `division_head` | All depts in their division |
| `c_suite` | Entire division |
| `ceo` | All divisions |
| `board_member` | Aggregates only |
| `admin` | Everything |

---

## Cloud integrations setup

### OneDrive (Microsoft)

1. [Azure Portal](https://portal.azure.com) → **App registrations** → **New registration**
2. Redirect URI: `http://localhost:8000/cloud/onedrive/callback`
3. **API permissions** → Add `Files.Read`, `offline_access`
4. Copy **Application (client) ID** → add to `.env`:

```env
MICROSOFT_CLIENT_ID=<your-client-id>
MICROSOFT_REDIRECT_URI=http://localhost:8000/cloud/onedrive/callback
```

No client secret needed — uses OAuth2 PKCE (public client flow).

### Gmail (Google)

1. [Google Cloud Console](https://console.cloud.google.com) → New project → **Enable Gmail API**
2. **OAuth consent screen** → External → scopes: `gmail.readonly`, `userinfo.email`
3. **Credentials** → OAuth 2.0 Client ID → Web → Redirect: `http://localhost:8000/cloud/gmail/callback`
4. Copy **Client ID** + **Client Secret** → add to `.env`:

```env
GOOGLE_CLIENT_ID=<your-client-id>
GOOGLE_CLIENT_SECRET=<your-client-secret>
GOOGLE_REDIRECT_URI=http://localhost:8000/cloud/gmail/callback
```

---

## LLM providers

RAPID supports four providers switchable at runtime via `/llm/configure` (no restart needed):

| Provider | Key env var | Notes |
|----------|-------------|-------|
| **Ollama** (default) | `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | Fully local, no data leaves the machine |
| **Anthropic** | `ANTHROPIC_API_KEY` | Claude Haiku (fast) + Sonnet (decomposition) |
| **OpenRouter** | `OPENROUTER_API_KEY` | Access 100+ models via one key |
| **OpenAI** | `OPENAI_API_KEY` | GPT-4o, o1, o3 |

---

## Governance

Column-level rules are defined in `constitution.yaml`:

```yaml
rules:
  - table: employees
    column: salary
    default_state: block          # no one sees raw salaries
    role_override:
      admin: allow
    dept_override:
      finance: anonymize          # finance sees redacted values
```

States: `allow` · `anonymize` · `block`

Priority: `role_override` > `dept_override` > `default_state`

Unregistered columns default to `allow`.

---

## Development notes

- **No LangChain** — all LLM calls use raw `openai.AsyncOpenAI` / `anthropic.AsyncAnthropic` / `httpx`
- **sqlparse AST** enforces SELECT-only SQL — no string matching
- **Structural privacy** — dataclasses have no `rows`, `chunks`, or `chunk_text` fields visible to the LLM
- Audit log retained for **7 years** (configurable in `config.py`)
- ChromaDB collections tagged with embedding dimension: `rapid_docs_1536d`
