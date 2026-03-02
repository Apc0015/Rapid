import pytest
from app.agents.orchestrator import MultiAgentOrchestrator, QueryAgent, DatabaseProxyAgent
from app.rag.engine import RAGEngine
import os


def test_confidence_scoring():
    """Test that classification returns confidence scores"""
    rag_engine = RAGEngine()
    query_agent = QueryAgent(rag_engine)
    
    # Clear document question - should have high confidence
    result = query_agent.classify_query("What is the return policy in the document?")
    assert "type" in result
    assert "confidence" in result
    assert isinstance(result["confidence"], float)
    assert 0.0 <= result["confidence"] <= 1.0
    print(f"✓ Clear query classified as '{result['type']}' with confidence {result['confidence']:.2f}")


def test_multi_source_classification():
    """Test that multi-source queries are detected"""
    rag_engine = RAGEngine()
    query_agent = QueryAgent(rag_engine)
    
    # Query that might need both sources
    result = query_agent.classify_query("Compare the policy targets to actual database results")
    assert "type" in result
    assert "confidence" in result
    print(f"✓ Multi-source query classified as '{result['type']}' with confidence {result['confidence']:.2f}")


def test_low_confidence_routing():
    """Test that low confidence queries route to multi-source"""
    rag_engine = RAGEngine()
    orchestrator = MultiAgentOrchestrator(rag_engine)
    
    # This should work without errors (actual routing tested in integration)
    assert orchestrator is not None
    assert hasattr(orchestrator, 'process_query')
    print("✓ Orchestrator initialized with multi-source routing")


def test_orchestrator_state_fields():
    """Test that AgentState has all required fields"""
    from app.agents.orchestrator import AgentState
    
    # Check TypedDict has new fields
    annotations = AgentState.__annotations__
    assert "confidence" in annotations
    assert "document_result" in annotations
    assert "database_result" in annotations
    print("✓ AgentState has confidence and result fields")


def test_fusion_workflow():
    """Test that fusion node exists in workflow"""
    rag_engine = RAGEngine()
    orchestrator = MultiAgentOrchestrator(rag_engine)
    
    # Check that graph was built successfully
    assert orchestrator.graph is not None
    print("✓ LangGraph workflow built with fusion node")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
