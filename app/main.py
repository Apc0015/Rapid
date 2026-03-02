import app.compat  # noqa: F401,E402  — numpy 2.0 shim (must be first)
import logging
import os
import uuid
import secrets
import asyncio
from typing import Optional, List

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel

from .rag.engine import RAGEngine
from .agents.orchestrator import MultiAgentOrchestrator
from .services.security_service import SecurityService
from .services.llm_service import LLMManager
from .services.database_service import CloudDatabaseService
from .services.embedding_service import EmbeddingManager
from .services.rag_config_service import RAGConfigurationService
from .services.cloud_storage_service import CloudStorageService
from .services.rbac_service import RBACService
from .services.organization_service import OrganizationService
from .services.token_service import TokenService
from .services.oauth_service import OAuthService
from .services.web_search_service import WebSearchService
from .services.query_router import QueryRouter, EmbeddingBasedRouter
from .services.conversation_service import ConversationService
from .services.document_classifier import DocumentClassifier
from .services.auto_config_service import AutoConfigService
from .pipelines.tabular_pipeline import TabularPipeline
from .services.data_catalog_service import DataCatalogService
from .services.query_decomposer import QueryDecomposer
from .services.trace_service import TraceService

# ---------------------------------------------------------------------------
# Centralized logging
# ---------------------------------------------------------------------------
_log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB

app = FastAPI(title="RAPID API", version="1.0.0")

# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:8501,http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
rag_engine = RAGEngine()
database_service = CloudDatabaseService()
orchestrator = MultiAgentOrchestrator(rag_engine, database_service=database_service)
security_service = SecurityService()
rbac_service = RBACService()
organization_service = OrganizationService()
token_service = TokenService()
llm_manager = LLMManager()
embedding_manager = EmbeddingManager()
rag_config_service = RAGConfigurationService()
cloud_storage_service = CloudStorageService()
oauth_service = OAuthService()
web_search_service = WebSearchService()
try:
    query_router = EmbeddingBasedRouter()
    logger.info("Using EmbeddingBasedRouter for query routing")
except Exception as _router_exc:
    query_router = QueryRouter()
    logger.info("EmbeddingBasedRouter unavailable (%s) — using regex QueryRouter", _router_exc)
conversation_service = ConversationService()
document_classifier = DocumentClassifier()
auto_config_service = AutoConfigService()
tabular_pipeline = TabularPipeline(database_service)
data_catalog = DataCatalogService()
query_decomposer = QueryDecomposer()
trace_service = TraceService()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


class QueryRequest(BaseModel):
    query: str


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


class LLMConfigRequest(BaseModel):
    provider: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class EmbeddingConfigRequest(BaseModel):
    provider: str  # "sentence-transformers", "ollama", "openai", "huggingface"
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class ApplyTemplateRequest(BaseModel):
    template_name: str


class CustomConfigRequest(BaseModel):
    config_name: str = "Custom"
    chunk_size: int
    overlap_size: int
    top_k: int
    embedding_model: str = "text-embedding-ada-002"


class DatabaseConnectRequest(BaseModel):
    db_type: str  # postgres, mysql
    host: str
    port: int
    database: str
    username: str
    password: Optional[str] = None
    ssl_mode: Optional[str] = "require"


class DatabaseQueryRequest(BaseModel):
    conn_id: str
    query: str


class OrganizationCreateRequest(BaseModel):
    org_name: str
    org_id: Optional[str] = None
    settings: Optional[dict] = None


class OrganizationUpdateRequest(BaseModel):
    org_name: Optional[str] = None
    settings: Optional[dict] = None
    active: Optional[bool] = None


class GroupCreateRequest(BaseModel):
    group_name: str
    description: Optional[str] = None


class GroupUpdateRequest(BaseModel):
    group_name: Optional[str] = None
    description: Optional[str] = None


class GroupMemberRequest(BaseModel):
    username: str


class AdminUserCreateRequest(BaseModel):
    username: str
    password: str
    role: str = "user"
    department: Optional[str] = None
    groups: Optional[List[str]] = None


class AdminUserUpdateRequest(BaseModel):
    role: Optional[str] = None
    department: Optional[str] = None
    groups: Optional[List[str]] = None
    active: Optional[bool] = None


class DocumentPermissionRequest(BaseModel):
    access_level: str = "private"
    allowed_users: Optional[List[str]] = None
    allowed_groups: Optional[List[str]] = None
    allowed_roles: Optional[List[str]] = None


class DocumentShareRequest(BaseModel):
    users: Optional[List[str]] = None
    groups: Optional[List[str]] = None
    roles: Optional[List[str]] = None


class TokenCreateRequest(BaseModel):
    service_type: str
    token_name: str
    token: str
    expires_at: Optional[str] = None


class TokenUpdateRequest(BaseModel):
    token_name: Optional[str] = None
    token: Optional[str] = None
    expires_at: Optional[str] = None
    active: Optional[bool] = None


class ConversationCreateRequest(BaseModel):
    title: Optional[str] = None


class MessageRequest(BaseModel):
    message: str
    stream: Optional[bool] = True


@app.get("/")
def read_root():
    return {"message": "Welcome to RAPID - RAG Application for Private Instant Deployment"}


@app.get("/health")
def health_check():
    """Return component-level health status."""
    components = {}

    # ChromaDB
    try:
        count = rag_engine.vectordb.collection.count()
        components["chromadb"] = {"status": "ok", "documents": count}
    except Exception as exc:
        components["chromadb"] = {"status": "error", "detail": str(exc)}

    # LLM provider
    try:
        providers = llm_manager.get_available_providers()
        components["llm"] = {"status": "ok", "providers": providers}
    except Exception as exc:
        components["llm"] = {"status": "error", "detail": str(exc)}

    # Embedding provider
    try:
        info = embedding_manager.get_provider_info()
        components["embedding"] = {"status": "ok", "active": info.get("active")}
    except Exception as exc:
        components["embedding"] = {"status": "error", "detail": str(exc)}

    overall = "healthy" if all(c["status"] == "ok" for c in components.values()) else "degraded"
    return {"status": overall, "components": components}


@app.post("/register")
def register_user(request: RegisterRequest):
    """Register a new user"""
    try:
        result = security_service.create_user(request.username, request.password)
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("Registration failed")
        raise HTTPException(status_code=500, detail="Registration failed")


@app.post("/login")
def login(request: LoginRequest):
    """Authenticate user and return JWT token"""
    user = security_service.authenticate_user(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = security_service.create_access_token({
        "sub": user["username"],
        "role": user["role"],
        "org_id": user.get("org_id", "default"),
        "groups": user.get("groups", []),
    })
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "username": user["username"],
            "role": user["role"],
            "org_id": user.get("org_id", "default"),
            "groups": user.get("groups", []),
        },
    }


@app.get("/me")
def get_current_user_info(
    current_user: dict = Depends(security_service.get_current_user),
):
    """Verify token and return current user info"""
    return {
        "username": current_user["username"],
        "role": current_user["role"],
        "org_id": current_user.get("org_id", "default"),
        "department": current_user.get("department"),
        "groups": current_user.get("groups", []),
    }


# ======================== OAuth / SSO ========================

@app.get("/auth/oauth/{provider}/login")
def oauth_login(provider: str):
    state = oauth_service.create_state(provider)
    url = oauth_service.get_authorization_url(provider, state)
    return RedirectResponse(url)


@app.get("/auth/oauth/{provider}/callback")
async def oauth_callback(provider: str, code: str, state: str):
    oauth_service.validate_state(state, provider)
    token = await oauth_service.exchange_code(provider, code)
    profile = await oauth_service.fetch_user_info(provider, token)

    # Use email as username fallback
    username = profile.get("email") or profile.get("id")
    if not username:
        raise HTTPException(status_code=400, detail="OAuth profile missing identifier")

    user = rbac_service.get_user(username)
    if not user:
        try:
            security_service.create_oauth_user(username, provider, profile.get("id", ""))
        except HTTPException:
            pass
    user_row = rbac_service.get_user(username) or {"username": username, "role": "user", "org_id": "default", "groups": []}

    access_token = security_service.create_access_token({
        "sub": username,
        "role": user_row.get("role", "user"),
        "org_id": user_row.get("org_id", "default"),
        "groups": user_row.get("groups", []),
    })
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "username": username,
            "role": user_row.get("role", "user"),
            "org_id": user_row.get("org_id", "default"),
            "groups": user_row.get("groups", []),
        },
        "profile": profile,
    }


@app.post("/auth/oauth/link")
async def oauth_link(
    provider: str,
    code: str,
    state: str,
    current_user: dict = Depends(security_service.get_current_user),
):
    oauth_service.validate_state(state, provider)
    token = await oauth_service.exchange_code(provider, code)
    profile = await oauth_service.fetch_user_info(provider, token)
    oauth_id = profile.get("id")
    if not oauth_id:
        raise HTTPException(status_code=400, detail="OAuth profile missing id")
    # Update oauth fields
    conn = security_service._get_db()
    try:
        conn.execute(
            "UPDATE users SET oauth_provider = ?, oauth_id = ? WHERE username = ?",
            (provider, oauth_id, current_user["username"]),
        )
        conn.commit()
    finally:
        conn.close()
    return {"message": "OAuth linked", "provider": provider}


@app.post("/auth/oauth/unlink")
def oauth_unlink(
    provider: str,
    current_user: dict = Depends(security_service.get_current_user),
):
    conn = security_service._get_db()
    try:
        conn.execute(
            "UPDATE users SET oauth_provider = NULL, oauth_id = NULL WHERE username = ? AND oauth_provider = ?",
            (current_user["username"], provider),
        )
        conn.commit()
    finally:
        conn.close()
    return {"message": "OAuth unlinked", "provider": provider}


# ======================== Cloud OAuth ========================

@app.get("/cloud/oauth/{service}/authorize")
def cloud_oauth_authorize(service: str, current_user: dict = Depends(security_service.get_current_user)):
    provider = {"google_drive": "google", "onedrive": "microsoft", "dropbox": "dropbox"}.get(service, service)
    state = oauth_service.create_state(provider, username=current_user["username"])
    url = oauth_service.get_authorization_url(provider, state)
    return RedirectResponse(url)


@app.get("/cloud/oauth/{service}/callback")
async def cloud_oauth_callback(service: str, code: str, state: str):
    provider = {"google_drive": "google", "onedrive": "microsoft", "dropbox": "dropbox"}.get(service, service)
    data = oauth_service.validate_state(state, provider)
    token = await oauth_service.exchange_code(provider, code)
    username = data.get("username")
    if not username:
        raise HTTPException(status_code=400, detail="Missing username for cloud OAuth")
    # Store token as credentials for the connector
    credentials = {"access_token": token.get("access_token"), "refresh_token": token.get("refresh_token")}
    conn_id = cloud_storage_service.connect_service(username, service, credentials, display_name=f"{service} OAuth")
    return {"message": "Cloud service connected", "connection_id": conn_id}


@app.get("/cloud/oauth/connections")
def cloud_oauth_connections(current_user: dict = Depends(security_service.get_current_user)):
    services = cloud_storage_service.get_user_services(current_user["username"])
    return {"connections": services}


@app.delete("/cloud/oauth/connections/{conn_id}")
def cloud_oauth_disconnect(conn_id: str, current_user: dict = Depends(security_service.get_current_user)):
    ok = cloud_storage_service.disconnect_service(current_user["username"], conn_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Connection not found")
    return {"message": "Disconnected", "connection_id": conn_id}


# ======================== Organization Management ========================

@app.post("/api/organizations")
def create_organization(
    request: OrganizationCreateRequest,
    current_user: dict = Depends(security_service.require_role("admin")),
):
    return organization_service.create_org(request.org_name, request.org_id, request.settings)


@app.get("/api/organizations/{org_id}")
def get_organization(
    org_id: str,
    current_user: dict = Depends(security_service.get_current_user),
):
    if current_user["role"] != "admin" and current_user.get("org_id") != org_id:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return organization_service.get_org(org_id)


@app.put("/api/organizations/{org_id}")
def update_organization(
    org_id: str,
    request: OrganizationUpdateRequest,
    current_user: dict = Depends(security_service.require_role("admin")),
):
    return organization_service.update_org(org_id, request.org_name, request.settings, request.active)


@app.get("/api/organizations/{org_id}/users")
def list_organization_users(
    org_id: str,
    current_user: dict = Depends(security_service.require_role("admin")),
):
    if current_user.get("org_id") != org_id:
        raise HTTPException(status_code=403, detail="Cannot view users for another organization")
    return {"users": rbac_service.list_users(org_id)}


# ======================== Group Management ========================

@app.post("/api/groups")
def create_group(
    request: GroupCreateRequest,
    current_user: dict = Depends(security_service.require_role("admin")),
):
    return rbac_service.create_group(
        current_user.get("org_id", "default"),
        request.group_name,
        request.description,
        current_user["username"],
    )


@app.get("/api/groups")
def list_groups(
    current_user: dict = Depends(security_service.get_current_user),
):
    return {"groups": rbac_service.list_groups(current_user.get("org_id", "default"))}


@app.put("/api/groups/{group_id}")
def update_group(
    group_id: str,
    request: GroupUpdateRequest,
    current_user: dict = Depends(security_service.require_role("admin")),
):
    return rbac_service.update_group(group_id, request.group_name, request.description)


@app.delete("/api/groups/{group_id}")
def delete_group(
    group_id: str,
    current_user: dict = Depends(security_service.require_role("admin")),
):
    return rbac_service.delete_group(group_id)


@app.post("/api/groups/{group_id}/members")
def add_group_member(
    group_id: str,
    request: GroupMemberRequest,
    current_user: dict = Depends(security_service.require_role("admin")),
):
    return rbac_service.add_user_to_group(group_id, request.username)


# ======================== User Management (Admin) ========================

@app.post("/api/admin/users")
def admin_create_user(
    request: AdminUserCreateRequest,
    current_user: dict = Depends(security_service.require_role("admin")),
):
    return security_service.create_user_admin(
        username=request.username,
        password=request.password,
        role=request.role,
        org_id=current_user.get("org_id", "default"),
        department=request.department,
        groups=request.groups,
    )


@app.get("/api/admin/users")
def admin_list_users(
    current_user: dict = Depends(security_service.require_role("admin")),
):
    org_id = current_user.get("org_id", "default")
    return {"users": rbac_service.list_users(org_id)}


@app.put("/api/admin/users/{username}")
def admin_update_user(
    username: str,
    request: AdminUserUpdateRequest,
    current_user: dict = Depends(security_service.require_role("admin")),
):
    target_user = rbac_service.get_user(username)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    if target_user.get("org_id") != current_user.get("org_id"):
        raise HTTPException(status_code=403, detail="Cannot update user in another organization")
    return rbac_service.update_user(
        username,
        role=request.role,
        groups=request.groups,
        department=request.department,
        active=request.active,
    )


@app.delete("/api/admin/users/{username}")
def admin_deactivate_user(
    username: str,
    current_user: dict = Depends(security_service.require_role("admin")),
):
    target_user = rbac_service.get_user(username)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    if target_user.get("org_id") != current_user.get("org_id"):
        raise HTTPException(status_code=403, detail="Cannot update user in another organization")
    return rbac_service.update_user(username, active=False)


@app.get("/api/admin/users/{username}/permissions")
def admin_user_permissions(
    username: str,
    current_user: dict = Depends(security_service.require_role("admin")),
):
    target_user = rbac_service.get_user(username)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    if target_user.get("org_id") != current_user.get("org_id"):
        raise HTTPException(status_code=403, detail="Cannot view user in another organization")
    permissions = rbac_service.list_permissions_for_user(username)
    return {"user": target_user, "document_permissions": permissions}


# ======================== Document Permissions ========================

@app.post("/api/documents/{doc_id}/permissions")
def set_document_permissions(
    doc_id: str,
    request: DocumentPermissionRequest,
    current_user: dict = Depends(security_service.get_current_user),
):
    if request.allowed_roles:
        invalid_roles = [r for r in request.allowed_roles if r not in ("admin", "manager", "user")]
        if invalid_roles:
            raise HTTPException(status_code=400, detail="Invalid roles in allowed_roles")
    org_id = current_user.get("org_id", "default")
    collection = rag_engine.vectordb._get_collection(org_id)
    meta_results = collection.get(where={"doc_id": doc_id}, include=["metadatas"])
    if not meta_results.get("metadatas"):
        raise HTTPException(status_code=404, detail="Document not found")
    sample_meta = (meta_results.get("metadatas") or [{}])[0]
    if not rbac_service.can_manage_document(current_user, doc_id, sample_meta):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return rbac_service.set_document_permissions(
        document_id=doc_id,
        org_id=org_id,
        owner_username=sample_meta.get("owner", current_user["username"]),
        access_level=request.access_level,
        allowed_users=request.allowed_users,
        allowed_groups=request.allowed_groups,
        allowed_roles=request.allowed_roles,
    )


@app.get("/api/documents/{doc_id}/permissions")
def get_document_permissions(
    doc_id: str,
    current_user: dict = Depends(security_service.get_current_user),
):
    org_id = current_user.get("org_id", "default")
    collection = rag_engine.vectordb._get_collection(org_id)
    meta_results = collection.get(where={"doc_id": doc_id}, include=["metadatas"])
    if not meta_results.get("metadatas"):
        raise HTTPException(status_code=404, detail="Document not found")
    sample_meta = (meta_results.get("metadatas") or [{}])[0]
    if not rbac_service.can_manage_document(current_user, doc_id, sample_meta):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    perms = rbac_service.get_document_permissions(doc_id)
    if not perms:
        raise HTTPException(status_code=404, detail="Permissions not found")
    return perms


@app.put("/api/documents/{doc_id}/permissions")
def update_document_permissions(
    doc_id: str,
    request: DocumentPermissionRequest,
    current_user: dict = Depends(security_service.get_current_user),
):
    return set_document_permissions(doc_id, request, current_user)


@app.post("/api/documents/{doc_id}/share")
def share_document(
    doc_id: str,
    request: DocumentShareRequest,
    current_user: dict = Depends(security_service.get_current_user),
):
    org_id = current_user.get("org_id", "default")
    collection = rag_engine.vectordb._get_collection(org_id)
    meta_results = collection.get(where={"doc_id": doc_id}, include=["metadatas"])
    if not meta_results.get("metadatas"):
        raise HTTPException(status_code=404, detail="Document not found")
    sample_meta = (meta_results.get("metadatas") or [{}])[0]
    if not rbac_service.can_manage_document(current_user, doc_id, sample_meta):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    perms = rbac_service.get_document_permissions(doc_id) or {}
    allowed_users = set(perms.get("allowed_users", []))
    allowed_groups = set(perms.get("allowed_groups", []))
    allowed_roles = set(perms.get("allowed_roles", []))

    allowed_users.update(request.users or [])
    allowed_groups.update(request.groups or [])
    allowed_roles.update(request.roles or [])

    access_level = perms.get("access_level", "private")
    if allowed_groups:
        access_level = "group"
    elif allowed_users or allowed_roles:
        access_level = "private"

    return rbac_service.set_document_permissions(
        document_id=doc_id,
        org_id=org_id,
        owner_username=perms.get("owner_username", current_user["username"]),
        access_level=access_level,
        allowed_users=sorted(allowed_users),
        allowed_groups=sorted(allowed_groups),
        allowed_roles=sorted(allowed_roles),
    )


# ======================== Token Management ========================

@app.post("/api/admin/tokens")
def create_org_token(
    request: TokenCreateRequest,
    current_user: dict = Depends(security_service.require_role("admin")),
):
    org_id = current_user.get("org_id", "default")
    return token_service.create_token(
        org_id=org_id,
        service_type=request.service_type,
        token_name=request.token_name,
        token_value=request.token,
        created_by=current_user["username"],
        expires_at=request.expires_at,
    )


@app.get("/api/admin/tokens")
def list_org_tokens(
    current_user: dict = Depends(security_service.require_role("admin")),
):
    org_id = current_user.get("org_id", "default")
    return {"tokens": token_service.list_tokens(org_id)}


@app.put("/api/admin/tokens/{token_id}")
def update_org_token(
    token_id: str,
    request: TokenUpdateRequest,
    current_user: dict = Depends(security_service.require_role("admin")),
):
    return token_service.update_token(
        token_id=token_id,
        token_name=request.token_name,
        token_value=request.token,
        expires_at=request.expires_at,
        active=request.active,
    )


@app.delete("/api/admin/tokens/{token_id}")
def delete_org_token(
    token_id: str,
    current_user: dict = Depends(security_service.require_role("admin")),
):
    return token_service.delete_token(token_id)


# ======================== Conversations & Streaming ========================

@app.post("/api/conversations")
def create_conversation(
    request: ConversationCreateRequest,
    current_user: dict = Depends(security_service.get_current_user),
):
    return conversation_service.create_conversation(current_user["username"], request.title)


@app.get("/api/conversations")
def list_conversations(
    current_user: dict = Depends(security_service.get_current_user),
):
    return {"conversations": conversation_service.list_conversations(current_user["username"])}


@app.get("/api/conversations/{conversation_id}/messages")
def list_conversation_messages(
    conversation_id: str,
    current_user: dict = Depends(security_service.get_current_user),
):
    return {"messages": conversation_service.list_messages(conversation_id, current_user["username"])}


@app.put("/api/conversations/{conversation_id}/archive")
def archive_conversation(
    conversation_id: str,
    current_user: dict = Depends(security_service.get_current_user),
):
    return conversation_service.archive_conversation(conversation_id, current_user["username"])


@app.post("/api/conversations/{conversation_id}/messages")
async def send_message_streaming(
    conversation_id: str,
    request: MessageRequest,
    current_user: dict = Depends(security_service.get_current_user),
):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if not security_service.rate_limit_check(current_user["username"], "query"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    sanitized = security_service.sanitize_input(request.message)

    # Persist user message immediately
    conversation_service.add_message(conversation_id, "user", sanitized)

    db_conn_ids = database_service.get_user_connections(current_user["username"])

    # Non-streaming path
    if request.stream is False:
        try:
            result = await _process_query_core(sanitized, current_user)
            answer = result["answer"]
        except Exception:
            logger.exception("Conversation query failed")
            answer = "Sorry, an error occurred while processing your question."
        import json as _json
        sources_json = _json.dumps(result.get("sources", [])) if "result" in dir() else "[]"
        conversation_service.add_message(conversation_id, "assistant", answer, sources=sources_json)
        security_service.audit_log(current_user["username"], "chat", conversation_id, {"message_len": len(sanitized)})
        return {"answer": answer, "sources": result.get("sources", []) if "result" in dir() else []}

    # Streaming path: use real LLM token streaming
    async def generate():
        import json as _json
        collected_tokens: list = []

        # Check if query needs database or is pure doc Q&A
        # Route quickly to decide streaming strategy
        needs_db = bool(db_conn_ids)
        enable_web = os.getenv("ENABLE_WEB_SEARCH", "false").lower() in ("1", "true", "yes")
        routing = query_router.route(sanitized) if enable_web else {
            "needs_web": False, "needs_internal": True,
            "strategy": "internal_only", "confidence": 1.0,
        }

        if needs_db or routing["strategy"] in ("web_only", "parallel"):
            # For DB/web queries: emit progress events, then run full pipeline
            if needs_db:
                yield f"data: {_json.dumps({'progress': 'Querying database...'})}\n\n"
            if routing.get("needs_web"):
                yield f"data: {_json.dumps({'progress': 'Searching the web...'})}\n\n"
            yield f"data: {_json.dumps({'progress': 'Searching documents...'})}\n\n"
            try:
                result = await _process_query_core(sanitized, current_user)
                answer = result["answer"]
                sources = result.get("sources", [])
                confidence = result.get("confidence")
            except Exception as e:
                answer = f"Error processing your query: {e}"
                sources = []
                confidence = None
            yield f"data: {_json.dumps({'progress': 'Synthesizing answer...'})}\n\n"

            # Stream the pre-computed answer word by word
            words = answer.split(" ")
            for i, word in enumerate(words):
                token = word + (" " if i < len(words) - 1 else "")
                collected_tokens.append(token)
                yield f"data: {_json.dumps({'token': token})}\n\n"
                await asyncio.sleep(0.005)
        else:
            # Pure doc Q&A: two-stage retrieval + real LLM token streaming
            sources: list = []
            confidence = None
            try:
                token_gen = await asyncio.to_thread(
                    lambda: list(
                        rag_engine.two_stage_stream_query(
                            sanitized, username=current_user["username"]
                        )
                    )
                )
                for token in token_gen:
                    collected_tokens.append(token)
                    yield f"data: {_json.dumps({'token': token})}\n\n"
                    await asyncio.sleep(0)
            except Exception as e:
                logger.warning("Two-stage streaming failed, falling back: %s", e)
                try:
                    fallback_gen = await asyncio.to_thread(
                        lambda: list(rag_engine.stream_query(sanitized, username=current_user["username"]))
                    )
                    for token in fallback_gen:
                        collected_tokens.append(token)
                        yield f"data: {_json.dumps({'token': token})}\n\n"
                        await asyncio.sleep(0)
                except Exception as e2:
                    fallback = await asyncio.to_thread(
                        rag_engine.query, sanitized, current_user["username"]
                    )
                    collected_tokens.append(fallback)
                    yield f"data: {_json.dumps({'token': fallback})}\n\n"

        full_answer = "".join(collected_tokens)
        conversation_service.add_message(
            conversation_id, "assistant", full_answer,
            sources=_json.dumps(sources),
        )
        security_service.audit_log(current_user["username"], "chat", conversation_id, {"message_len": len(sanitized)})
        yield f"data: {_json.dumps({'done': True, 'sources': sources})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/configure-llm")
def configure_llm(
    request: LLMConfigRequest,
    current_user: dict = Depends(security_service.get_current_user),
):
    """Configure the active LLM provider and model"""
    try:
        # Update provider config if credentials provided
        config = {}
        if request.api_key:
            config["api_key"] = request.api_key
        if request.base_url:
            config["base_url"] = request.base_url
        if config:
            llm_manager.update_provider_config(request.provider, config)

        # Set the active provider and model
        llm_manager.set_active(request.provider, request.model)
        return {
            "message": f"LLM configured: {request.provider}/{request.model}",
            "provider": request.provider,
            "model": request.model,
        }
    except Exception:
        logger.exception("LLM configuration failed")
        raise HTTPException(status_code=500, detail="Failed to configure LLM")


@app.get("/llm-models/{provider}")
def list_llm_models(
    provider: str,
    current_user: dict = Depends(security_service.get_current_user),
):
    """List available models for a provider"""
    models = llm_manager.get_provider_models(provider)
    return {"provider": provider, "models": models}


@app.post("/configure-embedding")
def configure_embedding(
    request: EmbeddingConfigRequest,
    current_user: dict = Depends(security_service.get_current_user),
):
    """Configure the active embedding provider and model"""
    try:
        kwargs = {}
        if request.model:
            kwargs["model"] = request.model
        if request.api_key:
            kwargs["api_key"] = request.api_key
        if request.base_url:
            kwargs["base_url"] = request.base_url
        if kwargs:
            embedding_manager.update_provider(request.provider, **kwargs)

        embedding_manager.set_active(request.provider, request.model)
        provider = embedding_manager.get_active_provider()
        return {
            "message": f"Embedding configured: {provider.get_name()}",
            "provider": request.provider,
            "model": request.model,
            "dimension": provider.get_dimension(),
        }
    except Exception:
        logger.exception("Embedding configuration failed")
        raise HTTPException(status_code=500, detail="Failed to configure embedding provider")


@app.get("/embedding-providers")
def list_embedding_providers(
    current_user: dict = Depends(security_service.get_current_user),
):
    """List available embedding providers and their models"""
    info = embedding_manager.get_provider_info()
    # Add model lists for each provider
    for name in info["providers"]:
        info["providers"][name]["models"] = embedding_manager.get_provider_models(name)
    return info


@app.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    access_level: str = Query("private"),
    allowed_users: Optional[str] = Query(None),
    allowed_groups: Optional[str] = Query(None),
    allowed_roles: Optional[str] = Query(None),
    current_user: dict = Depends(security_service.get_current_user),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = os.path.splitext(file.filename)[1].lower()
    from .utils.file_validator import ALLOWED_TYPES
    if ext not in ALLOWED_TYPES:
        supported = ", ".join(sorted(ALLOWED_TYPES.keys()))
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Supported: {supported}")

    doc_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{doc_id}{ext}")

    # Read with size limit
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024 * 1024)} MB",
        )

    if access_level not in ("private", "group", "org", "public"):
        raise HTTPException(status_code=400, detail="Invalid access level")

    with open(file_path, "wb") as f:
        f.write(content)

    try:
        parsed_allowed_users = [u.strip() for u in (allowed_users or "").split(",") if u.strip()]
        parsed_allowed_groups = [g.strip() for g in (allowed_groups or "").split(",") if g.strip()]
        parsed_allowed_roles = [r.strip() for r in (allowed_roles or "").split(",") if r.strip()]

        invalid_roles = [r for r in parsed_allowed_roles if r not in ("admin", "manager", "user")]
        if invalid_roles:
            raise HTTPException(status_code=400, detail="Invalid roles in allowed_roles")

        username = current_user["username"]

        # ── Intelligent Auto-RAG: classify document and select pipeline ──
        classification = document_classifier.classify(file_path, file.filename)
        pipeline_config = auto_config_service.get_pipeline_config(
            classification.doc_type, classification.doc_subtype
        )
        logger.info(
            "Document %s classified as (%s/%s) → pipeline=%s confidence=%.2f",
            file.filename, classification.doc_type, classification.doc_subtype,
            classification.pipeline, classification.confidence,
        )

        conn_id = None
        if pipeline_config.pipeline == "sql":
            # Tabular pipeline: load into SQLite, register as DB connection
            from app.services.rbac_service import RBACService
            _rbac = RBACService()
            user_ctx = _rbac.get_user(username) or {}
            org_id = user_ctx.get("org_id", "default")
            conn_id = tabular_pipeline.ingest(
                file_path, doc_id, username, org_id, file.filename, classification
            )
        else:
            # RAG pipeline: extract → chunk (with auto-config params) → embed → ChromaDB
            rag_engine.upload_document(
                file_path,
                doc_id,
                username=username,
                access_level=access_level,
                allowed_users=parsed_allowed_users,
                allowed_groups=parsed_allowed_groups,
                allowed_roles=parsed_allowed_roles,
                chunk_size_override=pipeline_config.chunk_size,
                overlap_override=pipeline_config.overlap,
                extra_metadata={
                    "doc_type": classification.doc_type,
                    "doc_subtype": classification.doc_subtype,
                    "pipeline": "rag",
                },
            )

        # ── Store document-level metadata in SQLite ──
        import json as _json
        import sqlite3 as _sqlite3
        from datetime import datetime, timezone
        _db_path = os.path.join("data", "users.db")
        try:
            _con = _sqlite3.connect(_db_path)
            _con.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id      TEXT PRIMARY KEY,
                    filename    TEXT NOT NULL,
                    username    TEXT NOT NULL,
                    org_id      TEXT,
                    upload_time TEXT NOT NULL,
                    doc_type    TEXT,
                    doc_subtype TEXT,
                    pipeline    TEXT,
                    confidence  REAL,
                    stats       TEXT,
                    auto_config TEXT,
                    conn_id     TEXT
                )
            """)
            _con.execute(
                "INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    doc_id,
                    file.filename,
                    username,
                    None,  # org_id resolved above if needed
                    datetime.now(timezone.utc).isoformat(),
                    classification.doc_type,
                    classification.doc_subtype,
                    pipeline_config.pipeline,
                    classification.confidence,
                    _json.dumps(classification.stats),
                    _json.dumps(pipeline_config.to_dict()),
                    conn_id,
                ),
            )
            _con.commit()
            _con.close()
        except Exception as _e:
            logger.warning("Could not store document metadata: %s", _e)

        # ── Register in data catalog ──
        try:
            data_catalog.register(
                doc_id=doc_id,
                filename=file.filename,
                username=username,
                doc_type=classification.doc_type,
                doc_subtype=classification.doc_subtype,
                pipeline=pipeline_config.pipeline,
                stats=classification.stats,
                conn_id=conn_id,
                text_sample=content.decode("utf-8", errors="ignore")[:5000],
            )
        except Exception as _ce:
            logger.debug("DataCatalog register failed: %s", _ce)

        security_service.audit_log(
            username,
            "upload",
            f"document_{doc_id}",
            {
                "filename": file.filename,
                "type": ext,
                "detected_type": classification.doc_type,
                "pipeline": pipeline_config.pipeline,
            },
        )
        return {
            "message": "Document uploaded and processed successfully",
            "doc_id": doc_id,
            "filename": file.filename,
            "detected": {
                "type": classification.doc_type,
                "subtype": classification.doc_subtype,
                "pipeline": pipeline_config.pipeline,
                "confidence": classification.confidence,
                "stats": classification.stats,
                "reason": classification.reason,
            },
            "config_applied": pipeline_config.to_dict(),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to process document")
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail="Failed to process document")


@app.get("/documents")
async def list_documents(current_user: dict = Depends(security_service.get_current_user)):
    """List all documents uploaded by the current user, with type and pipeline info."""
    import json as _json
    import sqlite3 as _sqlite3
    _db_path = os.path.join("data", "users.db")
    try:
        _con = _sqlite3.connect(_db_path)
        _con.row_factory = _sqlite3.Row
        _cur = _con.execute(
            "SELECT * FROM documents WHERE username = ? ORDER BY upload_time DESC",
            (current_user["username"],),
        )
        rows = [dict(r) for r in _cur.fetchall()]
        _con.close()
        # Parse JSON blobs
        for row in rows:
            try:
                row["stats"] = _json.loads(row["stats"] or "{}")
            except Exception:
                row["stats"] = {}
            try:
                row["auto_config"] = _json.loads(row["auto_config"] or "{}")
            except Exception:
                row["auto_config"] = {}
        return {"documents": rows}
    except Exception as e:
        logger.warning("Could not list documents: %s", e)
        return {"documents": []}


async def _process_query_core(
    query: str,
    current_user: dict,
) -> dict:
    """Unified query processing.

    Decomposition, CRAG self-healing, and intent routing are all handled
    inside the orchestrator.  This function is responsible only for:
      - Calling the orchestrator (and optionally web search in parallel)
      - Merging web results if ENABLE_WEB_SEARCH is set
      - Serialising the confidence result for the API response
    """
    username = current_user["username"]

    # ── Data catalog context hint (informational) ──────────────────────────
    try:
        catalog_summary = data_catalog.get_catalog_summary(username)
        if catalog_summary and catalog_summary != "No documents in catalog.":
            logger.debug("Catalog summary for %s: %s", username, catalog_summary[:200])
    except Exception as _cat_e:
        logger.debug("DataCatalog summary failed: %s", _cat_e)

    # ── Database connections ───────────────────────────────────────────────
    db_conn_ids = database_service.get_user_connections(username)

    # ── Orchestrator + optional web search ────────────────────────────────
    enable_web = os.getenv("ENABLE_WEB_SEARCH", "false").lower() in ("1", "true", "yes")

    internal_result = None
    web_results: list = []

    if enable_web:
        routing = query_router.route(query)
        if routing["strategy"] == "parallel":
            internal_task = asyncio.to_thread(
                orchestrator.process_query,
                query,
                username=username,
                db_conn_ids=db_conn_ids,
            )
            web_task = web_search_service.search(query)
            internal_result, web_results = await asyncio.gather(
                internal_task, web_task, return_exceptions=True
            )
        elif routing["strategy"] == "web_only":
            web_results = await web_search_service.search(query)
        else:
            internal_result = await asyncio.to_thread(
                orchestrator.process_query,
                query,
                username=username,
                db_conn_ids=db_conn_ids,
            )
    else:
        routing = {"strategy": "internal_only", "needs_web": False, "needs_internal": True, "confidence": 1.0}
        internal_result = await asyncio.to_thread(
            orchestrator.process_query,
            query,
            username=username,
            db_conn_ids=db_conn_ids,
        )

    if isinstance(internal_result, Exception):
        logger.warning("Internal query failed: %s", internal_result)
        internal_result = None
    if isinstance(web_results, Exception):
        web_results = []

    # ── Assemble response ──────────────────────────────────────────────────
    answer_parts: list = []
    sources: list = []
    db_result = None
    confidence_result_obj = None

    if internal_result and internal_result.get("answer"):
        answer_parts.append(internal_result["answer"])
        sources = internal_result.get("sources", [])
        db_result = internal_result.get("db_result")
        confidence_result_obj = internal_result.get("confidence_result")

    if web_results:
        web_section = "\n".join(
            f"- [{r.get('title', '')}]({r.get('url', '')})".strip()
            for r in web_results[:5]
        )
        answer_parts.append("**Web results:**\n" + web_section)

    final_answer = "\n\n".join(answer_parts) if answer_parts else "No results found."

    # Serialize ConfidenceResult dataclass for JSON response
    confidence_dict = None
    if confidence_result_obj is not None:
        try:
            from dataclasses import asdict
            confidence_dict = asdict(confidence_result_obj)
        except Exception:
            confidence_dict = {
                "overall": getattr(confidence_result_obj, "overall", None),
                "verdict": getattr(confidence_result_obj, "verdict", None),
            }

    return {
        "answer": final_answer,
        "sources": sources,
        "db_result": db_result,
        "web_results": web_results,
        "routing": routing,
        "query_type": (internal_result or {}).get("query_type", "unknown"),
        "context": (internal_result or {}).get("context", {}),
        "agent_info": (internal_result or {}).get("agent_path", []),
        "confidence": confidence_dict,
        "retry_count": (internal_result or {}).get("retry_count", 0),
        "repair_history": (internal_result or {}).get("repair_history", []),
        "is_partial_deliver": (internal_result or {}).get("is_partial_deliver", False),
    }


@app.post("/query")
async def query_documents(
    request: QueryRequest,
    current_user: dict = Depends(security_service.get_current_user),
):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    if not security_service.rate_limit_check(current_user["username"], "query"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    sanitized_query = security_service.sanitize_input(request.query)

    try:
        result = await _process_query_core(sanitized_query, current_user)
        security_service.audit_log(
            current_user["username"],
            "query",
            "documents",
            {"query_length": len(sanitized_query), "query_type": result.get("query_type")},
        )
        if result.get("routing", {}).get("needs_web") and result.get("web_results"):
            security_service.audit_log(
                current_user["username"],
                "web_search",
                "internet",
                {"query_length": len(sanitized_query), "results": len(result["web_results"])},
            )
        return result
    except Exception:
        logger.exception("Query failed")
        raise HTTPException(status_code=500, detail="Query failed")


@app.get("/catalog")
async def get_data_catalog(
    current_user: dict = Depends(security_service.get_current_user),
):
    """Return the data catalog for the current user — all uploaded docs with topics."""
    username = current_user["username"]
    entries = data_catalog.list_user_catalog(username)
    return {
        "catalog": [
            {
                "doc_id": e.doc_id,
                "filename": e.filename,
                "doc_type": e.doc_type,
                "doc_subtype": e.doc_subtype,
                "pipeline": e.pipeline,
                "topics": e.topics[:10],
                "stats": e.stats,
                "doc_date": e.doc_date,
                "upload_time": e.upload_time,
            }
            for e in entries
        ],
        "summary": data_catalog.get_catalog_summary(username),
    }


@app.get("/metrics")
async def get_metrics(
    current_user: dict = Depends(security_service.get_current_user),
    last_n: int = Query(default=100, ge=1, le=1000),
    scope: str = Query(default="user", regex="^(user|global)$"),
):
    """
    Return aggregate quality metrics from the query trace log.

    - **last_n**: how many recent queries to include (default 100, max 1000)
    - **scope**: "user" (default) returns only this user's queries; "global" returns all
    """
    username = current_user["username"] if scope == "user" else None
    metrics = trace_service.get_metrics(username=username, last_n=last_n)
    return metrics


@app.get("/metrics/traces")
async def get_recent_traces(
    current_user: dict = Depends(security_service.get_current_user),
    limit: int = Query(default=20, ge=1, le=200),
):
    """Return the most recent raw query traces for the current user."""
    username = current_user["username"]
    rows = trace_service.get_recent_traces(username=username, limit=limit)
    return {"traces": rows, "count": len(rows)}


@app.post("/connect-database")
def connect_database(
    request: DatabaseConnectRequest,
    current_user: dict = Depends(security_service.get_current_user),
):
    try:
        if request.db_type == "postgres":
            conn_id = database_service.connect_to_postgres(
                request.host, request.port, request.database,
                request.username, request.password, request.ssl_mode
            )
        elif request.db_type == "mysql":
            conn_id = database_service.connect_to_mysql(
                request.host, request.port, request.database,
                request.username, request.password
            )
        else:
            raise HTTPException(status_code=400, detail="Unsupported database type. Supported: postgres, mysql")

        # Register connection against the user so the chat pipeline can find it
        database_service.register_user_connection(current_user["username"], conn_id)
        security_service.audit_log(
            current_user["username"], "db_connect", conn_id, {"db_type": request.db_type}
        )
        return {"conn_id": conn_id, "message": "Connected successfully"}
    except Exception as e:
        logger.exception("Database connection failed")
        raise HTTPException(status_code=500, detail=f"Connection failed: {str(e)}")


@app.post("/execute-query")
def execute_query(
    request: DatabaseQueryRequest,
    current_user: dict = Depends(security_service.get_current_user),
):
    try:
        result = database_service.execute_query(request.conn_id, request.query)
        return {"result": result.to_dict('records') if not result.empty else []}
    except Exception as e:
        logger.exception("Query execution failed")
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@app.get("/list-tables/{conn_id}")
def list_tables(
    conn_id: str,
    current_user: dict = Depends(security_service.get_current_user),
):
    try:
        tables = database_service.list_tables(conn_id)
        return {"tables": tables}
    except Exception as e:
        logger.exception("List tables failed")
        raise HTTPException(status_code=500, detail=f"Failed to list tables: {str(e)}")


@app.get("/table-schema/{conn_id}/{table_name}")
def get_table_schema(
    conn_id: str,
    table_name: str,
    current_user: dict = Depends(security_service.get_current_user),
):
    try:
        schema = database_service.get_table_schema(conn_id, table_name)
        return schema
    except Exception as e:
        logger.exception("Get schema failed")
        raise HTTPException(status_code=500, detail=f"Failed to get schema: {str(e)}")


@app.delete("/close-connection/{conn_id}")
def close_connection(
    conn_id: str,
    current_user: dict = Depends(security_service.get_current_user),
):
    try:
        database_service.remove_user_connection(current_user["username"], conn_id)
        database_service.close_connection(conn_id)
        return {"message": "Connection closed"}
    except Exception as e:
        logger.exception("Close connection failed")
        raise HTTPException(status_code=500, detail=f"Failed to close connection: {str(e)}")


@app.get("/my-connections")
def get_my_connections(
    current_user: dict = Depends(security_service.get_current_user),
):
    """List the current user's active database connections with schema info."""
    conn_ids = database_service.get_user_connections(current_user["username"])
    connections = []
    for conn_id in conn_ids:
        try:
            tables = database_service.list_tables(conn_id)
        except Exception:
            tables = []
        connections.append({"conn_id": conn_id, "tables": tables})
    return {"connections": connections}


# ======================== RAG Configuration Endpoints ========================


@app.get("/rag/templates")
def list_rag_templates(
    current_user: dict = Depends(security_service.get_current_user),
):
    """Return all pre-built RAG templates"""
    return {"templates": rag_config_service.get_all_templates()}


@app.get("/rag/config")
def get_active_rag_config(
    current_user: dict = Depends(security_service.get_current_user),
):
    """Get the current user's active RAG configuration"""
    config = rag_config_service.get_user_active_config(current_user["username"])
    return {"config": config}


@app.post("/rag/config/apply-template")
def apply_rag_template(
    request: ApplyTemplateRequest,
    current_user: dict = Depends(security_service.get_current_user),
):
    """Apply a pre-built template as the user's active config"""
    try:
        config = rag_config_service.apply_template(current_user["username"], request.template_name)
        security_service.audit_log(
            current_user["username"],
            "rag_config",
            "apply_template",
            {"template": request.template_name},
        )
        return {"message": f"Template '{request.template_name}' applied", "config": config}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Failed to apply RAG template")
        raise HTTPException(status_code=500, detail="Failed to apply template")


@app.post("/rag/config/custom")
def create_custom_rag_config(
    request: CustomConfigRequest,
    current_user: dict = Depends(security_service.get_current_user),
):
    """Create a custom RAG configuration and set it as active"""
    try:
        config = rag_config_service.create_custom_config(
            current_user["username"], request.model_dump()
        )
        security_service.audit_log(
            current_user["username"],
            "rag_config",
            "create_custom",
            {"config_name": request.config_name},
        )
        return {"message": "Custom configuration saved", "config": config}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Failed to create custom RAG config")
        raise HTTPException(status_code=500, detail="Failed to save configuration")


@app.get("/rag/config/custom")
def list_custom_rag_configs(
    current_user: dict = Depends(security_service.get_current_user),
):
    """List all custom RAG configs for the current user"""
    configs = rag_config_service.list_user_custom_configs(current_user["username"])
    return {"configs": configs}


@app.delete("/rag/config/custom/{config_id}")
def delete_custom_rag_config(
    config_id: int,
    current_user: dict = Depends(security_service.get_current_user),
):
    """Delete a custom RAG configuration"""
    deleted = rag_config_service.delete_custom_config(current_user["username"], config_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Configuration not found")
    return {"message": "Configuration deleted"}


# ======================== Cloud Storage Endpoints ========================


class CloudConnectRequest(BaseModel):
    service_name: str  # "s3", "local"
    credentials: dict
    display_name: Optional[str] = None


class CloudIndexFileRequest(BaseModel):
    file_id: str


class CloudIndexFolderRequest(BaseModel):
    folder_path: str = "/"
    recursive: bool = True


@app.get("/cloud/services/available")
def list_available_cloud_services(
    current_user: dict = Depends(security_service.get_current_user),
):
    """List all available cloud storage services and their auth requirements"""
    return {"services": cloud_storage_service.get_available_services()}


@app.post("/cloud/connect")
def connect_cloud_service(
    request: CloudConnectRequest,
    current_user: dict = Depends(security_service.get_current_user),
):
    """Connect to a cloud storage service"""
    try:
        conn_id = cloud_storage_service.connect_service(
            current_user["username"],
            request.service_name,
            request.credentials,
            request.display_name,
        )
        security_service.audit_log(
            current_user["username"],
            "cloud_connect",
            request.service_name,
            {"connection_id": conn_id},
        )
        return {"connection_id": conn_id, "message": f"Connected to {request.service_name}"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Cloud connection failed")
        raise HTTPException(status_code=500, detail="Failed to connect to cloud service")


@app.delete("/cloud/disconnect/{conn_id}")
def disconnect_cloud_service(
    conn_id: str,
    current_user: dict = Depends(security_service.get_current_user),
):
    """Disconnect a cloud storage service"""
    disconnected = cloud_storage_service.disconnect_service(current_user["username"], conn_id)
    if not disconnected:
        raise HTTPException(status_code=404, detail="Connection not found")
    return {"message": "Disconnected"}


@app.get("/cloud/services")
def list_user_cloud_services(
    current_user: dict = Depends(security_service.get_current_user),
):
    """List user's connected cloud services"""
    services = cloud_storage_service.get_user_services(current_user["username"])
    return {"services": services}


@app.get("/cloud/{conn_id}/files")
def list_cloud_files(
    conn_id: str,
    folder_path: str = Query("/", description="Folder path to list"),
    current_user: dict = Depends(security_service.get_current_user),
):
    """List files in a cloud storage folder"""
    try:
        files = cloud_storage_service.list_files(current_user["username"], conn_id, folder_path)
        return {"files": files, "folder_path": folder_path}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Failed to list cloud files")
        raise HTTPException(status_code=500, detail="Failed to list files")


@app.get("/cloud/{conn_id}/search")
def search_cloud_files(
    conn_id: str,
    query: str = Query(..., description="Search query"),
    current_user: dict = Depends(security_service.get_current_user),
):
    """Search files in a cloud storage service"""
    try:
        results = cloud_storage_service.search_files(current_user["username"], conn_id, query)
        return {"results": results, "query": query}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Cloud search failed")
        raise HTTPException(status_code=500, detail="Search failed")


@app.post("/cloud/{conn_id}/index-file")
def index_cloud_file(
    conn_id: str,
    request: CloudIndexFileRequest,
    current_user: dict = Depends(security_service.get_current_user),
):
    """Download and index a single cloud file into the RAG engine"""
    try:
        result = cloud_storage_service.index_file(
            current_user["username"], conn_id, request.file_id, rag_engine
        )
        security_service.audit_log(
            current_user["username"],
            "cloud_index",
            conn_id,
            {"file_id": request.file_id, "doc_id": result.get("doc_id")},
        )
        return {"message": "File indexed successfully", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        logger.exception("Cloud file indexing failed")
        raise HTTPException(status_code=500, detail="Failed to index file")


@app.post("/cloud/{conn_id}/index-folder")
def index_cloud_folder(
    conn_id: str,
    request: CloudIndexFolderRequest,
    current_user: dict = Depends(security_service.get_current_user),
):
    """Index all supported files in a cloud folder"""
    try:
        results = cloud_storage_service.index_folder(
            current_user["username"], conn_id, request.folder_path,
            rag_engine, recursive=request.recursive,
        )
        security_service.audit_log(
            current_user["username"],
            "cloud_index_folder",
            conn_id,
            {"folder_path": request.folder_path, "files_indexed": len(results)},
        )
        return {"message": f"Indexed {len(results)} files", "results": results}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Cloud folder indexing failed")
        raise HTTPException(status_code=500, detail="Failed to index folder")


@app.get("/cloud/indexed-files")
def list_indexed_cloud_files(
    current_user: dict = Depends(security_service.get_current_user),
):
    """List all cloud files that have been indexed"""
    files = cloud_storage_service.get_indexed_files(current_user["username"])
    return {"files": files}


# ---------------------------------------------------------------------------
# Knowledge Graph endpoints
# ---------------------------------------------------------------------------

class GraphBuildRequest(BaseModel):
    text: str
    source_doc: str = "manual_input"

class GraphQueryRequest(BaseModel):
    question: str


@app.post("/graph/build")
def build_knowledge_graph(
    request: GraphBuildRequest,
    current_user: dict = Depends(security_service.get_current_user),
):
    """Extract entities/relationships from text and add to the knowledge graph."""
    try:
        from app.graph.knowledge_graph import KnowledgeGraphBuilder
        builder = KnowledgeGraphBuilder()
        llm = orchestrator.query_agent._get_llm()
        stats = builder.build_from_text(request.text, llm, source_doc=request.source_doc)
        return {"message": "Graph updated", **stats, "graph_stats": builder.get_stats()}
    except Exception:
        logger.exception("Graph build failed")
        raise HTTPException(status_code=500, detail="Failed to build knowledge graph")


@app.post("/graph/query")
def query_knowledge_graph(
    request: GraphQueryRequest,
    current_user: dict = Depends(security_service.get_current_user),
):
    """Query the knowledge graph using natural language."""
    try:
        from app.graph.knowledge_graph import GraphQueryEngine
        engine = GraphQueryEngine()
        llm = orchestrator.query_agent._get_llm()
        result = engine.query(request.question, llm)
        return result
    except Exception:
        logger.exception("Graph query failed")
        raise HTTPException(status_code=500, detail="Graph query failed")


@app.get("/graph/stats")
def get_graph_stats(
    current_user: dict = Depends(security_service.get_current_user),
):
    """Get knowledge graph statistics."""
    try:
        from app.graph.knowledge_graph import KnowledgeGraphBuilder
        builder = KnowledgeGraphBuilder()
        return builder.get_stats()
    except Exception:
        logger.exception("Graph stats failed")
        raise HTTPException(status_code=500, detail="Failed to get graph stats")


# ======================== Document Management Endpoints ========================

@app.get("/documents")
def list_documents(
    current_user: dict = Depends(security_service.get_current_user),
):
    """List all documents uploaded by the current user"""
    try:
        # Get documents from org-specific ChromaDB metadata
        org_id = current_user.get("org_id", "default")
        collection = rag_engine.vectordb._get_collection(org_id)
        results = collection.get(
            where={"$and": [{"source_type": "upload"}]},
            include=["metadatas"]
        )
        
        # Extract unique documents
        docs_map = {}
        for metadata in results.get("metadatas", []):
            doc_id = metadata.get("doc_id")
            if doc_id and doc_id not in docs_map:
                docs_map[doc_id] = {
                    "doc_id": doc_id,
                    "filename": metadata.get("filename", "unknown"),
                    "uploaded_at": metadata.get("uploaded_at", ""),
                }

        # Apply RBAC filtering
        filtered_docs = []
        for doc in docs_map.values():
            doc_meta = next(
                (m for m in results.get("metadatas", []) if m.get("doc_id") == doc["doc_id"]),
                {},
            )
            if rbac_service.can_access_document(current_user, doc["doc_id"], doc_meta):
                perms = rbac_service.get_document_permissions(doc["doc_id"]) or {}
                doc["access_level"] = perms.get("access_level")
                filtered_docs.append(doc)

        return {"documents": filtered_docs, "total": len(filtered_docs)}
    except Exception:
        logger.exception("Failed to list documents")
        raise HTTPException(status_code=500, detail="Failed to list documents")


@app.delete("/documents/{doc_id}")
def delete_document(
    doc_id: str,
    current_user: dict = Depends(security_service.get_current_user),
):
    """Delete a document from the system"""
    try:
        # Delete from ChromaDB (org-specific)
        org_id = current_user.get("org_id", "default")
        collection = rag_engine.vectordb._get_collection(org_id)
        results = collection.get(
            where={"doc_id": doc_id},
            include=["ids"]
        )
        
        if not results.get("ids"):
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Check permissions
        meta_results = collection.get(where={"doc_id": doc_id}, include=["metadatas"])
        sample_meta = (meta_results.get("metadatas") or [{}])[0]
        if not rbac_service.can_manage_document(current_user, doc_id, sample_meta):
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        collection.delete(ids=results["ids"])
        rbac_service.delete_document_permissions(doc_id)
        
        # Delete from filesystem
        import glob
        for file_path in glob.glob(f"{UPLOAD_DIR}/{doc_id}.*"):
            try:
                os.remove(file_path)
            except Exception as e:
                logger.warning(f"Failed to delete file {file_path}: {e}")
        
        # Log deletion
        security_service.audit_log(
            current_user["username"],
            "delete_document",
            doc_id,
            {"doc_id": doc_id}
        )
        
        return {"message": "Document deleted successfully", "doc_id": doc_id}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to delete document")
        raise HTTPException(status_code=500, detail="Failed to delete document")


@app.get("/stats")
def get_stats(
    current_user: dict = Depends(security_service.get_current_user),
):
    """Get system statistics"""
    try:
        org_id = current_user.get("org_id", "default")
        collection = rag_engine.vectordb._get_collection(org_id)
        total_chunks = collection.count()
        
        # Get unique documents count
        results = collection.get(include=["metadatas"])
        doc_ids = set(m.get("doc_id") for m in results.get("metadatas", []) if m.get("doc_id"))
        
        stats = {
            "total_documents": len(doc_ids),
            "total_chunks": total_chunks,
            "embedding_provider": embedding_manager.get_active_provider().get_name() if embedding_manager.get_active_provider() else "none",
            "llm_providers": llm_manager.get_available_providers(),
        }
        
        return stats
    except Exception:
        logger.exception("Failed to get stats")
        raise HTTPException(status_code=500, detail="Failed to get statistics")
