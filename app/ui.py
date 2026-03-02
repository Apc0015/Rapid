import copy
import streamlit as st
import requests
import os
import uuid
from datetime import datetime
from app.services.llm_service import LLMManager
from app.services.embedding_service import EmbeddingManager

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")

# Page configuration
st.set_page_config(
    page_title="RAPID",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="auto"
)

# Minimal custom CSS
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- Server-side session persistence (survives page refresh) ---
@st.cache_resource
def _get_session_store():
    return {}

_session_store = _get_session_store()

# Initialize LLM Manager
llm_manager = LLMManager()
embedding_manager = EmbeddingManager()

# --- Session state defaults ---
_DEFAULTS = {
    "token": None,
    "username": None,
    "role": None,
    "org_id": None,
    "messages": [],
    "uploaded_files": [],
    "llm_provider": None,
    "llm_model": None,
    "llm_models_list": [],
    "llm_connected": False,
    "embedding_provider": None,
    "embedding_model": None,
    "embedding_connected": False,
    "conversation_id": None,   # active conversation (persisted in DB)
    "active_db_connections": [],  # list of {conn_id, tables}
}
for _key, _val in _DEFAULTS.items():
    if _key not in st.session_state:
        st.session_state[_key] = copy.deepcopy(_val)


# --- Session persistence helpers ---
def _restore_session():
    """Restore auth session from server-side store on page refresh."""
    if st.session_state.token is not None:
        return  # Already logged in this session

    sid = st.query_params.get("sid")
    if not sid or sid not in _session_store:
        return

    data = _session_store[sid]
    # Verify the stored token is still valid
    try:
        resp = requests.get(
            f"{API_BASE}/me",
            headers={"Authorization": f"Bearer {data['token']}"},
            timeout=5,
        )
        if resp.status_code == 200:
            st.session_state.token = data["token"]
            st.session_state.username = data["username"]
            st.session_state.role = data.get("role")
            st.session_state.org_id = data.get("org_id")
            st.session_state.messages = copy.deepcopy(data.get("messages", []))
            st.session_state.uploaded_files = list(data.get("uploaded_files", []))
            st.session_state.conversation_id = data.get("conversation_id")
            st.session_state.active_db_connections = list(data.get("active_db_connections", []))
            return
    except Exception:
        pass

    # Token invalid or server unreachable — clean up
    del _session_store[sid]
    st.query_params.clear()


def _save_session():
    """Persist current session to the server-side store."""
    if not st.session_state.token:
        return
    sid = st.query_params.get("sid")
    if not sid:
        sid = str(uuid.uuid4())
        st.query_params["sid"] = sid
    _session_store[sid] = {
        "token": st.session_state.token,
        "username": st.session_state.username,
        "role": st.session_state.role,
        "org_id": st.session_state.org_id,
        "messages": copy.deepcopy(st.session_state.messages),
        "uploaded_files": list(st.session_state.uploaded_files),
        "conversation_id": st.session_state.conversation_id,
        "active_db_connections": list(st.session_state.active_db_connections),
    }


def _clear_session():
    """Logout: clear session from store and reset state."""
    sid = st.query_params.get("sid")
    if sid and sid in _session_store:
        del _session_store[sid]
    st.query_params.clear()
    for key, val in _DEFAULTS.items():
        st.session_state[key] = copy.deepcopy(val)


# Restore session on page load
_restore_session()


# --- Auth helpers ---
def _authenticate(username, password):
    try:
        resp = requests.post(
            f"{API_BASE}/login",
            json={"username": username, "password": password},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            st.session_state.token = data["access_token"]
            st.session_state.username = data["user"]["username"]
            st.session_state.role = data["user"].get("role")
            st.session_state.org_id = data["user"].get("org_id")
            st.session_state.active_db_connections = []

            # Try to resume latest conversation or create a new one
            auth_headers = {"Authorization": f"Bearer {data['access_token']}"}
            try:
                conv_resp = requests.get(
                    f"{API_BASE}/api/conversations",
                    headers=auth_headers,
                    timeout=10,
                )
                if conv_resp.status_code == 200:
                    convs = conv_resp.json().get("conversations", [])
                    if convs:
                        # Resume most recent conversation
                        conv_id = convs[0]["conversation_id"]
                        st.session_state.conversation_id = conv_id
                        # Load history from API
                        msg_resp = requests.get(
                            f"{API_BASE}/api/conversations/{conv_id}/messages",
                            headers=auth_headers,
                            timeout=10,
                        )
                        if msg_resp.status_code == 200:
                            api_msgs = msg_resp.json().get("messages", [])
                            st.session_state.messages = [
                                {"role": m["role"], "content": m["content"]}
                                for m in api_msgs
                            ]
                        else:
                            st.session_state.messages = []
                    else:
                        raise ValueError("no conversations")
            except Exception:
                # Create a fresh conversation
                try:
                    new_conv = requests.post(
                        f"{API_BASE}/api/conversations",
                        json={"title": "Chat"},
                        headers=auth_headers,
                        timeout=10,
                    )
                    if new_conv.status_code == 200:
                        st.session_state.conversation_id = new_conv.json()["conversation_id"]
                except Exception:
                    st.session_state.conversation_id = None
                st.session_state.messages = [
                    {
                        "role": "assistant",
                        "content": f"Welcome back, **{st.session_state.username}**! Upload a document or connect a database using the sidebar, then ask me anything.",
                    }
                ]

            _save_session()
            return True, None
        else:
            detail = resp.json().get("detail", "Invalid credentials")
            return False, detail
    except requests.exceptions.ConnectionError:
        return False, "Cannot connect to the API server. Is it running?"
    except Exception as e:
        return False, f"Connection error: {e}"


def _register(username, password):
    try:
        resp = requests.post(
            f"{API_BASE}/register",
            json={"username": username, "password": password},
            timeout=10,
        )
        if resp.status_code == 200:
            return True, None
        else:
            detail = resp.json().get("detail", "Registration failed")
            return False, detail
    except requests.exceptions.ConnectionError:
        return False, "Cannot connect to the API server. Is it running?"
    except Exception as e:
        return False, f"Connection error: {e}"


def _configure_backend_llm(provider, model, api_key=None, base_url=None):
    """Tell the backend which provider+model to use."""
    if not st.session_state.token:
        return
    try:
        payload = {"provider": provider, "model": model}
        if api_key:
            payload["api_key"] = api_key
        if base_url:
            payload["base_url"] = base_url
        requests.post(
            f"{API_BASE}/configure-llm",
            json=payload,
            headers={"Authorization": f"Bearer {st.session_state.token}"},
            timeout=10,
        )
    except Exception:
        pass  # Non-critical; backend will fall back to auto-detection


# ===================== SIDEBAR =====================
with st.sidebar:
    if st.session_state.token:
        st.markdown(f"**Logged in as:** {st.session_state.username}")
        if st.button("Logout"):
            _clear_session()
            st.rerun()

        st.divider()
        page = "Chat"
        if st.session_state.role == "admin":
            page = st.radio("Menu", ["Chat", "Admin"], key="menu_select")
        else:
            page = st.radio("Menu", ["Chat"], key="menu_select")
        st.session_state.page = page

        # --- File Upload ---
        st.subheader("Upload Document")
        uploaded_file = st.file_uploader(
            "Choose a file",
            type=["pdf", "docx", "txt", "csv", "xlsx", "xls", "json", "xml", "parquet", "md", "html"],
            key="file_uploader",
        )
        if uploaded_file and uploaded_file.name not in st.session_state.uploaded_files:
            with st.spinner("Uploading and analyzing..."):
                files = {"file": (uploaded_file.name, uploaded_file, uploaded_file.type)}
                headers = {"Authorization": f"Bearer {st.session_state.token}"}
                try:
                    resp = requests.post(
                        f"{API_BASE}/upload", files=files, headers=headers, timeout=120
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        detected = data.get("detected", {})
                        st.session_state.uploaded_files.append(uploaded_file.name)

                        # Build a friendly detection summary for the chat
                        pipeline = detected.get("pipeline", "rag")
                        doc_type = detected.get("type", "document")
                        doc_subtype = detected.get("subtype", "")
                        confidence = detected.get("confidence", 0.0)
                        stats = detected.get("stats", {})
                        reason = detected.get("reason", "")

                        # Stats line
                        stats_parts = []
                        if stats.get("rows"):
                            stats_parts.append(f"{stats['rows']:,} rows")
                        if stats.get("cols"):
                            stats_parts.append(f"{stats['cols']} columns")
                        if stats.get("word_count"):
                            stats_parts.append(f"{stats['word_count']:,} words")
                        if stats.get("pages"):
                            stats_parts.append(f"{stats['pages']} pages")
                        if stats.get("sheet_count", 0) > 1:
                            stats_parts.append(f"{stats['sheet_count']} sheets")
                        stats_line = " · ".join(stats_parts)

                        # Pipeline description
                        if pipeline == "sql":
                            pipeline_desc = "SQL pipeline active — ask questions in natural language"
                        else:
                            cfg = data.get("config_applied", {})
                            cs = cfg.get("chunk_size", "?")
                            sm = cfg.get("search_mode", "hybrid")
                            pipeline_desc = f"RAG pipeline · {sm} search · chunk_size={cs}"

                        chat_msg = (
                            f"**{uploaded_file.name}** uploaded\n\n"
                            f"**Detected:** {doc_type.replace('_', ' ').title()}"
                            + (f" · {doc_subtype.replace('_', ' ').title()}" if doc_subtype else "")
                            + f" ({confidence * 100:.0f}% confidence)\n"
                            + (f"**Stats:** {stats_line}\n" if stats_line else "")
                            + f"**Pipeline:** {pipeline_desc}"
                        )
                        st.session_state.messages.append(
                            {"role": "assistant", "content": chat_msg}
                        )
                        _save_session()
                        st.rerun()
                    elif resp.status_code == 401:
                        st.error("Session expired. Please login again.")
                        _clear_session()
                        st.rerun()
                    else:
                        detail = resp.json().get("detail", "Upload failed")
                        st.error(detail)
                except requests.exceptions.ConnectionError:
                    st.error("Cannot connect to the API server. Is it running?")
                except Exception as e:
                    st.error(f"Upload error: {e}")

        if st.session_state.uploaded_files:
            st.markdown("**Uploaded files:**")
            for fname in st.session_state.uploaded_files:
                st.markdown(f"- {fname}")

        st.divider()

        # --- LLM Configuration ---
        st.subheader("LLM Configuration")

        if st.session_state.llm_connected and st.session_state.llm_provider:
            st.success(f"Active: {st.session_state.llm_provider} / {st.session_state.llm_model}")

        provider_type = st.radio("Provider Type", ["Cloud", "Local"], key="provider_type")

        if provider_type == "Cloud":
            cloud_providers = ["openai", "anthropic", "openrouter"]
            selected = st.selectbox("Provider", cloud_providers, key="cloud_prov")
            api_key = st.text_input(f"{selected.upper()} API Key", type="password", key="api_key")
            if st.button("Connect", key="connect_cloud"):
                if api_key:
                    try:
                        llm_manager.update_provider_config(selected, {"api_key": api_key})
                        models = llm_manager.get_provider_models(selected)
                        if models:
                            st.session_state.llm_provider = selected
                            st.session_state.llm_models_list = models
                            st.session_state.llm_model = models[0]
                            st.session_state.llm_connected = True
                            # Configure backend
                            _configure_backend_llm(selected, models[0], api_key=api_key)
                            st.rerun()
                        else:
                            st.error("Could not retrieve models. Check your API key.")
                    except Exception as e:
                        st.error(f"Connection failed: {e}")
                else:
                    st.warning("Please enter an API key")
        else:
            local_providers = ["ollama", "lmstudio"]
            selected = st.selectbox("Provider", local_providers, key="local_prov")
            default_port = 11434 if selected == "ollama" else 1234
            base_url = st.text_input(
                "Base URL",
                value=f"http://localhost:{default_port}",
                key="base_url",
            )
            if st.button("Connect", key="connect_local"):
                try:
                    llm_manager.update_provider_config(selected, {"base_url": base_url})
                    models = llm_manager.get_provider_models(selected)
                    if models:
                        st.session_state.llm_provider = selected
                        st.session_state.llm_models_list = models
                        st.session_state.llm_model = models[0]
                        st.session_state.llm_connected = True
                        # Configure backend
                        _configure_backend_llm(selected, models[0], base_url=base_url)
                        st.rerun()
                    else:
                        st.error(f"No models found. Is {selected} running?")
                except Exception as e:
                    st.error(f"Connection failed: {e}")

        # --- Model selector (shown after connecting) ---
        if st.session_state.llm_connected and st.session_state.llm_models_list:
            st.divider()
            st.subheader("Select Model")
            current_idx = 0
            if st.session_state.llm_model in st.session_state.llm_models_list:
                current_idx = st.session_state.llm_models_list.index(st.session_state.llm_model)
            chosen_model = st.selectbox(
                "Model",
                st.session_state.llm_models_list,
                index=current_idx,
                key="model_selector",
            )
            if chosen_model != st.session_state.llm_model:
                st.session_state.llm_model = chosen_model
                _configure_backend_llm(st.session_state.llm_provider, chosen_model)
                st.rerun()

        st.divider()

        # --- Embedding Configuration ---
        st.subheader("Embedding Configuration")

        if st.session_state.embedding_connected and st.session_state.embedding_provider:
            st.success(f"Active: {st.session_state.embedding_provider} / {st.session_state.embedding_model}")

        emb_type = st.radio("Embedding Type", ["Local", "Cloud"], key="emb_type")

        if emb_type == "Local":
            local_emb_providers = ["sentence-transformers", "ollama"]
            emb_selected = st.selectbox("Provider", local_emb_providers, key="local_emb_prov")

            if emb_selected == "sentence-transformers":
                st_models = embedding_manager.get_provider_models("sentence-transformers")
                emb_model = st.selectbox(
                    "Model",
                    st_models,
                    index=0,
                    key="st_emb_model",
                )
                if st.button("Activate", key="activate_st_emb"):
                    try:
                        embedding_manager.update_provider("sentence-transformers", model=emb_model)
                        embedding_manager.set_active("sentence-transformers", emb_model)
                        st.session_state.embedding_provider = "sentence-transformers"
                        st.session_state.embedding_model = emb_model
                        st.session_state.embedding_connected = True
                        # Notify backend
                        if st.session_state.token:
                            try:
                                requests.post(
                                    f"{API_BASE}/configure-embedding",
                                    json={"provider": "sentence-transformers", "model": emb_model},
                                    headers={"Authorization": f"Bearer {st.session_state.token}"},
                                    timeout=10,
                                )
                            except Exception:
                                pass
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to load model: {e}")

            elif emb_selected == "ollama":
                ollama_url = st.text_input(
                    "Ollama URL",
                    value="http://localhost:11434",
                    key="ollama_emb_url",
                )
                ollama_emb_models = embedding_manager.get_provider_models("ollama")
                emb_model = st.selectbox(
                    "Model",
                    ollama_emb_models if ollama_emb_models else ["nomic-embed-text"],
                    key="ollama_emb_model",
                )
                if st.button("Activate", key="activate_ollama_emb"):
                    try:
                        embedding_manager.update_provider("ollama", base_url=ollama_url, model=emb_model)
                        embedding_manager.set_active("ollama", emb_model)
                        st.session_state.embedding_provider = "ollama"
                        st.session_state.embedding_model = emb_model
                        st.session_state.embedding_connected = True
                        if st.session_state.token:
                            try:
                                requests.post(
                                    f"{API_BASE}/configure-embedding",
                                    json={"provider": "ollama", "model": emb_model, "base_url": ollama_url},
                                    headers={"Authorization": f"Bearer {st.session_state.token}"},
                                    timeout=10,
                                )
                            except Exception:
                                pass
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed: {e}")

        else:  # Cloud
            cloud_emb_providers = ["openai", "huggingface"]
            emb_selected = st.selectbox("Provider", cloud_emb_providers, key="cloud_emb_prov")

            emb_api_key = st.text_input(f"{emb_selected.upper()} API Key", type="password", key="emb_api_key")

            cloud_models = embedding_manager.get_provider_models(emb_selected)
            emb_model = st.selectbox(
                "Model",
                cloud_models if cloud_models else ["default"],
                key="cloud_emb_model",
            )

            if st.button("Activate", key="activate_cloud_emb"):
                if emb_api_key:
                    try:
                        embedding_manager.update_provider(emb_selected, api_key=emb_api_key, model=emb_model)
                        embedding_manager.set_active(emb_selected, emb_model)
                        st.session_state.embedding_provider = emb_selected
                        st.session_state.embedding_model = emb_model
                        st.session_state.embedding_connected = True
                        if st.session_state.token:
                            try:
                                requests.post(
                                    f"{API_BASE}/configure-embedding",
                                    json={"provider": emb_selected, "model": emb_model, "api_key": emb_api_key},
                                    headers={"Authorization": f"Bearer {st.session_state.token}"},
                                    timeout=10,
                                )
                            except Exception:
                                pass
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed: {e}")
                else:
                    st.warning("Please enter an API key")

        st.caption("⚠️ Changing embedding provider requires re-uploading documents.")

        st.divider()

        # --- Database Connection ---
        st.subheader("🗄️ Database Connection")
        st.caption("Connect a database so RAPID can answer questions from your live data.")

        # Show active connections
        if st.session_state.active_db_connections:
            for conn in st.session_state.active_db_connections:
                conn_id = conn.get("conn_id", "")
                tables = conn.get("tables", [])
                st.success(f"✅ {conn_id}")
                if tables:
                    st.caption(f"Tables: {', '.join(tables[:5])}{'...' if len(tables) > 5 else ''}")
                if st.button("Disconnect", key=f"disc_db_{conn_id}"):
                    try:
                        requests.delete(
                            f"{API_BASE}/close-connection/{conn_id}",
                            headers={"Authorization": f"Bearer {st.session_state.token}"},
                            timeout=10,
                        )
                        st.session_state.active_db_connections = [
                            c for c in st.session_state.active_db_connections if c.get("conn_id") != conn_id
                        ]
                        _save_session()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

        with st.expander("➕ Connect Database"):
            db_type = st.selectbox(
                "Database Type",
                ["postgres", "mysql"],
                format_func=lambda x: {
                    "postgres": "🐘 PostgreSQL",
                    "mysql": "🐬 MySQL",
                }.get(x, x),
                key="db_type_select",
            )

            if db_type in ("postgres", "mysql"):
                db_host = st.text_input("Host", placeholder="localhost", key="db_host")
                db_port = st.number_input("Port", value=5432 if db_type == "postgres" else 3306, key="db_port")
                db_name = st.text_input("Database name", key="db_name")
                db_user = st.text_input("Username", key="db_user")
                db_pass = st.text_input("Password", type="password", key="db_pass")
                if db_type == "postgres":
                    db_ssl = st.selectbox("SSL Mode", ["prefer", "require", "disable"], key="db_ssl")

                if st.button("Connect", key="connect_db_btn"):
                    if all([db_host, db_name, db_user]):
                        payload = {
                            "db_type": db_type,
                            "host": db_host,
                            "port": int(db_port),
                            "database": db_name,
                            "username": db_user,
                            "password": db_pass,
                        }
                        if db_type == "postgres":
                            payload["ssl_mode"] = db_ssl
                        try:
                            r = requests.post(
                                f"{API_BASE}/connect-database",
                                json=payload,
                                headers={"Authorization": f"Bearer {st.session_state.token}"},
                                timeout=15,
                            )
                            if r.status_code == 200:
                                conn_id = r.json()["conn_id"]
                                # Fetch tables
                                t_resp = requests.get(
                                    f"{API_BASE}/list-tables/{conn_id}",
                                    headers={"Authorization": f"Bearer {st.session_state.token}"},
                                    timeout=10,
                                )
                                tables = t_resp.json().get("tables", []) if t_resp.status_code == 200 else []
                                st.session_state.active_db_connections.append({"conn_id": conn_id, "tables": tables})
                                _save_session()
                                st.success(f"Connected: {conn_id}")
                                st.rerun()
                            else:
                                st.error(r.json().get("detail", "Connection failed"))
                        except Exception as e:
                            st.error(f"Error: {e}")
                    else:
                        st.warning("Fill in host, database, and username")

        st.divider()

        # --- RAG Configuration ---
        st.subheader("RAG Configuration")

        rag_config_mode = st.radio("Configuration Mode", ["Use Template", "Custom Configuration"], key="rag_config_mode")

        if rag_config_mode == "Use Template":
            template_info = {
                "fast_search": ("⚡ Fast Search", "Quick FAQ lookups, real-time chat", "Less context, faster responses"),
                "balanced": ("⚖️ Balanced", "General-purpose queries", "Optimal speed/quality"),
                "deep_analysis": ("🔬 Deep Analysis", "Research, detailed analysis", "Slower but comprehensive"),
                "cost_optimized": ("💰 Cost Optimized", "Cost-sensitive deployments", "Minimal API calls"),
                "high_accuracy": ("🎯 High Accuracy", "Mission-critical accuracy", "Higher cost, max quality"),
            }
            template_keys = list(template_info.keys())
            template_labels = [template_info[k][0] for k in template_keys]

            selected_idx = st.selectbox(
                "Select Template",
                range(len(template_keys)),
                format_func=lambda i: template_labels[i],
                index=1,  # Default: balanced
                key="rag_template_select",
            )
            selected_template = template_keys[selected_idx]
            info = template_info[selected_template]
            st.caption(f"📝 {info[1]}")
            st.caption(f"⚖️ Trade-off: {info[2]}")

            if st.button("Apply Template", key="apply_rag_template"):
                if st.session_state.token:
                    try:
                        resp = requests.post(
                            f"{API_BASE}/rag/config/apply-template",
                            json={"template_name": selected_template},
                            headers={"Authorization": f"Bearer {st.session_state.token}"},
                            timeout=10,
                        )
                        if resp.status_code == 200:
                            st.success(f"Template '{info[0]}' applied!")
                            st.rerun()
                        else:
                            st.error(f"Failed: {resp.text}")
                    except Exception as e:
                        st.error(f"Error: {e}")
                else:
                    st.warning("Please log in first")

        else:  # Custom Configuration
            col1, col2 = st.columns(2)
            with col1:
                chunk_size = st.slider("Chunk Size (tokens)", 128, 2048, 512, step=128, key="rag_chunk")
                top_k = st.slider("Top-K Documents", 1, 20, 5, key="rag_topk")
            with col2:
                overlap = st.slider("Overlap (tokens)", 0, 256, 64, step=16, key="rag_overlap")
                embedding_model = st.selectbox(
                    "Embedding Model",
                    ["text-embedding-ada-002", "text-embedding-3-small", "text-embedding-3-large"],
                    key="rag_emb_model",
                )

            config_name = st.text_input("Config Name", value="My Custom Config", key="rag_config_name")

            if st.button("Save Custom Config", key="save_custom_rag"):
                if st.session_state.token:
                    try:
                        resp = requests.post(
                            f"{API_BASE}/rag/config/custom",
                            json={
                                "config_name": config_name,
                                "chunk_size": chunk_size,
                                "overlap_size": overlap,
                                "top_k": top_k,
                                "embedding_model": embedding_model,
                            },
                            headers={"Authorization": f"Bearer {st.session_state.token}"},
                            timeout=10,
                        )
                        if resp.status_code == 200:
                            st.success("Custom configuration saved!")
                            st.rerun()
                        else:
                            detail = resp.json().get("detail", resp.text)
                            st.error(f"Failed: {detail}")
                    except Exception as e:
                        st.error(f"Error: {e}")
                else:
                    st.warning("Please log in first")

        # Show active config
        if st.session_state.token:
            try:
                resp = requests.get(
                    f"{API_BASE}/rag/config",
                    headers={"Authorization": f"Bearer {st.session_state.token}"},
                    timeout=5,
                )
                if resp.status_code == 200:
                    cfg = resp.json().get("config", {})
                    with st.expander("📊 Active Configuration"):
                        st.markdown(f"**{cfg.get('config_name', 'Balanced')}** ({cfg.get('config_type', 'template')})")
                        st.markdown(f"Chunk: {cfg.get('chunk_size', 512)} · Overlap: {cfg.get('overlap_size', 64)} · Top-K: {cfg.get('top_k', 5)}")
            except Exception:
                pass

        st.divider()

        # --- Cloud Storage ---
        st.subheader("☁️ Cloud Storage")

        # Show connected services
        if st.session_state.token:
            try:
                svc_resp = requests.get(
                    f"{API_BASE}/cloud/services",
                    headers={"Authorization": f"Bearer {st.session_state.token}"},
                    timeout=5,
                )
                connected = svc_resp.json().get("services", []) if svc_resp.status_code == 200 else []
            except Exception:
                connected = []

            if connected:
                for svc in connected:
                    with st.expander(f"✅ {svc.get('display_name', svc['service_name'])}"):
                        st.caption(f"ID: {svc['id']} · Since: {svc.get('created_at', '')[:10]}")

                        # File browser
                        browse_path = st.text_input("Browse path", value="/", key=f"browse_{svc['id']}")
                        if st.button("Browse", key=f"btn_browse_{svc['id']}"):
                            try:
                                files_resp = requests.get(
                                    f"{API_BASE}/cloud/{svc['id']}/files",
                                    params={"folder_path": browse_path},
                                    headers={"Authorization": f"Bearer {st.session_state.token}"},
                                    timeout=10,
                                )
                                if files_resp.status_code == 200:
                                    file_list = files_resp.json().get("files", [])
                                    for fi in file_list[:20]:
                                        icon = "📁" if fi.get("is_folder") else "📄"
                                        st.text(f"{icon} {fi['name']}  ({fi.get('file_type', '')})")
                                else:
                                    st.error("Failed to list files")
                            except Exception as e:
                                st.error(f"Error: {e}")

                        # Index folder
                        idx_path = st.text_input("Index folder", value="/", key=f"idx_{svc['id']}")
                        if st.button("Index Folder", key=f"btn_idx_{svc['id']}"):
                            try:
                                idx_resp = requests.post(
                                    f"{API_BASE}/cloud/{svc['id']}/index-folder",
                                    json={"folder_path": idx_path, "recursive": True},
                                    headers={"Authorization": f"Bearer {st.session_state.token}"},
                                    timeout=60,
                                )
                                if idx_resp.status_code == 200:
                                    data = idx_resp.json()
                                    st.success(f"Indexed {len(data.get('results', []))} files")
                                else:
                                    st.error(f"Failed: {idx_resp.text}")
                            except Exception as e:
                                st.error(f"Error: {e}")

                        # Disconnect
                        if st.button("Disconnect", key=f"disc_{svc['id']}"):
                            try:
                                requests.delete(
                                    f"{API_BASE}/cloud/disconnect/{svc['id']}",
                                    headers={"Authorization": f"Bearer {st.session_state.token}"},
                                    timeout=5,
                                )
                                st.rerun()
                            except Exception:
                                pass

            # Connect new service
            with st.expander("➕ Connect New Service"):
                cloud_type = st.selectbox(
                    "Service",
                    ["local", "s3", "azure_blob", "google_drive", "onedrive", "dropbox"],
                    format_func=lambda x: {"local": "📁 Local Filesystem", "s3": "☁️ AWS S3",
                                           "azure_blob": "🔷 Azure Blob Storage",
                                           "google_drive": "📂 Google Drive",
                                           "onedrive": "📘 Microsoft OneDrive",
                                           "dropbox": "📦 Dropbox"}.get(x, x),
                    key="cloud_svc_type",
                )

                if cloud_type == "local":
                    local_path = st.text_input("Folder path", placeholder="/Users/you/Documents", key="local_path")
                    if st.button("Connect Local Folder", key="connect_local_folder"):
                        if local_path:
                            try:
                                resp = requests.post(
                                    f"{API_BASE}/cloud/connect",
                                    json={"service_name": "local", "credentials": {"path": local_path},
                                          "display_name": f"Local: {os.path.basename(local_path)}"},
                                    headers={"Authorization": f"Bearer {st.session_state.token}"},
                                    timeout=10,
                                )
                                if resp.status_code == 200:
                                    st.success("Connected!")
                                    st.rerun()
                                else:
                                    st.error(resp.json().get("detail", "Failed"))
                            except Exception as e:
                                st.error(f"Error: {e}")

                elif cloud_type == "s3":
                    s3_key = st.text_input("Access Key ID", key="s3_key")
                    s3_secret = st.text_input("Secret Access Key", type="password", key="s3_secret")
                    s3_bucket = st.text_input("Bucket Name", key="s3_bucket")
                    s3_region = st.text_input("Region", value="us-east-1", key="s3_region")
                    if st.button("Connect S3", key="connect_s3"):
                        if all([s3_key, s3_secret, s3_bucket]):
                            try:
                                resp = requests.post(
                                    f"{API_BASE}/cloud/connect",
                                    json={"service_name": "s3",
                                          "credentials": {"access_key": s3_key, "secret_key": s3_secret,
                                                          "bucket": s3_bucket, "region": s3_region},
                                          "display_name": f"S3: {s3_bucket}"},
                                    headers={"Authorization": f"Bearer {st.session_state.token}"},
                                    timeout=15,
                                )
                                if resp.status_code == 200:
                                    st.success("Connected to S3!")
                                    st.rerun()
                                else:
                                    st.error(resp.json().get("detail", "Failed"))
                            except Exception as e:
                                st.error(f"Error: {e}")
                        else:
                            st.warning("Please fill all S3 fields")

                elif cloud_type == "azure_blob":
                    az_auth = st.radio("Auth Method", ["Connection String", "Account Key"], key="az_auth", horizontal=True)
                    az_container = st.text_input("Container Name", key="az_container")
                    if az_auth == "Connection String":
                        az_conn_str = st.text_input("Connection String", type="password", key="az_conn_str")
                        az_creds = {"connection_string": az_conn_str, "container": az_container}
                        can_connect = bool(az_conn_str and az_container)
                    else:
                        az_acct = st.text_input("Account Name", key="az_acct")
                        az_key = st.text_input("Account Key", type="password", key="az_key")
                        az_creds = {"account_name": az_acct, "account_key": az_key, "container": az_container}
                        can_connect = bool(az_acct and az_key and az_container)
                    if st.button("Connect Azure Blob", key="connect_azure"):
                        if can_connect:
                            try:
                                resp = requests.post(
                                    f"{API_BASE}/cloud/connect",
                                    json={"service_name": "azure_blob",
                                          "credentials": az_creds,
                                          "display_name": f"Azure: {az_container}"},
                                    headers={"Authorization": f"Bearer {st.session_state.token}"},
                                    timeout=15,
                                )
                                if resp.status_code == 200:
                                    st.success("Connected to Azure Blob!")
                                    st.rerun()
                                else:
                                    st.error(resp.json().get("detail", "Failed"))
                            except Exception as e:
                                st.error(f"Error: {e}")
                        else:
                            st.warning("Please fill all required Azure fields")

                elif cloud_type == "google_drive":
                    gd_token = st.text_input("Access Token", type="password", key="gd_token")
                    gd_refresh = st.text_input("Refresh Token (optional)", type="password", key="gd_refresh")
                    gd_client_id = st.text_input("Client ID (optional)", key="gd_client_id")
                    gd_client_secret = st.text_input("Client Secret (optional)", type="password", key="gd_client_secret")
                    st.caption("💡 Provide a valid OAuth2 access token from Google Cloud Console. Add refresh token + client credentials for auto-renewal.")
                    if st.button("Connect Google Drive", key="connect_gdrive"):
                        if gd_token:
                            try:
                                creds = {"access_token": gd_token}
                                if gd_refresh:
                                    creds["refresh_token"] = gd_refresh
                                if gd_client_id:
                                    creds["client_id"] = gd_client_id
                                if gd_client_secret:
                                    creds["client_secret"] = gd_client_secret
                                resp = requests.post(
                                    f"{API_BASE}/cloud/connect",
                                    json={"service_name": "google_drive", "credentials": creds,
                                          "display_name": "Google Drive"},
                                    headers={"Authorization": f"Bearer {st.session_state.token}"},
                                    timeout=15,
                                )
                                if resp.status_code == 200:
                                    st.success("Connected to Google Drive!")
                                    st.rerun()
                                else:
                                    st.error(resp.json().get("detail", "Failed"))
                            except Exception as e:
                                st.error(f"Error: {e}")
                        else:
                            st.warning("Access token is required")

                elif cloud_type == "onedrive":
                    od_auth = st.radio("Auth Method", ["Access Token", "Client Credentials"], key="od_auth", horizontal=True)
                    if od_auth == "Access Token":
                        od_token = st.text_input("Access Token", type="password", key="od_token")
                        od_creds = {"access_token": od_token}
                        can_connect_od = bool(od_token)
                    else:
                        od_client_id = st.text_input("Client ID", key="od_client_id")
                        od_client_secret = st.text_input("Client Secret", type="password", key="od_client_secret")
                        od_refresh = st.text_input("Refresh Token", type="password", key="od_refresh")
                        od_tenant = st.text_input("Tenant ID", value="common", key="od_tenant")
                        od_creds = {"client_id": od_client_id, "client_secret": od_client_secret,
                                    "refresh_token": od_refresh, "tenant_id": od_tenant}
                        can_connect_od = bool(od_client_id and od_client_secret and od_refresh)
                    st.caption("💡 Requires an Azure AD App Registration with Microsoft Graph Files.Read permissions.")
                    if st.button("Connect OneDrive", key="connect_onedrive"):
                        if can_connect_od:
                            try:
                                resp = requests.post(
                                    f"{API_BASE}/cloud/connect",
                                    json={"service_name": "onedrive", "credentials": od_creds,
                                          "display_name": "OneDrive"},
                                    headers={"Authorization": f"Bearer {st.session_state.token}"},
                                    timeout=15,
                                )
                                if resp.status_code == 200:
                                    st.success("Connected to OneDrive!")
                                    st.rerun()
                                else:
                                    st.error(resp.json().get("detail", "Failed"))
                            except Exception as e:
                                st.error(f"Error: {e}")
                        else:
                            st.warning("Please fill all required fields")

                elif cloud_type == "dropbox":
                    db_auth = st.radio("Auth Method", ["Access Token", "App Credentials"], key="db_auth", horizontal=True)
                    if db_auth == "Access Token":
                        db_token = st.text_input("Access Token", type="password", key="db_token")
                        db_creds = {"access_token": db_token}
                        can_connect_db = bool(db_token)
                    else:
                        db_app_key = st.text_input("App Key", key="db_app_key")
                        db_app_secret = st.text_input("App Secret", type="password", key="db_app_secret")
                        db_refresh = st.text_input("Refresh Token", type="password", key="db_refresh")
                        db_creds = {"app_key": db_app_key, "app_secret": db_app_secret,
                                    "refresh_token": db_refresh}
                        can_connect_db = bool(db_app_key and db_app_secret and db_refresh)
                    st.caption("💡 Create a Dropbox App at dropbox.com/developers and generate an access token.")
                    if st.button("Connect Dropbox", key="connect_dropbox"):
                        if can_connect_db:
                            try:
                                resp = requests.post(
                                    f"{API_BASE}/cloud/connect",
                                    json={"service_name": "dropbox", "credentials": db_creds,
                                          "display_name": "Dropbox"},
                                    headers={"Authorization": f"Bearer {st.session_state.token}"},
                                    timeout=15,
                                )
                                if resp.status_code == 200:
                                    st.success("Connected to Dropbox!")
                                    st.rerun()
                                else:
                                    st.error(resp.json().get("detail", "Failed"))
                            except Exception as e:
                                st.error(f"Error: {e}")
                        else:
                            st.warning("Please fill all required fields")


# ===================== MAIN CONTENT =====================
if st.session_state.token is None:
    # ---------- NOT LOGGED IN: Welcome + Auth ----------
    st.title("🤖 RAPID")
    st.caption("RAG Application for Private Instant Deployment")
    st.markdown("Upload documents and chat with your data using advanced AI.")

    st.divider()

    tab_login, tab_register = st.tabs(["Login", "Register"])

    with tab_login:
        with st.form("login_form"):
            login_user = st.text_input("Username", key="login_user")
            login_pass = st.text_input("Password", type="password", key="login_pass")
            submitted = st.form_submit_button("Login")
            if submitted:
                if login_user and login_pass:
                    ok, err = _authenticate(login_user, login_pass)
                    if ok:
                        st.rerun()
                    else:
                        st.error(err)
                else:
                    st.warning("Please enter username and password")

    with tab_register:
        with st.form("register_form"):
            reg_user = st.text_input("Username", key="reg_user")
            reg_pass = st.text_input("Password", type="password", key="reg_pass")
            submitted = st.form_submit_button("Register")
            if submitted:
                if reg_user and reg_pass:
                    ok, err = _register(reg_user, reg_pass)
                    if ok:
                        st.success("Registration successful! Please switch to the Login tab.")
                    else:
                        st.error(err)
                else:
                    st.warning("Please fill in all fields")

else:
    # ---------- LOGGED IN: Main ----------
    st.title("🤖 RAPID")

    if st.session_state.get("page", "Chat") == "Admin" and st.session_state.role == "admin":
        st.subheader("Admin Dashboard")
        tabs = st.tabs(["Users", "Groups", "Tokens"])
        headers = {"Authorization": f"Bearer {st.session_state.token}"}

        with tabs[0]:
            st.markdown("### Users")
            col1, col2 = st.columns(2)
            with col1:
                with st.form("create_user_form"):
                    new_username = st.text_input("Username")
                    new_password = st.text_input("Password", type="password")
                    new_role = st.selectbox("Role", ["user", "manager", "admin"])
                    submitted = st.form_submit_button("Create User")
                    if submitted:
                        resp = requests.post(
                            f"{API_BASE}/api/admin/users",
                            json={
                                "username": new_username,
                                "password": new_password,
                                "role": new_role,
                            },
                            headers=headers,
                            timeout=10,
                        )
                        if resp.status_code == 200:
                            st.success("User created")
                        else:
                            st.error(resp.json().get("detail", "Failed"))
            with col2:
                if st.button("Refresh Users"):
                    pass
            try:
                resp = requests.get(f"{API_BASE}/api/admin/users", headers=headers, timeout=10)
                if resp.status_code == 200:
                    st.dataframe(resp.json().get("users", []))
            except Exception as e:
                st.error(f"Error: {e}")

        with tabs[1]:
            st.markdown("### Groups")
            with st.form("create_group_form"):
                group_name = st.text_input("Group Name")
                group_desc = st.text_input("Description")
                submitted = st.form_submit_button("Create Group")
                if submitted:
                    resp = requests.post(
                        f"{API_BASE}/api/groups",
                        json={"group_name": group_name, "description": group_desc},
                        headers=headers,
                        timeout=10,
                    )
                    if resp.status_code == 200:
                        st.success("Group created")
                    else:
                        st.error(resp.json().get("detail", "Failed"))
            try:
                resp = requests.get(f"{API_BASE}/api/groups", headers=headers, timeout=10)
                if resp.status_code == 200:
                    st.dataframe(resp.json().get("groups", []))
            except Exception as e:
                st.error(f"Error: {e}")

        with tabs[2]:
            st.markdown("### API Tokens")
            with st.form("create_token_form"):
                service_type = st.text_input("Service Type")
                token_name = st.text_input("Token Name")
                token_value = st.text_input("Token", type="password")
                submitted = st.form_submit_button("Add Token")
                if submitted:
                    resp = requests.post(
                        f"{API_BASE}/api/admin/tokens",
                        json={
                            "service_type": service_type,
                            "token_name": token_name,
                            "token": token_value,
                        },
                        headers=headers,
                        timeout=10,
                    )
                    if resp.status_code == 200:
                        st.success("Token added")
                    else:
                        st.error(resp.json().get("detail", "Failed"))
            try:
                resp = requests.get(f"{API_BASE}/api/admin/tokens", headers=headers, timeout=10)
                if resp.status_code == 200:
                    st.dataframe(resp.json().get("tokens", []))
            except Exception as e:
                st.error(f"Error: {e}")

    else:
        # ---------- Chat Interface ----------

        # Context bar: show what data sources are active
        active_sources = []
        if st.session_state.uploaded_files:
            active_sources.append(f"📄 {len(st.session_state.uploaded_files)} document(s)")
        if st.session_state.active_db_connections:
            for c in st.session_state.active_db_connections:
                active_sources.append(f"🗄️ {c['conn_id']}")
        if active_sources:
            st.caption("**Active data sources:** " + " · ".join(active_sources))

        # Conversation management row
        col_conv, col_new = st.columns([4, 1])
        with col_new:
            if st.button("+ New Chat", use_container_width=True):
                try:
                    r = requests.post(
                        f"{API_BASE}/api/conversations",
                        json={"title": "Chat"},
                        headers={"Authorization": f"Bearer {st.session_state.token}"},
                        timeout=10,
                    )
                    if r.status_code == 200:
                        st.session_state.conversation_id = r.json()["conversation_id"]
                        st.session_state.messages = []
                        _save_session()
                        st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

        # Display chat history
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                # Show sources if stored
                if msg.get("sources"):
                    with st.expander("Sources", expanded=False):
                        for src in msg["sources"]:
                            if isinstance(src, dict):
                                st.caption(f"📄 {src.get('filename', 'unknown')} — chunk {src.get('chunk_id', '')}")
                            else:
                                st.caption(str(src))

        # Chat input
        has_data = bool(st.session_state.uploaded_files or st.session_state.active_db_connections)
        placeholder = "Ask a question about your documents or database..." if has_data else "Upload a document or connect a database to get started..."

        if prompt := st.chat_input(placeholder):
            if not has_data:
                st.warning("Please upload a document or connect a database first.")
            else:
                # Show user message
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)

                # Ensure we have a conversation
                if not st.session_state.conversation_id:
                    try:
                        r = requests.post(
                            f"{API_BASE}/api/conversations",
                            json={"title": "Chat"},
                            headers={"Authorization": f"Bearer {st.session_state.token}"},
                            timeout=10,
                        )
                        if r.status_code == 200:
                            st.session_state.conversation_id = r.json()["conversation_id"]
                    except Exception:
                        pass

                # Stream response via conversation API
                with st.chat_message("assistant"):
                    response_placeholder = st.empty()
                    full_response = ""
                    sources = []

                    try:
                        conv_id = st.session_state.conversation_id
                        url = f"{API_BASE}/api/conversations/{conv_id}/messages" if conv_id else f"{API_BASE}/query"
                        headers = {"Authorization": f"Bearer {st.session_state.token}"}

                        if conv_id:
                            with requests.post(
                                url,
                                json={"message": prompt, "stream": True},
                                headers=headers,
                                stream=True,
                                timeout=120,
                            ) as resp:
                                if resp.status_code == 401:
                                    st.error("Session expired. Please login again.")
                                    _clear_session()
                                    st.rerun()
                                elif resp.status_code == 429:
                                    st.warning("Rate limit exceeded. Please wait.")
                                elif resp.status_code == 200:
                                    import json as _json
                                    for line in resp.iter_lines():
                                        if not line:
                                            continue
                                        line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                                        if line_str.startswith("data: "):
                                            payload_str = line_str[6:]
                                            try:
                                                payload = _json.loads(payload_str)
                                                if payload.get("done"):
                                                    sources = payload.get("sources", [])
                                                elif "token" in payload:
                                                    full_response += payload["token"]
                                                    response_placeholder.markdown(full_response + "▌")
                                            except _json.JSONDecodeError:
                                                full_response += payload_str
                                                response_placeholder.markdown(full_response + "▌")
                                    response_placeholder.markdown(full_response)
                                else:
                                    err = resp.json().get("detail", "Query failed")
                                    full_response = f"Error: {err}"
                                    response_placeholder.markdown(full_response)
                        else:
                            # Fallback to /query if no conversation
                            resp = requests.post(
                                f"{API_BASE}/query",
                                json={"query": prompt},
                                headers=headers,
                                timeout=120,
                            )
                            if resp.status_code == 200:
                                result = resp.json()
                                full_response = result.get("answer", "No answer")
                                sources = result.get("sources", [])
                                response_placeholder.markdown(full_response)
                            else:
                                full_response = f"Error: {resp.json().get('detail', 'Query failed')}"
                                response_placeholder.markdown(full_response)

                    except requests.exceptions.ConnectionError:
                        full_response = "Cannot connect to the API server. Is it running?"
                        response_placeholder.error(full_response)
                    except Exception as e:
                        full_response = f"Error: {e}"
                        response_placeholder.error(full_response)

                    # Show sources
                    if sources:
                        with st.expander("Sources", expanded=False):
                            for src in sources:
                                if isinstance(src, dict):
                                    st.caption(f"📄 {src.get('filename', 'unknown')} — chunk {src.get('chunk_id', '')}")
                                else:
                                    st.caption(str(src))

                    # Append to local messages
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": full_response,
                        "sources": sources,
                    })

                _save_session()
