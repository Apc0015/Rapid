"""
RAPID v2 — FastAPI Application

Privacy-first RAG + DB query system.
Brain 1 (LLM Brain) → Brain 2 (Master Agent) → Brain 3 (DB Master)

Endpoints follow the principle of least privilege:
- Regular users: login, query, upload documents
- Admin: governance, audit log, LLM/embedding config
"""

import hashlib
import json
import logging
import os
import sqlite3
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import (
    Depends, FastAPI, File, Form, HTTPException, Query,
    UploadFile, status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

# Services
from app.services.llm_service import LLMManager
from app.services.embedding_service import EmbeddingManager
from app.services.auth_service import AuthService
from app.services.database_service import DatabaseService
from app.services.vector_store import VectorStore
from app.services.full_text_search import FullTextSearchEngine
from app.services.chunking_service import ChunkingService
from app.services.text_extractor import TextExtractor
from app.services.web_search_service import WebSearchService

# Governance
from app.governance.column_registry import ColumnRegistry
from app.governance.rules import GovernanceRules
from app.governance.policy_reader import PolicyReader

# DB Track (Brain 3)
from app.db.db_master import DBMasterAgent

# RAG Track
from app.rag.r1_classifier import DocumentClassifier
from app.rag.r2_rewriter import QueryRewriter
from app.rag.r3_retriever import ChunkRetriever
from app.rag.r4_summarizer import NLSummarizer
from app.rag.rag_track import RAGTrack

# Core (Brains 1 & 2)
from app.core.confidence import ConfidenceScorer
from app.core.master_agent import MasterAgent
from app.core.llm_brain import LLMBrain

# Web Search
from app.search.web_agent import WebSearchAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
AUDIT_LOG = os.path.join(DATA_DIR, "audit.log")
DOCS_DB = os.path.join(DATA_DIR, "documents.db")


# ---------------------------------------------------------------------------
# Document registry (lightweight SQLite tracking of uploaded documents)
# ---------------------------------------------------------------------------

class DocumentRegistry:
    """Tracks uploaded document metadata in SQLite."""

    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        with sqlite3.connect(DOCS_DB) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id      TEXT PRIMARY KEY,
                    filename    TEXT NOT NULL,
                    uploader    TEXT NOT NULL,
                    doc_type    TEXT NOT NULL,
                    chunks      INTEGER NOT NULL DEFAULT 0,
                    uploaded_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def register(self, doc_id: str, filename: str, uploader: str, doc_type: str, chunks: int):
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(DOCS_DB) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO documents "
                "(doc_id, filename, uploader, doc_type, chunks, uploaded_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (doc_id, filename, uploader, doc_type, chunks, now),
            )
            conn.commit()

    def list_all(self) -> List[Dict]:
        with sqlite3.connect(DOCS_DB) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM documents ORDER BY uploaded_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def delete(self, doc_id: str):
        with sqlite3.connect(DOCS_DB) as conn:
            conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
            conn.commit()


# ---------------------------------------------------------------------------
# App State
# ---------------------------------------------------------------------------

class _AppState:
    llm: LLMManager
    embedder: EmbeddingManager
    auth: AuthService
    db_service: DatabaseService
    vector_store: VectorStore
    fts: FullTextSearchEngine
    chunker: ChunkingService
    extractor: TextExtractor
    classifier: DocumentClassifier
    doc_registry: DocumentRegistry
    gov_rules: GovernanceRules
    policy_reader: PolicyReader
    rag_track: RAGTrack
    db_master: DBMasterAgent
    web_agent: WebSearchAgent
    master: MasterAgent
    brain: LLMBrain


_state = _AppState()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Core services
    _state.llm = LLMManager()
    _state.embedder = EmbeddingManager()
    _state.auth = AuthService()
    _state.db_service = DatabaseService()
    _state.vector_store = VectorStore(_state.embedder)
    _state.fts = FullTextSearchEngine()
    _state.chunker = ChunkingService()
    _state.extractor = TextExtractor()
    _state.classifier = DocumentClassifier()
    _state.doc_registry = DocumentRegistry()

    # Governance
    registry = ColumnRegistry()
    _state.gov_rules = GovernanceRules(registry)
    _state.policy_reader = PolicyReader(_state.llm)

    # DB Track — Brain 3 creates sub-agents (D1–D5) internally
    _state.db_master = DBMasterAgent(_state.db_service, _state.gov_rules, _state.llm)

    # RAG Track
    r2 = QueryRewriter(_state.llm)
    r3 = ChunkRetriever(_state.vector_store, _state.fts)
    r4 = NLSummarizer(_state.llm)
    _state.rag_track = RAGTrack(
        _state.classifier, r2, r3, r4, _state.embedder
    )

    # Web Search
    web_svc = WebSearchService()
    _state.web_agent = WebSearchAgent(web_svc, _state.llm)

    # Core brains (1 & 2)
    scorer = ConfidenceScorer()
    _state.master = MasterAgent(
        rag_track=_state.rag_track,
        db_master=_state.db_master,
        web_agent=_state.web_agent,
        confidence_scorer=scorer,
        llm_manager=_state.llm,
    )
    _state.brain = LLMBrain(_state.llm)

    logger.info("RAPID v2 started")
    yield
    logger.info("RAPID v2 shutting down")


app = FastAPI(title="RAPID", version="2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

_bearer = HTTPBearer()


def _current_user(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> Dict[str, Any]:
    payload = _state.auth.verify_token(creds.credentials)
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return {
        "username": payload["username"],
        "department": payload["department"],
        "role": payload["role"],
    }


def _admin_only(user: Dict = Depends(_current_user)) -> Dict:
    if user["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    department: str
    role: str = "viewer"


class QueryRequest(BaseModel):
    question: str
    conn_id: Optional[str] = None


class DBConnectRequest(BaseModel):
    conn_id: str
    uri: str  # sqlite:///path | postgresql://... | mysql+pymysql://...


class ColumnUpdateRequest(BaseModel):
    default_state: str              # "allowed" | "anonymize" | "block"
    dept_overrides: Dict[str, str] = {}
    role_overrides: Dict[str, str] = {}


class LLMConfigRequest(BaseModel):
    provider: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class EmbeddingConfigRequest(BaseModel):
    provider: str
    model: Optional[str] = None
    api_key: Optional[str] = None


class FetchModelsRequest(BaseModel):
    provider: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.post("/auth/login")
async def login(req: LoginRequest):
    user = _state.auth.authenticate(req.username, req.password)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    token = _state.auth.create_token(user)
    return {"token": token, "type": "Bearer"}


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest):
    return _state.auth.create_user(req.username, req.password, req.department, req.role)


@app.get("/me")
async def me(user: Dict = Depends(_current_user)):
    return user


# ---------------------------------------------------------------------------
# Query endpoint — full Brain1 → Brain2 → Brain1 pipeline
# ---------------------------------------------------------------------------

@app.post("/query")
async def query(req: QueryRequest, user: Dict = Depends(_current_user)):
    # Brain 1: extract intent (sees only the question)
    intent = await _state.brain.extract_intent(req.question, user["department"])

    # Brain 2: run RAG + DB tracks in parallel, fuse NL summaries
    fusion = await _state.master.run(
        raw_query=req.question,
        tracks_needed=intent.tracks_needed,
        user_context=user,
        conn_id=req.conn_id,
    )

    # Brain 1: compose final answer from fused NL summary (sees only summary)
    response = await _state.brain.compose_final_answer(
        user_question=req.question,
        fused_nl_summary=fusion.fused_nl_summary,
        sources=fusion.all_sources,
        confidence_result=fusion.confidence_result,
        tracks_used=fusion.tracks_activated,
    )

    return {
        "answer": response.answer,
        "confidence": round(fusion.overall_confidence, 3),
        "tracks_used": fusion.tracks_activated,
        "sources": _serialize_sources(fusion.all_sources),
    }


def _serialize_sources(sources: list) -> list:
    out = []
    for s in sources:
        if hasattr(s, "__dict__"):
            out.append(vars(s))
        elif isinstance(s, dict):
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# Document endpoints
# ---------------------------------------------------------------------------

@app.post("/documents/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    user: Dict = Depends(_current_user),
):
    content = await file.read()
    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1]

    # Write to temp file — needed by classifier (reads file content/metadata)
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        clf = _state.classifier.classify(tmp_path, filename)
        text = _state.extractor.extract(tmp_path, filename)
    finally:
        os.unlink(tmp_path)

    if not text.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Could not extract text from file")

    # Stable doc_id from content hash
    doc_id = hashlib.sha256(content).hexdigest()[:16]

    # Chunk + index
    chunks = _state.chunker.chunk_text(text, clf.doc_type)
    metadata = {
        "doc_id": doc_id,
        "filename": filename,
        "doc_type": clf.doc_type,
        "uploader": user["username"],
    }
    _state.vector_store.add_document(doc_id, chunks, metadata)
    _state.fts.index_document(doc_id, text, metadata=metadata)
    _state.doc_registry.register(doc_id, filename, user["username"], clf.doc_type, len(chunks))

    return {
        "doc_id": doc_id,
        "filename": filename,
        "doc_type": clf.doc_type,
        "chunks": len(chunks),
    }


@app.get("/documents")
async def list_documents(user: Dict = Depends(_current_user)):
    return _state.doc_registry.list_all()


@app.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(doc_id: str, user: Dict = Depends(_current_user)):
    _state.vector_store.delete_document(doc_id)
    _state.fts.remove_document(doc_id)
    _state.doc_registry.delete(doc_id)


# ---------------------------------------------------------------------------
# Database connection endpoints
# ---------------------------------------------------------------------------

@app.post("/db/connect")
async def connect_db(req: DBConnectRequest, user: Dict = Depends(_current_user)):
    uri = req.uri.strip()
    try:
        if uri.startswith("sqlite:///"):
            db_path = uri[len("sqlite:///"):]
            conn_id = _state.db_service.connect_to_sqlite(db_path, label=req.conn_id)
        elif uri.startswith("postgresql://") or uri.startswith("postgres://"):
            conn_id = _parse_and_connect_postgres(uri)
        elif uri.startswith("mysql"):
            conn_id = _parse_and_connect_mysql(uri)
        else:
            raise ValueError(f"Unsupported URI scheme. Use sqlite:///, postgresql://, or mysql://")
        _state.db_service.register_user_connection(user["username"], conn_id)
        return {"status": "connected", "conn_id": conn_id}
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


def _parse_and_connect_postgres(uri: str) -> str:
    from urllib.parse import urlparse
    p = urlparse(uri)
    return _state.db_service.connect_to_postgres(
        host=p.hostname or "localhost",
        port=p.port or 5432,
        database=(p.path or "/").lstrip("/"),
        username=p.username or "",
        password=p.password or "",
    )


def _parse_and_connect_mysql(uri: str) -> str:
    from urllib.parse import urlparse
    p = urlparse(uri)
    return _state.db_service.connect_to_mysql(
        host=p.hostname or "localhost",
        port=p.port or 3306,
        database=(p.path or "/").lstrip("/"),
        username=p.username or "",
        password=p.password or "",
    )


@app.get("/db/connections")
async def list_connections(user: Dict = Depends(_current_user)):
    return {"connections": _state.db_service.get_user_connections(user["username"])}


# ---------------------------------------------------------------------------
# Governance endpoints (admin only)
# ---------------------------------------------------------------------------

@app.post("/governance/columns/scan")
async def scan_schema(
    conn_id: str = Query(..., description="DB connection ID to scan"),
    user: Dict = Depends(_admin_only),
):
    count = _state.gov_rules.scan_and_register_schema(_state.db_service, conn_id)
    return {"status": "scanned", "conn_id": conn_id, "columns_registered": count}


@app.get("/governance/columns")
async def list_columns(user: Dict = Depends(_admin_only)):
    rules = _state.gov_rules.get_all_rules()
    return {"rules": [_rule_to_dict(r) for r in rules]}


@app.put("/governance/columns/{table_name}/{col_name}")
async def update_column_rule(
    table_name: str,
    col_name: str,
    req: ColumnUpdateRequest,
    user: Dict = Depends(_admin_only),
):
    rule = _state.gov_rules.upsert_column_rule(
        table_name=table_name,
        column_name=col_name,
        default_state=req.default_state,
        dept_overrides=req.dept_overrides,
        role_overrides=req.role_overrides,
    )
    return {"status": "updated", "rule": _rule_to_dict(rule)}


@app.post("/governance/policy-upload")
async def upload_policy(
    file: UploadFile = File(...),
    conn_id: str = Form(default=""),
    user: Dict = Depends(_admin_only),
):
    content = (await file.read()).decode("utf-8", errors="replace")
    proposed = await _state.policy_reader.parse_policy(
        content, _state.db_service, conn_id or ""
    )
    return {
        "proposed_rules": [_rule_to_dict(r) for r in proposed],
        "count": len(proposed),
        "note": "These are proposed only. Apply via PUT /governance/columns/{table}/{col}.",
    }


def _rule_to_dict(rule) -> Dict:
    return vars(rule) if hasattr(rule, "__dict__") else dict(rule)


# ---------------------------------------------------------------------------
# Audit log (admin only)
# ---------------------------------------------------------------------------

@app.get("/audit/log")
async def get_audit_log(
    n: int = Query(default=100, le=1000),
    user: Dict = Depends(_admin_only),
):
    if not os.path.exists(AUDIT_LOG):
        return []
    entries = []
    with open(AUDIT_LOG) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    entries.append({"raw": line})
    return entries[-n:]


# ---------------------------------------------------------------------------
# LLM / Embedding configuration (admin only)
# ---------------------------------------------------------------------------

@app.post("/llm/configure")
async def configure_llm(req: LLMConfigRequest, user: Dict = Depends(_admin_only)):
    if req.api_key or req.base_url:
        config: Dict[str, Any] = {}
        if req.api_key:
            config["api_key"] = req.api_key
        if req.base_url:
            config["base_url"] = req.base_url
        _state.llm.update_provider_config(req.provider, config)
    _state.llm.set_active(req.provider, req.model)
    return {"status": "configured", "provider": req.provider, "model": req.model}


@app.get("/llm/providers")
async def llm_providers(user: Dict = Depends(_admin_only)):
    return _state.llm.get_provider_info()


@app.post("/embedding/configure")
async def configure_embedding(req: EmbeddingConfigRequest, user: Dict = Depends(_admin_only)):
    if req.api_key or req.model:
        _state.embedder.update_provider(req.provider, model=req.model, api_key=req.api_key)
    _state.embedder.set_active(req.provider, model=req.model)
    return {"status": "configured", "provider": req.provider}


# ---------------------------------------------------------------------------
# Model discovery endpoints (admin only)
# ---------------------------------------------------------------------------

@app.post("/llm/fetch-models")
async def fetch_llm_models(req: FetchModelsRequest, user: Dict = Depends(_admin_only)):
    try:
        models = await _discover_llm_models(req.provider, req.api_key, req.base_url)
        return {"status": "ok", "models": models}
    except Exception as e:
        return {"status": "error", "message": str(e), "models": []}


@app.post("/embedding/fetch-models")
async def fetch_embedding_models(req: FetchModelsRequest, user: Dict = Depends(_admin_only)):
    try:
        models = await _discover_embedding_models(req.provider, req.api_key, req.base_url)
        return {"status": "ok", "models": models}
    except Exception as e:
        return {"status": "error", "message": str(e), "models": []}


async def _discover_llm_models(provider: str, api_key: Optional[str], base_url: Optional[str]) -> List[str]:
    import httpx

    if provider == "openai":
        import openai
        key = api_key or os.getenv("OPENAI_API_KEY", "")
        client = openai.AsyncOpenAI(api_key=key)
        resp = await client.models.list()
        chat = [m.id for m in resp.data if any(p in m.id for p in ("gpt-", "o1", "o3", "o4"))]
        return sorted(chat, reverse=True)

    if provider == "anthropic":
        key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        async with httpx.AsyncClient() as c:
            r = await c.get(
                "https://api.anthropic.com/v1/models",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                timeout=10,
            )
            r.raise_for_status()
            return [m["id"] for m in r.json().get("data", [])]

    if provider == "openrouter":
        key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        async with httpx.AsyncClient() as c:
            r = await c.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10,
            )
            r.raise_for_status()
            return [m["id"] for m in r.json().get("data", [])][:80]

    if provider == "ollama":
        base = (base_url or "http://localhost:11434").rstrip("/")
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{base}/api/tags", timeout=5)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]

    if provider == "lmstudio":
        base = (base_url or "http://localhost:1234").rstrip("/")
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{base}/v1/models", timeout=5)
            r.raise_for_status()
            return [m["id"] for m in r.json().get("data", [])]

    return []


async def _discover_embedding_models(provider: str, api_key: Optional[str], base_url: Optional[str]) -> List[str]:
    import httpx

    if provider == "openai":
        import openai
        key = api_key or os.getenv("OPENAI_API_KEY", "")
        client = openai.AsyncOpenAI(api_key=key)
        resp = await client.models.list()
        return sorted([m.id for m in resp.data if "embedding" in m.id], reverse=True)

    if provider == "sentence-transformers":
        return [
            "all-MiniLM-L6-v2",
            "all-MiniLM-L12-v2",
            "all-mpnet-base-v2",
            "paraphrase-multilingual-MiniLM-L12-v2",
            "multi-qa-MiniLM-L6-cos-v1",
            "all-distilroberta-v1",
            "BAAI/bge-small-en-v1.5",
            "BAAI/bge-base-en-v1.5",
            "BAAI/bge-large-en-v1.5",
        ]

    if provider == "ollama":
        base = (base_url or "http://localhost:11434").rstrip("/")
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{base}/api/tags", timeout=5)
            r.raise_for_status()
            all_models = [m["name"] for m in r.json().get("models", [])]
            emb = [m for m in all_models if any(k in m.lower() for k in ("embed", "nomic", "mxbai", "bge"))]
            return emb if emb else all_models

    return []


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "llm": _state.llm.get_provider_info(),
        "fts": _state.fts.get_stats(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
