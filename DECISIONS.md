# RAPID — Decisions (why we built it this way)

_Plain-language record of the big calls. If you're about to re-add something that
was removed, read this first — the removals were deliberate._

For **how** the system is built, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## The product decision

RAPID is an **autonomous "AI company in a box"**: a founder onboards their
product and gets a full staff of department agents that do the day-to-day work
off the founder's own data, experienced through role-based views (log in as CEO →
CEO's picture; a department head sees only their department). It is a
**multi-tenant SaaS** — many founders sign up, each getting a fully private
company.

_(Historical note: a brief once tried to reposition RAPID as a non-autonomous
"operating-cadence workspace" and remove the agents entirely. That was overruled
by the founder. We kept that brief's engineering **discipline** — structural
security, deterministic routing, an audit log, human approval on consequential
actions — but not its product direction.)_

## The five decisions

- **D1 — Do the work, approve the consequences.** Agents act on their own until
  something spends money, goes public, or can't be undone; those pause for a
  human. Full autonomy was rejected because, across the industry, agents left
  fully unattended "hallucinate success" and get rolled back. A human stays on
  the irreversible controls.
- **D2 — Real multi-tenant SaaS.** Every customer's data is separated at the data
  layer (a tenant identity travels with every query and record). This designs out
  the original defect where a tenant id never reached the query layer and every
  request silently ran as one shared tenant.
- **D3 — Security is structural, not a prompt.** One fail-closed rulebook decides
  what any role may see (ALLOW / ANONYMIZE / BLOCK), and it runs before retrieval.
  The old code enforced access as a hint in the AI's prompt — advisory and easily
  ignored.
- **D4 — Deterministic routing + independent verification.** No agents competing
  to answer. Work is routed by explicit rules, and every step is checked by a
  separate verifier before it counts.
- **D5 — Keep the portal and role views; rebuild the engine.** The React
  workspace was already the right product surface. The mess was underneath.

---

## What we REMOVED, and why it must stay removed

The original codebase tried to combine two architectures that conflict: an
**autonomous multi-agent bidding mesh** (agents compete to answer; most confident
wins) and **governed access control**. Bolting governance onto a bidding-first
system made enforcement advisory instead of structural. Phase 0 removed the
bidding apparatus entirely (125 files). Do not re-add any of the following:

| Removed | What it was | Why it's gone |
|---------|-------------|---------------|
| **Agent bidding mesh** (`agents/mesh/`: MeshBus, EscalationRouter, AgentMemory, Orchestrator) | Agents bid on confidence to answer a query; a router escalated between them. | Non-deterministic and impossible to govern cleanly. Replaced by one governed AI call over permission-scoped evidence. |
| **C-suite agent hierarchy** (`agents/csuite/`) | Autonomous "executive" agents overseeing the mesh. | Part of the bidding system. **Note:** the C-suite as a *role/view* ("log in as CEO") is kept — that's a permission scope, not an autonomous agent. |
| **Department bidding agents** (`agents/departments/*/agent.py`) + `agents/registry.py` | 10 agents that bid to answer within the mesh. | The mesh is gone; these went with it. Department *work* now runs through `orgos/`. |
| **Dynamic / natural-language agent creation** (`routers/nl_agent_creator.py`, `routers/custom_agents.py`, `agent_supervisor.py`, admin `/agent-requests`) | Users/admins could spawn brand-new agents at runtime. | A reliability and security footgun. A fixed, tested set of departments is safer and auditable. |
| **Second, dead governance engine** (`infrastructure/governance_engine.py`, `pipeline_loader.py`) | A parallel rules engine nothing called. | Dead code; two rulebooks can silently disagree. There is now one. |
| **Bidding helpers** (`master_planner`, `fusion_agent`, `bid_selector`, `confidence_model`, `pipeline_merger`, `web_agent`, `memory_store`) | Support code for the bidding mesh. | Orphaned by the mesh removal. |
| **`/query` endpoint** | The raw multi-agent fan-out (~30 LLM calls). | Replaced by the governed gateway and the lean `/ask`. |

**If you grep the codebase** for `mesh`, `bid`, or `csuite` you will still find a
few legitimate matches — they are **not** the removed system:

- **`c_suite`** appears as a **role name** in `routers/` — that's the kept
  CEO/leadership *view*, not an autonomous agent.
- **`mesh`** appears in `orgos/` — that's **cross-department orchestration** (one
  department's work triggering another's, e.g. HR onboarding triggering IT and
  Finance). This is a real, kept capability of the autonomous engine and is a
  different thing from the deleted Q&A *bidding* mesh. Do not confuse them.
- **`escalation`** appears in `orgos/` and `people_ops_store` — that's the
  human-approval gate (D1), a kept feature, distinct from the deleted mesh's
  `EscalationRouter`.

---

## What we KEPT

- **The React portal** (`frontend/`) and its role-based views.
- **orgos** (`orgos/`) — the task engine that does real work and verifies it,
  including its cross-department orchestration.
- **The governed retrieval / RAG path** and the **intelligence gateway** (now
  making one governed AI call instead of falling back to the bidding engine).
- **The single governance module** (`governance_filter.py`) and the **audit
  ledger**.
- **`agents/system/{spokesperson, governance_filter, audit_logger}`**,
  **`agents/intelligence/`** (portal intelligence) and **`agents/skills/`**.

---

## Consequences we accept (honest gaps)

- The column-level rulebook is proven by tests but **not yet wired into live
  structured-record retrieval** — the path that used it (`db_pipeline`) was
  removed with the bidding agents. **Phase 1 wires it in** (the Marketing
  department, end-to-end).
- The secondary **`/ask`** endpoint is department-scoped but has no per-document
  sensitivity filter yet (the main product path, the gateway, does).
- AI runs on a local Ollama model by default; quality improves with a hosted
  model, swappable behind one adapter.

_Every claim here was true at the end of Phase 0 (2026-07-20): the app boots and
the full test suite passes (401 passed / 1 skipped)._
