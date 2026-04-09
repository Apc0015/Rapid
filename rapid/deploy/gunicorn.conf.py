"""
deploy/gunicorn.conf.py — Production Gunicorn configuration for RAPID.

Usage:
  gunicorn -c deploy/gunicorn.conf.py main:app

Or with uvicorn workers (recommended for async FastAPI):
  gunicorn -c deploy/gunicorn.conf.py -k uvicorn.workers.UvicornWorker main:app
"""

import multiprocessing
import os

# ── Binding ───────────────────────────────────────────────────────────────────
# Gunicorn listens on a Unix socket; Nginx proxies to it.
# Change to "0.0.0.0:8000" if you want direct TCP (no Nginx).
bind = os.getenv("GUNICORN_BIND", "unix:/tmp/rapid.sock")

# ── Workers ───────────────────────────────────────────────────────────────────
# Recommended: (2 × CPU cores) + 1 for I/O-heavy async apps.
# Override with GUNICORN_WORKERS env var.
workers = int(os.getenv("GUNICORN_WORKERS", str(multiprocessing.cpu_count() * 2 + 1)))

# UvicornWorker gives you full async support (required for FastAPI).
worker_class = "uvicorn.workers.UvicornWorker"

# How many concurrent connections each worker accepts.
worker_connections = int(os.getenv("GUNICORN_CONNECTIONS", "1000"))

# ── Timeouts ──────────────────────────────────────────────────────────────────
# 130s > the 120s query timeout in main.py so Gunicorn doesn't kill mid-query.
timeout           = int(os.getenv("GUNICORN_TIMEOUT", "130"))
graceful_timeout  = 30       # seconds to finish in-flight requests on SIGTERM
keepalive         = 5        # keep-alive on idle connections (seconds)

# ── Process ───────────────────────────────────────────────────────────────────
# Daemonise and write a PID file so systemd / shell scripts can manage it.
daemon      = os.getenv("GUNICORN_DAEMON", "false").lower() == "true"
pidfile     = os.getenv("GUNICORN_PIDFILE", "/tmp/rapid.pid")
user        = os.getenv("GUNICORN_USER", None)
group       = os.getenv("GUNICORN_GROUP", None)
umask       = 0o007           # socket permissions (rwxrwx---)

# ── Logging ───────────────────────────────────────────────────────────────────
loglevel    = os.getenv("GUNICORN_LOGLEVEL", "info")
accesslog   = os.getenv("GUNICORN_ACCESSLOG", "-")   # "-" = stdout
errorlog    = os.getenv("GUNICORN_ERRORLOG",  "-")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(f)s %(a)s %(D)sμs'

# ── Reload (dev only) ─────────────────────────────────────────────────────────
reload      = os.getenv("GUNICORN_RELOAD", "false").lower() == "true"
reload_engine = "auto"

# ── Security ──────────────────────────────────────────────────────────────────
limit_request_line        = 4096    # max URL length
limit_request_fields      = 100     # max HTTP headers
limit_request_field_size  = 8190    # max header value size

# ── Preload app ───────────────────────────────────────────────────────────────
# preload_app = True loads the Python app before forking workers.
# Saves RAM via copy-on-write. Disable if workers need independent state.
preload_app = os.getenv("GUNICORN_PRELOAD", "true").lower() == "true"

# ── Hooks ─────────────────────────────────────────────────────────────────────

def on_starting(server):
    server.log.info("RAPID Gunicorn starting — %d workers", workers)


def worker_exit(server, worker):
    server.log.info("Worker %d exited (pid=%d)", worker.age, worker.pid)


def on_exit(server):
    server.log.info("RAPID Gunicorn stopped")
