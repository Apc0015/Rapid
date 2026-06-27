"""
tests/conftest.py — Shared pytest configuration and fixtures.
"""

import os
import sys
from pathlib import Path

# ── Ensure 'rapid/' is on the Python path ────────────────────────────────────
# Tests are run from the 'rapid/' directory, but add it explicitly just in case.
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Force test-safe environment variables ────────────────────────────────────
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-only-not-for-production")
os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("JWT_REFRESH_TOKEN_EXPIRE_DAYS",   "7")
os.environ.setdefault("OPENAI_API_KEY",  "test-key-not-real")
os.environ.setdefault("SERPER_API_KEY",  "test-key-not-real")
