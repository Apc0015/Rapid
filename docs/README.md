# Project Documentation

This `docs/` directory centralises the project's documentation and developer notes.

Contents:

- `README.md` — top-level project overview (kept at repository root)
- `architecture.md` — architectural summary (see below)

## Quick Architecture Summary

The backend service lives in the `rapid/` package (FastAPI). It exposes `/query` and other admin endpoints.

Key components:
- `rapid/main.py` — FastAPI application entrypoint
- `rapid/agents/` — multi-agent layer (Spokesperson, MasterPlanner, Dept agents, Fusion, C-Suite)
- `rapid/infrastructure/` — connectors (LLM client, DB, cloud connectors)
- `rapid/pipelines/` — `rag_pipeline.py`, `db_pipeline.py`

Developer quickstart:

```bash
make install
make run
```
