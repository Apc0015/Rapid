# RAPID — Architecture (in plain language)

_Last updated: 2026-07-20, end of Phase 0 (the cleanup)._

This document explains how RAPID is built, written so a non-engineer can follow
the reasoning. For **why** we made the big calls (and what we removed), see
[DECISIONS.md](DECISIONS.md).

---

## What RAPID is

RAPID is **a company in a box, run by AI.** A founder connects their product and
its data, and gets a staff of department agents (marketing, sales, and more) that
do day-to-day work using the founder's own data. Each person experiences the
company **through the eyes of their role** — a CEO sees the whole company; a
department head sees only their department. That role boundary is enforced in the
data layer, which is what makes it real and safe.

Motto: **Know what matters. Decide with context. Follow through.**

---

## The shape of the system

```
  Person (in a role)
        │
        ▼
  React portal  ──────────────►  API (FastAPI, main.py + routers/)
  (frontend/)                          │
                                       ▼
                            ┌──────────────────────┐
                            │   Governance gate     │  ← decides what this role
                            │  (fail-closed rules)   │    may see, BEFORE anything
                            └──────────┬────────────┘    is retrieved
                                       ▼
             ┌─────────────────────────┼──────────────────────────┐
             ▼                         ▼                          ▼
      Governed answers          Workspace records          Work that gets done
   (intelligence_gateway,     (meetings, actions,          (orgos/ — the task
    documents + evidence)      CRM, projects, tickets)      engine: plan → do →
                                                            verify → log)
```

Everything a customer owns — their data, their agents — is separated per customer
(**multi-tenant**): a tenant identity travels with every request and every stored
record, so one customer can never see another's data.

---

## The parts, and what each does

| Part | Where | What it does |
|------|-------|--------------|
| **React portal** | `frontend/` | Every screen people use: overview, meetings, actions, people, CRM, projects, tickets, reports, library, chat. Role-based views. |
| **API** | `main.py`, `routers/` | The web endpoints the portal calls. Auth, workspace records, admin, intelligence. |
| **Governance** | `agents/system/governance_filter.py` (+ `constitution.yaml`) | The one rulebook: for any role and column, decide **ALLOW / ANONYMIZE / BLOCK**. Fail-closed. See below. |
| **Intelligence gateway** | `infrastructure/intelligence_gateway.py` | The product's "ask RAPID" brain. Collects permission-scoped evidence, then makes **one governed AI call** to write a cited, confidence-scored answer. |
| **Retrieval (documents)** | `pipelines/rag_pipeline.py`, `infrastructure/organization_rag.py` | Finds relevant documents. The gateway path also filters documents by classification and per-source ownership. |
| **orgos (the work engine)** | `orgos/` | Runs actual multi-step work as **Task Runs**: plan → do → **verify** (an independent check) → log. This is how agents do real work and prove it. |
| **Audit ledger** | `agents/system/audit_logger.py` | An immutable record of what happened and every access decision. |
| **Multi-tenant** | tenant id on every query + `data/faiss/{tenant}/…` | Keeps each customer's data and agents private. |

---

## The governance model (the important part)

Security is **structural** — a gate every request passes through — not a polite
instruction to the AI. There is exactly **one decision function**:

- `resolve_column_action(column, rules, role, default_action)` in
  `agents/system/governance_filter.py`.
- It returns **ALLOW** (show it), **ANONYMIZE** (mask it, e.g. salary → a team
  average), or **BLOCK** (remove it entirely).
- **Fail-closed:** anything not explicitly allowed is BLOCKED. A brand-new column
  is hidden until someone allows it. A malformed rule is treated as BLOCK.
- The **same function** is used everywhere columns are governed, so two paths can
  never disagree — in particular about which roles satisfy an "allow managers"
  rule.
- The rules themselves live in `constitution.yaml` (e.g. HR salary → ANONYMIZE,
  SSN → BLOCK, performance score → BLOCK).

**Department scope comes first.** Before any retrieval runs, the request is
checked against the role's permitted departments (`orgos/access.py`,
`routers/deps.py`, and the gateway's `allowed_departments`). A marketing-scoped
user is refused the HR department up front.

**Proof it works.** `tests/test_governance_boundaries.py` contains the hard-gate
tests: a marketing user is refused HR; an employee never receives raw
salary/SSN/performance; a manager sees "allow-manager" columns an employee can't.
These are written to **fail the build if governance is ever bypassed** — flip the
default to ALLOW and the raw SSN leaks, which the tests catch. CI runs every test,
so this blocks any weakening of security from reaching `main`.

---

## The retrieval paths, and where governance applies today

Being honest about the current state:

| Path | Used by | Governed how |
|------|---------|--------------|
| **Intelligence gateway** | The product chat (`/intelligence/ask`) | Department scope + document classification + per-source ownership. **The main, governed path.** |
| **Workspace records** | Meetings/actions/CRM/projects/tickets screens | Role + department checks in `routers/` (see `tests/test_role_boundaries.py`). |
| **orgos** | The task engine | Department view/write checks (`orgos/access.py`). |
| **`/ask` (grounded RAG)** | A secondary Q&A endpoint | Restricted to the user's permitted departments' document indexes. **Gap:** no per-document sensitivity filter yet. |

**Known gap, scheduled for Phase 1:** the column-level rulebook
(`resolve_column_action`) is proven by tests but is **not yet wired into live
structured-record retrieval** — the old path that used it (`db_pipeline`) was
removed with the bidding agents. Phase 1 (the Marketing department, end-to-end)
wires the one rulebook into the live records path so structured data is governed
column-by-column, and closes the `/ask` document gap.

---

## How agents do work: "do the work, approve the consequences"

Agents run on their own **up to any action that spends money, goes public, or
can't be undone.** Those pause for a human with the right role to approve. This is
enforced in `orgos/` as three tiers of autonomy:

- **A — runs on its own** (e.g. drafting a plan)
- **B — a human approves** (e.g. spending a budget)
- **C — a human decides** (e.g. anything legal/irreversible)

Every step is independently **verified** before it counts — an agent can't grade
its own homework — and everything is written to the audit ledger.

---

## Reliability

- **Confidence gating:** answers are scored; below the bar they route to a human
  rather than being guessed (thresholds `HIGH_CONF = 0.65`, `LOW_CONF = 0.40` in
  `config.py`).
- **Evidence + citations:** answers cite real sources.
- **Independent verification:** in orgos, a separate check confirms work actually
  happened.
- **Honest reporting:** status reflects what really occurred.

---

## Running it

See [README.md](README.md) for setup. In short: a FastAPI backend and a Vite
React frontend, a local Ollama model for AI by default, SQLite for data. The test
suite (`pytest tests/`) is the safety net and runs in CI on every change.
