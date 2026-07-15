"""Small in-process metrics registry for health and Prometheus scraping."""
from __future__ import annotations

import threading
import time
from collections import Counter


class RuntimeMetrics:
    def __init__(self):
        self.started_at = time.time()
        self._lock = threading.Lock()
        self._requests: Counter[tuple[str, str, int]] = Counter()
        self._duration: Counter[tuple[str, str]] = Counter()

    def observe(self, method: str, route: str, status: int, duration: float) -> None:
        route = route if route.startswith("/") else "unknown"
        with self._lock:
            self._requests[(method, route, status)] += 1
            self._duration[(method, route)] += duration

    def prometheus(self, job_stats: dict[str, int]) -> str:
        with self._lock:
            request_items = list(self._requests.items())
            duration_items = list(self._duration.items())
        lines = [
            "# HELP rapid_uptime_seconds Process uptime in seconds.",
            "# TYPE rapid_uptime_seconds gauge",
            f"rapid_uptime_seconds {max(0, time.time() - self.started_at):.3f}",
            "# HELP rapid_http_requests_total HTTP requests by route and status.",
            "# TYPE rapid_http_requests_total counter",
        ]
        for (method, route, status), count in request_items:
            lines.append(f'rapid_http_requests_total{{method="{method}",route="{route}",status="{status}"}} {count}')
        lines.extend(["# HELP rapid_http_request_duration_seconds_sum Cumulative request duration.", "# TYPE rapid_http_request_duration_seconds_sum counter"])
        for (method, route), duration in duration_items:
            lines.append(f'rapid_http_request_duration_seconds_sum{{method="{method}",route="{route}"}} {duration:.6f}')
        lines.extend(["# HELP rapid_jobs Queue jobs by status.", "# TYPE rapid_jobs gauge"])
        for status, count in job_stats.items():
            lines.append(f'rapid_jobs{{status="{status}"}} {count}')
        return "\n".join(lines) + "\n"


_metrics = RuntimeMetrics()


def get_runtime_metrics() -> RuntimeMetrics:
    return _metrics
