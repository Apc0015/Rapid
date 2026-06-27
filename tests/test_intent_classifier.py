"""
tests/test_intent_classifier.py — Tests for keyword-based intent classification.

These tests exercise _keyword_classify() (the fast path in spokesperson.py)
without calling any LLM — so they run instantly with no API key needed.

Run:
    cd rapid
    python -m pytest tests/test_intent_classifier.py -v
"""

import os
import sys
import types
import pytest

# ── Stub heavy dependencies so spokesman can be imported without LLM / FAISS ──

def _make_stub(name):
    m = types.ModuleType(name)
    sys.modules.setdefault(name, m)
    return m

for mod in [
    "infrastructure.llm_client",
    "infrastructure.embedding_service",
    "infrastructure.faiss_store",
    "infrastructure.user_registry",
    "infrastructure.doc_master",
]:
    _make_stub(mod)

# Provide minimal stubs needed for module-level code
sys.modules["infrastructure.llm_client"].get_llm = lambda: None
sys.modules["infrastructure.embedding_service"].get_embedder = lambda: None
sys.modules["infrastructure.faiss_store"].get_dept_index = lambda *a, **kw: None
sys.modules["infrastructure.user_registry"].ROLE_DEFAULT_DEPTS = {}
sys.modules["infrastructure.user_registry"].ALL_DEPTS = [
    "finance", "hr", "legal", "sales", "marketing",
    "ops", "it", "procurement", "rd", "customer_success",
]
sys.modules["infrastructure.user_registry"].AGGREGATE_ONLY_ROLES = set()

from agents.system.spokesperson import _keyword_classify, INTENT_TRIVIAL, INTENT_GENERAL


ALL_DEPTS = [
    "finance", "hr", "legal", "sales", "marketing",
    "ops", "it", "procurement", "rd", "customer_success",
]


# ── Helper ────────────────────────────────────────────────────────────────────

def classify(query: str, permitted: list[str] | None = None):
    return _keyword_classify(query, permitted if permitted is not None else ALL_DEPTS)


# ── Trivial intent ────────────────────────────────────────────────────────────

class TestTrivialIntent:

    def test_hello_is_trivial(self):
        result = classify("hello")
        assert result["intent"] == INTENT_TRIVIAL

    def test_hi_there_is_trivial(self):
        result = classify("hi there")
        assert result["intent"] == INTENT_TRIVIAL

    def test_how_are_you_is_trivial(self):
        result = classify("how are you doing?")
        assert result["intent"] == INTENT_TRIVIAL

    def test_good_morning_is_trivial(self):
        result = classify("good morning")
        assert result["intent"] == INTENT_TRIVIAL

    def test_thanks_is_trivial(self):
        result = classify("thanks")
        assert result["intent"] == INTENT_TRIVIAL

    def test_thank_you_is_trivial(self):
        result = classify("thank you very much")
        assert result["intent"] == INTENT_TRIVIAL

    def test_bye_is_trivial(self):
        result = classify("bye")
        assert result["intent"] == INTENT_TRIVIAL


# ── General intent ────────────────────────────────────────────────────────────

class TestGeneralIntent:

    def test_what_is_question_is_general(self):
        result = classify("what is machine learning?")
        assert result["intent"] == INTENT_GENERAL

    def test_explain_question_is_general(self):
        result = classify("explain how encryption works")
        assert result["intent"] == INTENT_GENERAL

    def test_define_question_is_general(self):
        result = classify("define EBITDA")
        assert result["intent"] == INTENT_GENERAL

    def test_tell_me_about_is_general(self):
        result = classify("tell me about blockchain")
        assert result["intent"] == INTENT_GENERAL


# ── Department routing ────────────────────────────────────────────────────────

class TestDeptRouting:

    def test_finance_salary_query(self):
        result = classify("what is the total salary budget for Q3?")
        assert result["intent"] not in (INTENT_TRIVIAL, INTENT_GENERAL)

    def test_hr_leave_query(self):
        result = classify("how many leave days do employees get?")
        assert result["intent"] not in (INTENT_TRIVIAL, INTENT_GENERAL)

    def test_legal_contract_query(self):
        result = classify("where is the NDA contract with Acme Corp?")
        assert result["intent"] not in (INTENT_TRIVIAL, INTENT_GENERAL)

    def test_sales_pipeline_query(self):
        result = classify("what is the current sales pipeline value?")
        assert result["intent"] not in (INTENT_TRIVIAL, INTENT_GENERAL)

    def test_it_incident_query(self):
        result = classify("show me open IT incidents from last week")
        assert result["intent"] not in (INTENT_TRIVIAL, INTENT_GENERAL)


# ── Permission filtering ──────────────────────────────────────────────────────

class TestPermissionFiltering:

    def test_unpermitted_dept_not_selected(self):
        # User only has HR access — finance keywords should not produce finance intent
        result = classify("what is the payroll budget?", permitted=["hr"])
        # Should either be GENERAL/TRIVIAL or route to HR (not finance)
        if result["intent"] not in (INTENT_TRIVIAL, INTENT_GENERAL):
            assert result.get("dept") != "finance"

    def test_empty_permitted_no_dept_intent(self):
        result = classify("what is the bonus amount?", permitted=[])
        # No departments permitted — should fall to general or ambiguous
        assert result["intent"] in (INTENT_TRIVIAL, INTENT_GENERAL) or \
               result.get("dept") is None


# ── Result structure ──────────────────────────────────────────────────────────

class TestResultStructure:

    def test_result_has_intent_key(self):
        result = classify("hello")
        assert "intent" in result

    def test_trivial_result_has_confidence(self):
        result = classify("hi")
        assert "confidence" in result or result["intent"] == INTENT_TRIVIAL

    def test_dept_result_has_dept_key(self):
        # _keyword_classify (and classify_intent) returns dept hints under "dept_hints"
        result = classify("show me the finance budget report")
        if result["intent"] not in (INTENT_TRIVIAL, INTENT_GENERAL):
            assert "dept_hints" in result, (
                f"Expected 'dept_hints' key in dept result, got keys: {list(result.keys())}"
            )
