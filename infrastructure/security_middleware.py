"""HTTP security headers, request correlation, size limits, and timing."""
from __future__ import annotations

import os
import re
import time
import uuid

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from infrastructure.runtime_metrics import get_runtime_metrics

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


class RapidSecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-ID", "")
        if not _REQUEST_ID.fullmatch(request_id):
            request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        max_bytes = int(os.getenv("RAPID_MAX_REQUEST_BYTES", str(25 * 1024 * 1024)))
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                too_large = int(content_length) > max_bytes
            except ValueError:
                too_large = True
            if too_large:
                return JSONResponse(status_code=413, content={"detail": "Request body is too large", "request_id": request_id})
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            get_runtime_metrics().observe(request.method, request.url.path, 500, time.perf_counter() - started)
            raise
        route = getattr(request.scope.get("route"), "path", request.url.path)
        duration = time.perf_counter() - started
        get_runtime_metrics().observe(request.method, route, response.status_code, duration)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        response.headers["X-Response-Time"] = f"{duration * 1000:.1f}ms"
        if request.url.path.startswith(("/auth/", "/organization/integrations/oauth/")):
            response.headers["Cache-Control"] = "no-store"
        if os.getenv("RAPID_ENV", "development") == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
