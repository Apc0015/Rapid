"""
tests/test_sql_guard.py — Tests for SQL detection in QueryRewriter.

Run:
    cd rapid
    python -m pytest tests/test_sql_guard.py -v
"""

import pytest
import sys
import types

# ── Stub out heavy dependencies before import ─────────────────────────────────

# Stub infrastructure.llm_client so QueryRewriter can be imported without LLM
llm_mod = types.ModuleType("infrastructure.llm_client")
llm_mod.get_llm = lambda: None  # never called in these tests
sys.modules.setdefault("infrastructure.llm_client", llm_mod)

# Stub agents.base_dept_agent for TYPE_CHECKING
base_mod = types.ModuleType("agents.base_dept_agent")
sys.modules.setdefault("agents.base_dept_agent", base_mod)

from agents.query_rewriter import _looks_like_sql


# ── _looks_like_sql tests ─────────────────────────────────────────────────────

class TestSQLDetection:

    # ── Positive: should detect SQL ───────────────────────────────────────────

    def test_simple_select(self):
        assert _looks_like_sql("SELECT * FROM employees") is True

    def test_select_with_where(self):
        assert _looks_like_sql("SELECT name, salary FROM employees WHERE dept = 'finance'") is True

    def test_select_upper_lower(self):
        assert _looks_like_sql("select id from users limit 10") is True

    def test_with_cte(self):
        assert _looks_like_sql("WITH cte AS (SELECT 1) SELECT * FROM cte") is True

    def test_join_query(self):
        assert _looks_like_sql(
            "SELECT e.name FROM employees e JOIN departments d ON e.dept_id = d.id"
        ) is True

    def test_aggregate_query(self):
        assert _looks_like_sql(
            "SELECT dept, COUNT(*) FROM employees GROUP BY dept HAVING COUNT(*) > 5"
        ) is True

    def test_insert(self):
        assert _looks_like_sql("INSERT INTO logs (event) VALUES ('login')") is True

    def test_update(self):
        assert _looks_like_sql("UPDATE users SET password = 'x' WHERE id = 1") is True

    def test_delete(self):
        assert _looks_like_sql("DELETE FROM sessions WHERE expired = 1") is True

    def test_nested_subquery(self):
        assert _looks_like_sql(
            "SELECT * FROM orders WHERE customer_id IN (SELECT id FROM customers WHERE active = 1)"
        ) is True

    def test_union(self):
        assert _looks_like_sql(
            "SELECT name FROM employees UNION SELECT name FROM contractors"
        ) is True

    # ── Negative: should NOT detect as SQL ────────────────────────────────────

    def test_plain_english_question(self):
        assert _looks_like_sql("What is the total headcount in finance?") is False

    def test_question_with_select_word(self):
        # "select" appearing in natural language, not as SQL keyword
        assert _looks_like_sql("Can you select the best candidates from the HR database?") is False

    def test_general_knowledge(self):
        assert _looks_like_sql("How does the bonus structure work?") is False

    def test_empty_string(self):
        assert _looks_like_sql("") is False

    def test_numbers_only(self):
        assert _looks_like_sql("42") is False

    def test_greeting(self):
        assert _looks_like_sql("Hello, how are you?") is False

    def test_policy_question(self):
        assert _looks_like_sql("What is the remote work policy for engineers?") is False

    def test_document_question(self):
        assert _looks_like_sql("Summarise the Q4 financial report") is False
