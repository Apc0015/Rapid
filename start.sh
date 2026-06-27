#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  RAPID — One-command startup script
#  Usage:  ./start.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e
cd "$(dirname "$0")"

PYTHON=python3
PORT=8000
VENV=".venv"

echo ""
echo "  ██████╗  █████╗ ██████╗ ██╗██████╗ "
echo "  ██╔══██╗██╔══██╗██╔══██╗██║██╔══██╗"
echo "  ██████╔╝███████║██████╔╝██║██║  ██║"
echo "  ██╔══██╗██╔══██║██╔═══╝ ██║██║  ██║"
echo "  ██║  ██║██║  ██║██║     ██║██████╔╝"
echo "  ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═════╝ "
echo "  Departmental Intelligence OS"
echo ""

# ── 1. Check Python ───────────────────────────────────────────────────────────
if ! command -v $PYTHON &>/dev/null; then
  echo "✗ Python 3 not found. Install from https://python.org"
  exit 1
fi
echo "✓ Python: $($PYTHON --version)"

# ── 2. Create virtualenv if missing ──────────────────────────────────────────
if [ ! -d "$VENV" ]; then
  echo "→ Creating virtual environment..."
  $PYTHON -m venv "$VENV"
fi

# ── 3. Activate venv ─────────────────────────────────────────────────────────
source "$VENV/bin/activate"

# ── 4. Install / update dependencies ─────────────────────────────────────────
echo "→ Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "✓ Dependencies ready"

# ── 5. Create runtime directories ────────────────────────────────────────────
mkdir -p data/db data/faiss data/chroma data/documents data/backups logs
echo "✓ Data directories ready"

# ── 6. Check .env ─────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
  echo "→ Creating .env from template..."
  cp .env.example .env
  # Generate a random JWT secret
  JWT=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  sed -i.bak "s/your-strong-random-secret-key-here-minimum-32-characters/$JWT/" .env
  rm -f .env.bak
  echo "✓ .env created with a fresh JWT secret"
else
  echo "✓ .env found"
fi

# ── 7. Kill any process already on port 8000 ─────────────────────────────────
if lsof -ti :$PORT &>/dev/null; then
  echo "→ Stopping existing process on port $PORT..."
  lsof -ti :$PORT | xargs kill -9 2>/dev/null || true
  sleep 1
fi

# ── 8. Start the server ───────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Starting RAPID backend on http://localhost:$PORT"
echo "  API docs: http://localhost:$PORT/docs"
echo ""
echo "  Frontend: open frontend/index.html in your browser"
echo "  OR run:   cd frontend && python3 -m http.server 3000"
echo "  Then:     open http://localhost:3000"
echo ""
echo "  Login credentials:"
echo "    ayush  / Admin@1234  (Admin)"
echo "    alice  / Alice@1234  (Manager)"
echo "    bob    / Bob@1234    (Employee)"
echo ""
echo "  Press Ctrl+C to stop"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Open browser after short delay (macOS)
if command -v open &>/dev/null; then
  (sleep 3 && open "frontend/index.html") &
fi

uvicorn main:app --host 0.0.0.0 --port $PORT --reload --log-level info
