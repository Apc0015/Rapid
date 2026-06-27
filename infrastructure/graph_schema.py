"""
infrastructure/graph_schema.py — Knowledge Graph node and edge definitions.

Every piece of data in RAPID is stored as a connected node.
Relationships between nodes form the knowledge graph that enables
questions like:
  - "Which risks are blocking this milestone?"
  - "What deals are at risk because of the CAC issue?"
  - "Show me everything connected to the TechNova deal"

NODE TYPES
──────────
  Entity       — A named thing: Deal, Customer, Person, Vendor, Product
  Event        — Something that happened or is scheduled: Milestone, Activity, Meeting
  Data         — A measured value: KPI, Budget line, Metric reading
  Insight      — LLM-generated finding: Risk assessment, Recommendation, Pattern
  Action       — A queued or completed action: Task, Approval request, Alert
  Communication — A message: Email thread, Slack message, Note, Document

EDGE TYPES
──────────
  RELATES_TO    — Generic soft relationship
  BLOCKS        — A blocks B (milestone blocks deal close)
  DEPENDS_ON    — A depends on B
  CAUSES        — A caused B (CAC increase caused budget alert)
  IMPACTS       — A impacts B (risk impacts KPI)
  LINKED_TO     — Explicit link between two nodes
  OWNS          — Person/agent owns a node
  PRODUCES      — Agent/skill produced this node (report, insight)
  REFERENCES    — Document/insight references another node
  FOLLOWS       — Temporal: A happened after B
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


# ── Enums ─────────────────────────────────────────────────────────────────────

class NodeType(str, Enum):
    ENTITY        = "entity"         # Deal, Customer, Person, Vendor
    EVENT         = "event"          # Milestone, Activity, Meeting
    DATA          = "data"           # KPI, Budget, Metric
    INSIGHT       = "insight"        # LLM finding, Risk assessment
    ACTION        = "action"         # Task, Approval, Alert
    COMMUNICATION = "communication"  # Email, Note, Document, Slack


class EdgeType(str, Enum):
    RELATES_TO  = "relates_to"
    BLOCKS      = "blocks"
    DEPENDS_ON  = "depends_on"
    CAUSES      = "causes"
    IMPACTS     = "impacts"
    LINKED_TO   = "linked_to"
    OWNS        = "owns"
    PRODUCES    = "produces"
    REFERENCES  = "references"
    FOLLOWS     = "follows"


# ── Node dataclass ────────────────────────────────────────────────────────────

@dataclass
class GraphNode:
    """
    A single node in the project knowledge graph.

    node_id       — Unique ID (UUID string)
    node_type     — NodeType enum value
    label         — Short display name ("TechNova Deal", "CAC Risk")
    source_table  — Which project DB table this came from ("project_risks")
    source_id     — Primary key of the source row (str coerced)
    properties    — Arbitrary JSON-serializable dict of attributes
    project_id    — Which project this node belongs to
    created_at    — ISO timestamp
    updated_at    — ISO timestamp
    vector_id     — FAISS index ID for semantic similarity (optional)
    """
    node_id:      str
    node_type:    NodeType
    label:        str
    source_table: str
    source_id:    str
    properties:   dict             = field(default_factory=dict)
    project_id:   str              = ""
    tenant_id:    str              = "default"
    created_at:   str              = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at:   str              = field(default_factory=lambda: datetime.utcnow().isoformat())
    vector_id:    Optional[int]    = None

    def to_dict(self) -> dict:
        return {
            "node_id":      self.node_id,
            "node_type":    self.node_type.value,
            "label":        self.label,
            "source_table": self.source_table,
            "source_id":    self.source_id,
            "properties":   self.properties,
            "project_id":   self.project_id,
            "tenant_id":    self.tenant_id,
            "created_at":   self.created_at,
            "updated_at":   self.updated_at,
            "vector_id":    self.vector_id,
        }

    def summary(self) -> str:
        """Short text representation for LLM prompts."""
        props = ", ".join(f"{k}={v}" for k, v in list(self.properties.items())[:4])
        return f"[{self.node_type.value.upper()}] {self.label} ({props})"


# ── Edge dataclass ────────────────────────────────────────────────────────────

@dataclass
class GraphEdge:
    """
    A directed relationship between two nodes.

    edge_id     — Unique ID (UUID string)
    from_node   — Source node_id
    to_node     — Target node_id
    edge_type   — EdgeType enum value
    weight      — Relationship strength 0.0-1.0 (default 1.0)
    properties  — Optional metadata (reason, confidence, etc.)
    created_at  — ISO timestamp
    """
    edge_id:    str
    from_node:  str
    to_node:    str
    edge_type:  EdgeType
    weight:     float              = 1.0
    properties: dict               = field(default_factory=dict)
    created_at: str                = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "edge_id":    self.edge_id,
            "from_node":  self.from_node,
            "to_node":    self.to_node,
            "edge_type":  self.edge_type.value,
            "weight":     self.weight,
            "properties": self.properties,
            "created_at": self.created_at,
        }


# ── SQL DDL for graph tables (added to each project DB) ──────────────────────

GRAPH_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS graph_nodes (
    node_id       TEXT PRIMARY KEY,
    node_type     TEXT NOT NULL,
    label         TEXT NOT NULL,
    source_table  TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    properties    TEXT DEFAULT '{}',
    project_id    TEXT NOT NULL,
    tenant_id     TEXT NOT NULL DEFAULT 'default',
    vector_id     INTEGER,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE(source_table, source_id, project_id)
);

CREATE TABLE IF NOT EXISTS graph_edges (
    edge_id       TEXT PRIMARY KEY,
    from_node     TEXT NOT NULL REFERENCES graph_nodes(node_id) ON DELETE CASCADE,
    to_node       TEXT NOT NULL REFERENCES graph_nodes(node_id) ON DELETE CASCADE,
    edge_type     TEXT NOT NULL,
    weight        REAL DEFAULT 1.0,
    properties    TEXT DEFAULT '{}',
    created_at    TEXT NOT NULL,
    UNIQUE(from_node, to_node, edge_type)
);

CREATE INDEX IF NOT EXISTS idx_graph_nodes_type      ON graph_nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_project   ON graph_nodes(project_id);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_source    ON graph_nodes(source_table, source_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_from      ON graph_edges(from_node);
CREATE INDEX IF NOT EXISTS idx_graph_edges_to        ON graph_edges(to_node);
CREATE INDEX IF NOT EXISTS idx_graph_edges_type      ON graph_edges(edge_type);
"""


# ── Ingestion rule registry ───────────────────────────────────────────────────
# Maps source_table → (NodeType, label_column, property_columns)
# Used by NodeIngestionPipeline to auto-convert rows to nodes.

INGESTION_RULES: dict[str, dict] = {
    "project_milestones": {
        "node_type":       NodeType.EVENT,
        "label_col":       "name",
        "id_col":          "milestone_id",
        "property_cols":   ["status", "due_date", "priority", "completed_date"],
        "edge_rules":      [],
    },
    "project_risks": {
        "node_type":       NodeType.ENTITY,
        "label_col":       "title",
        "id_col":          "risk_id",
        "property_cols":   ["category", "probability", "impact", "risk_score", "status", "mitigation_plan"],
        "edge_rules":      [],
    },
    "project_kpis": {
        "node_type":       NodeType.DATA,
        "label_col":       "kpi_name",
        "id_col":          "kpi_id",
        "property_cols":   ["current_value", "target_value", "unit", "status", "trend", "period"],
        "edge_rules":      [],
    },
    "project_pipeline": {
        "node_type":       NodeType.ENTITY,
        "label_col":       "customer_name",
        "id_col":          "deal_id",
        "property_cols":   ["stage", "value", "close_date", "owner", "probability"],
        "edge_rules":      [],
    },
    "project_activities": {
        "node_type":       NodeType.EVENT,
        "label_col":       "activity_type",
        "id_col":          "activity_id",
        "property_cols":   ["outcome", "owner", "activity_date", "notes"],
        "edge_rules":      [
            # Activities link to deals via deal_id
            {"fk_col": "deal_id", "target_table": "project_pipeline", "edge_type": EdgeType.LINKED_TO},
        ],
    },
    "project_documents": {
        "node_type":       NodeType.COMMUNICATION,
        "label_col":       "title",
        "id_col":          "doc_id",
        "property_cols":   ["doc_type", "skill_used", "file_format", "status"],
        "edge_rules":      [],
    },
    "project_metadata": {
        "node_type":       NodeType.DATA,
        "label_col":       "name",
        "id_col":          "project_id",
        "property_cols":   ["health_status", "completion_pct", "budget_total", "budget_spent"],
        "edge_rules":      [],
    },
}


# ── Semantic auto-edge rules ──────────────────────────────────────────────────
# Cross-table edges inferred from domain knowledge.
# Each rule: if a risk has impact='high' → IMPACTS edge to KPIs with status='at_risk'

AUTO_EDGE_RULES = [
    {
        "description":  "High-impact risks impact at-risk KPIs",
        "from_table":   "project_risks",
        "from_filter":  {"impact": "high"},
        "to_table":     "project_kpis",
        "to_filter":    {"status": "at_risk"},
        "edge_type":    EdgeType.IMPACTS,
        "weight":       0.9,
    },
    {
        "description":  "Open risks may block pending milestones",
        "from_table":   "project_risks",
        "from_filter":  {"status": "open"},
        "to_table":     "project_milestones",
        "to_filter":    {"status": "pending"},
        "edge_type":    EdgeType.BLOCKS,
        "weight":       0.7,
    },
    {
        "description":  "Completed milestones precede in-progress ones (temporal)",
        "from_table":   "project_milestones",
        "from_filter":  {"status": "completed"},
        "to_table":     "project_milestones",
        "to_filter":    {"status": "in_progress"},
        "edge_type":    EdgeType.FOLLOWS,
        "weight":       0.8,
    },
    {
        "description":  "Pipeline deals depend on in-progress milestones (playbook, pilots)",
        "from_table":   "project_pipeline",
        "from_filter":  {},
        "to_table":     "project_milestones",
        "to_filter":    {"status": "in_progress"},
        "edge_type":    EdgeType.DEPENDS_ON,
        "weight":       0.6,
    },
]
