"""
RAPID v2 — Streamlit UI  (Claude / ChatGPT-style layout)
"""

import os
import requests
import streamlit as st
from typing import Optional

API_BASE = os.getenv("API_BASE_URL", "http://localhost:3000")

st.set_page_config(
    page_title="RAPID",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
/* ── chrome ── */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1rem !important; padding-bottom: 5rem !important; }

/* ── sidebar shell ── */
[data-testid="stSidebar"] {
    background: #171717 !important;
    border-right: 1px solid #2d2d2d !important;
}
[data-testid="stSidebar"] > div:first-child { padding: 0 !important; }

/* ── sidebar all text ── */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] div { color: #8e8ea0; }

/* ── sidebar buttons (New chat / Sign out) ── */
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    border: 1px solid #3d3d3d !important;
    color: #ececf1 !important;
    text-align: left !important;
    width: 100% !important;
    padding: 8px 14px !important;
    border-radius: 6px !important;
    font-size: 0.88rem !important;
    font-weight: 400 !important;
    box-shadow: none !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: #2a2a2a !important;
    border-color: #555 !important;
}

/* ── nav radio: hide the circle widget ── */
[data-testid="stSidebar"] [data-testid="stRadio"] > div > label > div:first-child {
    display: none !important;
}
/* hide the "Navigation" group label */
[data-testid="stSidebar"] [data-testid="stRadio"] > label {
    display: none !important;
}
/* each nav option label */
[data-testid="stSidebar"] [data-testid="stRadio"] label {
    padding: 9px 14px !important;
    border-radius: 6px !important;
    cursor: pointer !important;
    width: 100% !important;
    font-size: 0.88rem !important;
    color: #9ca3b0 !important;
    gap: 0 !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    background: #252525 !important;
    color: #ececf1 !important;
}
/* selected nav item */
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
    background: #2a2a2a !important;
    color: #ececf1 !important;
}
/* reduce gap between nav items */
[data-testid="stSidebar"] [data-testid="stRadio"] > div {
    gap: 0 !important;
}

/* ── sidebar divider ── */
[data-testid="stSidebar"] hr {
    border-color: #2d2d2d !important;
    margin: 10px 0 !important;
}


/* ── main chat area ── */
.chat-wrap {
    max-width: 700px;
    margin: 0 auto;
}

/* ── welcome / empty state ── */
.welcome {
    text-align: center;
    padding: 5rem 1rem 2rem;
}
.welcome-logo { font-size: 3.5rem; line-height: 1; }
.welcome-title { font-size: 2rem; font-weight: 700; margin: 0.4rem 0 0.2rem; }
.welcome-sub { color: #8e8ea0; font-size: 0.9rem; margin-bottom: 2.5rem; }

/* suggestion cards */
.sugg-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    max-width: 560px;
    margin: 0 auto;
}
.sugg-card {
    background: #1a1d27;
    border: 1px solid #2a2d38;
    border-radius: 10px;
    padding: 14px 16px;
    font-size: 0.83rem;
    color: #c4c7ce;
    text-align: left;
}
.sugg-card b { display: block; color: #ececf1; margin-bottom: 3px; font-size: 0.85rem; }

/* ── confidence bar ── */
.conf-wrap { display: flex; align-items: center; gap: 8px; margin-top: 6px; }
.conf-bg { flex: 0 0 100px; height: 4px; background: #e2e8f0; border-radius: 2px; }
.conf-fill { height: 4px; border-radius: 2px; }
.conf-lbl { font-size: 0.72rem; font-weight: 600; }

/* ── track / badge chips ── */
.chip {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 2px 9px; border-radius: 20px;
    font-size: 0.71rem; font-weight: 600; margin-right: 4px;
}
.chip-rag    { background:#2563eb18; color:#3b82f6; border:1px solid #3b82f644; }
.chip-db     { background:#7c3aed18; color:#8b5cf6; border:1px solid #7c3aed44; }
.chip-web    { background:#64748b18; color:#94a3b8; border:1px solid #64748b44; }
.chip-green  { background:#16a34a18; color:#22c55e; border:1px solid #16a34a44; }
.chip-amber  { background:#d9770618; color:#f59e0b; border:1px solid #d9770644; }
.chip-red    { background:#dc262618; color:#ef4444; border:1px solid #dc262644; }
.chip-gray   { background:#64748b18; color:#94a3b8; border:1px solid #64748b44; }

/* ── source rows ── */
.src { display:flex; gap:8px; padding:6px 0; font-size:0.84rem; border-bottom:1px solid #f1f5f9; }
.src:last-child { border:none; }

/* ── doc type pill ── */
.dpill {
    display:inline-block; padding:1px 7px; border-radius:4px;
    font-size:0.67rem; font-weight:700; text-transform:uppercase;
    letter-spacing:0.05em; margin-left:6px; vertical-align:middle;
}

/* ── status dot ── */
.dot { display:inline-block; width:7px; height:7px; border-radius:50%; margin-right:5px; flex-shrink:0; }
.d-green { background:#16a34a; }
.d-red   { background:#dc2626; }
.d-amber { background:#d97706; }
.d-gray  { background:#9ca3af; }

/* ── panel header ── */
.ph { font-size:1.35rem; font-weight:700; margin-bottom:1.25rem; }

/* ── form cards ── */
.fcard {
    background:#f8f9fb;
    border:1px solid #e2e8f0;
    border-radius:10px;
    padding:1.25rem 1.5rem;
    margin-bottom:1rem;
}

/* ── list row ── */
.lrow {
    display:flex; align-items:center; justify-content:space-between;
    padding:10px 0; border-bottom:1px solid #f1f5f9;
}
.lrow:last-child { border:none; }

/* ── health card ── */
.hcard {
    display:flex; align-items:center; gap:10px;
    padding:10px 14px; border-radius:8px;
    background:#f8f9fb; border:1px solid #e9ecef;
    margin-bottom:8px; font-size:0.88rem;
}
.hcard-name { font-weight:600; }
.hcard-det  { color:#6c757d; font-size:0.78rem; }

/* ── audit table ── */
.atbl { width:100%; border-collapse:collapse; font-size:0.83rem; }
.atbl th { text-align:left; padding:6px 10px; color:#94a3b8; font-weight:600;
           border-bottom:1px solid #e2e8f0; font-size:0.75rem; text-transform:uppercase; }
.atbl td { padding:8px 10px; border-bottom:1px solid #f1f5f9; vertical-align:top; }
.atbl tr:last-child td { border:none; }
.atbl tr:hover td { background:#f8f9fb; }
.ts-cell { color:#94a3b8; font-family:monospace; white-space:nowrap; }
.q-cell  { font-family:monospace; word-break:break-all; color:#374151; }

/* ── governance table ── */
.gtbl { width:100%; border-collapse:collapse; font-size:0.85rem; }
.gtbl th { text-align:left; padding:8px 12px; color:#6b7280;
           border-bottom:1px solid #e5e7eb; font-size:0.75rem; font-weight:600; text-transform:uppercase; }
.gtbl td { padding:8px 12px; border-bottom:1px solid #f3f4f6; }
.gtbl tr:hover td { background:#fafafa; }
.gtbl tr:last-child td { border:none; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Session / API helpers
# ─────────────────────────────────────────────────────────────────────────────

def _token() -> Optional[str]:
    return st.session_state.get("token")

def _user() -> Optional[dict]:
    return st.session_state.get("user")

def _is_admin() -> bool:
    u = _user()
    return u is not None and u.get("role") == "admin"

def _headers() -> dict:
    t = _token()
    return {"Authorization": f"Bearer {t}"} if t else {}

def _api(method: str, path: str, **kwargs) -> requests.Response:
    try:
        return getattr(requests, method)(f"{API_BASE}{path}", headers=_headers(), timeout=60, **kwargs)
    except requests.exceptions.ConnectionError:
        class _Fake:
            status_code = 503
            def json(self): return {"detail": "Cannot connect to API"}
            text = "Cannot connect to API"
        return _Fake()

def _show_error(resp):
    try:
        detail = resp.json().get("detail", resp.text)
    except Exception:
        detail = resp.text
    st.error(f"**{resp.status_code}** — {detail}")

def _page() -> str:
    return st.session_state.get("page", "Chat")

def _set_page(p: str):
    st.session_state["page"] = p


# ─────────────────────────────────────────────────────────────────────────────
# Building blocks
# ─────────────────────────────────────────────────────────────────────────────

_DOC_COLORS = {
    "pdf": ("#ef4444","#fff"), "docx": ("#3b82f6","#fff"), "doc": ("#3b82f6","#fff"),
    "xlsx": ("#22c55e","#fff"), "xls": ("#22c55e","#fff"), "csv": ("#22c55e","#fff"),
    "txt": ("#94a3b8","#fff"), "md": ("#a78bfa","#fff"), "html": ("#f97316","#fff"),
    "json": ("#06b6d4","#fff"), "py": ("#facc15","#1e293b"), "ipynb": ("#f97316","#fff"),
    "tabular": ("#22c55e","#fff"), "code": ("#facc15","#1e293b"),
}

def _dpill(doc_type: str) -> str:
    bg, fg = _DOC_COLORS.get(doc_type.lower(), ("#64748b","#fff"))
    return f'<span class="dpill" style="background:{bg};color:{fg};">{doc_type.upper()}</span>'

def _conf_html(c: float) -> str:
    if c >= 0.75:
        color, label = "#16a34a", "High"
    elif c >= 0.50:
        color, label = "#d97706", "Medium"
    else:
        color, label = "#dc2626", "Low"
    pct = int(c * 100)
    return (
        f'<div class="conf-wrap">'
        f'<div class="conf-bg"><div class="conf-fill" style="width:{pct}%;background:{color};"></div></div>'
        f'<span class="conf-lbl" style="color:{color};">{label} · {pct}%</span>'
        f'</div>'
    )

def _tracks_html(tracks: list) -> str:
    _map = {"rag": ("📄 RAG","chip-rag"), "db": ("🗄️ DB","chip-db"), "web": ("🌐 Web","chip-web")}
    return "".join(
        f'<span class="chip {cls}">{lbl}</span>'
        for t in tracks for lbl, cls in [_map.get(t.lower(), (t,"chip-gray"))]
    )

def _sources_html(sources: list) -> str:
    rows = []
    for s in sources:
        if not isinstance(s, dict):
            continue
        if s.get("url"):
            rows.append(
                f'<div class="src"><span>🌐</span>'
                f'<a href="{s["url"]}" target="_blank" style="color:#3b82f6;">'
                f'{s.get("title", s["url"])[:80]}</a></div>'
            )
        elif s.get("filename"):
            pg = f" · p.{s['page']}" if s.get("page") else ""
            rows.append(f'<div class="src"><span>📄</span><span><b>{s["filename"]}</b>{pg}</span></div>')
        elif s.get("tables_used"):
            tbls = ", ".join(s["tables_used"])
            rows.append(f'<div class="src"><span>🗄️</span><span>Tables: <code>{tbls}</code>'
                        + (f' · {s["row_count"]} rows' if s.get("row_count") else "") + '</span></div>')
    return "\n".join(rows)

def _gov_chip(state: str) -> str:
    _map = {"allowed": ("chip-green","✓ Allowed"), "anonymize": ("chip-amber","~ Anonymize"), "block": ("chip-red","✕ Block")}
    cls, lbl = _map.get(state, ("chip-gray", state))
    return f'<span class="chip {cls}">{lbl}</span>'


# ─────────────────────────────────────────────────────────────────────────────
# Login
# ─────────────────────────────────────────────────────────────────────────────

def _login_page():
    _, col, _ = st.columns([1.4, 1.2, 1.4])
    with col:
        st.markdown("""
        <div style="text-align:center;padding:3rem 0 1.5rem;">
          <div style="font-size:3rem;">⚡</div>
          <div style="font-size:2rem;font-weight:800;margin:4px 0;">RAPID</div>
          <div style="color:#8e8ea0;font-size:0.85rem;margin-bottom:1.8rem;">
            RAG Application for Private Instant Deployment<br>
            The LLM never sees your raw data
          </div>
        </div>
        """, unsafe_allow_html=True)

        tab_in, tab_up = st.tabs(["Sign in", "Create account"])

        with tab_in:
            with st.form("lf"):
                st.text_input("Username", key="li_u", placeholder="username")
                st.text_input("Password", type="password", key="li_p", placeholder="••••••••")
                ok = st.form_submit_button("Sign in →", use_container_width=True, type="primary")
            if ok:
                _do_login(st.session_state.li_u, st.session_state.li_p)

        with tab_up:
            with st.form("rf"):
                st.text_input("Username", key="ru_u")
                st.text_input("Password", type="password", key="ru_p")
                st.text_input("Department", key="ru_d", placeholder="engineering / finance / …")
                st.selectbox("Role", ["viewer", "manager", "admin"], key="ru_r")
                ok = st.form_submit_button("Create account", use_container_width=True, type="primary")
            if ok:
                _do_register(st.session_state.ru_u, st.session_state.ru_p,
                             st.session_state.ru_d, st.session_state.ru_r)


def _do_login(username: str, password: str):
    try:
        r = requests.post(f"{API_BASE}/auth/login",
                          json={"username": username, "password": password}, timeout=10)
        if r.status_code == 200:
            tok = r.json()["token"]
            st.session_state["token"] = tok
            me = requests.get(f"{API_BASE}/me",
                              headers={"Authorization": f"Bearer {tok}"}, timeout=10).json()
            st.session_state["user"] = me
            st.session_state["page"] = "Chat"
            st.rerun()
        else:
            _show_error(r)
    except Exception as e:
        st.error(f"Cannot reach API: {e}")


def _do_register(username, password, dept, role):
    try:
        r = requests.post(f"{API_BASE}/auth/register",
                          json={"username": username, "password": password,
                                "department": dept, "role": role}, timeout=10)
        if r.status_code == 201:
            st.success("Account created — sign in to continue.")
        else:
            _show_error(r)
    except Exception as e:
        st.error(f"Cannot reach API: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

def _sidebar():
    user = _user() or {}

    with st.sidebar:
        # Logo
        st.markdown(
            '<div style="padding:18px 14px 8px;">'
            '<span style="font-size:1.4rem;font-weight:800;color:#ececf1;">⚡ RAPID</span>'
            '</div>',
            unsafe_allow_html=True,
        )

        # New chat button
        if st.button("✏️  New chat", key="new_chat", use_container_width=True):
            st.session_state["messages"] = []
            st.session_state["page"] = "Chat"
            st.rerun()

        st.markdown("<hr>", unsafe_allow_html=True)

        # ── Navigation via radio (reliable, styled via CSS) ──
        _PAGES = ["💬  Chat", "📄  Documents", "🗄️  Database", "🔒  Governance", "⚙️  Settings", "📋  Audit"]
        _LABELS = ["Chat", "Documents", "Database", "Governance", "Settings", "Audit"]

        cur_label = st.session_state.get("page", "Chat")
        cur_idx = _LABELS.index(cur_label) if cur_label in _LABELS else 0

        chosen = st.radio(
            "Navigation",
            _PAGES,
            index=cur_idx,
            key="nav_radio",
            label_visibility="collapsed",
        )
        # Sync page from radio
        chosen_label = _LABELS[_PAGES.index(chosen)]
        if chosen_label != st.session_state.get("page"):
            st.session_state["page"] = chosen_label
            st.rerun()

        st.markdown("<hr>", unsafe_allow_html=True)

        # User info
        role  = user.get("role", "")
        dept  = user.get("department", "")
        uname = user.get("username", "")
        role_color = {"admin": "#ef4444", "manager": "#f59e0b", "viewer": "#8e8ea0"}.get(role, "#8e8ea0")
        st.markdown(
            f'<div style="padding:4px 14px 10px;">'
            f'<div style="font-size:0.88rem;color:#c4c7ce;font-weight:600;">{uname}</div>'
            f'<div style="font-size:0.76rem;color:#6b6b7a;">{dept} · '
            f'<span style="color:{role_color};">{role}</span></div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("Sign out", key="signout", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Chat
# ─────────────────────────────────────────────────────────────────────────────

_SUGGESTIONS = [
    ("Summarize documents", "What are the key insights from my uploaded documents?"),
    ("Query a database", "Show me a summary of the data in the connected database"),
    ("Compare sources", "What does the database say vs what the documents say about this topic?"),
    ("Search the web", "What are the latest developments in [topic]?"),
]


def _chat_panel():
    if "messages" not in st.session_state:
        st.session_state["messages"] = []
    if "recent_qs" not in st.session_state:
        st.session_state["recent_qs"] = []

    msgs = st.session_state["messages"]

    # DB connection (top, compact)
    conn_id = None
    conn_resp = _api("get", "/db/connections")
    if conn_resp.status_code == 200:
        conns = conn_resp.json().get("connections", [])
        if conns:
            with st.expander("🗄️ Database connection", expanded=False):
                sel = st.selectbox("", ["— none —"] + conns, key="chat_conn", label_visibility="collapsed")
                conn_id = None if sel == "— none —" else sel

    # Empty state
    if not msgs:
        st.markdown("""
        <div class="welcome">
          <div class="welcome-logo">⚡</div>
          <div class="welcome-title">What can I help you with?</div>
          <div class="welcome-sub">Ask about your documents, databases, or anything else.</div>
        </div>
        <div class="sugg-grid">
          <div class="sugg-card"><b>Summarize documents</b>What are the key insights from my uploaded documents?</div>
          <div class="sugg-card"><b>Query a database</b>Show me a summary of the connected database</div>
          <div class="sugg-card"><b>Compare sources</b>What do the documents say about this topic?</div>
          <div class="sugg-card"><b>Search the web</b>What are the latest developments in…</div>
        </div>
        """, unsafe_allow_html=True)

    # Message history
    for msg in msgs:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                extra_html = ""
                if msg.get("tracks"):
                    extra_html += _tracks_html(msg["tracks"])
                if extra_html:
                    st.markdown(f'<div style="margin-top:6px;">{extra_html}</div>', unsafe_allow_html=True)
                if msg.get("confidence") is not None:
                    st.markdown(_conf_html(msg["confidence"]), unsafe_allow_html=True)
                if msg.get("sources"):
                    src = _sources_html(msg["sources"])
                    if src:
                        with st.expander(f"Sources ({len(msg['sources'])})", expanded=False):
                            st.markdown(src, unsafe_allow_html=True)

    # Input
    if question := st.chat_input("Message RAPID…"):
        st.session_state["messages"].append({"role": "user", "content": question})
        st.session_state["recent_qs"].append(question)
        if len(st.session_state["recent_qs"]) > 20:
            st.session_state["recent_qs"] = st.session_state["recent_qs"][-20:]

        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner(""):
                resp = _api("post", "/query", json={"question": question, "conn_id": conn_id})

            if resp.status_code == 200:
                data       = resp.json()
                answer     = data["answer"]
                confidence = data.get("confidence", 0.0)
                sources    = data.get("sources", [])
                tracks     = data.get("tracks_used", [])

                st.markdown(answer)

                if tracks:
                    st.markdown(
                        f'<div style="margin-top:6px;">{_tracks_html(tracks)}</div>',
                        unsafe_allow_html=True,
                    )
                st.markdown(_conf_html(confidence), unsafe_allow_html=True)

                if sources:
                    src = _sources_html(sources)
                    if src:
                        with st.expander(f"Sources ({len(sources)})", expanded=False):
                            st.markdown(src, unsafe_allow_html=True)

                st.session_state["messages"].append({
                    "role": "assistant", "content": answer,
                    "confidence": confidence, "sources": sources, "tracks": tracks,
                })
            else:
                _show_error(resp)


# ─────────────────────────────────────────────────────────────────────────────
# Documents
# ─────────────────────────────────────────────────────────────────────────────

def _documents_panel():
    st.markdown('<div class="ph">📄 Documents</div>', unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "Upload a document",
        type=["pdf","docx","txt","md","html","csv","xlsx","xls","json","py","ipynb"],
        key="doc_upload",
        label_visibility="collapsed",
    )
    if uploaded:
        c1, c2 = st.columns([4, 1])
        c1.caption(f"**{uploaded.name}** · {uploaded.size / 1024:.1f} KB")
        if c2.button("Upload & Index", key="do_upload", type="primary"):
            with st.spinner("Indexing…"):
                resp = _api("post", "/documents/upload",
                            files={"file": (uploaded.name, uploaded.getvalue())})
            if resp.status_code == 201:
                d = resp.json()
                st.success(f"✓  **{d['filename']}** — {d['chunks']} chunks indexed")
                st.rerun()
            else:
                _show_error(resp)

    st.divider()

    resp = _api("get", "/documents")
    if resp.status_code != 200:
        _show_error(resp)
        return

    docs = resp.json()
    if not docs:
        st.markdown(
            '<div style="text-align:center;color:#8e8ea0;padding:3rem 0;">'
            'No documents yet.<br>Upload your first document above.</div>',
            unsafe_allow_html=True,
        )
        return

    st.caption(f"{len(docs)} document(s) indexed")

    for doc in docs:
        c1, c2 = st.columns([11, 1])
        with c1:
            pill = _dpill(doc.get("doc_type","?"))
            st.markdown(
                f'**{doc["filename"]}**{pill} '
                f'<span style="color:#8e8ea0;font-size:0.8rem;">'
                f'{doc["chunks"]} chunks · {doc["uploader"]}</span>',
                unsafe_allow_html=True,
            )
            st.caption(doc.get("uploaded_at","")[:19].replace("T", "  "))
        with c2:
            if st.button("🗑", key=f"del_{doc['doc_id']}", help="Delete"):
                r = _api("delete", f"/documents/{doc['doc_id']}")
                if r.status_code == 204:
                    st.rerun()
                else:
                    _show_error(r)
        st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────────────────────────

def _database_panel():
    st.markdown('<div class="ph">🗄️ Database Connections</div>', unsafe_allow_html=True)

    with st.form("db_form"):
        st.text_input("Connection ID", key="db_id", placeholder="analytics_db")
        st.text_input("URI", key="db_uri",
                      placeholder="sqlite:///data/my.db   |   postgresql://user:pass@host/db")
        if st.form_submit_button("Connect", type="primary"):
            r = _api("post", "/db/connect",
                     json={"conn_id": st.session_state.db_id, "uri": st.session_state.db_uri})
            if r.status_code == 200:
                st.success(f"✓ Connected: **{r.json()['conn_id']}**")
                st.rerun()
            else:
                _show_error(r)

    st.divider()

    resp = _api("get", "/db/connections")
    if resp.status_code != 200:
        _show_error(resp)
        return

    conns = resp.json().get("connections", [])
    if not conns:
        st.markdown(
            '<div style="text-align:center;color:#8e8ea0;padding:2rem 0;">No connections yet.</div>',
            unsafe_allow_html=True,
        )
        return

    st.caption(f"{len(conns)} connection(s)")
    for c in conns:
        col1, col2 = st.columns([5, 2])
        col1.markdown(f'🗄️ **{c}**')
        if _is_admin():
            if col2.button("Scan governance", key=f"scan_{c}", use_container_width=True):
                with st.spinner(f"Scanning {c}…"):
                    r = _api("post", f"/governance/columns/scan?conn_id={c}")
                if r.status_code == 200:
                    d = r.json()
                    st.success(f"✓ {d['columns_registered']} new column rules registered.")
                    st.rerun()
                else:
                    _show_error(r)
        st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# Governance
# ─────────────────────────────────────────────────────────────────────────────

def _governance_panel():
    st.markdown('<div class="ph">🔒 Governance</div>', unsafe_allow_html=True)

    if not _is_admin():
        st.warning("Admin access required.")
        return

    tab_rules, tab_policy = st.tabs(["Column Rules", "Policy Upload"])

    with tab_rules:
        resp = _api("get", "/governance/columns")
        if resp.status_code != 200:
            _show_error(resp)
            return

        rules = resp.json().get("rules", [])
        if not rules:
            st.info("No column rules yet. Connect a database and scan its governance schema.")
            return

        from collections import Counter
        counts = Counter(r["default_state"] for r in rules)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total", len(rules))
        m2.metric("Allowed",   counts.get("allowed",   0))
        m3.metric("Anonymize", counts.get("anonymize", 0))
        m4.metric("Blocked",   counts.get("block",     0))

        st.divider()

        tables: dict = {}
        for r in rules:
            tables.setdefault(r["table_name"], []).append(r)

        for tbl, cols in sorted(tables.items()):
            n_blk  = sum(1 for c in cols if c["default_state"] == "block")
            n_anon = sum(1 for c in cols if c["default_state"] == "anonymize")
            chips  = ""
            if n_blk:
                chips += f' <span class="chip chip-red">{n_blk} blocked</span>'
            if n_anon:
                chips += f' <span class="chip chip-amber">{n_anon} anonymized</span>'

            with st.expander(
                f"**{tbl}** &nbsp;·&nbsp; {len(cols)} columns" + (" &nbsp;" + chips if chips else ""),
                expanded=False,
            ):
                # Column header
                h1, h2, h3, h4 = st.columns([3, 2, 2, 1])
                h1.markdown("<small style='color:#9ca3af;'>Column</small>", unsafe_allow_html=True)
                h2.markdown("<small style='color:#9ca3af;'>Current</small>",  unsafe_allow_html=True)
                h3.markdown("<small style='color:#9ca3af;'>Change to</small>", unsafe_allow_html=True)

                for col in sorted(cols, key=lambda x: x["column_name"]):
                    r1, r2, r3, r4 = st.columns([3, 2, 2, 1])
                    r1.code(col["column_name"], language=None)
                    r2.markdown(_gov_chip(col["default_state"]), unsafe_allow_html=True)
                    new_state = r3.selectbox(
                        "s", ["allowed","anonymize","block"],
                        index=["allowed","anonymize","block"].index(col["default_state"]),
                        key=f"gs_{tbl}_{col['column_name']}",
                        label_visibility="collapsed",
                    )
                    if r4.button("Save", key=f"sv_{tbl}_{col['column_name']}"):
                        r = _api("put", f"/governance/columns/{tbl}/{col['column_name']}",
                                 json={"default_state": new_state,
                                       "dept_overrides": col.get("dept_overrides", {}),
                                       "role_overrides": col.get("role_overrides", {})})
                        if r.status_code == 200:
                            st.success(f"Updated `{col['column_name']}` → {new_state}")
                        else:
                            _show_error(r)

    with tab_policy:
        st.caption("Upload a compliance or data policy document to auto-extract column rules.")
        conns = _api("get", "/db/connections")
        conn_list = conns.json().get("connections",[]) if conns.status_code == 200 else []
        conn_id = st.selectbox("Database (for schema context)", ["— none —"] + conn_list, key="pol_conn")
        if conn_id == "— none —":
            conn_id = ""

        pol_file = st.file_uploader("Policy document (.txt / .pdf / .docx)", type=["txt","pdf","docx"],
                                    key="pol_up")
        if pol_file and st.button("Extract Rules", type="primary", key="ext_rules"):
            with st.spinner("Analyzing policy…"):
                r = _api("post", "/governance/policy-upload",
                         files={"file": (pol_file.name, pol_file.getvalue())},
                         data={"conn_id": conn_id})
            if r.status_code == 200:
                res = r.json()
                st.success(f"✓ Found **{res['count']}** proposed rule(s).")
                if res.get("note"):
                    st.info(res["note"])
                for rule in res.get("proposed_rules", []):
                    st.markdown(
                        f'`{rule["table_name"]}.{rule["column_name"]}` → {_gov_chip(rule["default_state"])}',
                        unsafe_allow_html=True,
                    )
            else:
                _show_error(r)


# ─────────────────────────────────────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────────────────────────────────────

def _provider_configurator(prefix: str, providers: list, fetch_endpoint: str, configure_endpoint: str):
    """
    Reusable step-by-step provider configurator.
    prefix: "llm" or "emb" — used to namespace session state keys.
    """
    sk = lambda k: f"_{prefix}_{k}"   # session-state key helper

    # ── Step 1: Provider ────────────────────────────────────────────────────
    st.markdown("**1 · Select provider**")
    provider = st.selectbox(
        "Provider",
        providers,
        key=sk("provider"),
        label_visibility="collapsed",
    )

    # Reset fetched models when provider changes
    if st.session_state.get(sk("last_provider")) != provider:
        for k in ("models", "conn_ok", "conn_err", "api_key_used", "base_url_used"):
            st.session_state.pop(sk(k), None)
        st.session_state[sk("last_provider")] = provider

    # ── Step 2: Credentials ─────────────────────────────────────────────────
    needs_key = provider not in ("ollama", "lmstudio", "sentence-transformers")
    needs_url = provider in ("ollama", "lmstudio")

    st.markdown("**2 · Credentials**")
    api_key = ""
    base_url = ""
    if needs_key:
        api_key = st.text_input(
            "API Key",
            type="password",
            key=sk("api_key_input"),
            placeholder="sk-…  (leave blank to reuse saved key)",
        )
    if needs_url:
        base_url = st.text_input(
            "Base URL",
            key=sk("base_url_input"),
            placeholder="http://localhost:11434" if provider == "ollama" else "http://localhost:1234",
        )

    if provider == "sentence-transformers":
        st.caption("No API key needed — runs locally.")

    # ── Check connection & fetch models ─────────────────────────────────────
    if st.button("Check connection & fetch models", key=sk("fetch_btn"), use_container_width=True):
        with st.spinner("Connecting…"):
            r = _api("post", fetch_endpoint, json={
                "provider": provider,
                "api_key":  api_key  or None,
                "base_url": base_url or None,
            })
        if r.status_code == 200:
            data = r.json()
            if data["status"] == "ok":
                st.session_state[sk("models")]       = data["models"]
                st.session_state[sk("conn_ok")]      = True
                st.session_state[sk("conn_err")]     = ""
                st.session_state[sk("api_key_used")] = api_key
                st.session_state[sk("base_url_used")]= base_url
            else:
                st.session_state[sk("conn_ok")]  = False
                st.session_state[sk("conn_err")] = data.get("message", "Unknown error")
        else:
            st.session_state[sk("conn_ok")]  = False
            st.session_state[sk("conn_err")] = f"HTTP {r.status_code}"

    # ── Connection status ────────────────────────────────────────────────────
    if st.session_state.get(sk("conn_ok")):
        st.markdown(
            '<span class="dot d-green"></span> **Connected**',
            unsafe_allow_html=True,
        )
    elif st.session_state.get(sk("conn_err")):
        st.markdown(
            f'<span class="dot d-red"></span> **Failed:** {st.session_state[sk("conn_err")]}',
            unsafe_allow_html=True,
        )

    # ── Step 3: Model selection ──────────────────────────────────────────────
    models = st.session_state.get(sk("models"), [])
    if not models:
        return

    st.divider()
    st.markdown(f"**3 · Choose model** &nbsp; <span style='color:#64748b;font-size:0.8rem;'>{len(models)} available</span>", unsafe_allow_html=True)

    chosen_model = st.selectbox(
        "Model",
        models,
        key=sk("model_sel"),
        label_visibility="collapsed",
    )

    # ── Step 4: Set as default ───────────────────────────────────────────────
    st.divider()
    st.markdown("**4 · Apply**")
    if st.button("Set as default model", key=sk("set_btn"), type="primary", use_container_width=True):
        payload: dict = {"provider": provider, "model": chosen_model}
        saved_key  = st.session_state.get(sk("api_key_used"))
        saved_base = st.session_state.get(sk("base_url_used"))
        if saved_key:  payload["api_key"]  = saved_key
        if saved_base: payload["base_url"] = saved_base
        r = _api("post", configure_endpoint, json=payload)
        if r.status_code == 200:
            st.success(f"✓ Default set: **{provider}** / `{chosen_model}`")
        else:
            _show_error(r)


def _settings_panel():
    st.markdown('<div class="ph">⚙️ Settings</div>', unsafe_allow_html=True)

    if not _is_admin():
        st.warning("Admin access required.")
        return

    tab_llm, tab_emb, tab_health = st.tabs(["LLM Provider", "Embeddings", "Health"])

    with tab_llm:
        # Current active config
        resp = _api("get", "/llm/providers")
        if resp.status_code == 200:
            info = resp.json()
            ap = info.get("active_provider") or "—"
            am = info.get("active_model")    or "—"
            avail = info.get("available", [])
            dot = "d-green" if ap != "—" else "d-gray"
            chips = "".join(f'<span class="chip chip-gray">{p}</span>' for p in avail)
            st.markdown(
                f'<div style="margin-bottom:1rem;padding:10px 14px;background:#f8f9fb;'
                f'border:1px solid #e2e8f0;border-radius:8px;">'
                f'<span class="dot {dot}"></span>'
                f'<b>Active:</b> {ap} / <code>{am}</code>'
                f'{"<br><small style=\'color:#64748b;\'>Configured: " + chips + "</small>" if avail else ""}'
                f'</div>',
                unsafe_allow_html=True,
            )

        _provider_configurator(
            prefix="llm",
            providers=["openai", "anthropic", "openrouter", "ollama", "lmstudio"],
            fetch_endpoint="/llm/fetch-models",
            configure_endpoint="/llm/configure",
        )

    with tab_emb:
        _provider_configurator(
            prefix="emb",
            providers=["openai", "sentence-transformers", "ollama"],
            fetch_endpoint="/embedding/fetch-models",
            configure_endpoint="/embedding/configure",
        )

    with tab_health:
        if st.button("↻ Refresh"):
            st.rerun()
        resp = _api("get", "/health")
        if resp.status_code != 200:
            _show_error(resp)
            return
        h = resp.json()
        overall = h.get("status","unknown")
        dot = "d-green" if overall == "ok" else "d-red"
        st.markdown(
            f'<div style="margin-bottom:1rem;">'
            f'<span class="dot {dot}"></span><b>Status: {overall.upper()}</b></div>',
            unsafe_allow_html=True,
        )
        comps = h.get("components", {}) or {k: v for k, v in h.items() if k != "status"}
        for name, val in comps.items():
            if isinstance(val, dict):
                ok, detail = val.get("status","ok") == "ok", val.get("detail","")
            else:
                ok, detail = str(val) == "ok", str(val)
            d = "d-green" if ok else "d-red"
            st.markdown(
                f'<div class="hcard"><span class="dot {d}"></span>'
                f'<div><div class="hcard-name">{name}</div>'
                f'<div class="hcard-det">{detail}</div></div></div>',
                unsafe_allow_html=True,
            )


# ─────────────────────────────────────────────────────────────────────────────
# Audit
# ─────────────────────────────────────────────────────────────────────────────

def _audit_panel():
    st.markdown('<div class="ph">📋 Audit Log</div>', unsafe_allow_html=True)

    if not _is_admin():
        st.warning("Admin access required.")
        return

    c1, c2 = st.columns([4, 1])
    n = c1.slider("Entries to show", 10, 500, 100, key="audit_n")
    if c2.button("↻ Refresh", key="ar"):
        st.rerun()

    resp = _api("get", f"/audit/log?n={n}")
    if resp.status_code != 200:
        _show_error(resp)
        return

    entries = resp.json()
    if not entries:
        st.info("Audit log is empty.")
        return

    rows_html = ""
    for e in reversed(entries):
        ts   = e.get("timestamp","")[:19].replace("T"," ")
        user = e.get("username","—")
        q    = (e.get("query") or e.get("raw") or "")[:160]
        rows_html += (
            f'<tr>'
            f'<td class="ts-cell">{ts}</td>'
            f'<td style="color:#6b7280;">{user}</td>'
            f'<td class="q-cell">{q}</td>'
            f'</tr>'
        )

    st.markdown(
        f'<table class="atbl">'
        f'<thead><tr><th>Timestamp</th><th>User</th><th>Query</th></tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if not _token():
        _login_page()
        return

    _sidebar()

    page = _page()
    if page == "Chat":
        _chat_panel()
    elif page == "Documents":
        _documents_panel()
    elif page == "Database":
        _database_panel()
    elif page == "Governance":
        _governance_panel()
    elif page == "Settings":
        _settings_panel()
    elif page == "Audit":
        _audit_panel()


if __name__ == "__main__":
    main()
