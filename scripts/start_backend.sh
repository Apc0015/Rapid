#!/usr/bin/env bash
set -euo pipefail

if [ -d ".venv" ]; then
  # Activate virtualenv if present
  # shellcheck disable=SC1091
  . .venv/bin/activate
else
  echo "Virtualenv not found. Run 'make venv' or 'make install' first."
fi

exec uvicorn rapid.main:app --reload --host 127.0.0.1 --port 8000
