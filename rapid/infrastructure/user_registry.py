"""
RAPID — User Registry v3
Self-registration + multi-stage approval:
  SUBMITTED → DEPT_REVIEW → DIVISION_REVIEW → ADMIN_REVIEW → APPROVED / REJECTED

Org layers (top → bottom):
  board_member  → read-only, aggregated, all depts
  ceo           → full visibility, all depts
  c_suite       → their division's depts only
  division_head → same scope as c_suite for their division
  manager       → all depts
  dept_head     → their specific department(s)
  employee / sales_rep / finance_analyst / legal_counsel

Files:
  data/user_registry.json   — all requests
  data/users.yaml           — active users (login store)
  data/dept_heads.yaml      — dept → head_user_id mapping
  data/divisions.yaml       — division → {head_user_id, depts}
"""
from __future__ import annotations
import hashlib
import json
import logging
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Optional
import yaml

logger = logging.getLogger(__name__)

REGISTRY_PATH   = Path("data/user_registry.json")
USERS_YAML      = Path("data/users.yaml")
DEPT_HEADS_YAML = Path("data/dept_heads.yaml")
DIVISIONS_YAML  = Path("data/divisions.yaml")

# ── Org constants ─────────────────────────────────────────────────────────────

ALL_ROLES = [
    "employee", "sales_rep", "finance_analyst", "legal_counsel",
    "manager", "dept_head",
    "division_head", "c_suite",
    "ceo", "board_member",
    "admin",
]

ALL_DEPTS = [
    "hr", "finance", "legal", "sales", "marketing",
    "ops", "it", "procurement", "rd", "customer_success",
]

# 5 divisions — each maps to a set of departments
ALL_DIVISIONS = ["commercial", "finance_div", "people", "technology", "operations"]

DIVISION_DEPTS: dict[str, list[str]] = {
    "commercial":   ["sales", "marketing", "customer_success"],
    "finance_div":  ["finance", "procurement"],
    "people":       ["hr", "legal"],
    "technology":   ["it", "rd"],
    "operations":   ["ops"],
}

# C-Suite titles per division (informational — stored in users.yaml)
DIVISION_CSUITE: dict[str, str] = {
    "commercial":   "CMO / CCO",
    "finance_div":  "CFO",
    "people":       "CHRO / CLO",
    "technology":   "CTO / CIO",
    "operations":   "COO",
}

# Reverse map: dept → which division it belongs to
DEPT_DIVISION: dict[str, str] = {
    dept: div
    for div, depts in DIVISION_DEPTS.items()
    for dept in depts
}

# Default departments visible per role (used when no custom assignment exists)
ROLE_DEFAULT_DEPTS: dict[str, list[str]] = {
    "employee":        ["hr", "it"],
    "sales_rep":       ["sales", "marketing", "hr", "it", "customer_success"],
    "finance_analyst": ["finance", "hr", "it", "procurement"],
    "legal_counsel":   ["legal", "hr", "it"],
    "manager":         ALL_DEPTS,
    "dept_head":       ALL_DEPTS,   # scoped by assignment
    "division_head":   ALL_DEPTS,   # scoped by division assignment
    "c_suite":         ALL_DEPTS,   # scoped by division assignment
    "ceo":             ALL_DEPTS,
    "board_member":    ALL_DEPTS,   # aggregated-only (governance enforced)
    "admin":           ALL_DEPTS,
}

# Roles that should only see aggregated summaries (no row-level data)
AGGREGATE_ONLY_ROLES = {"board_member"}

# Roles with unrestricted cross-division access
EXECUTIVE_ROLES = {"ceo", "admin", "board_member"}

# ── Password hashing (PBKDF2-SHA256) ─────────────────────────────────────────

def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    key  = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return f"{salt}${key.hex()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        salt, key = stored.split("$")
        new_key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
        return new_key.hex() == key
    except Exception:
        return False

# ── Persistence helpers ───────────────────────────────────────────────────────

def _load() -> dict:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text())
    return {"requests": {}, "counters": {"req": 0, "usr": 0}}

def _save(data: dict):
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(data, indent=2, default=str))

def _load_users() -> dict:
    return yaml.safe_load(USERS_YAML.read_text()) if USERS_YAML.exists() else {}

def _save_users(users: dict):
    USERS_YAML.parent.mkdir(parents=True, exist_ok=True)
    USERS_YAML.write_text(yaml.dump(users, default_flow_style=False, allow_unicode=True))

def _load_dept_heads() -> dict:
    return yaml.safe_load(DEPT_HEADS_YAML.read_text()) if DEPT_HEADS_YAML.exists() else {}

def _save_dept_heads(data: dict):
    DEPT_HEADS_YAML.parent.mkdir(parents=True, exist_ok=True)
    DEPT_HEADS_YAML.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True))

def _load_divisions() -> dict:
    return yaml.safe_load(DIVISIONS_YAML.read_text()) if DIVISIONS_YAML.exists() else {}

def _save_divisions(data: dict):
    DIVISIONS_YAML.parent.mkdir(parents=True, exist_ok=True)
    DIVISIONS_YAML.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True))

def _next_req_id(data: dict) -> str:
    data["counters"]["req"] += 1
    return f"REQ-{datetime.utcnow().year}-{data['counters']['req']:04d}"

def _next_usr_id(data: dict) -> str:
    data["counters"]["usr"] += 1
    return f"USR-{datetime.utcnow().year}-{data['counters']['usr']:04d}"

def _build_login_key(employee_name: str, existing_users: dict) -> str:
    first = "".join(c for c in employee_name.strip().split()[0].lower() if c.isalnum())
    base  = f"rapid_{first}"
    if base not in existing_users:
        return base
    i = 2
    while f"{base}{i}" in existing_users:
        i += 1
    return f"{base}{i}"

# ── Division management ───────────────────────────────────────────────────────

def get_divisions() -> dict:
    """Returns {division: {user_id, name, title, depts, assigned_at}}"""
    stored = _load_divisions()
    # Always include the static dept mapping
    result = {}
    for div in ALL_DIVISIONS:
        entry = stored.get(div, {})
        result[div] = {
            "division":    div,
            "depts":       DIVISION_DEPTS[div],
            "csuite_title": DIVISION_CSUITE[div],
            "user_id":     entry.get("user_id"),
            "name":        entry.get("name"),
            "assigned_at": entry.get("assigned_at"),
            "assigned_by": entry.get("assigned_by"),
        }
    return result

def set_division_head(division: str, user_id: str, admin_id: str, title: str = "") -> dict:
    """Admin assigns a user as C-Suite / division head."""
    if division not in ALL_DIVISIONS:
        raise ValueError(f"Unknown division: {division}. Valid: {ALL_DIVISIONS}")
    users = _load_users()
    if user_id not in users:
        raise ValueError(f"User '{user_id}' not found")
    divs = _load_divisions()
    divs[division] = {
        "user_id":     user_id,
        "name":        users[user_id].get("name", user_id),
        "title":       title or DIVISION_CSUITE[division],
        "assigned_at": datetime.utcnow().isoformat(),
        "assigned_by": admin_id,
    }
    _save_divisions(divs)
    # Promote user role to c_suite / division_head if needed
    role = users[user_id].get("role", "employee")
    if role not in ("admin", "ceo", "board_member", "c_suite", "division_head"):
        users[user_id]["role"] = "c_suite"
        # Grant all depts in this division
        users[user_id]["permitted_departments"] = DIVISION_DEPTS[division]
        users[user_id]["division"] = division
        _save_users(users)
    logger.info(f"[divisions] {division} head set to {user_id} by {admin_id}")
    return divs[division]

def remove_division_head(division: str, admin_id: str):
    divs = _load_divisions()
    divs.pop(division, None)
    _save_divisions(divs)
    logger.info(f"[divisions] {division} head removed by {admin_id}")

def get_user_division_head_of(user_id: str) -> list[str]:
    """Returns list of divisions this user heads."""
    divs = _load_divisions()
    return [div for div, info in divs.items() if info.get("user_id") == user_id]

def get_depts_for_division(division: str) -> list[str]:
    return DIVISION_DEPTS.get(division, [])

def get_division_for_dept(dept: str) -> Optional[str]:
    return DEPT_DIVISION.get(dept)

# ── Department head management ────────────────────────────────────────────────

def get_dept_heads() -> dict:
    """Returns {dept: {user_id, name, assigned_at, assigned_by}}"""
    return _load_dept_heads()

def set_dept_head(dept: str, user_id: str, admin_id: str) -> dict:
    """Admin assigns a user as head of a department."""
    if dept not in ALL_DEPTS:
        raise ValueError(f"Unknown department: {dept}")
    users = _load_users()
    if user_id not in users:
        raise ValueError(f"User '{user_id}' not found in user store")
    heads = _load_dept_heads()
    heads[dept] = {
        "user_id":     user_id,
        "name":        users[user_id].get("name", user_id),
        "assigned_at": datetime.utcnow().isoformat(),
        "assigned_by": admin_id,
    }
    _save_dept_heads(heads)
    role = users[user_id].get("role", "employee")
    if role not in ("admin", "manager", "dept_head", "c_suite", "division_head", "ceo", "board_member"):
        users[user_id]["role"] = "dept_head"
        _save_users(users)
    logger.info(f"[dept_heads] {dept} head set to {user_id} by {admin_id}")
    return heads[dept]

def remove_dept_head(dept: str, admin_id: str):
    heads = _load_dept_heads()
    heads.pop(dept, None)
    _save_dept_heads(heads)

def get_user_dept_head_of(user_id: str) -> list[str]:
    """Returns list of depts this user is head of."""
    heads = _load_dept_heads()
    return [dept for dept, info in heads.items() if info.get("user_id") == user_id]

# ── Self-registration ─────────────────────────────────────────────────────────

def register_user(
    employee_name: str,
    org_email: str,
    password: str,
    employee_id: str,
    requested_depts: list[str],
    justification: str,
) -> dict:
    """
    Employee self-registers. Request enters DEPT_REVIEW stage.
    Password is hashed immediately — plaintext never stored.

    Approval flow:
      dept_review → division_review → admin_review → approved
    """
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if not org_email or "@" not in org_email:
        raise ValueError("Valid organisation email is required")
    if not requested_depts:
        raise ValueError("Select at least one department")
    for d in requested_depts:
        if d not in ALL_DEPTS:
            raise ValueError(f"Unknown department: {d}")

    data  = _load()
    users = _load_users()

    # Duplicate checks
    for u in users.values():
        if u.get("email", "").lower() == org_email.lower():
            raise ValueError("An account with this email already exists")
    for req in data["requests"].values():
        if req.get("org_email", "").lower() == org_email.lower() \
                and req["stage"] not in ("approved", "rejected"):
            raise ValueError("A pending request for this email already exists")

    req_id = _next_req_id(data)
    heads  = _load_dept_heads()
    divs   = _load_divisions()

    # Per-dept approval slots
    dept_approvals: dict = {}
    for dept in requested_depts:
        head_info = heads.get(dept)
        dept_approvals[dept] = {
            "status":      "pending",
            "head_id":     head_info["user_id"] if head_info else None,
            "projects":    [],
            "notes":       "",
            "reviewed_at": None,
        }

    # Per-division approval slots (derived from requested depts)
    involved_divisions = list({DEPT_DIVISION[d] for d in requested_depts if d in DEPT_DIVISION})
    division_approvals: dict = {}
    for div in involved_divisions:
        div_info = divs.get(div)
        division_approvals[div] = {
            "status":      "pending",
            "head_id":     div_info["user_id"] if div_info else None,
            "notes":       "",
            "reviewed_at": None,
        }

    req = {
        "request_id":          req_id,
        "stage":               "dept_review",
        "employee_name":       employee_name,
        "org_email":           org_email,
        "password_hash":       hash_password(password),
        "employee_id":         employee_id,
        "requested_depts":     requested_depts,
        "involved_divisions":  involved_divisions,
        "justification":       justification,
        "dept_approvals":      dept_approvals,
        "division_approvals":  division_approvals,
        "admin_approval":      {"status": "pending", "notes": "", "reviewed_by": None, "reviewed_at": None},
        "submitted_at":        datetime.utcnow().isoformat(),
        "rapid_user_id":       None,
        "login_key":           None,
    }
    data["requests"][req_id] = req
    _save(data)
    logger.info(f"[register] {req_id} by {org_email} — depts {requested_depts} — divs {involved_divisions}")
    return req

# ── Stage 1: Dept head review ─────────────────────────────────────────────────

def get_dept_requests(dept: str, head_id: str) -> list[dict]:
    """All requests that need this dept head's review."""
    data = _load()
    out  = []
    for req in data["requests"].values():
        if req["stage"] != "dept_review":
            continue
        approval = req["dept_approvals"].get(dept)
        if not approval:
            continue
        if approval.get("head_id") == head_id or approval.get("head_id") is None:
            out.append(req)
    return sorted(out, key=lambda r: r["submitted_at"], reverse=True)

def dept_head_approve(req_id: str, dept: str, head_id: str, projects: list[str], notes: str = "") -> dict:
    """Dept head approves. When ALL depts done → moves to division_review."""
    data = _load()
    req  = data["requests"].get(req_id)
    if not req:
        raise ValueError(f"Request {req_id} not found")
    if req["stage"] != "dept_review":
        raise ValueError(f"Request is not in dept_review stage (current: {req['stage']})")
    if dept not in req["dept_approvals"]:
        raise ValueError(f"Dept '{dept}' not in this request")

    req["dept_approvals"][dept].update({
        "status":      "approved",
        "head_id":     head_id,
        "projects":    projects,
        "notes":       notes,
        "reviewed_at": datetime.utcnow().isoformat(),
    })

    all_done     = all(a["status"] != "pending" for a in req["dept_approvals"].values())
    any_rejected = any(a["status"] == "rejected" for a in req["dept_approvals"].values())

    if any_rejected:
        req["stage"] = "rejected"
        logger.info(f"[dept_review] {req_id} REJECTED by dept head {head_id} ({dept})")
    elif all_done:
        # Move to division review (or skip if no division heads assigned)
        has_division_reviewers = any(
            a.get("head_id") for a in req.get("division_approvals", {}).values()
        )
        req["stage"] = "division_review" if has_division_reviewers else "admin_review"
        logger.info(f"[dept_review] {req_id} all depts done → {req['stage']}")
    else:
        logger.info(f"[dept_review] {req_id} dept {dept} approved, waiting on others")

    data["requests"][req_id] = req
    _save(data)
    return req

def dept_head_reject(req_id: str, dept: str, head_id: str, notes: str = "") -> dict:
    """Dept head rejects — entire request is rejected."""
    data = _load()
    req  = data["requests"].get(req_id)
    if not req:
        raise ValueError(f"Request {req_id} not found")
    req["dept_approvals"][dept].update({
        "status":      "rejected",
        "head_id":     head_id,
        "notes":       notes,
        "reviewed_at": datetime.utcnow().isoformat(),
    })
    req["stage"] = "rejected"
    data["requests"][req_id] = req
    _save(data)
    logger.info(f"[dept_review] {req_id} REJECTED by {head_id} (dept={dept})")
    return req

# ── Stage 2: Division / C-Suite review ───────────────────────────────────────

def get_division_requests(division: str, head_id: str) -> list[dict]:
    """Requests waiting for this division head's review."""
    data = _load()
    out  = []
    for req in data["requests"].values():
        if req["stage"] != "division_review":
            continue
        approval = req.get("division_approvals", {}).get(division)
        if not approval:
            continue
        if approval.get("head_id") == head_id or approval.get("head_id") is None:
            out.append(req)
    return sorted(out, key=lambda r: r["submitted_at"], reverse=True)

def get_all_division_requests_for_user(user_id: str) -> tuple[list[dict], list[str]]:
    """Returns (requests, my_divisions) for a division head."""
    my_divs = get_user_division_head_of(user_id)
    all_reqs: list[dict] = []
    for div in my_divs:
        all_reqs.extend(get_division_requests(div, user_id))
    # deduplicate
    seen: set = set()
    unique = [r for r in all_reqs if not (r["request_id"] in seen or seen.add(r["request_id"]))]
    return unique, my_divs

def division_head_approve(req_id: str, division: str, head_id: str, notes: str = "") -> dict:
    """Division head (C-Suite) approves. When ALL divisions done → admin_review."""
    data = _load()
    req  = data["requests"].get(req_id)
    if not req:
        raise ValueError(f"Request {req_id} not found")
    if req["stage"] != "division_review":
        raise ValueError(f"Request is not in division_review stage (current: {req['stage']})")

    div_approvals = req.get("division_approvals", {})
    if division not in div_approvals:
        raise ValueError(f"Division '{division}' not in this request")

    div_approvals[division].update({
        "status":      "approved",
        "head_id":     head_id,
        "notes":       notes,
        "reviewed_at": datetime.utcnow().isoformat(),
    })
    req["division_approvals"] = div_approvals

    all_done     = all(a["status"] != "pending" for a in div_approvals.values())
    any_rejected = any(a["status"] == "rejected" for a in div_approvals.values())

    if any_rejected:
        req["stage"] = "rejected"
        logger.info(f"[division_review] {req_id} REJECTED by {head_id} ({division})")
    elif all_done:
        req["stage"] = "admin_review"
        logger.info(f"[division_review] {req_id} all divisions approved → admin_review")
    else:
        logger.info(f"[division_review] {req_id} division {division} approved, waiting on others")

    data["requests"][req_id] = req
    _save(data)
    return req

def division_head_reject(req_id: str, division: str, head_id: str, notes: str = "") -> dict:
    """Division head rejects — entire request is rejected."""
    data = _load()
    req  = data["requests"].get(req_id)
    if not req:
        raise ValueError(f"Request {req_id} not found")
    div_approvals = req.get("division_approvals", {})
    if division in div_approvals:
        div_approvals[division].update({
            "status":      "rejected",
            "head_id":     head_id,
            "notes":       notes,
            "reviewed_at": datetime.utcnow().isoformat(),
        })
    req["division_approvals"] = div_approvals
    req["stage"] = "rejected"
    data["requests"][req_id] = req
    _save(data)
    logger.info(f"[division_review] {req_id} REJECTED by {head_id} ({division})")
    return req

# ── Stage 3: Admin final approval ────────────────────────────────────────────

def get_admin_review_requests() -> list[dict]:
    """Requests waiting for admin final approval."""
    data = _load()
    return sorted(
        [r for r in data["requests"].values() if r["stage"] == "admin_review"],
        key=lambda r: r["submitted_at"], reverse=True,
    )

def admin_approve(req_id: str, admin_id: str, notes: str = "") -> dict:
    """Admin final approval — creates the user account."""
    data  = _load()
    req   = data["requests"].get(req_id)
    if not req:
        raise ValueError(f"Request {req_id} not found")
    if req["stage"] != "admin_review":
        raise ValueError(f"Request is not in admin_review stage (current: {req['stage']})")

    users     = _load_users()
    rapid_uid = _next_usr_id(data)
    login_key = _build_login_key(req["employee_name"], users)

    permitted_depts: list[str] = []
    project_access:  dict      = {}
    for dept, approval in req["dept_approvals"].items():
        if approval["status"] == "approved":
            permitted_depts.append(dept)
            if approval["projects"]:
                project_access[dept] = approval["projects"]

    users[login_key] = {
        "password_hash":          req["password_hash"],
        "role":                   "employee",
        "name":                   req["employee_name"],
        "email":                  req["org_email"],
        "employee_id":            req["employee_id"],
        "rapid_user_id":          rapid_uid,
        "permitted_departments":  permitted_depts,
        "project_access":         project_access,
        "db_mode_enabled":        False,
        "created_by":             admin_id,
        "created_at":             datetime.utcnow().isoformat(),
    }
    _save_users(users)

    req.update({
        "stage":         "approved",
        "rapid_user_id": rapid_uid,
        "login_key":     login_key,
        "admin_approval": {
            "status":      "approved",
            "reviewed_by": admin_id,
            "reviewed_at": datetime.utcnow().isoformat(),
            "notes":       notes,
        },
    })
    data["requests"][req_id] = req
    _save(data)
    logger.info(f"[admin_approve] {req_id} APPROVED → {rapid_uid} ({login_key})")
    return req

def admin_reject(req_id: str, admin_id: str, notes: str = "") -> dict:
    data = _load()
    req  = data["requests"].get(req_id)
    if not req:
        raise ValueError(f"Request {req_id} not found")
    req.update({
        "stage": "rejected",
        "admin_approval": {
            "status":      "rejected",
            "reviewed_by": admin_id,
            "reviewed_at": datetime.utcnow().isoformat(),
            "notes":       notes,
        },
    })
    data["requests"][req_id] = req
    _save(data)
    logger.info(f"[admin_reject] {req_id} REJECTED by {admin_id}")
    return req

# ── Pending count helpers ─────────────────────────────────────────────────────

def get_pending_count_for_user(user_id: str) -> int:
    """
    Returns the number of requests needing this user's action:
      - admin       → admin_review count
      - c_suite / division_head → division_review count for their divisions
      - dept_head   → dept_review count for their depts
    """
    users = _load_users()
    user  = users.get(user_id, {})
    role  = user.get("role", "employee")

    if role == "admin":
        return len(get_admin_review_requests())

    if role in ("c_suite", "division_head"):
        reqs, _ = get_all_division_requests_for_user(user_id)
        return len(reqs)

    my_depts = get_user_dept_head_of(user_id)
    count = 0
    for dept in my_depts:
        count += len(get_dept_requests(dept, user_id))
    return count

# ── User self-service ─────────────────────────────────────────────────────────

def get_user_access(login_key: str) -> dict:
    users = _load_users()
    user  = users.get(login_key)
    if not user:
        raise ValueError(f"User '{login_key}' not found")
    role = user.get("role", "employee")
    division = user.get("division")
    return {
        "login_key":             login_key,
        "name":                  user.get("name", ""),
        "email":                 user.get("email", ""),
        "role":                  role,
        "rapid_user_id":         user.get("rapid_user_id", ""),
        "permitted_departments": user.get("permitted_departments", []),
        "project_access":        user.get("project_access", {}),
        "db_mode_enabled":       user.get("db_mode_enabled", False),
        "division":              division,
        "is_executive":          role in EXECUTIVE_ROLES,
        "aggregate_only":        role in AGGREGATE_ONLY_ROLES,
    }

def set_db_mode(login_key: str, enabled: bool):
    users = _load_users()
    if login_key not in users:
        raise ValueError(f"User '{login_key}' not found")
    users[login_key]["db_mode_enabled"] = enabled
    _save_users(users)

def list_all_requests(stage: str | None = None) -> list[dict]:
    data = _load()
    reqs = list(data["requests"].values())
    if stage:
        reqs = [r for r in reqs if r["stage"] == stage]
    return sorted(reqs, key=lambda r: r["submitted_at"], reverse=True)

def list_portal_users() -> list[dict]:
    users  = _load_users()
    result = []
    for login_key, u in users.items():
        result.append({
            "login_key":             login_key,
            "rapid_user_id":         u.get("rapid_user_id", ""),
            "name":                  u.get("name", login_key),
            "email":                 u.get("email", ""),
            "employee_id":           u.get("employee_id", ""),
            "role":                  u.get("role", "employee"),
            "division":              u.get("division"),
            "permitted_departments": u.get("permitted_departments", []),
            "project_access":        u.get("project_access", {}),
            "db_mode_enabled":       u.get("db_mode_enabled", False),
            "created_at":            u.get("created_at", ""),
        })
    return sorted(result, key=lambda u: u.get("created_at", ""), reverse=True)

def change_password(login_key: str, current_password: str, new_password: str):
    users = _load_users()
    user  = users.get(login_key)
    if not user:
        raise ValueError("User not found")
    if not verify_password(current_password, user.get("password_hash", "")):
        raise ValueError("Current password is incorrect")
    if len(new_password) < 8:
        raise ValueError("New password must be at least 8 characters")
    users[login_key]["password_hash"] = hash_password(new_password)
    _save_users(users)
