"""
routers/cloud_github.py — GitHub repository ingestion endpoints.

Endpoints:
  POST /cloud/github/ingest        — Ingest a repo into company KB or project KB
  GET  /cloud/github/preview       — List files that WOULD be ingested (dry run)
  GET  /cloud/github/rate-limit    — Check GitHub API rate limit status
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from routers.deps import get_current_user, require_admin

router = APIRouter(prefix="/cloud/github", tags=["cloud-github"])
logger = logging.getLogger("rapid.github_router")


# ── Request models ─────────────────────────────────────────────────────────────

class GitHubIngestRequest(BaseModel):
    repo:       str                          # "owner/repo"
    branch:     Optional[str] = None         # defaults to repo's default branch
    dept_tag:   Optional[str] = None         # company KB → tag by department
    project_id: Optional[str] = None         # project KB → scoped to a project
    paths:      Optional[list[str]] = None   # e.g. ["docs/", "README.md"]
    extensions: Optional[list[str]] = None  # e.g. [".md", ".py"] — defaults to all supported


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/ingest")
async def ingest_github_repo(
    req: GitHubIngestRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Ingest a GitHub repository into the knowledge base.

    - dept_tag   → ingests into the company-wide department knowledge base (admin only)
    - project_id → ingests into a specific project's knowledge base (project members)

    For private repos, set GITHUB_TOKEN in your .env.
    Rate limit: 60 req/hr unauthenticated, 5000/hr with token.
    """
    role = current_user.get("role", "")

    # Company KB ingestion is admin-only
    if req.dept_tag and role not in ("admin",):
        raise HTTPException(status_code=403, detail="Only admins can ingest into the company knowledge base")

    # Project KB — any project member can add sources (validated by project membership elsewhere)
    if not req.dept_tag and not req.project_id:
        raise HTTPException(status_code=400, detail="Provide either dept_tag (company KB) or project_id (project KB)")

    from infrastructure.github_connector import ingest_repo

    ext_set = set(req.extensions) if req.extensions else None

    try:
        result = await ingest_repo(
            repo=req.repo,
            branch=req.branch or "main",
            dept_tag=req.dept_tag,
            project_id=req.project_id,
            paths=req.paths,
            extensions=ext_set,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"GitHub ingest failed for {req.repo}")
        raise HTTPException(status_code=502, detail=f"GitHub ingest failed: {str(e)}")

    logger.info(
        f"[github/ingest] user={current_user['sub']} repo={req.repo} "
        f"ingested={result['files_ingested']} chunks={result['chunks_created']}"
    )
    return result


@router.get("/preview")
async def preview_github_repo(
    repo:       str            = Query(..., description="owner/repo"),
    branch:     str            = Query("main"),
    paths:      Optional[str]  = Query(None, description="Comma-separated path prefixes"),
    extensions: Optional[str]  = Query(None, description="Comma-separated extensions, e.g. .md,.py"),
    current_user: dict         = Depends(get_current_user),
):
    """
    Dry-run: list files that would be ingested from this repo without actually ingesting.
    Useful for the admin UI to show a file tree before committing.
    """
    from infrastructure.github_connector import list_repo_files, get_repo_info

    path_list = [p.strip() for p in paths.split(",")] if paths else None
    ext_set   = {e.strip() for e in extensions.split(",")} if extensions else None

    try:
        info  = await get_repo_info(repo)
        files = await list_repo_files(repo, branch, path_list, ext_set)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {str(e)}")

    return {
        "repo":           info["repo"],
        "description":    info["description"],
        "default_branch": info["default_branch"],
        "private":        info["private"],
        "files_found":    len(files),
        "files":          files[:50],   # cap preview at 50 entries
        "truncated":      len(files) > 50,
    }


@router.get("/rate-limit")
async def github_rate_limit(current_user: dict = Depends(get_current_user)):
    """Check current GitHub API rate limit. Shows if GITHUB_TOKEN is active."""
    from infrastructure.github_connector import check_rate_limit
    return await check_rate_limit()
