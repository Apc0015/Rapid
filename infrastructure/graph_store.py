"""
infrastructure/graph_store.py — SQLite-backed Knowledge Graph engine.

GraphStore is a lightweight graph database built on top of the project's
existing SQLite file. No Neo4j, no external service — it just adds two
tables (graph_nodes + graph_edges) to the project DB and provides a
clean graph API over them.

Why SQLite as a graph backend?
  - Every project already has its own SQLite DB — zero new infrastructure
  - SQLite is fast for the graph sizes we expect (<100k nodes per project)
  - CTE recursive queries handle multi-hop traversal efficiently
  - Data stays co-located with the project's operational data

API summary:
    store = GraphStore(db_path, project_id)
    store.ensure_tables()

    node = store.add_node(GraphNode(...))
    edge = store.add_edge(GraphEdge(...))

    neighbors = store.get_neighbors(node_id, edge_type=EdgeType.BLOCKS)
    path      = store.find_path(from_id, to_id, max_hops=3)
    subgraph  = store.get_subgraph(node_id, depth=2)
    results   = store.search_nodes(query="TechNova", node_type=NodeType.ENTITY)
    context   = store.get_graph_context(node_ids=[...])
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from infrastructure.graph_schema import (
    GraphNode, GraphEdge,
    NodeType, EdgeType,
    GRAPH_TABLES_SQL,
)

logger = logging.getLogger(__name__)


# ── Traversal result ──────────────────────────────────────────────────────────

@dataclass
class TraversalResult:
    """Result of a multi-hop graph traversal."""
    nodes:    list[GraphNode]
    edges:    list[GraphEdge]
    depth:    int
    root_id:  str

    def to_text(self) -> str:
        """Serialize to LLM-readable text."""
        lines = [f"Graph context (depth {self.depth}, {len(self.nodes)} nodes):"]
        for node in self.nodes:
            lines.append(f"  {node.summary()}")
        if self.edges:
            lines.append("Relationships:")
            for edge in self.edges:
                lines.append(f"  {edge.from_node[:8]}... --[{edge.edge_type}]--> {edge.to_node[:8]}...")
        return "\n".join(lines)


# ── GraphStore ────────────────────────────────────────────────────────────────

class GraphStore:
    """
    SQLite-backed graph database for a single project.

    One GraphStore instance per project DB. The store operates on the
    graph_nodes and graph_edges tables added to the project's SQLite file.
    """

    def __init__(self, db_path: str, project_id: str, tenant_id: str = "default"):
        self.db_path    = db_path
        self.project_id = project_id
        self.tenant_id  = tenant_id

    # ── Setup ─────────────────────────────────────────────────────────────────

    def ensure_tables(self) -> None:
        """Create graph tables if they don't exist yet."""
        if not Path(self.db_path).exists():
            raise FileNotFoundError(f"Project DB not found: {self.db_path}")
        conn = self._connect()
        try:
            conn.executescript(GRAPH_TABLES_SQL)
            conn.commit()
            logger.info(f"[GraphStore] Graph tables ready in {self.db_path}")
        finally:
            conn.close()

    # ── Write operations ──────────────────────────────────────────────────────

    def add_node(self, node: GraphNode) -> GraphNode:
        """
        Insert or update a node. Uses UPSERT on (source_table, source_id, project_id).
        Returns the node with its node_id confirmed.
        """
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO graph_nodes
                    (node_id, node_type, label, source_table, source_id,
                     properties, project_id, tenant_id, vector_id,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_table, source_id, project_id) DO UPDATE SET
                    label      = excluded.label,
                    properties = excluded.properties,
                    updated_at = excluded.updated_at
                """,
                (
                    node.node_id,
                    node.node_type.value,
                    node.label,
                    node.source_table,
                    node.source_id,
                    json.dumps(node.properties),
                    node.project_id or self.project_id,
                    node.tenant_id or self.tenant_id,
                    node.vector_id,
                    node.created_at,
                    node.updated_at,
                ),
            )
            conn.commit()
            return node
        finally:
            conn.close()

    def add_edge(self, edge: GraphEdge) -> Optional[GraphEdge]:
        """
        Insert an edge. Uses UPSERT on (from_node, to_node, edge_type).
        Returns None if either node doesn't exist (silent safety guard).
        """
        conn = self._connect()
        try:
            # Verify both nodes exist
            exists = conn.execute(
                "SELECT COUNT(*) FROM graph_nodes WHERE node_id IN (?, ?)",
                (edge.from_node, edge.to_node),
            ).fetchone()[0]
            if exists < 2:
                logger.debug(
                    f"[GraphStore] Edge skipped — node(s) missing: "
                    f"{edge.from_node[:8]} → {edge.to_node[:8]}"
                )
                return None

            conn.execute(
                """
                INSERT INTO graph_edges
                    (edge_id, from_node, to_node, edge_type, weight, properties, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(from_node, to_node, edge_type) DO UPDATE SET
                    weight     = excluded.weight,
                    properties = excluded.properties
                """,
                (
                    edge.edge_id,
                    edge.from_node,
                    edge.to_node,
                    edge.edge_type.value,
                    edge.weight,
                    json.dumps(edge.properties),
                    edge.created_at,
                ),
            )
            conn.commit()
            return edge
        finally:
            conn.close()

    def upsert_node_for_row(
        self,
        source_table: str,
        source_id:    str,
        node_type:    NodeType,
        label:        str,
        properties:   dict,
    ) -> GraphNode:
        """Convenience: create and persist a node from a DB row."""
        node = GraphNode(
            node_id=str(uuid.uuid4()),
            node_type=node_type,
            label=label,
            source_table=source_table,
            source_id=str(source_id),
            properties=properties,
            project_id=self.project_id,
            tenant_id=self.tenant_id,
        )
        return self.add_node(node)

    # ── Read operations ───────────────────────────────────────────────────────

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Fetch a single node by ID."""
        conn = self._connect_ro()
        try:
            row = conn.execute(
                "SELECT * FROM graph_nodes WHERE node_id = ?", (node_id,)
            ).fetchone()
            return self._row_to_node(row) if row else None
        finally:
            conn.close()

    def get_node_by_source(self, source_table: str, source_id: str) -> Optional[GraphNode]:
        """Fetch node by its origin row."""
        conn = self._connect_ro()
        try:
            row = conn.execute(
                """
                SELECT * FROM graph_nodes
                WHERE source_table = ? AND source_id = ? AND project_id = ?
                """,
                (source_table, str(source_id), self.project_id),
            ).fetchone()
            return self._row_to_node(row) if row else None
        finally:
            conn.close()

    def get_neighbors(
        self,
        node_id:   str,
        edge_type: Optional[EdgeType] = None,
        direction: str = "both",   # 'out' | 'in' | 'both'
        limit:     int = 20,
    ) -> list[GraphNode]:
        """
        Return nodes directly connected to node_id.
        direction: 'out' = edges FROM node_id, 'in' = edges TO node_id
        """
        conn = self._connect_ro()
        try:
            type_filter = f"AND e.edge_type = '{edge_type.value}'" if edge_type else ""

            if direction in ("out", "both"):
                out_rows = conn.execute(
                    f"""
                    SELECT n.* FROM graph_nodes n
                    JOIN graph_edges e ON e.to_node = n.node_id
                    WHERE e.from_node = ? {type_filter}
                    LIMIT ?
                    """,
                    (node_id, limit),
                ).fetchall()
            else:
                out_rows = []

            if direction in ("in", "both"):
                in_rows = conn.execute(
                    f"""
                    SELECT n.* FROM graph_nodes n
                    JOIN graph_edges e ON e.from_node = n.node_id
                    WHERE e.to_node = ? {type_filter}
                    LIMIT ?
                    """,
                    (node_id, limit),
                ).fetchall()
            else:
                in_rows = []

            seen = set()
            results = []
            for row in list(out_rows) + list(in_rows):
                nid = row["node_id"]
                if nid not in seen:
                    seen.add(nid)
                    results.append(self._row_to_node(row))
            return results
        finally:
            conn.close()

    def get_subgraph(self, node_id: str, depth: int = 2) -> TraversalResult:
        """
        BFS traversal up to `depth` hops from `node_id`.
        Returns all reachable nodes and their connecting edges.
        Uses SQLite recursive CTE for efficiency.
        """
        conn = self._connect_ro()
        try:
            # Recursive CTE: traverse edges up to `depth` hops
            rows = conn.execute(
                f"""
                WITH RECURSIVE traversal(node_id, depth) AS (
                    SELECT ?, 0
                    UNION
                    SELECT e.to_node, t.depth + 1
                    FROM graph_edges e
                    JOIN traversal t ON e.from_node = t.node_id
                    WHERE t.depth < ?
                    UNION
                    SELECT e.from_node, t.depth + 1
                    FROM graph_edges e
                    JOIN traversal t ON e.to_node = t.node_id
                    WHERE t.depth < ?
                )
                SELECT DISTINCT n.*
                FROM graph_nodes n
                JOIN traversal t ON n.node_id = t.node_id
                """,
                (node_id, depth, depth),
            ).fetchall()

            node_ids = {r["node_id"] for r in rows}
            nodes = [self._row_to_node(r) for r in rows]

            # Fetch edges between discovered nodes
            if node_ids:
                placeholders = ",".join("?" * len(node_ids))
                edge_rows = conn.execute(
                    f"""
                    SELECT * FROM graph_edges
                    WHERE from_node IN ({placeholders})
                      AND to_node   IN ({placeholders})
                    """,
                    list(node_ids) + list(node_ids),
                ).fetchall()
                edges = [self._row_to_edge(r) for r in edge_rows]
            else:
                edges = []

            return TraversalResult(
                nodes=nodes, edges=edges, depth=depth, root_id=node_id
            )
        finally:
            conn.close()

    def find_path(
        self,
        from_id:  str,
        to_id:    str,
        max_hops: int = 4,
    ) -> list[GraphNode]:
        """
        Find the shortest path between two nodes using BFS via SQLite CTE.
        Returns ordered list of nodes from source to target (empty if no path).
        """
        conn = self._connect_ro()
        try:
            rows = conn.execute(
                """
                WITH RECURSIVE path_search(node_id, path, depth) AS (
                    SELECT ?, ?, 0
                    UNION
                    SELECT e.to_node,
                           path_search.path || ',' || e.to_node,
                           path_search.depth + 1
                    FROM graph_edges e
                    JOIN path_search ON e.from_node = path_search.node_id
                    WHERE path_search.depth < ?
                      AND path_search.path NOT LIKE '%' || e.to_node || '%'
                )
                SELECT path FROM path_search WHERE node_id = ? ORDER BY depth LIMIT 1
                """,
                (from_id, from_id, max_hops, to_id),
            ).fetchone()

            if not rows:
                return []

            path_ids = rows["path"].split(",")
            nodes = []
            for nid in path_ids:
                n = self.get_node(nid)
                if n:
                    nodes.append(n)
            return nodes
        except Exception as e:
            logger.debug(f"[GraphStore] find_path failed: {e}")
            return []
        finally:
            conn.close()

    def search_nodes(
        self,
        query:     str,
        node_type: Optional[NodeType] = None,
        limit:     int = 10,
    ) -> list[GraphNode]:
        """
        Full-text search across node labels and properties.
        Uses SQLite LIKE for substring matching (no FTS required).
        """
        conn = self._connect_ro()
        try:
            type_filter = f"AND node_type = '{node_type.value}'" if node_type else ""
            rows = conn.execute(
                f"""
                SELECT * FROM graph_nodes
                WHERE project_id = ?
                  AND (label LIKE ? OR properties LIKE ?)
                  {type_filter}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (self.project_id, f"%{query}%", f"%{query}%", limit),
            ).fetchall()
            return [self._row_to_node(r) for r in rows]
        finally:
            conn.close()

    def get_all_nodes(
        self,
        node_type: Optional[NodeType] = None,
        limit:     int = 200,
    ) -> list[GraphNode]:
        """Return all nodes for this project, optionally filtered by type."""
        conn = self._connect_ro()
        try:
            type_filter = f"AND node_type = '{node_type.value}'" if node_type else ""
            rows = conn.execute(
                f"""
                SELECT * FROM graph_nodes
                WHERE project_id = ? {type_filter}
                ORDER BY created_at
                LIMIT ?
                """,
                (self.project_id, limit),
            ).fetchall()
            return [self._row_to_node(r) for r in rows]
        finally:
            conn.close()

    def get_edges_between(self, node_ids: list[str]) -> list[GraphEdge]:
        """Get all edges between a set of nodes."""
        if not node_ids:
            return []
        conn = self._connect_ro()
        try:
            placeholders = ",".join("?" * len(node_ids))
            rows = conn.execute(
                f"""
                SELECT * FROM graph_edges
                WHERE from_node IN ({placeholders})
                  AND to_node   IN ({placeholders})
                """,
                node_ids + node_ids,
            ).fetchall()
            return [self._row_to_edge(r) for r in rows]
        finally:
            conn.close()

    def get_graph_context(
        self,
        node_ids: list[str],
        include_neighbors: bool = True,
    ) -> str:
        """
        Serialize a set of nodes (and optionally their neighbors) into
        a compact text block for LLM prompts.
        """
        if not node_ids:
            return "No graph context available."

        conn = self._connect_ro()
        try:
            placeholders = ",".join("?" * len(node_ids))
            rows = conn.execute(
                f"SELECT * FROM graph_nodes WHERE node_id IN ({placeholders})",
                node_ids,
            ).fetchall()
            nodes = [self._row_to_node(r) for r in rows]

            edges = self.get_edges_between(node_ids)

            lines = ["KNOWLEDGE GRAPH CONTEXT:"]
            for n in nodes:
                lines.append(f"  {n.summary()}")

            if edges:
                lines.append("RELATIONSHIPS:")
                # Resolve node labels for readable output
                id_to_label = {n.node_id: n.label for n in nodes}
                for e in edges:
                    from_label = id_to_label.get(e.from_node, e.from_node[:8])
                    to_label   = id_to_label.get(e.to_node,   e.to_node[:8])
                    lines.append(
                        f"  {from_label} --[{e.edge_type.value}]--> {to_label}"
                        + (f" (weight: {e.weight:.1f})" if e.weight < 1.0 else "")
                    )

            if include_neighbors:
                # Fetch one hop of neighbors for each node
                neighbor_lines = []
                for nid in node_ids[:5]:   # limit to first 5 anchor nodes
                    neighbors = self.get_neighbors(nid, limit=5)
                    for nb in neighbors:
                        if nb.node_id not in node_ids:
                            neighbor_lines.append(f"  (connected) {nb.summary()}")
                if neighbor_lines:
                    lines.append("CONNECTED NODES:")
                    lines.extend(neighbor_lines[:10])

            return "\n".join(lines)
        finally:
            conn.close()

    def stats(self) -> dict:
        """Return node and edge counts by type."""
        conn = self._connect_ro()
        try:
            node_counts = conn.execute(
                "SELECT node_type, COUNT(*) cnt FROM graph_nodes WHERE project_id=? GROUP BY node_type",
                (self.project_id,),
            ).fetchall()
            edge_counts = conn.execute(
                """
                SELECT e.edge_type, COUNT(*) cnt FROM graph_edges e
                JOIN graph_nodes n ON n.node_id = e.from_node
                WHERE n.project_id = ?
                GROUP BY e.edge_type
                """,
                (self.project_id,),
            ).fetchall()
            return {
                "nodes": {r["node_type"]: r["cnt"] for r in node_counts},
                "edges": {r["edge_type"]: r["cnt"] for r in edge_counts},
                "total_nodes": sum(r["cnt"] for r in node_counts),
                "total_edges": sum(r["cnt"] for r in edge_counts),
            }
        finally:
            conn.close()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _connect_ro(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _row_to_node(self, row: sqlite3.Row) -> GraphNode:
        return GraphNode(
            node_id=row["node_id"],
            node_type=NodeType(row["node_type"]),
            label=row["label"],
            source_table=row["source_table"],
            source_id=row["source_id"],
            properties=json.loads(row["properties"] or "{}"),
            project_id=row["project_id"],
            tenant_id=row["tenant_id"],
            vector_id=row["vector_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_edge(self, row: sqlite3.Row) -> GraphEdge:
        return GraphEdge(
            edge_id=row["edge_id"],
            from_node=row["from_node"],
            to_node=row["to_node"],
            edge_type=EdgeType(row["edge_type"]),
            weight=row["weight"],
            properties=json.loads(row["properties"] or "{}"),
            created_at=row["created_at"],
        )


# ── Factory ───────────────────────────────────────────────────────────────────

def get_graph_store(db_path: str, project_id: str, tenant_id: str = "default") -> GraphStore:
    """Create a GraphStore for a project. Call ensure_tables() before first use."""
    return GraphStore(db_path=db_path, project_id=project_id, tenant_id=tenant_id)
