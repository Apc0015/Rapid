"""
Build/refresh the per-department FAISS indexes from data/documents/.

Walks data/documents/<dept>/** and ingests every supported file into that
department's index via DocMaster (same path the folder watcher and upload
API use). Idempotent: sources already present in an index are skipped, so
re-running only picks up new files. Requires Ollama running with the
embedding model pulled (see .env — nomic-embed-text by default).

Usage (from repo root):
    .venv/bin/python3 scripts/build_indexes.py [dept ...]

With no args, all department folders are indexed. `projects/` is excluded —
project files belong to the per-project pipeline, not department RAG.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from infrastructure.doc_master import get_doc_master  # noqa: E402

DOCS_ROOT = Path(__file__).resolve().parent.parent / "data" / "documents"
SUPPORTED = {".txt", ".md", ".pdf", ".docx", ".csv", ".json"}
EXCLUDED_DIRS = {"projects"}


async def build(depts: list[str]) -> int:
    doc = get_doc_master()
    failures = 0
    for dept in depts:
        dept_dir = DOCS_ROOT / dept
        existing = set(doc.list_sources(dept))
        files = sorted(
            p for p in dept_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in SUPPORTED
        )
        print(f"\n[{dept}] {len(files)} file(s), {len(existing)} already indexed")
        for path in files:
            if path.name in existing:
                print(f"  = {path.name} (skipped, already indexed)")
                continue
            try:
                n = await doc.ingest_document(str(path), dept)
                print(f"  + {path.name} → {n} chunks")
            except Exception as e:
                failures += 1
                print(f"  ! {path.name} FAILED: {e}")
        print(f"[{dept}] index now holds {doc.doc_count(dept)} chunks")
    return failures


def main():
    requested = sys.argv[1:]
    available = sorted(
        d.name for d in DOCS_ROOT.iterdir()
        if d.is_dir() and d.name not in EXCLUDED_DIRS
    )
    depts = requested or available
    unknown = [d for d in depts if d not in available]
    if unknown:
        sys.exit(f"Unknown department(s): {unknown}. Available: {available}")
    failures = asyncio.run(build(depts))
    if failures:
        sys.exit(f"\n{failures} file(s) failed to ingest")
    print("\nAll indexes built.")


if __name__ == "__main__":
    main()
