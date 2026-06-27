# ──────────────────────────────────────────────────────────────────────────────
#  RAPID — Makefile
#  Usage: make <target>
# ──────────────────────────────────────────────────────────────────────────────

.PHONY: help install run dev test lint seed docker-build docker-up docker-down clean

PYTHON  := python3
UVICORN := uvicorn
PORT    := 8000

help:          ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ── Local development ─────────────────────────────────────────────────────────

install:       ## Install Python dependencies
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

run:           ## Start server (production mode)
	$(UVICORN) main:app --host 0.0.0.0 --port $(PORT) --workers 2

dev:           ## Start server with auto-reload (development)
	$(UVICORN) main:app --host 127.0.0.1 --port $(PORT) --reload --log-level debug

# ── Database ──────────────────────────────────────────────────────────────────

seed:          ## Seed the database with sample data
	$(PYTHON) scripts/seed_db.py

# ── Testing ───────────────────────────────────────────────────────────────────

test:          ## Run unit + integration tests
	pytest tests/ -v --tb=short

test-fast:     ## Run tests, stop on first failure
	pytest tests/ -x --tb=short

e2e:           ## Run full end-to-end test suite (requires Ollama)
	$(PYTHON) scripts/run_and_test.py

# ── Code quality ──────────────────────────────────────────────────────────────

lint:          ## Lint with ruff (fast)
	ruff check . --ignore E501

format:        ## Auto-format with ruff
	ruff format .

typecheck:     ## Type-check with mypy
	mypy main.py config.py shared.py --ignore-missing-imports

# ── Docker ────────────────────────────────────────────────────────────────────

docker-build:  ## Build Docker image
	docker build -t rapid:latest .

docker-up:     ## Start services with Docker Compose
	docker-compose up -d

docker-down:   ## Stop Docker Compose services
	docker-compose down

docker-logs:   ## Tail RAPID server logs
	docker-compose logs -f rapid

# ── Housekeeping ──────────────────────────────────────────────────────────────

clean:         ## Remove Python cache and temp files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage

dirs:          ## Create required runtime directories
	mkdir -p data/db data/faiss data/chroma data/documents data/backups logs
