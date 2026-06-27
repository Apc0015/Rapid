# QA Audit Report — RAPID Auth System
**Date:** 2026-05-24  
**Auditor:** Code QA Auditor (automated)  
**Files Audited:** `routers/auth.py`, `routers/deps.py`, `infrastructure/jwt_manager.py`, `infrastructure/user_registry.py`

---

## Phase 0 — Application Intelligence

### Purpose
RAPID is an enterprise knowledge-management platform. The auth module provides JWT-based authentication (register, login, refresh, logout) for employees across an org hierarchy. Only fully approved, password-authenticated users receive JWTs; only users with valid non-revoked JWTs can access protected resources.

### User Flows
| Flow | Endpoint | Risk |
|------|----------|------|
| Self-Registration | POST /auth/register | password_hash stored in pending JSON before approval |
| Login | POST /auth/login | users.yaml read from disk every request (no cache) |
| Token Refresh | POST /auth/refresh | Refresh token NOT rotated on use |
| Logout | POST /auth/logout | Access token valid 30 min after logout |
| Logout-All | POST /auth/logout-all | Same 30-min access token window |
| Password Change | POST /users/change-password | Redundant double-verification (harmless) |

### Risk Register

| ID | Description | Likelihood | Impact |
|----|-------------|------------|--------|
| R-01 | Default SECRET_KEY "CHANGE_ME_IN_PRODUCTION" | HIGH | **CRITICAL** |
| R-02 | Refresh token not rotated on use | MEDIUM | HIGH |
| R-03 | Access token valid 30 min after logout | HIGH | MEDIUM |
| R-04 | users.yaml read from disk every request | HIGH | MEDIUM |
| R-05 | No password strength rules beyond length | MEDIUM | MEDIUM |
| R-06 | password_hash in pending user_registry.json | MEDIUM | HIGH |
| R-07 | Rate limit only on /auth/login, not /auth/refresh | MEDIUM | MEDIUM |
| R-08 | revoke_refresh_token() silently ignores failures | MEDIUM | MEDIUM |
| R-09 | No max_length on user_id / password fields | LOW | LOW |
| R-10 | Email validated only by "@" presence | LOW | LOW |

---

## Phase 1 — Component Inventory (21 components audited)
See full test file `tests/test_auth_qa.py` for all components and test IDs.

---

## Phase 4 — Coverage Gaps

| Gap | Component | Risk | Description |
|-----|-----------|------|-------------|
| G-01 | login() | HIGH | Rate limit enforcement not tested |
| G-02 | login() | MEDIUM | Whitespace-only user_id behavior |
| G-03 | login() | MEDIUM | Very long inputs (bcrypt DoS) |
| G-04 | refresh_token() | HIGH | Concurrent refresh with same token (race) |
| G-05 | logout() | MEDIUM | DB failure → silent 200 |
| G-06 | change_password | MEDIUM | spokesperson.reload_users() failure |
| G-07 | register_user() | HIGH | Concurrent duplicate email race condition |
| G-08 | register_user() | HIGH | Full approval pipeline end-to-end |
| G-09 | All | MEDIUM | TLS/HTTPS not tested |
| G-10 | get_current_user | LOW | Future iat token (clock-skew) |

---

## Phase 5 — QA Summary

| Metric | Value |
|--------|-------|
| Components Audited | 21 |
| PASS | 1 (JWTManager — pre-existing tests) |
| FAIL | 8 (no tests existed) |
| CANNOT VERIFY | 3 |
| Test Cases Designed | 46 |
| Runnable Tests Generated | 46 |
| Coverage Gaps | 10 |
| CRITICAL Risks | 3 |
| HIGH Risks | 6 |

---

## Top Issues — Fix These First

### 🔴 CRITICAL-1: Default JWT Secret Key (jwt_manager.py:24)
```python
# CURRENT (dangerous)
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE_ME_IN_PRODUCTION")

# FIX
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY or SECRET_KEY == "CHANGE_ME_IN_PRODUCTION":
    raise RuntimeError("JWT_SECRET_KEY env var must be set to a secure random value")
```

### 🔴 CRITICAL-2: Cross-User Logout (auth.py:168–172)
`/auth/logout` does not verify that the submitted refresh token belongs to the authenticated user. User A can revoke User B's sessions.
```python
# FIX — add ownership check in logout():
try:
    payload = jwt.decode(body.refresh_token, SECRET_KEY, algorithms=[ALGORITHM],
                         options={"verify_exp": False})
    if payload.get("sub") != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Cannot revoke another user's token")
except Exception:
    pass  # let revoke handle invalid tokens
```

### 🟠 HIGH: Refresh Token Rotation (auth.py:128–159)
Comment on line 133 already acknowledges: *"The refresh token is NOT rotated."*  
Implement rotation: on each /auth/refresh, revoke the old JTI and issue a new refresh token.

### 🟠 HIGH: Silent Logout Failure (jwt_manager.py:183)
`revoke_refresh_token()` catches all exceptions silently. Add `logger.error(...)` and consider returning failure info to the caller.

---

## Production Readiness
The JWTManager core and bcrypt/PBKDF2 password handling are correct and well-structured. However, CRITICAL-1 (default secret) and CRITICAL-2 (cross-user logout) must be resolved before production deployment. Zero auth endpoint tests existed prior to this audit.

**Verdict: NOT READY for production security-sensitive deployment without fixes to CRITICAL-1 and CRITICAL-2.**
