"""Tests for the knowledge graph builder and query engine."""

import os
import sys
import json
import tempfile
import shutil
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def check_networkx():
    pytest.importorskip("networkx")


@pytest.fixture
def graph_dir(tmp_path):
    """Use a temporary directory for graph storage."""
    gdir = tmp_path / "kg"
    gdir.mkdir()
    with patch("app.graph.knowledge_graph.GRAPH_DIR", str(gdir)), \
         patch("app.graph.knowledge_graph.GRAPH_PATH", str(gdir / "graph.json")):
        yield gdir


@pytest.fixture
def mock_llm():
    """Create a mock LLM that returns entity extraction results."""
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(
        content=json.dumps({
            "entities": [
                {"name": "John Smith", "type": "Person"},
                {"name": "Acme Corp", "type": "Organization"},
                {"name": "Sales", "type": "Department"},
            ],
            "relationships": [
                {"source": "John Smith", "target": "Acme Corp", "relation": "works_at"},
                {"source": "John Smith", "target": "Sales", "relation": "works_in"},
            ],
        })
    )
    return llm


class TestKnowledgeGraphBuilder:
    def test_build_from_text(self, graph_dir, mock_llm):
        from app.graph.knowledge_graph import KnowledgeGraphBuilder
        builder = KnowledgeGraphBuilder()
        stats = builder.build_from_text(
            "John Smith works at Acme Corp in the Sales department",
            mock_llm,
            source_doc="test.txt",
        )
        assert stats["entities_added"] == 3
        assert stats["relations_added"] == 2
        assert builder.graph.number_of_nodes() == 3
        assert builder.graph.number_of_edges() == 2

    def test_entity_types(self, graph_dir, mock_llm):
        from app.graph.knowledge_graph import KnowledgeGraphBuilder
        builder = KnowledgeGraphBuilder()
        builder.build_from_text("test", mock_llm, source_doc="test.txt")
        assert builder.graph.nodes["John Smith"]["type"] == "Person"
        assert builder.graph.nodes["Acme Corp"]["type"] == "Organization"

    def test_graph_persistence(self, graph_dir, mock_llm):
        from app.graph.knowledge_graph import KnowledgeGraphBuilder
        builder = KnowledgeGraphBuilder()
        builder.build_from_text("test", mock_llm)
        assert os.path.exists(str(graph_dir / "graph.json"))

        # Load existing graph
        builder2 = KnowledgeGraphBuilder()
        assert builder2.graph.number_of_nodes() == 3

    def test_incremental_build(self, graph_dir, mock_llm):
        from app.graph.knowledge_graph import KnowledgeGraphBuilder
        builder = KnowledgeGraphBuilder()
        builder.build_from_text("doc1", mock_llm)

        # Second call with different entities
        mock_llm2 = MagicMock()
        mock_llm2.invoke.return_value = MagicMock(
            content=json.dumps({
                "entities": [
                    {"name": "Jane Doe", "type": "Person"},
                    {"name": "Acme Corp", "type": "Organization"},  # existing
                ],
                "relationships": [
                    {"source": "Jane Doe", "target": "Acme Corp", "relation": "works_at"},
                ],
            })
        )
        builder.build_from_text("doc2", mock_llm2)
        assert builder.graph.number_of_nodes() == 4  # 3 + 1 new
        assert builder.graph.number_of_edges() == 3  # 2 + 1 new

    def test_get_stats(self, graph_dir, mock_llm):
        from app.graph.knowledge_graph import KnowledgeGraphBuilder
        builder = KnowledgeGraphBuilder()
        builder.build_from_text("test", mock_llm)
        stats = builder.get_stats()
        assert stats["nodes"] == 3
        assert stats["edges"] == 2
        assert "Person" in stats["node_types"]

    def test_failed_extraction(self, graph_dir):
        from app.graph.knowledge_graph import KnowledgeGraphBuilder
        builder = KnowledgeGraphBuilder()
        bad_llm = MagicMock()
        bad_llm.invoke.return_value = MagicMock(content="not json at all")
        stats = builder.build_from_text("test", bad_llm)
        assert stats["entities_added"] == 0
        assert stats["relations_added"] == 0


class TestGraphQueryEngine:
    @pytest.fixture
    def populated_engine(self, graph_dir, mock_llm):
        from app.graph.knowledge_graph import KnowledgeGraphBuilder, GraphQueryEngine
        builder = KnowledgeGraphBuilder()
        builder.build_from_text("test", mock_llm)
        return GraphQueryEngine(builder)

    def test_find_entity(self, populated_engine):
        result = populated_engine.find_entity("John Smith")
        assert result is not None
        assert result["name"] == "John Smith"
        assert result["type"] == "Person"

    def test_find_entity_case_insensitive(self, populated_engine):
        result = populated_engine.find_entity("john smith")
        assert result is not None
        assert result["name"] == "John Smith"

    def test_find_entity_not_found(self, populated_engine):
        result = populated_engine.find_entity("Unknown Person")
        assert result is None

    def test_get_neighbors(self, populated_engine):
        neighbors = populated_engine.get_neighbors("John Smith")
        assert len(neighbors) == 2
        names = [n["entity"] for n in neighbors]
        assert "Acme Corp" in names
        assert "Sales" in names

    def test_shortest_path(self, populated_engine):
        result = populated_engine.find_shortest_path("John Smith", "Acme Corp")
        assert result is not None
        assert result["length"] == 1
        assert "works_at" in result["edges"][0]

    def test_shortest_path_no_path(self, graph_dir, mock_llm):
        from app.graph.knowledge_graph import KnowledgeGraphBuilder, GraphQueryEngine
        builder = KnowledgeGraphBuilder()
        # Add two disconnected nodes
        builder.graph.add_node("A", type="X", sources=[])
        builder.graph.add_node("B", type="Y", sources=[])
        engine = GraphQueryEngine(builder)
        result = engine.find_shortest_path("A", "B")
        assert result is None

    def test_search_entities(self, populated_engine):
        results = populated_engine.search_entities("John")
        assert len(results) == 1
        assert results[0]["name"] == "John Smith"

    def test_find_similar_entities(self, populated_engine):
        results = populated_engine.find_similar_entities("Acme Corp")
        # Sales and Acme Corp share John Smith as neighbor
        names = [r["entity"] for r in results]
        assert "Sales" in names

    def test_query_dispatch(self, populated_engine):
        mock_q_llm = MagicMock()
        mock_q_llm.invoke.return_value = MagicMock(
            content=json.dumps({"op": "find_entity", "entity": "John Smith"})
        )
        result = populated_engine.query("Tell me about John Smith", mock_q_llm)
        assert result["operation"] == "find_entity"
        assert result["result"]["name"] == "John Smith"

    def test_query_fallback_on_bad_llm(self, populated_engine):
        bad_llm = MagicMock()
        bad_llm.invoke.side_effect = Exception("LLM down")
        result = populated_engine.query("test", bad_llm)
        assert result["operation"] == "search"
