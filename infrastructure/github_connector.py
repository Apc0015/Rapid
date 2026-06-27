"""
GitHub connector — ingest a repository's files into RAPID's knowledge base.

Supports:
  - Public repos  (no token needed)
  - Private repos (GITHUB_TOKEN env var — personal access token or fine-grained PAT)

Usage:
  chunks = await ingest_repo(
      repo="owner/repo",
      branch="main",
      dept_tag="engineering",          # company KB dept tag  OR
      project_id="proj_abc123",        # project-scoped KB
      paths=["docs/", "README.md"],    # optional filter (defaults to whole repo)
      extensions=[".md", ".py", ".txt"],
  )

Environment:
  GITHUB_TOKEN   — optional; required for private repos
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("rapid.github")

GITHUB_API = "https://api.github.com"

# File types we can meaningfully ingest
_DEFAULT_EXTENSIONS = {
    ".md", ".txt", ".rst", ".pdf",
    ".py", ".js", ".ts", ".java", ".go", ".rs", ".cpp", ".c", ".cs",
    ".yaml", ".yml", ".json", ".toml", ".ini", ".env.example",
    ".html", ".css", ".sql",
    ".docx",
}

_MAX_FILE_SIZE = 500_000   # 500 KB per file — skip large binaries
_MAX_FILES     = 200       # safety cap per ingest call


def _headers() -> dict:
    token = os.getenv("GITHUB_TOKEN", "")
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


# ── Public API ─────────────────────────────────────────────────────────────────

async def get_repo_info(repo: str) -> dict:
    """Return basic repo metadata (name, description, default_branch, private)."""
    async with httpx.AsyncClient(headers=_headers(), timeout=15) as client:
        res = await client.get(f"{GITHUB_API}/repos/{repo}")
    if res.status_code == 404:
        raise ValueError(f"Repository '{repo}' not found or not accessible")
    if res.status_code == 401:
        raise ValueError("GitHub authentication failed — check GITHUB_TOKEN")
    res.raise_for_status()
    data = res.json()
    return {
        "repo":           data["full_name"],
        "description":    data.get("description") or "",
        "default_branch": data.get("default_branch", "main"),
        "private":        data.get("private", False),
        "url":            data.get("html_url", ""),
        "stars":          data.get("stargazers_count", 0),
        "language":       data.get("language") or "",
    }


async def list_repo_files(
    repo: str,
    branch: str = "main",
    paths: Optional[list[str]] = None,
    extensions: Optional[set[str]] = None,
) -> list[dict]:
    """
    Walk the repo tree and return file metadata for ingestible files.
    Returns list of {path, download_url, size}.
    """
    exts = extensions or _DEFAULT_EXTENSIONS

    async with httpx.AsyncClient(headers=_headers(), timeout=30) as client:
        # Get the full recursive tree in one call
        res = await client.get(
            f"{GITHUB_API}/repos/{repo}/git/trees/{branch}",
            params={"recursive": "1"},
        )
    if res.status_code == 409:
        raise ValueError(f"Repository '{repo}' is empty")
    if res.status_code == 422:
        raise ValueError(f"Tree too large for single call — use paths filter")
    res.raise_for_status()

    tree = res.json().get("tree", [])
    files = []

    for item in tree:
        if item["type"] != "blob":
            continue
        file_path = item["path"]
        size = item.get("size", 0)

        # Apply path filter if given
        if paths:
            if not any(file_path.startswith(p.rstrip("/")) for p in paths):
                continue

        # Extension filter
        suffix = Path(file_path).suffix.lower()
        if suffix not in exts:
            continue

        # Size cap
        if size > _MAX_FILE_SIZE:
            logger.debug(f"Skipping {file_path} — too large ({size} bytes)")
            continue

        files.append({
            "path":         file_path,
            "size":         size,
            "download_url": f"https://raw.githubusercontent.com/{repo}/{branch}/{file_path}",
        })

    return files[:_MAX_FILES]


async def _download_text(url: str) -> str:
    """Download a raw file and return its text content."""
    async with httpx.AsyncClient(headers=_headers(), timeout=20) as client:
        res = await client.get(url)
    res.raise_for_status()
    return res.text


async def ingest_repo(
    repo: str,
    branch: str = "main",
    dept_tag: Optional[str] = None,
    project_id: Optional[str] = None,
    paths: Optional[list[str]] = None,
    extensions: Optional[set[str]] = None,
) -> dict:
    """
    Fetch files from a GitHub repo and ingest them into the knowledge base.

    Exactly one of dept_tag or project_id must be supplied:
      - dept_tag   → company-wide department knowledge base
      - project_id → project-scoped knowledge base

    Returns {repo, branch, files_ingested, chunks_created, skipped}.
    """
    if not dept_tag and not project_id:
        raise ValueError("Supply either dept_tag (company KB) or project_id (project KB)")
    if dept_tag and project_id:
        raise ValueError("Supply dept_tag OR project_id, not both")

    # Verify repo is reachable
    info = await get_repo_info(repo)
    actual_branch = branch or info["default_branch"]

    files = await list_repo_files(repo, actual_branch, paths, extensions)
    if not files:
        return {"repo": repo, "branch": actual_branch, "files_ingested": 0, "chunks_created": 0, "skipped": 0}

    from infrastructure.doc_master import get_doc_master
    doc = get_doc_master()

    total_chunks = 0
    ingested = 0
    skipped = 0

    with tempfile.TemporaryDirectory() as tmp:
        for file_meta in files:
            file_path_str = file_meta["path"]
            try:
                text = await _download_text(file_meta["download_url"])

                # Write to a temp file so doc_master can process it normally
                tmp_path = Path(tmp) / Path(file_path_str).name
                tmp_path.write_text(text, encoding="utf-8", errors="replace")

                tag = dept_tag or f"project_{project_id}"
                chunks = await doc.ingest_document(str(tmp_path), tag)
                total_chunks += chunks
                ingested += 1
                logger.info(f"[github] Ingested {file_path_str} → {chunks} chunks (tag={tag})")

            except Exception as exc:
                logger.warning(f"[github] Skipped {file_path_str}: {exc}")
                skipped += 1

    return {
        "repo":           repo,
        "branch":         actual_branch,
        "files_found":    len(files),
        "files_ingested": ingested,
        "chunks_created": total_chunks,
        "skipped":        skipped,
    }


async def check_rate_limit() -> dict:
    """Return GitHub API rate limit status."""
    async with httpx.AsyncClient(headers=_headers(), timeout=10) as client:
        res = await client.get(f"{GITHUB_API}/rate_limit")
    if res.status_code != 200:
        return {"authenticated": False, "remaining": 60, "limit": 60}
    data = res.json().get("rate", {})
    return {
        "authenticated": bool(os.getenv("GITHUB_TOKEN")),
        "limit":         data.get("limit", 60),
        "remaining":     data.get("remaining", 0),
        "reset_at":      data.get("reset", 0),
    }
