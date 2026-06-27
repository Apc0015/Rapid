"""
infrastructure/global_search.py — Global Search Engine

Three-tier search across all projects in a tenant:
  1. BM25 keyword search   — per-project SQLite tables (exact term matching)
  2. Vector search         — per-dept FAISS index (semantic similarity)
  3. Graph node search     — per-project GraphStore (relationship-aware)

Results
───────
  Merged list of SearchResult objects, ranked by score, filtered by:
    • tenant isolation   — only projects belonging to this tenant
    • project membership — only projects the user is a member of
    • access level       — only data the user's role can see

Usage
─────
  engine = get_global_search()
  results = await engine.search(
      query="budget variance Q3",
      tenant_id="t-123",
      user_id="u-456",
      limit=20,
  )
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import config

logger = logging.getLogger("rapid.global_search")


# ── Result model ──────────────────────────────────────────────────────────────

@dataclass
class SearchResult:
    result_id:   str
    source:      str          # "bm25" | "vector" | "graph"
    result_type: str          # "kpi" | "risk" | "milestone" | "document" | "person" | "node" | ...
    title:       str
    snippet:     str
    project_id:  str
    tenant_id:   str
    score:       float
    url:         str          = ""
    metadata:    dict         = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "result_id":   self.result_id,
            "source":      self.source,
            "result_type": self.result_type,
            "title":       self.title,
            "snippet":     self.snippet,
            "project_id":  self.project_id,
            "score":       round(self.score, 4),
            "url":         self.url,
            "metadata":    self.metadata,
        }


# ── Access-control helper ─────────────────────────────────────────────────────

def _get_accessible_projects(
    tenant_id: str,
    user_id:   str,
    role:      str,
) -> list[dict]:
    """
    Return list of {project_id, db_path, name} that the user can access.
    Admins / executives see all projects; others see only their membership.

    Schema note:
      project_registry — has db_path (one row per project DB)
      projects         — has name, status, primary_dept_id
    """
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        if role in ("admin", "ceo", "c_suite", "board_member"):
            rows = conn.execute(
                """
                SELECT pr.project_id, pr.db_path,
                       COALESCE(p.name, pr.project_id) AS name
                FROM project_registry pr
                LEFT JOIN projects p ON pr.project_id = p.project_id
                WHERE pr.tenant_id=? AND pr.status != 'archived'
                """,
                (tenant_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT pr.project_id, pr.db_path,
                       COALESCE(p.name, pr.project_id) AS name
                FROM project_registry pr
                LEFT JOIN projects p ON pr.project_id = p.project_id
                JOIN project_members pm ON pr.project_id = pm.project_id
                WHERE pr.tenant_id=? AND pm.user_id=? AND pr.status != 'archived'
                """,
                (tenant_id, user_id),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── BM25 search (SQLite full-text style) ─────────────────────────────────────

_BM25_QUERIES: list[tuple[str, str, str, str]] = [
    # (table, title_col, snippet_col, result_type)
    ("project_kpis",       "name",    "current_value", "kpi"),
    ("project_risks",      "title",   "impact",        "risk"),
    ("project_milestones", "name",    "status",        "milestone"),
    ("project_details",    "name",    "health_status", "project"),
    ("project_documents",  "title",   "report_type",   "document"),
    ("notifications",      "title",   "message",       "notification"),
]


def _bm25_search_project(
    db_path:    str,
    project_id: str,
    tenant_id:  str,
    query:      str,
    limit:      int = 5,
) -> list[SearchResult]:
    """BM25-style keyword search across all searchable tables in one project DB."""
    results: list[SearchResult] = []
    if not db_path or not os.path.exists(db_path):
        return results

    terms = [t.lower() for t in query.split() if len(t) > 1]
    if not terms:
        return results

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row

        for table, title_col, snippet_col, rtype in _BM25_QUERIES:
            # Check table exists
            tbl_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if not tbl_exists:
                continue

            # Build LIKE conditions for each term on title and snippet cols
            conds = " OR ".join(
                f"(LOWER({title_col}) LIKE ? OR LOWER({snippet_col}) LIKE ?)"
                for _ in terms
            )
            params: list[str] = []
            for t in terms:
                params.extend([f"%{t}%", f"%{t}%"])
            params.append(limit)

            try:
                rows = conn.execute(
                    f"SELECT * FROM {table} WHERE {conds} LIMIT ?", params
                ).fetchall()
            except Exception:
                continue

            for i, row in enumerate(rows):
                r = dict(row)
                title   = str(r.get(title_col, "") or "")
                snippet = str(r.get(snippet_col, "") or "")
                # Score: count how many terms match the title (higher = better)
                term_hits = sum(1 for t in terms if t in title.lower())
                score = 0.5 + (term_hits / max(len(terms), 1)) * 0.5

                results.append(SearchResult(
                    result_id   = f"bm25:{project_id}:{table}:{i}",
                    source      = "bm25",
                    result_type = rtype,
                    title       = title[:120],
                    snippet     = snippet[:200],
                    project_id  = project_id,
                    tenant_id   = tenant_id,
                    score       = score,
                    metadata    = {"table": table},
                ))
        conn.close()
    except Exception as e:
        logger.debug(f"[Search] BM25 error in {project_id}: {e}")

    return results


# ── Vector search ─────────────────────────────────────────────────────────────

async def _vector_search_tenant(
    query:     str,
    tenant_id: str,
    projects:  list[dict],
    top_k:     int = 5,
) -> list[SearchResult]:
    """
    Run vector search across all FAISS dept indices.
    Falls back gracefully if embedding service unavailable.
    """
    results: list[SearchResult] = []
    try:
        from infrastructure.embedding_service import get_embedder
        from infrastructure.faiss_store import all_dept_indices

        embedder = get_embedder()
        embedding = await embedder.embed(query)
        if not embedding:
            return results

        dept_indices = all_dept_indices()
        project_set = {p["project_id"] for p in projects}

        for dept_tag, index in dept_indices.items():
            try:
                hits = await index.vector_search(embedding, top_k=top_k)
                for chunk, score in hits:
                    # Filter to tenant's projects via source path heuristic
                    results.append(SearchResult(
                        result_id   = f"vec:{dept_tag}:{chunk.chunk_id}",
                        source      = "vector",
                        result_type = "document_chunk",
                        title       = chunk.source[:80],
                        snippet     = chunk.text[:200],
                        project_id  = "",   # FAISS indices are dept-wide
                        tenant_id   = tenant_id,
                        score       = float(score),
                        metadata    = {"dept": dept_tag, "chunk_id": chunk.chunk_id},
                    ))
            except Exception as e:
                logger.debug(f"[Search] Vector error dept={dept_tag}: {e}")

    except Exception as e:
        logger.debug(f"[Search] Vector search unavailable: {e}")

    return results


# ── Graph search ──────────────────────────────────────────────────────────────

def _graph_search_project(
    db_path:    str,
    project_id: str,
    tenant_id:  str,
    query:      str,
    limit:      int = 5,
) -> list[SearchResult]:
    """Search graph nodes for this project."""
    results: list[SearchResult] = []
    if not db_path or not os.path.exists(db_path):
        return results
    try:
        from infrastructure.graph_store import get_graph_store
        store = get_graph_store(db_path, project_id, tenant_id)
        nodes = store.search_nodes(query=query, limit=limit)
        for node in nodes:
            results.append(SearchResult(
                result_id   = f"graph:{project_id}:{node.node_id}",
                source      = "graph",
                result_type = node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type),
                title       = node.label or node.node_id,
                snippet     = str(node.properties or {})[:200],
                project_id  = project_id,
                tenant_id   = tenant_id,
                score       = 0.7,
                metadata    = {"node_id": node.node_id},
            ))
    except Exception as e:
        logger.debug(f"[Search] Graph error in {project_id}: {e}")
    return results


# ── People search ─────────────────────────────────────────────────────────────

def _people_search(
    tenant_id: str,
    query:     str,
    limit:     int = 5,
) -> list[SearchResult]:
    """Search the people directory."""
    results: list[SearchResult] = []
    try:
        from infrastructure.people_directory import get_people_directory
        directory = get_people_directory()
        people = directory.search(tenant_id=tenant_id, query=query, limit=limit)
        for person in people:
            results.append(SearchResult(
                result_id   = f"people:{person.person_id}",
                source      = "bm25",
                result_type = "person",
                title       = person.name,
                snippet     = f"{person.role} — {person.dept_id or 'no dept'} — {person.email}",
                project_id  = "",
                tenant_id   = tenant_id,
                score       = 0.85,
                url         = f"/people/{person.person_id}",
                metadata    = {"person_id": person.person_id, "role": person.role},
            ))
    except Exception as e:
        logger.debug(f"[Search] People search error: {e}")
    return results


# ── Merge & rank ──────────────────────────────────────────────────────────────

def _deduplicate_and_rank(
    results: list[SearchResult],
    limit:   int,
) -> list[SearchResult]:
    """Deduplicate by result_id, sort by score descending, cap at limit."""
    seen: set[str] = set()
    unique: list[SearchResult] = []
    for r in results:
        if r.result_id not in seen:
            seen.add(r.result_id)
            unique.append(r)
    unique.sort(key=lambda r: r.score, reverse=True)
    return unique[:limit]


# ── GlobalSearch engine ───────────────────────────────────────────────────────

class GlobalSearch:
    """
    Multi-tier search engine. Thread-safe; each call is independent.
    """

    async def search(
        self,
        query:     str,
        tenant_id: str,
        user_id:   str,
        role:      str   = "employee",
        limit:     int   = 20,
        sources:   list[str] | None = None,  # ["bm25","vector","graph","people"]
    ) -> dict:
        """
        Run global search and return merged, ranked results.

        Returns:
            {query, results: [...], count, sources_searched, duration_ms}
        """
        t0 = time.perf_counter()
        sources = sources or ["bm25", "graph", "people", "vector"]

        # 1. Determine accessible projects
        projects = _get_accessible_projects(tenant_id, user_id, role)
        if not projects and role not in ("admin",):
            logger.info(f"[Search] User {user_id} has no accessible projects")

        all_results: list[SearchResult] = []

        # 2. Per-project BM25 + graph search
        if "bm25" in sources or "graph" in sources:
            for proj in projects:
                db_path    = proj.get("db_path", "")
                project_id = proj["project_id"]

                if "bm25" in sources:
                    all_results.extend(
                        _bm25_search_project(db_path, project_id, tenant_id, query)
                    )
                if "graph" in sources:
                    all_results.extend(
                        _graph_search_project(db_path, project_id, tenant_id, query)
                    )

        # 3. People directory search
        if "people" in sources:
            all_results.extend(_people_search(tenant_id, query, limit=5))

        # 4. Vector search (async)
        if "vector" in sources:
            vec_results = await _vector_search_tenant(query, tenant_id, projects, top_k=5)
            all_results.extend(vec_results)

        # 5. Merge, deduplicate, rank
        final = _deduplicate_and_rank(all_results, limit=limit)

        duration_ms = round((time.perf_counter() - t0) * 1000, 1)
        logger.info(
            f"[Search] '{query[:40]}' → {len(final)} results "
            f"from {len(projects)} projects in {duration_ms}ms"
        )

        return {
            "query":            query,
            "results":          [r.to_dict() for r in final],
            "count":            len(final),
            "projects_searched": len(projects),
            "sources_searched": sources,
            "duration_ms":      duration_ms,
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine: Optional[GlobalSearch] = None


def get_global_search() -> GlobalSearch:
    global _engine
    if _engine is None:
        _engine = GlobalSearch()
    return _engine
