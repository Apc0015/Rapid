# RAPID — Comprehensive Technical Analysis

**Project:** RAPID (RAG Application for Private Instant Deployment)
**Analysis Date:** February 27, 2026
**Document Version:** 1.0

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Project Overview & Purpose](#2-project-overview--purpose)
3. [How It Works — Deep Dive](#3-how-it-works--deep-dive)
4. [Comprehensive Feature Analysis](#4-comprehensive-feature-analysis)
5. [Workflow Analysis](#5-workflow-analysis)
6. [Pros and Cons](#6-pros-and-cons)
7. [Real-World Problem Solving — Two Detailed Scenarios](#7-real-world-problem-solving)
8. [Use Case Documentation](#8-use-case-documentation)
9. [Orchestration & Architecture](#9-orchestration--architecture)
10. [Technology Stack & Libraries](#10-technology-stack--libraries)
11. [Appendix — Glossary](#11-appendix--glossary)

---

## 1. Executive Summary

RAPID is an enterprise-grade, **private AI assistant platform** that lets any organization query its own internal documents and databases using plain English — without sending sensitive data to third-party cloud services.

Think of it as a private version of ChatGPT that knows everything your organization has ever written down. Upload a legal contract, a financial report, or a CSV of last year's sales data, and RAPID will automatically figure out the best way to answer questions about it — either through intelligent document search (RAG) or through auto-generated SQL queries on structured data.

### What Makes RAPID Different

Most AI document tools require manual configuration of chunk sizes, embedding models, and search strategies. RAPID eliminates this complexity with an **Intelligent Auto-RAG** system — it automatically detects what kind of document you uploaded (legal contract? academic paper? spreadsheet?) and configures the entire pipeline with research-backed optimal parameters, invisible to the end user.

### Key Capabilities at a Glance

| Capability | Details |
|---|---|
| Document types supported | 32+ file types (PDF, Word, Excel, CSV, code, JSON, YAML, and more) |
| LLM providers | OpenAI, Anthropic Claude, OpenRouter, Ollama (local), LM Studio (local) |
| Embedding providers | SentenceTransformers (local), OpenAI, Ollama, HuggingFace |
| Search modes | Semantic (vector), Keyword (BM25), Hybrid (RRF fusion) |
| Data query | Natural Language → SQL for spreadsheets and databases |
| Multi-tenancy | Multiple organizations, departments, groups with fine-grained permissions |
| Privacy | Fully self-hostable; no data leaves your infrastructure |

---

## 2. Project Overview & Purpose

### 2.1 What Is RAPID?

RAPID stands for **RAG Application for Private Instant Deployment**. It is a full-stack AI application that serves as a private, organizational knowledge base assistant. Users can:

- Upload documents in 32+ formats
- Ask questions in plain English
- Get answers sourced directly from their uploaded documents
- Query spreadsheet data without knowing SQL
- Connect to live databases (PostgreSQL, MySQL, Snowflake, BigQuery)
- Get web-augmented answers when internal documents lack the information

### 2.2 The Problem It Solves

Organizations accumulate vast amounts of knowledge locked in files: contracts, reports, policies, research papers, spreadsheets. Employees spend hours searching through these files manually. Traditional search tools find documents but don't **answer questions**.

Existing commercial AI tools (ChatGPT Enterprise, Google Gemini for Workspace) have two critical drawbacks for many organizations:
1. **Data privacy**: Documents are sent to third-party servers
2. **Configuration burden**: Optimal AI configuration requires expertise most organizations don't have

RAPID solves both:
- It runs entirely on your infrastructure (no data leaves)
- It automatically configures itself based on what you upload

### 2.3 Target Audience

- **Primary:** Organizations with sensitive data that cannot leave their environment (legal firms, healthcare providers, financial institutions, government agencies, research institutions)
- **Secondary:** Any organization wanting a self-hosted AI knowledge base without needing a team of ML engineers to configure it

### 2.4 Core Value Proposition

> "Upload your files, ask your questions, get answers — automatically and privately."

RAPID's value comes from three pillars:
1. **Zero-configuration intelligence** — Auto-detects document type and auto-configures the entire AI pipeline
2. **Privacy by design** — Deployable entirely on-premises with local LLMs (Ollama) and local embeddings (SentenceTransformers)
3. **Dual-pipeline routing** — Automatically routes structured data to SQL and unstructured text to RAG

---

## 3. How It Works — Deep Dive

### 3.1 Architecture Overview

RAPID has a **layered architecture** with three tiers:

```
┌───────────────────────────────────────────────┐
│           PRESENTATION TIER                    │
│   Streamlit Web UI  ←→  FastAPI REST Backend   │
└───────────────────────────────────────────────┘
                        │
┌───────────────────────────────────────────────┐
│            INTELLIGENCE TIER                   │
│  DocumentClassifier → AutoConfigService        │
│  ChunkingOptimizer → TextPreprocessor          │
│  QueryDecomposer → MultiAgentOrchestrator      │
│  ConfidenceScorer → SpeculativePipeline        │
└───────────────────────────────────────────────┘
                        │
┌───────────────────────────────────────────────┐
│             STORAGE TIER                       │
│  ChromaDB (vectors)  SQLite (users, metadata)  │
│  BM25 Index (keywords)  SQLite (tabular data)  │
│  NetworkX (knowledge graph)                    │
└───────────────────────────────────────────────┘
```

### 3.2 The Upload Flow — How Documents Are Processed

When a user uploads a file, these steps happen automatically:

**Step 1 — File Validation**
The file validator checks the extension and MIME type against a whitelist of 32+ supported formats. Files exceeding the size limit are rejected.

**Step 2 — Document Classification**
The `DocumentClassifier` analyzes the file using heuristics (no LLM call needed):
- Checks file extension (`.csv`, `.parquet` → always tabular)
- For text files, reads a sample and scores keyword frequency against domain vocabularies (legal terms, medical terms, academic terms, etc.)
- Outputs: `doc_type` (e.g., "academic", "legal", "tabular") and `doc_subtype` (e.g., "research_paper", "contract", "financial_spreadsheet")

**Step 3 — Pipeline Routing**
Based on classification:
- **Tabular files** → `TabularPipeline` (loads into SQLite, enables NL-to-SQL)
- **All other files** → `RAGEngine` (chunks, embeds, stores in ChromaDB)

**Step 4A — Tabular Pipeline (for spreadsheets)**
1. Loads CSV/Excel/Parquet into SQLite table
2. Registers as a database connection in `CloudDatabaseService`
3. Subsequent queries generate SQL automatically

**Step 4B — RAG Pipeline (for text documents)**
1. `AutoConfigService` looks up research-backed optimal settings for this doc type
2. `TextPreprocessor` cleans OCR artifacts, normalizes whitespace, resolves pronouns
3. `LanguageDetector` checks language → switches to multilingual embedding model if needed
4. `ChunkingOptimizer` selects from 11 chunking strategies based on doc type
5. Text is split into chunks, embedded (converted to vectors), and stored in ChromaDB
6. BM25 keyword index is also built for hybrid retrieval
7. Knowledge graph entities are extracted (optional, async)
8. Document registered in `DataCatalogService` with topic keywords

**Step 5 — Registration**
The document is registered in the data catalog with its topics, stats, and pipeline type so the query router can find it later.

### 3.3 The Query Flow — How Questions Are Answered

**Step 1 — Query Decomposition**
`QueryDecomposer` checks if the query is complex (multiple questions, comparisons, conjunctions). If so, it splits it into focused sub-queries. Example: "What was Q3 revenue and who approved the budget?" → two separate queries.

**Step 2 — Intent Classification**
The `MultiAgentOrchestrator` (powered by LangGraph) classifies query intent:
- `general_chat` → direct LLM answer (no documents needed)
- `query_agent` → RAG retrieval
- `db_agent` → SQL generation
- `multi_source` → both RAG + SQL
- `graph_query` → knowledge graph traversal

**Step 3 — Retrieval**
For RAG queries:
- Semantic search in ChromaDB (vector similarity)
- Keyword search via BM25 index
- Results merged using Reciprocal Rank Fusion (RRF)
- RBAC filter applied (user only sees documents they can access)

For SQL queries:
- Schema context provided to LLM
- LLM generates SQL
- SQL executed on the appropriate database
- Results formatted as natural language

**Step 4 — Generation**
The LLM generates an answer from retrieved context. Optionally uses the Speculative Pipeline (draft fast → verify with larger model).

**Step 5 — Confidence Scoring**
`ConfidenceScorer` evaluates the answer on three dimensions:
- **Context Relevance** (30%) — Are retrieved chunks actually about the question?
- **Faithfulness** (50%) — Is the answer grounded in the retrieved text?
- **Completeness** (20%) — Did the answer address what was asked?

If overall score < 0.40: retry with different strategy (expand search, try web search)
If 0.40–0.65: return with "low confidence" flag
If ≥ 0.65: return with high confidence

**Step 6 — Response & Citation**
Answer returned with source citations. Conflicts between sources are detected and flagged. If a LLM-based faithfulness check is configured, sentence-level citation tracking is performed.

### 3.4 Data Flow Diagram (Text Description)

```
User Question
    │
    ▼
QueryDecomposer ──── complex? ──── split into sub-queries
    │
    ▼
MultiAgentOrchestrator (LangGraph state machine)
    │
    ├── classify_node → intent label
    │
    ├── [general_chat]  → direct_answer_node → LLM → response
    │
    ├── [query_agent]   → two_stage_query:
    │       ├── semantic search (ChromaDB)
    │       ├── keyword search (BM25)
    │       └── RRF fusion → top chunks
    │           → LLM generates answer from chunks
    │
    ├── [db_agent]      → schema_context → LLM → SQL → execute → format
    │
    └── [multi_source]  → both paths above → fusion_node → merged answer
    │
    ▼
verify_node (ConfidenceScorer)
    │
    ├── score ≥ 0.65 → return answer
    ├── score 0.40–0.65 → return with low-confidence flag
    └── score < 0.40 → repair_node (HyDE / broader search) → retry once
    │
    ▼
Response with sources, confidence level, conflict warnings
```

---

## 4. Comprehensive Feature Analysis

### Feature 1: Intelligent Auto-RAG (Document Classification + Auto-Configuration)

**Description:**
The flagship feature. When any document is uploaded, two services work together invisibly: `DocumentClassifier` identifies what kind of document it is, and `AutoConfigService` maps that to research-backed optimal chunking and retrieval settings.

**How It Works:**
- `DocumentClassifier` uses file extension + keyword scoring (no LLM) to assign `(doc_type, doc_subtype)` pairs
- `AutoConfigService` maintains a lookup table with 15+ specific configurations derived from academic benchmarks
- Each configuration specifies: `chunk_size`, `overlap`, `top_k`, `search_mode`, `embedding_hint`

**Research-Backed Configurations:**
| Document Type | Chunk Size | Overlap | Search Mode | Benchmark Source |
|---|---|---|---|---|
| FAQ | 220 words | 25 | Keyword (BM25) | NQ / TriviaQA |
| Policy / Procedure | 380 words | 50 | Hybrid | SQuAD / FinQA |
| General narrative | 512 words | 64 | Hybrid | BEIR multi-domain |
| Academic paper | 950 words | 150 | Hybrid | QASPER (+12% F1 vs 512w) |
| Legal contract | 780 words | 100 | Hybrid | CUAD benchmark |
| Medical / clinical | 500 words | 60 | Hybrid | PubMedQA / MedQA |
| Financial report | 600 words | 80 | Hybrid | FinanceBench |
| Source code | 300 words | 50 | Hybrid | Function-level chunking |

**Benefits:**
- Zero configuration for end users
- Demonstrably better retrieval quality (e.g., 12% F1 improvement on academic papers)
- Consistent, reproducible behavior based on published research

**Drawbacks:**
- Heuristic classification can misclassify ambiguous documents (e.g., a policy document that looks like a legal contract)
- Configuration table is static (no online learning or feedback loop)
- Admin cannot override individual document settings through the UI (only via the `update_config` API in memory — resets on restart)
- No A/B testing infrastructure to validate configurations against this organization's specific data

**Dependencies:** `DocumentClassifier`, `AutoConfigService`, `ChunkingOptimizer`

**Future Improvements:**
- User feedback loop to fine-tune configs over time
- Per-organization config overrides persisted to database
- LLM-assisted classification for edge cases

---

### Feature 2: Eleven-Strategy Chunking Optimizer

**Description:**
Instead of a single fixed chunking approach, RAPID implements 11 different strategies and automatically selects the best one for each document type.

**Strategies Implemented:**
1. `fixed_word` — Fixed word-count windows (baseline)
2. `fixed_sentence` — Group N sentences per chunk
3. `paragraph` — Split on blank lines
4. `semantic` — Embedding-based split at semantic discontinuities
5. `recursive` — LangChain-style recursive character splitting
6. `sliding_window` — 50% overlap for dense Q&A content
7. `token_aware` — Accounts for word-to-token ratio
8. `section_aware` — Detects markdown headers, ALL-CAPS lines, numbered sections
9. `code_aware` — Splits at function/class boundaries (Python, JS, Java, Go, Rust)
10. `table_intact` — Keeps markdown/HTML tables as atomic units
11. `step_aware` — Splits at numbered step boundaries for procedural docs

**Selection Logic:**
- Subtype overrides: `faq` → `step_aware`, `markdown_table` → `table_intact`, `research_paper` → `section_aware`
- Type defaults: `code` → `code_aware`, `academic` → `section_aware`, `legal` → `paragraph`
- Optional trial-scoring: runs top-2 candidates and picks the better one by heuristic quality score

**Quality Score:**
Chunks are scored on: coverage (fraction of original text preserved), uniformity (std-dev of chunk sizes), and average chunk length penalty for extremes.

**Benefits:**
- Preserves document structure (tables stay together, code functions stay together)
- Better retrieval precision for structured documents
- No configuration required from users

**Drawbacks:**
- Semantic strategy requires loading a SentenceTransformer model — adds latency
- Trial scoring doubles processing time for ambiguous documents
- Quality scoring is heuristic only, not based on actual retrieval outcomes
- Code-aware strategy detects Python/JS/Java patterns but may miss other languages

**Dependencies:** `sentence-transformers`, `AutoConfigService`

---

### Feature 3: Dual-Pipeline (RAG + SQL) with Automatic Routing

**Description:**
When a user uploads a CSV, Excel, or Parquet file, instead of trying to embed rows of numbers into vectors (which performs poorly), RAPID loads the data into a local SQLite database and routes all queries through an NL-to-SQL pipeline. From the user's perspective, they ask questions in English; the system silently writes SQL.

**How It Works:**
1. `TabularPipeline.ingest()` reads the file with automatic encoding/delimiter detection
2. Data is loaded into `data/tabular_uploads.db` as a named SQLite table
3. The connection is registered in `CloudDatabaseService`
4. On query, the multi-agent orchestrator's `DatabaseProxyAgent` gets schema context and asks the LLM to generate SQL
5. SQL is executed, results returned as natural language

**Benefits:**
- Handles datasets with hundreds of thousands of rows efficiently
- Exact numeric answers (vector search on numbers is unreliable)
- Supports CSV, Excel (multi-sheet), Parquet, and JSON arrays
- Multiple sheets become multiple tables with clear naming

**Drawbacks:**
- SQL generation can fail for complex aggregations or ambiguous column names
- SQLite has limitations compared to production databases (no window functions in older versions, 500k row cap enforced by code)
- No schema inference validation — bad data types may cause silent coercion errors
- Excel files with merged cells or pivot tables may not load correctly
- Generated SQL is not validated before execution (SQL injection via LLM is theoretically possible if LLM is compromised)

**Dependencies:** `pandas`, `pyarrow`, `SQLAlchemy`, `CloudDatabaseService`, LLM provider

---

### Feature 4: Multi-Agent Orchestrator with LangGraph

**Description:**
The query handling system is implemented as a directed state graph (using LangGraph), where different "agents" handle different types of queries. This is a **CRAG-inspired (Corrective RAG)** architecture.

**Graph Nodes:**
- `classify_node` — LLM classifies intent into one of 5 categories
- `direct_answer_node` — For general chat (no retrieval needed)
- `query_agent_node` — RAG retrieval + generation
- `db_agent_node` — SQL generation + execution
- `multi_source_node` — Parallel RAG + SQL
- `fusion_node` — Merges results from multiple sources
- `graph_query_node` — Knowledge graph traversal
- `verify_node` — Confidence scoring (ConfidenceScorer)
- `repair_node` — HyDE (Hypothetical Document Embedding) retry for low-confidence answers
- `partial_deliver_node` — Returns best available answer if max retries exceeded

**Flow:**
1. Query enters → classify_node
2. Routed to appropriate agent node(s)
3. Results pass through verify_node
4. If confidence ≥ 0.65: done; else retry once via repair_node
5. After repair: if still low → partial_deliver_node

**Benefits:**
- Clean separation of concerns between query types
- Automatic retry with different strategy for low-confidence answers
- Complex queries can use multiple sources simultaneously
- State is inspectable for debugging/tracing

**Drawbacks:**
- LangGraph adds complexity; debugging state machine issues is non-trivial
- LLM classification step adds latency to every query
- The repair mechanism (HyDE) makes another LLM call, doubling cost for low-confidence queries
- Concurrent parallel queries (multi_source) are executed with ThreadPoolExecutor but may hit rate limits

**Dependencies:** `langgraph`, `langchain-core`, `LLMManager`

---

### Feature 5: 3D Confidence Scoring System

**Description:**
After every answer is generated, the `ConfidenceScorer` evaluates it on three dimensions and produces a structured verdict with retry recommendations.

**Three Dimensions:**
1. **Context Relevance (30% weight)** — Keyword overlap between query and retrieved chunks. Scaled so 30% raw overlap maps to "reasonably relevant."
2. **Faithfulness (50% weight)** — If an LLM client is provided: sends a 0–10 faithfulness prompt to the LLM. Otherwise, uses heuristic keyword overlap between answer and chunks.
3. **Completeness (20% weight)** — Checks answer length, evasion phrases ("I don't know", "no information"), and keyword coverage of query terms.

**Additional Capabilities:**
- **Unanswerable Detection**: If fewer than 20% of query keywords appear in chunks → flag as unanswerable, route to web search
- **Conflict Detection**: Cross-chunk numeric conflict detection (e.g., same subject has different values in different sources)
- **Citation-level Faithfulness**: For each sentence in the answer, finds the supporting chunk and reports unsupported sentences

**Verdict Thresholds:**
- ≥ 0.65 → `"high"` — return answer
- 0.40–0.65 → `"medium"` — return with low-confidence warning
- < 0.40 → `"low"` — trigger retry

**Benefits:**
- Prevents hallucinated answers from being served confidently
- Conflict detection helps users know when sources disagree
- Sentence-level citation tracking for auditability

**Drawbacks:**
- Heuristic faithfulness (keyword overlap) can give high scores to answers that repeat context verbatim without understanding it
- LLM faithfulness check adds latency and cost
- Numeric conflict detection is purely pattern-based and generates false positives (e.g., different years' data)
- Completeness scoring penalizes valid short answers

**Dependencies:** `ConfidenceScorer`, optional LLM client for faithfulness

---

### Feature 6: Hybrid Search (Semantic + BM25 + RRF Fusion)

**Description:**
Instead of relying solely on vector similarity (semantic search) or keyword matching, RAPID combines both using Reciprocal Rank Fusion (RRF) — a rank-aggregation technique that is robust to score scale differences.

**Components:**
- **Semantic search**: ChromaDB cosine similarity on chunk embeddings
- **Keyword search**: BM25 (Okapi BM25 via `rank-bm25`) on tokenized chunks
- **RRF Fusion**: Ranks from both lists are combined using `score = Σ (weight / (rank + 60))`

**Search Mode Selection:**
- `keyword` — FAQ/factual documents (BM25 only)
- `semantic` — Structured/nested documents
- `hybrid` — All other types (default)

**Benefits:**
- Catches cases where semantic search fails (exact term match, specific numbers, abbreviations)
- Catches cases where keyword search fails (synonyms, paraphrasing)
- RRF is parameter-robust and doesn't require tuning score scales

**Drawbacks:**
- BM25 index is stored as JSON on disk and fully reloaded on restart (no incremental update)
- BM25 model is rebuilt from scratch on every new document indexing (O(n) in total corpus size)
- No deduplication of overlapping chunks from semantic and keyword results
- The `alpha` weighting parameter for RRF is fixed at 0.5 (not tunable per document type)

**Dependencies:** `rank-bm25`, `chromadb`, `FullTextSearchEngine`

---

### Feature 7: Knowledge Graph Builder

**Description:**
When documents are ingested, RAPID can optionally extract entities and relationships using LLM-based Named Entity Recognition (NER), building a NetworkX directed graph stored per-user as a JSON file.

**How It Works:**
1. LLM is prompted to extract entities (Person, Organization, Location, Product, Concept) and relationships (works_at, reports_to, manufactures)
2. Entities become nodes; relationships become directed edges
3. Graph is persisted to `data/knowledge_graph/user_{username}_graph.json`
4. Graph queries allow finding connected entities, relationship chains

**Benefits:**
- Enables relationship queries ("Who reports to the CFO?" "Which departments use which systems?")
- Per-user isolation preserves privacy
- NetworkX provides rich graph algorithms out of the box

**Drawbacks:**
- LLM-based extraction is slow and costly for large document sets
- Entity resolution is not implemented — "Apple Inc." and "Apple" may become separate nodes
- Graph is not integrated with the main query router (graph_query_node exists but is separate from the confidence/retry loop)
- JSON persistence doesn't scale for large graphs (no pagination, loads entirely into memory)
- No graph visualization in the UI

**Dependencies:** `networkx`, LLM provider

---

### Feature 8: Multi-Provider LLM & Embedding Support

**Description:**
RAPID supports 5 LLM providers and 4 embedding providers, with automatic selection and runtime switching.

**LLM Providers:**
| Provider | Type | Notes |
|---|---|---|
| OpenAI | Cloud | GPT-3.5, GPT-4, GPT-4o |
| Anthropic | Cloud | Claude 3 Haiku/Sonnet/Opus |
| OpenRouter | Cloud | 100+ models via single API |
| Ollama | Local | Any pulled model (Llama, Mistral, etc.) |
| LM Studio | Local | OpenAI-compatible local server |

**Embedding Providers:**
| Provider | Type | Notes |
|---|---|---|
| SentenceTransformers | Local | Default; all-MiniLM-L6-v2 (384d) |
| Ollama | Local | nomic-embed-text, mxbai-embed-large |
| OpenAI | Cloud | text-embedding-3-small/large |
| HuggingFace | Cloud | Via Inference API |

**Auto-Selection Logic:**
- Embeddings: prefers local (SentenceTransformers) → Ollama → OpenAI → HuggingFace
- LLM: uses explicitly configured provider/model; falls back to first available

**Benefits:**
- Organization can start with local models (100% private) and switch to cloud if needed
- Multilingual model auto-switching (LanguageDetector recommends `multilingual-e5-base`)
- No vendor lock-in

**Drawbacks:**
- LLM context windows differ across providers (not accounted for in chunk assembly)
- Model dimension mismatch if embedding provider is switched after documents are indexed (ChromaDB collection becomes incompatible)
- Anthropic doesn't provide embedding endpoints — only usable as LLM
- Ollama embedding availability check polls `/api/tags` on every operation

**Dependencies:** `openai`, `anthropic`, `langchain-openai`, `langchain-anthropic`, `langchain-community`, `sentence-transformers`, `requests`

---

### Feature 9: Enterprise Security — JWT Auth, RBAC, Encryption, Audit Log

**Description:**
RAPID implements a layered security model appropriate for enterprise deployment.

**Authentication:**
- JWT tokens (HS256) with 30-minute expiration
- bcrypt password hashing with salt
- OAuth/OIDC SSO for Google, Microsoft, generic OIDC, Dropbox
- Rate limiting: in-memory sliding window (configurable limit/window)
- Password strength requirements: min 8 chars, uppercase + lowercase + digit

**Authorization (RBAC):**
- Three roles: `admin`, `manager`, `user`
- Document access levels: `private`, `group`, `org`, `public`
- Permission checked per document per user: owner → admin → access level → allowed_users → allowed_roles → allowed_groups
- RBAC filter applied to all retrieval results before returning to user

**Encryption:**
- `EncryptionService` for encrypting file contents at rest
- JWT secret auto-generated and stored with `chmod 600` permissions

**Audit Logging:**
- Rotating log file (10MB max, 5 backups) for all security events
- Events: login, logout, document upload/delete, permission changes
- JSON-structured log entries with timestamp, user, action, resource

**Benefits:**
- Multi-tenant isolation at organization and group level
- Comprehensive audit trail for compliance
- SSO integration reduces password management burden

**Drawbacks:**
- Rate limiting is **in-memory only** — resets on restart; doesn't work across multiple server instances
- JWT secret stored in a file (not in a proper secret manager)
- No refresh token mechanism — users must re-login every 30 minutes
- RBAC permissions are stored in SQLite — not designed for high-concurrency writes
- Input sanitization strips HTML tags but relies on parameterized queries for SQL injection prevention (correct approach, but HTML stripping is incomplete for complex XSS vectors)

**Dependencies:** `PyJWT`, `bcrypt`, `cryptography`, `sqlite3`, `msal` (Microsoft OAuth)

---

### Feature 10: Cloud Storage Connectors

**Description:**
RAPID connects to four cloud storage services to pull documents directly from where organizations already store them.

**Supported Services:**
- AWS S3 (via `boto3`)
- Azure Blob Storage (via `azure-storage-blob`)
- Google Drive (via `google-api-python-client` + OAuth)
- Microsoft OneDrive (via `msal` + Graph API)
- Dropbox (via `dropbox` SDK + OAuth)

**How It Works:**
1. User authenticates via OAuth to the cloud service
2. Files are listed and can be browsed in the UI
3. Selected files are downloaded to a local cache (`cloud_cache/`)
4. Downloaded file is processed through the normal upload pipeline (classify → chunk → index)

**Benefits:**
- Users don't need to manually download and re-upload files
- Supports the major enterprise storage ecosystems
- Files cached locally for faster re-processing

**Drawbacks:**
- Cache is not synchronized — changes in cloud storage don't automatically re-index
- OAuth tokens are not encrypted in storage
- No incremental sync (entire file is re-downloaded on update)
- Local cache directory grows unboundedly without cleanup

**Dependencies:** `boto3`, `azure-storage-blob`, `google-api-python-client`, `google-auth-oauthlib`, `msal`, `dropbox`

---

### Feature 11: Web Search Augmentation

**Description:**
When internal documents don't contain the answer to a query (detected by `ConfidenceScorer.is_unanswerable()`), RAPID can optionally fall back to web search.

**Supported Providers:**
- Tavily (AI-optimized search with summarization)
- Google Custom Search
- Bing Search API

**How It Works:**
1. Confidence scorer determines the query is unanswerable from internal docs
2. Query is sent to configured web search provider
3. Results (title, snippet, URL, date) are returned alongside internal results
4. LLM synthesizes a combined answer

**Benefits:**
- Answers questions not covered in internal documents
- Provides up-to-date information for time-sensitive queries
- Multiple provider options for redundancy

**Drawbacks:**
- Disabled by default (`ENABLE_WEB_SEARCH=false`) — organizations may not want external data mixed with internal answers
- No source trust ranking (untrusted web results could override accurate internal results)
- Web search results are not indexed or cached for future use
- Tavily provides AI-generated summaries that may themselves be hallucinated

**Dependencies:** `httpx`, web search API keys (optional)

---

### Feature 12: Speculative RAG Pipeline

**Description:**
An optional two-stage generation pipeline where a fast/small LLM drafts an answer, a larger LLM verifies it, and the system returns the draft if it passes or the corrected version if it doesn't.

**Flow:**
1. Small LLM (e.g., GPT-3.5-turbo) generates a draft answer
2. `ConfidenceScorer.score_citation_faithfulness()` evaluates draft faithfulness
3. If faithfulness ≥ threshold (default 0.70): return draft
4. If below threshold: larger LLM (e.g., GPT-4o) corrects the draft
5. Return the corrected answer

**Benefits:**
- Lower cost: most queries can be answered by the draft (fast + cheap)
- Higher quality: a verifier catches errors before serving
- Configurable threshold for quality/cost trade-off

**Drawbacks:**
- Requires two different LLM configurations (draft model + verify model)
- Still incurs two LLM calls when draft fails
- Verification notes are generated but not always surfaced to user
- Not currently wired into the default query path — must be explicitly invoked

**Dependencies:** `ConfidenceScorer`, two LLM clients

---

### Feature 13: Query Decomposition

**Description:**
Complex multi-part questions are automatically split into focused sub-queries, each answered independently, then synthesized.

**Detection:**
- Multiple question marks in one query
- Conjunction patterns: "and also", "as well as", "furthermore", "in addition"
- Comparison patterns: "compare", "difference between", "versus"
- Three or more question words (what/who/when/where/why/how)

**Decomposition Strategy:**
- Heuristic (no LLM): for queries < 15 words or with clear split points
- LLM-based: for complex queries — asks LLM to return a JSON array of sub-questions

**Synthesis:**
- `"compare"` hint → numbered comparison format
- `"list"` hint → concatenated list
- `"merge"` hint → coherent paragraph (via LLM synthesis)

**Benefits:**
- Better retrieval precision (focused sub-queries produce better embeddings)
- Enables routing different parts to different pipelines (revenue → SQL, strategy → RAG)
- Users don't need to manually simplify complex questions

**Drawbacks:**
- Heuristic detection can split questions that don't need splitting
- LLM decomposition adds latency for already-slow queries
- Synthesis quality depends on LLM coherence; simple concatenation fallback loses context
- Sub-queries run sequentially (not parallelized), multiplying latency

**Dependencies:** `QueryDecomposer`, optional LLM client

---

### Feature 14: Data Catalog Service

**Description:**
Every uploaded document is registered in a lightweight queryable catalog that maintains a topic index for smart query routing.

**Schema:**
```
data_catalog:
  doc_id, filename, username, doc_type, doc_subtype,
  pipeline, topics (JSON array), stats (JSON), conn_id, doc_date, upload_time
```

**Topic Extraction:**
Top-N keywords by frequency from document text (stop words removed), stored as the document's "topic fingerprint."

**Query Routing Use:**
Before retrieval, `DataCatalogService.find_relevant()` scores catalog entries by keyword overlap with the query and returns the most relevant documents to include in the retrieval scope.

**Benefits:**
- Avoids searching irrelevant documents (especially in large collections)
- Provides a human-readable summary of available data sources to include in LLM context
- Supports filtering by pipeline type (SQL vs RAG)

**Drawbacks:**
- Topic extraction is frequency-based TF-style (not TF-IDF) — common domain words are overrepresented
- No semantic similarity in catalog lookup (only exact keyword matching)
- Topics are extracted at upload time only — not updated if document is re-indexed
- The catalog summary included in LLM context grows with document count, consuming tokens

**Dependencies:** `sqlite3`, `DataCatalogService`

---

### Feature 15: Conversation Persistence

**Description:**
RAPID maintains full conversation history in SQLite, allowing users to pick up where they left off across sessions.

**Schema:**
```
conversations: conversation_id, user_id, title, created_at, last_message_at, archived
messages: message_id, conversation_id, role, content, created_at, sources
```

**UI Session Persistence:**
Streamlit sessions are ephemeral. RAPID adds server-side session caching (via `@st.cache_resource`) keyed by a query-parameter session ID, allowing page refreshes to restore the auth state without re-login.

**Benefits:**
- Users can reference previous conversations
- Conversation history can be included in LLM context for follow-up questions
- Archived conversations are kept for audit

**Drawbacks:**
- Message content stored in plaintext in SQLite (not encrypted)
- No conversation search
- No automatic summarization of long conversations to manage context window
- SQLite doesn't scale well for hundreds of concurrent conversation writers

**Dependencies:** `sqlite3`, `ConversationService`

---

### Feature 16: Text Preprocessing Pipeline

**Description:**
Before chunking, raw extracted text passes through a preprocessing pipeline to improve quality.

**Steps:**
1. **OCR Artifact Cleaning** — fixes hyphenation artifacts (end-of-line word splits), ligature substitutions (`ﬁ` → `fi`), excessive spaces between characters (OCR spacing errors), garbled character sequences
2. **Whitespace Normalization** — collapses 3+ newlines to 2, normalizes spaces
3. **Heuristic Coreference Resolution** — replaces common pronouns with inferred referents using surrounding noun context (lightweight, no ML model)

**Benefits:**
- Improved embedding quality from cleaner text
- Heuristic coreference makes embeddings more semantically precise ("the company" → "Acme Corp")
- No external model dependency (no spaCy required)

**Drawbacks:**
- Heuristic coreference is naive — can replace the wrong pronoun in complex sentences
- OCR cleaning uses regex patterns that may incorrectly alter technical content (code snippets, URLs)
- No language-aware processing (assumes ASCII/Latin text patterns)

**Dependencies:** `re` (standard library only)

---

## 5. Workflow Analysis

### Workflow 1: Document Upload Workflow

**Starting Point:** User selects a file in the Streamlit UI

**Steps:**
1. User clicks "Upload File" and selects a document
2. Streamlit sends the file via multipart form POST to `/upload`
3. FastAPI receives the file, saves to `uploads/` directory with UUID filename
4. `FileValidator.validate()` checks extension, MIME type, file size
5. `DocumentClassifier.classify()` analyzes content:
   - Reads file extension
   - Samples up to 2000 words from text files
   - Scores keyword frequency against domain vocabularies
   - Returns `ClassificationResult` with doc_type, doc_subtype, pipeline, confidence, stats
6. **Branch A (tabular):** `TabularPipeline.ingest()` called:
   - Reads file with pandas (auto-encoding detection)
   - Cleans column names (sanitizes special characters)
   - Loads into SQLite table in `data/tabular_uploads.db`
   - Registers engine in `CloudDatabaseService`
   - Returns `conn_id`
7. **Branch B (narrative/rag):** `RAGEngine.ingest_document()` called:
   - `AutoConfigService.get_pipeline_config()` → optimal settings
   - `TextPreprocessor.preprocess()` → clean text
   - `LanguageDetector.detect()` → select embedding model
   - `ChunkingOptimizer.optimize()` → best chunking strategy → chunks
   - Each chunk embedded via `EmbeddingManager`
   - Chunks stored in ChromaDB collection
   - BM25 index updated in `FullTextSearchEngine`
   - Knowledge graph entities extracted (async, optional)
8. `DataCatalogService.register()` saves document metadata + topics
9. Document entry created in `users.db` documents table
10. RBAC permissions set to `private` (owner only, by default)
11. Success response with doc_id returned to UI

**Decision Points:**
- If file type not supported → HTTP 400 error
- If classification confidence < 0.5 → uses `narrative/general/rag` as fallback
- If tabular loading fails → error returned, no RAG fallback automatically
- If ChromaDB unavailable → error

**End State:** Document indexed and queryable

**Error Handling:**
- File validator rejects unsupported types before any processing
- Classification fallback ensures all files are processed (never silently dropped)
- TabularPipeline catches pandas read errors and raises clear RuntimeError
- RAG engine wraps per-chunk failures; partial ingestion continues

---

### Workflow 2: Query/Chat Workflow

**Starting Point:** User types a question in the chat interface

**Steps:**
1. User submits query via Streamlit chat input
2. Streamlit POST to `/query` with `{question, conversation_id, provider, model}`
3. FastAPI receives request; `SecurityService.get_current_user()` validates JWT
4. `QueryDecomposer.decompose()` checks query complexity:
   - Simple (< 10 words, no conjunctions) → `sub_queries = [original_query]`
   - Complex → heuristic or LLM split into 2–4 sub-queries
5. For each sub-query: `orchestrator._invoke_graph(sub_query)` called
6. LangGraph graph executes:
   - `classify_node`: LLM classifies intent (general_chat / query_agent / db_agent / etc.)
   - Routed to appropriate node(s)
   - `query_agent_node`: semantic + keyword retrieval → RRF fusion → generate
   - `db_agent_node`: schema → LLM SQL generation → execute → format
   - `verify_node`: ConfidenceScorer evaluates answer
   - If score < 0.40: `repair_node` → retry with HyDE (hypothetical document embedding)
   - If still low after 1 retry: `partial_deliver_node` returns best available
7. If multiple sub-queries: `QueryDecomposer.synthesize()` combines sub-answers
8. RBAC filter applied to source citations
9. Response includes: answer, sources (filenames + chunks), confidence level, conflicts
10. Message saved to conversation in `users.db`
11. Response streamed back to Streamlit UI
12. UI renders answer with source attribution panel

**Decision Points:**
- `general_chat` detected → skip retrieval entirely (faster, no document search)
- No chunks retrieved → `is_unanswerable()` → trigger web search (if enabled)
- Low confidence after retry → partial answer with low-confidence flag
- DB query fails → error message, not crash

**End State:** Answer displayed with sources and confidence indicator

---

### Workflow 3: Database Connection Workflow

**Starting Point:** User wants to connect a live database (PostgreSQL, MySQL, etc.)

**Steps:**
1. User navigates to "Database" settings in UI
2. Enters host, port, database name, username, password
3. POST to `/database/connect` with credentials
4. `CloudDatabaseService.connect_to_postgres()` (or mysql/snowflake/bigquery) creates SQLAlchemy engine
5. Test connection: lists tables to verify connectivity
6. `conn_id` stored in memory; associated with user
7. Schema context pre-fetched via `get_db_schema_context()` — table names and column types
8. User can now ask SQL questions about this database
9. On disconnect: `close_connection()` disposes SQLAlchemy engine

**Decision Points:**
- Connection failure → HTTP 500 with database error detail
- Empty database → warning shown
- SSL mode configurable for PostgreSQL

**End State:** Database tables queryable alongside uploaded documents

---

### Workflow 4: Cloud Storage Sync Workflow

**Starting Point:** User selects files from Google Drive / S3 / etc.

**Steps:**
1. User authenticates via OAuth to cloud provider
2. RAPID lists files from cloud service
3. User selects files to import
4. Files downloaded to `cloud_cache/` directory
5. Each file processed through normal upload pipeline (steps 4–11 of Upload Workflow)
6. Cloud source URL stored in document metadata

**Error Handling:**
- OAuth token expiry → re-authentication prompt
- File not downloadable → error per file; other files continue
- Unsupported file type → skip with warning

---

## 6. Pros and Cons

### PROS (Strengths)

**1. Zero-Configuration Intelligent Automation**
The most significant differentiator. Users upload a file and immediately get research-backed optimal retrieval — no manual configuration of chunk sizes, embedding models, or search strategies. The system derives from published academic benchmarks (BEIR, QASPER, CUAD, PubMedQA, FinanceBench), giving it a defensible and reproducible quality baseline.

**2. Genuine Privacy-First Design**
RAPID is architected to work 100% offline: local LLMs via Ollama or LM Studio, local embeddings via SentenceTransformers, local vector storage via ChromaDB, local SQLite for all metadata. An organization can deploy it with zero internet connectivity.

**3. Sophisticated Dual-Pipeline Architecture**
The automatic routing of spreadsheet/tabular data to SQL and narrative text to RAG is architecturally sound. Vector search on numeric data (prices, quantities, dates) is fundamentally weak; SQL is the right tool. RAPID makes this decision invisibly.

**4. Research-Backed Retrieval Parameters**
Unlike most RAG systems that use arbitrary chunk sizes (often just 512 tokens everywhere), RAPID's AutoConfigService cites specific benchmarks for each configuration. For example, 950-word chunks for academic papers achieve +12% F1 over 512-word chunks on the QASPER benchmark.

**5. Multi-Tenancy with Fine-Grained RBAC**
Organizations, departments, groups, and document-level permissions are all implemented. Document access checking is performed on every retrieval result. Audit logging provides a compliance trail.

**6. Eleven Chunking Strategies**
The breadth of chunking strategies — including specialized ones like `table_intact` (preserves markdown tables atomically), `code_aware` (splits at function boundaries), and `step_aware` (splits at numbered procedure steps) — is unusual for a single open-source system. Each addresses a specific retrieval failure mode.

**7. Hybrid Search with RRF Fusion**
Combining semantic and keyword search via Reciprocal Rank Fusion is a proven technique that outperforms either alone. RAPID implements this properly rather than using a simple weighted sum of scores.

**8. Confidence Scoring with Retry Logic**
The 3-dimensional confidence scoring (context relevance + faithfulness + completeness) with automatic retry is a meaningful quality gate. Most RAG systems return whatever the LLM generates; RAPID has a mechanism to detect and remediate low-quality answers.

**9. Extensible Provider Architecture**
The abstract base class pattern for both LLM providers (`LLMProvider`) and embedding providers (`EmbeddingProvider`) makes adding new providers straightforward. The singleton manager pattern ensures consistent state.

**10. Cloud Storage Integration**
Native connectors for S3, Azure Blob, Google Drive, OneDrive, and Dropbox cover the majority of enterprise storage use cases, reducing manual download-upload friction.

---

### CONS (Weaknesses)

**1. Rate Limiting Not Production-Ready**
The rate limiter is in-memory using a Python dictionary. It resets on every server restart and doesn't work across multiple server instances. In production (load-balanced or containerized), this means rate limits are per-instance, not per-user globally. A proper production rate limiter would use Redis.

**2. BM25 Index Rebuild on Every Insert**
Every time a new document is indexed, the BM25 `BM25Okapi` object is rebuilt from scratch over the entire corpus. For a corpus with thousands of documents, this becomes increasingly expensive and blocks the ingestion thread. The index should be made incremental or moved to a proper inverted index.

**3. ChromaDB Collection Dimension Mismatch**
If a user switches embedding providers (or models) after documents are already indexed, the new embeddings will have a different dimension than stored vectors. ChromaDB will reject them or return garbage results. There is no migration path or detection of this mismatch.

**4. No Token Budget Management**
When assembling chunks for the LLM prompt, the code uses a fixed `top_k` but doesn't verify whether the total token count (chunks + question + system prompt + answer budget) fits within the LLM's context window. Different LLMs have different limits (4K, 8K, 128K). This can cause silent truncation or API errors.

**5. SQLite Concurrency Limitations**
SQLite is used for users, conversations, messages, documents, permissions, and the data catalog — all in one file (`users.db`). SQLite's write concurrency is limited (one writer at a time). Under high user load, this creates a bottleneck. Conversation writes and permission checks will queue behind each other.

**6. SQL Injection Risk from LLM-Generated SQL**
The `execute_query()` method uses SQLAlchemy's `text()` with LLM-generated SQL. If the LLM generates SQL with injection payloads (either from a compromised model or adversarial user input that leaks into the prompt), it could execute arbitrary SQL. A proper implementation would restrict to SELECT-only and validate against a schema whitelist.

**7. No Persistent Rate-Limit State**
Related to point 1: even if Redis were added, the current rate limit data structure (list of timestamps per key) doesn't persist rate limit state across restarts. Persistent rate limiting requires a server-side store that outlives the process.

**8. Conversation History Not Encrypted**
Messages stored in `users.db` are plaintext. If the SQLite file is compromised, all conversation content (which may include sensitive business information referenced in questions) is exposed. This is a significant gap for a system designed to handle sensitive organizational data.

**9. Knowledge Graph Not Integrated with Confidence Loop**
The knowledge graph is built during ingestion but the `graph_query_node` in the orchestrator is a separate code path from the verify/repair confidence loop. Graph queries cannot be automatically retried with different strategies if they return low-confidence results.

**10. No UI for Configuration Management**
The `AutoConfigService.update_config()` method allows in-memory overrides, but there's no UI for administrators to tune configurations. The admin would need to call the API directly. Config changes are also not persisted (restart resets them), making configuration management impractical without code changes.

---

## 7. Real-World Problem Solving

### Scenario 1: Law Firm Document Intelligence

**The Situation:**
Hartley & Associates is a mid-size law firm with 45 attorneys. Over 20 years, they have accumulated 80,000+ legal documents: contracts, case files, precedent analyses, and internal policy documents stored across shared drives. New associates spend 2–4 hours per case doing initial document review, searching for relevant precedents and clause examples. The firm handles sensitive client information and cannot use public cloud AI tools.

**Without RAPID:**
- Associates manually search through folder structures and use Windows Search
- Relevant documents are missed because search is keyword-only (misses synonyms, conceptual matches)
- Two attorneys independently research the same precedent, duplicating effort
- Junior associates lack the domain knowledge to know which search terms to use
- Average time for a contract review starting point: 3.5 hours

**With RAPID:**

*Setup (done once by IT):*
1. RAPID deployed on-premises (firm's own server)
2. 80,000 documents bulk-uploaded via the cloud storage connector (Google Drive OAuth)
3. RAPID auto-classifies each file: legal contracts → `legal/contract` (780-word chunks, hybrid search), case analysis memos → `narrative/policy`, spreadsheets of billing data → `tabular/financial_spreadsheet` (SQL pipeline)
4. All processing stays on-premises — client data never leaves the firm

*Daily use:*
An associate is reviewing a new software licensing agreement and needs to know how similar indemnification clauses have been handled in past contracts.

1. Opens RAPID, asks: "Show me indemnification clauses from software licensing agreements where we represented the licensee, and how courts ruled on them in any associated case files."
2. RAPID decomposes: (a) "indemnification clauses from software licensing agreements, licensee representation" → legal contract RAG, (b) "court rulings on these clauses" → case file RAG
3. System retrieves relevant clause text from 8 historical contracts (hybrid search captures both "indemnification" keyword and semantic matches for "hold harmless")
4. System retrieves relevant case outcome summaries
5. ConfidenceScorer: context relevance 0.82, faithfulness 0.79, completeness 0.71 → overall 0.78 → high confidence
6. Answer delivered with exact clause text, source document names, and page references in 8 seconds

**Outcome & Impact:**
- Initial document review time: 3.5 hours → 20 minutes (83% reduction)
- Zero data leaves the firm's premises (compliance maintained)
- Junior associates produce research at near-senior-associate quality for precedent lookups
- After 6 months: firm estimates 1,200 associate-hours saved per month across 45 attorneys

---

### Scenario 2: Hospital Research Department Analytics

**The Situation:**
Mercy General Hospital's research department conducts 40+ clinical trials simultaneously. Each trial generates patient outcome spreadsheets, protocol documents, IRB approval letters, published research papers, and regulatory correspondence. Department leadership needs to answer funders' questions quickly — "What was the 90-day readmission rate for Trial XR-44?" or "Summarize the adverse events across all trials using Drug Class B" — but data is scattered across Excel files and PDF reports.

**Without RAPID:**
- Department coordinator manually opens multiple Excel files, applies filters, copies numbers to a new spreadsheet
- Summary reports require 4–6 hours of manual compilation
- Formatting errors occur when copying across spreadsheets
- Published literature must be read manually to cross-reference with internal findings
- If the lead coordinator is absent, institutional knowledge of where data lives is lost

**With RAPID:**

*Setup:*
1. Trial coordinators upload outcome spreadsheets (CSV/Excel) and protocol PDFs as they're created
2. Spreadsheets auto-route to SQL pipeline — each becomes a queryable SQLite table
3. PDFs auto-classify as `medical/clinical_document` → 500-word chunks, hybrid search, domain embedding hint
4. Published papers auto-classify as `academic/research_paper` → 950-word section-aware chunks
5. Data catalog maintains topic index with trial IDs, drug names, endpoints as keywords

*Funder Q&A session:*

Question 1: "What was the 90-day readmission rate for Trial XR-44?"
1. RAPID DataCatalog finds the XR-44 outcome spreadsheet (topic match: "XR-44", "readmission")
2. Routed to `db_agent` → generates SQL: `SELECT AVG(readmission_90d) FROM tbl_xr44_outcomes WHERE ...`
3. Returns: "The 90-day readmission rate for Trial XR-44 was 12.3% (n=847 patients)"
4. ConfidenceScorer: overall 0.91 — high confidence (exact SQL result)

Question 2: "Summarize adverse events across all trials using Drug Class B"
1. Query decomposed: separate sub-queries for each Drug Class B trial spreadsheet + their protocol PDFs
2. Parallel SQL queries across 6 trial tables for adverse event columns
3. RAG query on protocol PDFs for adverse event definitions and categorization
4. Results synthesized: "Across 6 Drug Class B trials (n=2,341 patients), the most common adverse events were nausea (18.2%), fatigue (14.7%), and elevated liver enzymes (6.3%)..."

**Outcome & Impact:**
- Funder Q&A prep: 4–6 hours → 15 minutes of conversational querying
- Zero errors from manual copy-paste between spreadsheets
- Research papers and trial data answered together in unified responses
- New coordinators can query institutional data from day one without needing to know where files are stored
- Estimated: 200 coordinator-hours saved per quarter; equivalent to 1 FTE

---

## 8. Use Case Documentation

### Use Case 1: Upload and Query a Financial Spreadsheet

**Actor:** Finance analyst (role: `user`)

**Preconditions:**
- User is authenticated (valid JWT)
- User has appropriate org membership

**Main Flow:**
1. User navigates to "Upload" tab in Streamlit UI
2. User selects an Excel file (quarterly_sales.xlsx)
3. System validates file type and size
4. `DocumentClassifier` detects tabular type (column names: revenue, cost, margin)
5. `TabularPipeline` loads into SQLite; registers as `conn_id = tabular_abc123`
6. `DataCatalogService` registers with topics: [revenue, cost, margin, quarterly, sales]
7. User navigates to "Chat" tab
8. User asks: "What was the highest revenue quarter in 2024?"
9. Orchestrator routes to `db_agent_node`
10. LLM generates: `SELECT quarter, MAX(revenue) FROM tbl_abc123 WHERE year = 2024 GROUP BY quarter LIMIT 1`
11. Query executed; result: "Q3 2024, $4.2M"
12. LLM formats natural language response
13. Answer displayed: "The highest revenue quarter in 2024 was Q3 with $4.2 million."

**Alternative Flows:**
- File has encoding issues: system tries UTF-8, latin-1, cp1252 automatically
- Multi-sheet Excel: each sheet becomes a separate table (tbl_abc123_Sheet1, tbl_abc123_Sheet2)

**Exception Flows:**
- SQL generation failure: error returned, user prompted to rephrase
- File too large: HTTP 413 error before upload completes

**Postconditions:** Spreadsheet queryable via NL indefinitely until user deletes it

**Business Rules:**
- Document stays private to uploading user unless permissions explicitly shared
- Maximum 500,000 rows loaded (safety cap)

---

### Use Case 2: Ask a Multi-Source Question

**Actor:** HR manager (role: `manager`)

**Preconditions:**
- User is authenticated
- Policy document (PDF) previously uploaded and indexed
- Employee database connected (PostgreSQL)

**Main Flow:**
1. User asks: "How many employees are on paternity leave this month and what does our leave policy say about duration?"
2. `QueryDecomposer` splits into: (a) "employees on paternity leave this month" → SQL, (b) "leave policy paternity leave duration" → RAG
3. Orchestrator routes to `multi_source_node`
4. DB agent queries employee table: `SELECT COUNT(*) FROM employees WHERE leave_type='paternity' AND current_month=TRUE`
5. RAG agent retrieves policy PDF chunks about paternity leave duration
6. `fusion_node` merges: count from DB + policy text from RAG
7. LLM synthesizes: "Currently 7 employees are on paternity leave. Per the Leave Policy v2.3 (Section 4.2), employees are entitled to 12 weeks of paid paternity leave..."
8. Response includes sources: [employees database, HR_Leave_Policy_2024.pdf, p.12]

**Alternative Flows:**
- No DB connected: only RAG answer provided (policy only), with note that headcount requires database access
- Policy doesn't mention paternity specifically: confidence scorer flags "medium" confidence, suggests web search for legal requirements

**Postconditions:** Answer with dual-source citation returned

---

### Use Case 3: Admin Creates New User with Department

**Actor:** Administrator (role: `admin`)

**Preconditions:** Admin JWT token

**Main Flow:**
1. Admin calls `POST /admin/users` with `{username, password, role, org_id, department, groups}`
2. Password validated (min 8 chars, complexity)
3. User created in `users.db`
4. `RBAC groups` pre-populated if groups specified
5. Admin can now share documents with this user via `PUT /documents/{doc_id}/permissions`

**Exception Flows:**
- Username already exists: HTTP 400
- Weak password: HTTP 400 with specific requirements
- Invalid role: HTTP 400

---

### Use Case 4: Connect to External Database

**Actor:** Data analyst (role: `manager`)

**Preconditions:** Authenticated user; network access to database host

**Main Flow:**
1. User opens "Databases" settings panel
2. Enters: host, port, database name, username, password, SSL mode
3. POST to `/database/connect`
4. `CloudDatabaseService.connect_to_postgres()` creates SQLAlchemy engine
5. Test connection: `engine.connect()` succeeds
6. `get_db_schema_context()` pre-fetches table names and column types
7. Connection registered for user; available immediately in chat

**Alternative Flows:**
- MySQL: same flow, `connect_to_mysql()` called
- Snowflake: warehouse and schema required additionally
- BigQuery: credentials JSON file path required

**Exception Flows:**
- Connection refused: HTTP 500 with error detail
- Authentication failure: HTTP 500 with "could not connect" message

---

### Use Case 5: Query Returns Low Confidence → Retry

**Actor:** Researcher (role: `user`)

**Main Flow:**
1. User asks a highly specific technical question not well-covered in documents
2. Orchestrator retrieves chunks; ConfidenceScorer evaluates: context_relevance=0.25, faithfulness=0.41, completeness=0.30 → overall=0.34 (< 0.40 threshold)
3. `repair_node` activated: Hypothetical Document Embedding (HyDE) — LLM generates a hypothetical document passage that would answer the question; this passage is embedded and used as the new query vector
4. Re-retrieval with HyDE vector finds more relevant chunks
5. Re-evaluation: overall=0.58 → `"medium"` verdict
6. Answer returned with "⚠ Low-confidence answer" flag and suggestion to "check source documents directly"
7. If web search enabled and `is_unanswerable()` was True: web results also returned

**Postconditions:** Answer delivered with appropriate confidence qualification

---

## 9. Orchestration & Architecture

### 9.1 LangGraph State Machine

The core orchestration is a **directed state graph** implemented with LangGraph. The graph state is a `TypedDict` containing:

```python
class AgentState(TypedDict):
    query: str
    intent: str
    messages: List[BaseMessage]
    rag_context: List[str]
    db_results: Optional[str]
    final_answer: str
    confidence: float
    retry_count: int
    sources: List[str]
```

**Node responsibilities:**

| Node | Input | Output | LLM call? |
|---|---|---|---|
| `classify_node` | query | intent label | Yes |
| `direct_answer_node` | query + history | answer | Yes |
| `query_agent_node` | query | rag_context + answer | Yes |
| `db_agent_node` | query + schema | db_results + answer | Yes |
| `multi_source_node` | query | spawns both above | Parallel |
| `fusion_node` | rag_context + db_results | merged_answer | Yes |
| `graph_query_node` | query | graph traversal result | Yes |
| `verify_node` | answer + chunks | confidence score | Optional |
| `repair_node` | low-confidence answer | HyDE query | Yes |
| `partial_deliver_node` | best available | final answer | No |

**Conditional edges:**
- classify_node → intent-based routing
- verify_node → score ≥ 0.65: END; score < 0.40 and retry < 1: repair_node; else: partial_deliver_node

### 9.2 Service Singleton Pattern

`LLMManager` and `EmbeddingManager` both implement the **Singleton pattern** using `__new__` override. This ensures:
- Single model instance loaded in memory (avoids re-loading multi-GB transformer models)
- Consistent active provider/model state across all requests
- Thread safety for provider selection

### 9.3 Pipeline Orchestration Flow

```
File Upload
    │
    ├── FileValidator (gate)
    │
    ├── DocumentClassifier (classify)
    │       │
    │       ├── tabular → TabularPipeline
    │       │       └── SQLite → CloudDatabaseService.register()
    │       │
    │       └── narrative/code/etc → RAGEngine
    │               ├── AutoConfigService (settings lookup)
    │               ├── TextPreprocessor (clean)
    │               ├── LanguageDetector (embedding model)
    │               ├── ChunkingOptimizer (strategy + chunk)
    │               ├── EmbeddingManager (vectorize)
    │               ├── ChromaDB (store vectors)
    │               ├── FullTextSearchEngine (BM25 index)
    │               └── KnowledgeGraphBuilder (async, optional)
    │
    └── DataCatalogService.register() (metadata)
```

### 9.4 Event Handling

RAPID is synchronous-first with async where needed:
- FastAPI async endpoints for upload and query
- Web search service uses `httpx.AsyncClient`
- Knowledge graph building can be deferred (not on the critical path)
- ThreadPoolExecutor used in orchestrator for parallel multi-source queries

### 9.5 State Management

Application state is managed at three levels:
1. **Request level**: FastAPI dependency injection (current_user, db connections)
2. **Session level**: Streamlit `session_state` + server-side cache dict keyed by session ID
3. **Persistent level**: SQLite for users, documents, conversations; ChromaDB for vectors; JSON files for BM25 index and knowledge graphs; SQLite for tabular data

---

## 10. Technology Stack & Libraries

### Backend Framework

| Technology | Version | Purpose |
|---|---|---|
| **FastAPI** | 0.104.0 | REST API framework; async support; Pydantic validation |
| **Uvicorn** | 0.24.0 | ASGI server for FastAPI |
| **Gunicorn** | 21.0+ | Production process manager for Uvicorn workers |

### Frontend

| Technology | Version | Purpose |
|---|---|---|
| **Streamlit** | 1.30.0 | Web UI; chat interface, file upload, settings panels |

### AI / ML

| Technology | Version | Purpose |
|---|---|---|
| **LangChain OpenAI** | 0.1.0 | LangChain adapter for OpenAI models |
| **LangChain Anthropic** | 0.1.0 | LangChain adapter for Claude models |
| **LangChain Community** | 0.0.20+ | Ollama LLM adapter |
| **LangGraph** | 0.0.40+ | State machine for multi-agent orchestration |
| **OpenAI SDK** | 1.109.1 | Direct OpenAI API calls, embeddings |
| **Anthropic SDK** | 0.16.0+ | Direct Anthropic API calls |
| **sentence-transformers** | 2.2.0+ | Local embedding models (all-MiniLM-L6-v2, multilingual-e5) |

### Vector Store & Search

| Technology | Version | Purpose |
|---|---|---|
| **ChromaDB** | 0.4.22 | Vector database for semantic search |
| **rank-bm25** | 0.2.2+ | BM25 Okapi keyword search |

### Document Processing

| Technology | Version | Purpose |
|---|---|---|
| **pypdf** | 4.0.0 | PDF text extraction |
| **pdfplumber** | 0.10.0 | Advanced PDF extraction (tables, layout) |
| **python-docx** | 1.1.0 | Word document parsing |
| **openpyxl** | 3.1.0 | Excel file reading |
| **beautifulsoup4** | 4.12.0 | HTML parsing |
| **chardet** | 5.2.0+ | Character encoding detection |
| **langdetect** | 1.0.9+ | Language detection |
| **pyarrow** | 14.0.0+ | Parquet file reading |

### Database

| Technology | Version | Purpose |
|---|---|---|
| **SQLAlchemy** | 2.0.36+ | ORM for PostgreSQL, MySQL, Snowflake, BigQuery |
| **aiosqlite** | 0.19.0 | Async SQLite access |
| **sqlite3** | stdlib | User DB, catalog, conversations, tabular data |
| **pymysql** | 1.1.0 | MySQL driver |
| **snowflake-connector-python** | 3.7.1 | Snowflake connectivity |
| **google-cloud-bigquery** | 3.13.0 | BigQuery connectivity |

### Data Processing

| Technology | Version | Purpose |
|---|---|---|
| **pandas** | latest | DataFrame operations, CSV/Excel/Parquet loading |
| **numpy** | < 2 | Numerical operations (version capped for compatibility) |
| **networkx** | 3.0+ | Knowledge graph (directed graph, graph algorithms) |

### Security

| Technology | Version | Purpose |
|---|---|---|
| **PyJWT** | 2.8.0 | JWT token creation and verification |
| **bcrypt** | 4.1.2 | Password hashing |
| **cryptography** | 41.0.0+ | Encryption service for file contents at rest |
| **msal** | 1.24.0+ | Microsoft OAuth / Azure AD authentication |

### Cloud Storage

| Technology | Version | Purpose |
|---|---|---|
| **boto3** | 1.34.0+ | AWS S3 operations |
| **azure-storage-blob** | 12.19.0+ | Azure Blob Storage |
| **google-api-python-client** | 2.100.0+ | Google Drive API |
| **google-auth-oauthlib** | 1.1.0+ | Google OAuth flow |
| **dropbox** | 11.36.0+ | Dropbox API |

### Caching & Infrastructure

| Technology | Version | Purpose |
|---|---|---|
| **redis** | 5.0.0 | Query result caching (optional) |
| **httpx** | 0.25.0 | Async HTTP for web search |
| **requests** | 2.31.0 | Sync HTTP for provider availability checks |
| **Jinja2** | 3.1.0 | Template rendering |
| **python-multipart** | 0.0.6 | Multipart form data (file uploads) |

### Testing

| Technology | Version | Purpose |
|---|---|---|
| **pytest** | 7.4.0 | Test framework |

### Optional / Commented Out

| Technology | Notes |
|---|---|
| **llama-cpp-python** | Commented out — local GGUF model inference (future use) |
| **reportlab** | PDF report generation (present in requirements, not yet wired to UI) |

---

### Infrastructure & Deployment

**Docker:**
- `docker/start.sh` for container startup
- Supports containerized deployment

**Data Storage Layout:**
```
data/
├── users.db                  # SQLite: users, orgs, groups, docs, conversations, data_catalog
├── tabular_uploads.db        # SQLite: uploaded spreadsheet data (auto-created)
├── chroma/                   # ChromaDB vector store (persistent)
├── fulltext_index.db         # SQLite: BM25 search metadata
├── search/bm25_index.json    # BM25 corpus (JSON)
├── knowledge_graph/          # NetworkX graphs (per-user JSON)
├── traces.db                 # Query traces for debugging
├── audit.log                 # Rotating security audit log
├── .jwt_secret               # Auto-generated JWT signing key (chmod 600)
└── .encryption_key           # Encryption service key
```

---

## 11. Appendix — Glossary

| Term | Definition |
|---|---|
| **RAG** | Retrieval-Augmented Generation. AI technique where relevant documents are retrieved and included in the prompt to ground LLM answers. |
| **BM25** | Okapi BM25. A probabilistic ranking function for keyword-based document retrieval. Outperforms TF-IDF for most search tasks. |
| **ChromaDB** | Open-source vector database. Stores document embeddings and enables nearest-neighbor similarity search. |
| **Embedding** | A numerical vector representation of text. Semantically similar texts produce similar vectors. |
| **Chunk** | A portion of a document. Large documents are split into chunks so each fits in the LLM context and can be individually retrieved. |
| **RRF** | Reciprocal Rank Fusion. A rank aggregation method that combines results from multiple retrieval systems without requiring score normalization. |
| **LangGraph** | A library for building stateful, multi-step AI workflows as directed graphs. Each node is a processing step; edges define flow. |
| **CRAG** | Corrective RAG. An architecture pattern where retrieved documents are evaluated and corrected/augmented before generation if quality is insufficient. |
| **HyDE** | Hypothetical Document Embedding. A technique where the LLM generates a hypothetical answer, which is then embedded and used as the retrieval query. Improves recall for vague queries. |
| **RBAC** | Role-Based Access Control. Authorization scheme where permissions are assigned to roles rather than individual users. |
| **JWT** | JSON Web Token. A compact, self-contained token for transmitting authentication information between parties. |
| **NL-to-SQL** | Natural Language to SQL. Converting plain English questions to SQL queries automatically using an LLM. |
| **SentenceTransformers** | A Python library providing pre-trained transformer models optimized for generating sentence/document embeddings. |
| **Ollama** | An open-source tool for running large language models locally on consumer hardware. |
| **Speculative RAG** | A two-LLM pattern: a fast small model drafts the answer, a larger model verifies it. Only verified drafts are returned without correction. |
| **QASPER** | A dataset benchmark for question answering over scientific papers. Used to evaluate academic document retrieval. |
| **CUAD** | Contract Understanding Atticus Dataset. A benchmark for evaluating AI on legal contract analysis. |
| **FinanceBench** | A benchmark dataset for evaluating financial document question answering. |
| **BEIR** | Benchmarking IR. A heterogeneous benchmark for information retrieval systems across diverse domains. |
| **TF-IDF** | Term Frequency–Inverse Document Frequency. A classic text relevance scoring method. |
| **NER** | Named Entity Recognition. Identifying and classifying named entities (persons, organizations, locations) in text. |
| **NetworkX** | A Python library for creating, analyzing, and visualizing complex graphs and networks. |

---

## PDF Conversion Instructions

To convert this document to a professionally formatted PDF:

### Option 1: Pandoc (Recommended)
```bash
pandoc RAPID_ANALYSIS.md -o RAPID_Analysis.pdf \
  --pdf-engine=xelatex \
  --variable geometry:margin=1in \
  --variable fontsize=11pt \
  --variable mainfont="Times New Roman" \
  --toc --toc-depth=3 \
  --highlight-style=tango
```

### Option 2: VS Code Extension
1. Install "Markdown PDF" extension in VS Code
2. Open this file
3. Right-click → "Markdown PDF: Export (pdf)"

### Option 3: Online Tools
- Upload to https://md-to-pdf.fly.dev/ (no API key required)
- Pandoc online converter at https://pandoc.org/try/

### Recommended Diagram Tools
For visual architecture diagrams based on the text descriptions in this document:
- **draw.io** (diagrams.net) — free, exports to PDF
- **Mermaid** — embed in markdown; renders in GitHub, Notion, Obsidian
- **Lucidchart** — professional diagrams

### Suggested Diagrams to Create:
1. **System Architecture Diagram** — three-tier layout (UI → Intelligence → Storage)
2. **Upload Pipeline Flowchart** — classification → pipeline routing → storage
3. **Query Pipeline State Machine** — LangGraph node/edge diagram
4. **Confidence Scoring Decision Tree** — high/medium/low → action
5. **Multi-Tenant RBAC Model** — org → department → groups → users → documents

---

## Quality Checklist

- [x] Every section from the framework is thoroughly documented
- [x] All 16 major features analyzed (including drawbacks)
- [x] 2 detailed real-world examples included (law firm + hospital)
- [x] All major use cases documented with complete flows
- [x] Technology stack fully listed and explained with versions
- [x] Orchestration patterns clearly explained (LangGraph state machine)
- [x] 10 pros and 10 cons, balanced and detailed
- [x] Writing accessible to non-technical readers
- [x] Technical accuracy maintained throughout
- [x] All major workflows documented step-by-step
- [x] Document has logical flow and structure
- [x] Glossary included for technical terms
- [x] PDF conversion instructions provided
