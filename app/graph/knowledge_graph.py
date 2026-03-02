"""
Knowledge Graph builder and query engine for RAPID.

Uses NetworkX as the graph store and LLM-based Named Entity Recognition
(NER) to extract entities and relationships from documents.  The graph
is persisted as a JSON adjacency file.

Multi-tenant isolation (S4)
---------------------------
Each user gets their own graph file:

    data/knowledge_graph/user_{username}_graph.json

A shared ``global`` graph (``data/knowledge_graph/graph.json``) is kept for
backwards-compatibility and for system-level documents that are not owned by a
specific user.

Pass ``username`` to ``KnowledgeGraphBuilder`` / ``GraphQueryEngine`` to use a
user-scoped graph.  Omit (or pass ``None``) for the global graph.
"""

import os
import json
import logging
import re
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

GRAPH_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "knowledge_graph",
)
# Legacy / global path (kept for backwards-compat)
GRAPH_PATH = os.path.join(GRAPH_DIR, "graph.json")


def _user_graph_path(username: Optional[str]) -> str:
    """Return the graph file path for *username*, or the global path if None."""
    if username:
        # Sanitise: only keep alphanumeric + underscore/hyphen/dot
        safe = re.sub(r"[^\w.\-]", "_", username)
        return os.path.join(GRAPH_DIR, f"user_{safe}_graph.json")
    return GRAPH_PATH


class KnowledgeGraphBuilder:
    """Build a knowledge graph from documents using LLM-based NER.

    Args:
        username: Scope the graph to this user.  ``None`` uses the shared
                  global graph.
    """

    def __init__(self, username: Optional[str] = None):
        try:
            import networkx as nx
        except ImportError:
            raise RuntimeError("networkx is required. Install with: pip install networkx")
        self.nx = nx
        self.username = username
        self.graph_path = _user_graph_path(username)
        os.makedirs(GRAPH_DIR, exist_ok=True)
        self.graph = self._load_graph()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_graph(self):
        """Load graph from JSON or create a new one."""
        if os.path.exists(self.graph_path):
            try:
                from networkx.readwrite import json_graph
                with open(self.graph_path, "r") as f:
                    data = json.load(f)
                return json_graph.node_link_graph(data)
            except Exception as e:
                logger.warning("Failed to load graph '%s': %s — starting fresh", self.graph_path, e)
        return self.nx.DiGraph()

    def save_graph(self):
        """Persist graph to JSON."""
        from networkx.readwrite import json_graph
        data = json_graph.node_link_data(self.graph)
        with open(self.graph_path, "w") as f:
            json.dump(data, f, indent=2)

    # ------------------------------------------------------------------
    # Entity / relationship extraction via LLM
    # ------------------------------------------------------------------

    @staticmethod
    def _build_extraction_prompt(text: str) -> str:
        return f"""Extract entities and their relationships from the text below.

Return ONLY a JSON object with two keys:
- "entities": list of objects with "name" (string) and "type" (string, e.g. Person, Organization, Location, Product, Department, Concept).
- "relationships": list of objects with "source" (entity name), "target" (entity name), and "relation" (verb-phrase describing the relationship, e.g. "works_at", "reports_to", "manufactures").

If no entities or relationships can be found, return {{"entities": [], "relationships": []}}.

TEXT:
\"\"\"
{text[:3000]}
\"\"\"

JSON:"""

    def extract_entities_and_relations(
        self, text: str, llm: Any
    ) -> Tuple[List[Dict], List[Dict]]:
        """Use an LLM to extract entities and relationships from text."""
        from langchain_core.messages import HumanMessage

        prompt = self._build_extraction_prompt(text)

        try:
            response = llm.invoke([HumanMessage(content=prompt)])
            content = response.content.strip()

            # Handle possible markdown code block wrapping
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                content = content.rsplit("```", 1)[0]

            data = json.loads(content)
            entities = data.get("entities", [])
            relations = data.get("relationships", [])
            return entities, relations
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Entity extraction failed: %s", e)
            return [], []

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def add_entities_and_relations(
        self,
        entities: List[Dict],
        relations: List[Dict],
        source_doc: str = "unknown",
    ):
        """Add extracted entities and relationships to the graph."""
        for ent in entities:
            name = ent.get("name", "").strip()
            etype = ent.get("type", "Unknown")
            if not name:
                continue
            if self.graph.has_node(name):
                # Merge types
                existing = self.graph.nodes[name].get("type", "")
                if etype not in existing:
                    self.graph.nodes[name]["type"] = f"{existing},{etype}" if existing else etype
                sources = self.graph.nodes[name].get("sources", [])
                if source_doc not in sources:
                    sources.append(source_doc)
                    self.graph.nodes[name]["sources"] = sources
            else:
                self.graph.add_node(name, type=etype, sources=[source_doc])

        for rel in relations:
            src = rel.get("source", "").strip()
            tgt = rel.get("target", "").strip()
            relation = rel.get("relation", "related_to")
            if not src or not tgt:
                continue
            # Ensure nodes exist
            for n in [src, tgt]:
                if not self.graph.has_node(n):
                    self.graph.add_node(n, type="Unknown", sources=[source_doc])
            self.graph.add_edge(src, tgt, relation=relation, source=source_doc)

        self.save_graph()
        logger.info(
            "Graph '%s' updated: %d nodes, %d edges",
            self.graph_path,
            self.graph.number_of_nodes(),
            self.graph.number_of_edges(),
        )

    def build_from_text(self, text: str, llm: Any, source_doc: str = "unknown"):
        """One-shot: extract and add to graph."""
        entities, relations = self.extract_entities_and_relations(text, llm)
        self.add_entities_and_relations(entities, relations, source_doc)
        return {"entities_added": len(entities), "relations_added": len(relations)}

    # ------------------------------------------------------------------
    # Graph stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "node_types": _count_types(self.graph),
            "graph_file": self.graph_path,
            "username": self.username,
        }


class GraphQueryEngine:
    """Natural language → graph query → formatted answer.

    Args:
        builder:  An existing ``KnowledgeGraphBuilder`` to reuse.
        username: If ``builder`` is not provided, create one scoped to this user.
    """

    def __init__(
        self,
        builder: Optional[KnowledgeGraphBuilder] = None,
        username: Optional[str] = None,
    ):
        self.builder = builder or KnowledgeGraphBuilder(username=username)
        self.graph = self.builder.graph

    # ------------------------------------------------------------------
    # Basic graph operations
    # ------------------------------------------------------------------

    def find_entity(self, name: str) -> Optional[Dict[str, Any]]:
        """Find a node by exact or case-insensitive match."""
        if self.graph.has_node(name):
            return {"name": name, **self.graph.nodes[name]}
        # Case-insensitive search
        for n in self.graph.nodes:
            if n.lower() == name.lower():
                return {"name": n, **self.graph.nodes[n]}
        return None

    def get_neighbors(self, entity: str) -> List[Dict[str, Any]]:
        """Get all entities connected to the given entity."""
        node = self.find_entity(entity)
        if node is None:
            return []
        name = node["name"]
        results = []
        # Outgoing edges
        for _, tgt, data in self.graph.out_edges(name, data=True):
            results.append({
                "entity": tgt,
                "direction": "outgoing",
                "relation": data.get("relation", "related_to"),
                "entity_type": self.graph.nodes[tgt].get("type", "Unknown"),
            })
        # Incoming edges
        for src, _, data in self.graph.in_edges(name, data=True):
            results.append({
                "entity": src,
                "direction": "incoming",
                "relation": data.get("relation", "related_to"),
                "entity_type": self.graph.nodes[src].get("type", "Unknown"),
            })
        return results

    def find_shortest_path(self, entity1: str, entity2: str) -> Optional[Dict[str, Any]]:
        """Find shortest path between two entities."""
        import networkx as nx

        n1 = self.find_entity(entity1)
        n2 = self.find_entity(entity2)
        if n1 is None or n2 is None:
            return None

        try:
            path = nx.shortest_path(self.graph, n1["name"], n2["name"])
        except nx.NetworkXNoPath:
            # Try undirected version
            try:
                path = nx.shortest_path(self.graph.to_undirected(), n1["name"], n2["name"])
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                return None

        edges_desc = []
        for i in range(len(path) - 1):
            edge_data = self.graph.get_edge_data(path[i], path[i + 1]) or {}
            rel = edge_data.get("relation", "related_to")
            edges_desc.append(f"{path[i]} —[{rel}]→ {path[i + 1]}")

        return {"path": path, "length": len(path) - 1, "edges": edges_desc}

    def find_similar_entities(self, entity: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Find entities sharing the most neighbors with the given entity."""
        node = self.find_entity(entity)
        if node is None:
            return []

        name = node["name"]
        my_neighbors = set(self.graph.predecessors(name)) | set(self.graph.successors(name))

        scores = []
        for other in self.graph.nodes:
            if other == name:
                continue
            other_neighbors = set(self.graph.predecessors(other)) | set(self.graph.successors(other))
            overlap = len(my_neighbors & other_neighbors)
            if overlap > 0:
                scores.append({
                    "entity": other,
                    "type": self.graph.nodes[other].get("type", "Unknown"),
                    "shared_neighbors": overlap,
                })

        scores.sort(key=lambda x: x["shared_neighbors"], reverse=True)
        return scores[:top_k]

    def search_entities(self, query: str) -> List[Dict[str, Any]]:
        """Search nodes by substring match on name."""
        q = query.lower()
        results = []
        for name, data in self.graph.nodes(data=True):
            if q in name.lower():
                results.append({"name": name, **data})
        return results

    # ------------------------------------------------------------------
    # Natural language query dispatch (via LLM)
    # ------------------------------------------------------------------

    def query(self, question: str, llm: Any) -> Dict[str, Any]:
        """
        Interpret a natural-language graph question using the LLM,
        dispatch to the appropriate graph operation, and return results.
        """
        from langchain_core.messages import HumanMessage

        all_nodes = list(self.graph.nodes)[:200]  # Cap for prompt size
        prompt = f"""You are a graph query classifier. Given a user question and the
available entities in a knowledge graph, decide the operation.

Available entities (subset): {json.dumps(all_nodes[:50])}

Operations:
1. "find_entity" - Look up info about a specific entity. Return: {{"op": "find_entity", "entity": "..."}}
2. "neighbors"   - Find connections of an entity. Return: {{"op": "neighbors", "entity": "..."}}
3. "path"        - Find path between two entities. Return: {{"op": "path", "entity1": "...", "entity2": "..."}}
4. "similar"     - Find similar entities. Return: {{"op": "similar", "entity": "..."}}
5. "search"      - Search by keyword. Return: {{"op": "search", "query": "..."}}

Question: "{question}"

Return ONLY the JSON object, no other text."""

        try:
            response = llm.invoke([HumanMessage(content=prompt)])
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0]
            parsed = json.loads(content)
        except Exception as e:
            logger.warning("Graph query classification failed: %s", e)
            # Fallback: search
            parsed = {"op": "search", "query": question}

        op = parsed.get("op", "search")

        if op == "find_entity":
            result = self.find_entity(parsed.get("entity", ""))
            return {"operation": op, "result": result}
        elif op == "neighbors":
            result = self.get_neighbors(parsed.get("entity", ""))
            return {"operation": op, "result": result}
        elif op == "path":
            result = self.find_shortest_path(
                parsed.get("entity1", ""), parsed.get("entity2", "")
            )
            return {"operation": op, "result": result}
        elif op == "similar":
            result = self.find_similar_entities(parsed.get("entity", ""))
            return {"operation": op, "result": result}
        else:  # search
            result = self.search_entities(parsed.get("query", question))
            return {"operation": "search", "result": result}


def _count_types(graph) -> Dict[str, int]:
    """Count node types in the graph."""
    counts: Dict[str, int] = {}
    for _, data in graph.nodes(data=True):
        for t in data.get("type", "Unknown").split(","):
            t = t.strip()
            counts[t] = counts.get(t, 0) + 1
    return counts
