"""routers/it.py — HTTP surface for the IT department. See orgos/api.py."""

from __future__ import annotations

from orgos.api import build_department_router

router = build_department_router("it")
