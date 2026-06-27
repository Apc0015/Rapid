"""
infrastructure/node_ingestion.py — Node Ingestion Pipeline.

Converts project DB rows into knowledge graph nodes automatically.
Called after any write to the project database (provisioning, data import,
agent actions) to keep the graph in sync.

The pipeline:
  1. Reads every source table defined in INGESTION_RULES
  2. Creates/updates one GraphNode per row
  3. Creates FK-based edges (activity → deal)
  4. Applies AUTO_EDGE_RULES to create semantic cross-table edges
     (high-impact risks → at-risk KPIs, open risks → pending milestones, etc.)

Usage:
    pipeline = NodeIngestionPipeline(db_path, project_id, tenant_id)
    result   = pipeline.ingest_all()
    # → {"nodes_created": 24, "edges_created": 11, "tables_processed": 7}

    # Or ingest a single table after a targeted write:
    pipeline.ingest_table("project_risks")
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from infrastructure.graph_schema import (
    INGESTION_RULES,
    AUTO_EDGE_RULES,
    GraphNode,
    GraphEdge,
    NodeType,
    EdgeType,
)
from infrastructure.graph_store import GraphStore, get_graph_store

logger = logging.getLogger(__name__)


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class IngestionResult:
    nodes_created:    int           = 0
    nodes_updated:    int           = 0
    edges_created:    int           = 0
    tables_processed: int           = 0
    errors:           list[str]     = field(default_factory=list)
    node_ids:         list[str]     = field(default_factory=list)  # all node IDs touched

    def summary(self) -> str:
        return (
            f"Ingested {self.nodes_created} new nodes, "
            f"{self.nodes_updated} updated, "
            f"{self.edges_created} edges across "
            f"{self.tables_processed} tables"
            + (f" ({len(self.errors)} errors)" if self.errors else "")
        )


# ── NodeIngestionPipeline ─────────────────────────────────────────────────────

class NodeIngestionPipeline:
    """
    Converts project DB rows → knowledge graph nodes + edges.

    Thread-safe for concurrent reads. Writes are serialised by SQLite's
    WAL mode (one writer at a time, fine for project-level concurrency).
    """

    def __init__(self, db_path: str, project_id: str, tenant_id: str = "default"):
        self.db_path    = db_path
        self.project_id = project_id
        self.tenant_id  = tenant_id
        self._store: Optional[GraphStore] = None

    @property
    def store(self) -> GraphStore:
        if self._store is None:
            self._store = get_graph_store(self.db_path, self.project_id, self.tenant_id)
            self._store.ensure_tables()
        return self._store

    # ── Public API ────────────────────────────────────────────────────────────

    def ingest_all(self) -> IngestionResult:
        """
        Full ingestion: process all source tables, then apply auto-edge rules.
        Idempotent — safe to call repeatedly (uses UPSERT).
        """
        result = IngestionResult()
        conn = self._connect_ro()

        # 1. Ingest each table
        for table_name, rule in INGESTION_RULES.items():
            try:
                table_result = self._ingest_table(conn, table_name, rule)
                result.nodes_created    += table_result["created"]
                result.nodes_updated    += table_result["updated"]
                result.edges_created    += table_result["edges"]
                result.node_ids.extend(table_result["node_ids"])
                result.tables_processed += 1
            except Exception as e:
                msg = f"Table '{table_name}': {e}"
                logger.warning(f"[NodeIngestion] {msg}")
                result.errors.append(msg)

        conn.close()

        # 2. Apply auto-edge rules (cross-table semantic edges)
        try:
            auto_edges = self._apply_auto_edge_rules()
            result.edges_created += auto_edges
        except Exception as e:
            result.errors.append(f"Auto-edge rules: {e}")

        logger.info(f"[NodeIngestion] {result.summary()} for project {self.project_id[:8]}")
        return result

    def ingest_table(self, table_name: str) -> IngestionResult:
        """Ingest a single table. Use after targeted writes."""
        result = IngestionResult()
        rule = INGESTION_RULES.get(table_name)
        if not rule:
            result.errors.append(f"No ingestion rule for table '{table_name}'")
            return result

        conn = self._connect_ro()
        try:
            table_result = self._ingest_table(conn, table_name, rule)
            result.nodes_created    = table_result["created"]
            result.nodes_updated    = table_result["updated"]
            result.edges_created    = table_result["edges"]
            result.node_ids         = table_result["node_ids"]
            result.tables_processed = 1
        except Exception as e:
            result.errors.append(str(e))
        finally:
            conn.close()

        return result

    def ingest_single_row(
        self,
        table_name:  str,
        row_data:    dict,
        source_id:   str,
    ) -> Optional[GraphNode]:
        """
        Ingest a single row immediately — called inline after any project write.
        Returns the created/updated GraphNode or None on failure.
        """
        rule = INGESTION_RULES.get(table_name)
        if not rule:
            return None
        try:
            label = str(row_data.get(rule["label_col"], source_id))
            props = {k: row_data.get(k) for k in rule["property_cols"] if k in row_data}
            node = self.store.upsert_node_for_row(
                source_table=table_name,
                source_id=str(source_id),
                node_type=rule["node_type"],
                label=label,
                properties=props,
            )
            return node
        except Exception as e:
            logger.warning(f"[NodeIngestion] Single row ingest failed ({table_name}/{source_id}): {e}")
            return None

    # ── Internal table ingestion ───────────────────────────────────────────────

    def _ingest_table(self, conn: sqlite3.Connection, table_name: str, rule: dict) -> dict:
        """
        Read all rows from `table_name` and create/update nodes.
        Returns {created, updated, edges, node_ids}.
        """
        # Check table exists
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        if not exists:
            return {"created": 0, "updated": 0, "edges": 0, "node_ids": []}

        rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
        if not rows:
            return {"created": 0, "updated": 0, "edges": 0, "node_ids": []}

        id_col     = rule["id_col"]
        label_col  = rule["label_col"]
        prop_cols  = rule["property_cols"]
        node_type  = rule["node_type"]
        edge_rules = rule.get("edge_rules", [])

        created   = 0
        updated   = 0
        edge_count = 0
        node_ids   = []

        for row in rows:
            row_dict  = dict(row)
            source_id = str(row_dict.get(id_col, ""))
            label     = str(row_dict.get(label_col, source_id))
            props     = {k: row_dict.get(k) for k in prop_cols if row_dict.get(k) is not None}

            # Check if node already exists (upsert handles it, but we track create vs update)
            existing = self.store.get_node_by_source(table_name, source_id)

            node = self.store.upsert_node_for_row(
                source_table=table_name,
                source_id=source_id,
                node_type=node_type,
                label=label,
                properties=props,
            )
            node_ids.append(node.node_id)

            if existing:
                updated += 1
            else:
                created += 1

            # FK-based edges
            for edge_rule in edge_rules:
                fk_val = row_dict.get(edge_rule["fk_col"])
                if not fk_val:
                    continue
                target = self.store.get_node_by_source(
                    edge_rule["target_table"], str(fk_val)
                )
                if target:
                    edge = GraphEdge(
                        edge_id=str(uuid.uuid4()),
                        from_node=node.node_id,
                        to_node=target.node_id,
                        edge_type=edge_rule["edge_type"],
                        weight=1.0,
                        properties={"reason": "foreign_key"},
                    )
                    if self.store.add_edge(edge):
                        edge_count += 1

        return {"created": created, "updated": updated, "edges": edge_count, "node_ids": node_ids}

    # ── Auto-edge rules ───────────────────────────────────────────────────────

    def _apply_auto_edge_rules(self) -> int:
        """
        Apply semantic cross-table edge rules.
        Returns total edges created.
        """
        total = 0
        for rule in AUTO_EDGE_RULES:
            try:
                count = self._apply_one_rule(rule)
                total += count
                if count:
                    logger.debug(
                        f"[NodeIngestion] Auto-edge '{rule['description']}': {count} edges"
                    )
            except Exception as e:
                logger.warning(f"[NodeIngestion] Auto-edge rule failed: {rule['description']}: {e}")
        return total

    def _apply_one_rule(self, rule: dict) -> int:
        """Apply a single auto-edge rule. Returns edges created."""
        from_table  = rule["from_table"]
        to_table    = rule["to_table"]
        from_filter = rule["from_filter"]
        to_filter   = rule["to_filter"]
        edge_type   = rule["edge_type"]
        weight      = rule.get("weight", 1.0)

        from_rule = INGESTION_RULES.get(from_table)
        to_rule   = INGESTION_RULES.get(to_table)
        if not from_rule or not to_rule:
            return 0

        from_id_col = from_rule["id_col"]
        to_id_col   = to_rule["id_col"]

        conn = self._connect_ro()
        try:
            # Build WHERE clauses from filters
            def _build_where(filters: dict) -> tuple[str, list]:
                if not filters:
                    return "1=1", []
                clauses = " AND ".join(f"{k} = ?" for k in filters)
                return clauses, list(filters.values())

            from_where, from_params = _build_where(from_filter)
            to_where,   to_params   = _build_where(to_filter)

            from_rows = conn.execute(
                f"SELECT * FROM {from_table} WHERE {from_where}", from_params
            ).fetchall()
            to_rows = conn.execute(
                f"SELECT * FROM {to_table} WHERE {to_where}", to_params
            ).fetchall()
        finally:
            conn.close()

        if not from_rows or not to_rows:
            return 0

        created = 0
        for fr in from_rows:
            from_node = self.store.get_node_by_source(from_table, str(fr[from_id_col]))
            if not from_node:
                continue
            for tr in to_rows:
                # Don't self-link
                if from_table == to_table and fr[from_id_col] == tr[to_id_col]:
                    continue
                to_node = self.store.get_node_by_source(to_table, str(tr[to_id_col]))
                if not to_node:
                    continue
                edge = GraphEdge(
                    edge_id=str(uuid.uuid4()),
                    from_node=from_node.node_id,
                    to_node=to_node.node_id,
                    edge_type=edge_type,
                    weight=weight,
                    properties={"rule": rule["description"]},
                )
                if self.store.add_edge(edge):
                    created += 1

        return created

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _connect_ro(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn


# ── Convenience function ──────────────────────────────────────────────────────

def ingest_project(db_path: str, project_id: str, tenant_id: str = "default") -> IngestionResult:
    """
    One-liner: create pipeline + ingest all tables for a project.
    Called at provisioning time and after bulk data imports.
    """
    pipeline = NodeIngestionPipeline(db_path=db_path, project_id=project_id, tenant_id=tenant_id)
    return pipeline.ingest_all()
