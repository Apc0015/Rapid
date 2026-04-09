"""
tests/test_governance.py — Unit tests for GovernanceFilter.

Run:
    cd rapid
    python -m pytest tests/test_governance.py -v
"""

import pytest
import textwrap
from pathlib import Path


# ── Shared test constitution ──────────────────────────────────────────────────

CONSTITUTION_YAML = textwrap.dedent("""
column_permissions:
  finance:
    salaries:
      salary:      BLOCK
      bonus:       ALLOW_MANAGER
      employee_id: ALLOW
      name:        ALLOW
    budgets:
      budget_amount: ALLOW_MANAGER
      dept:          ALLOW

  hr:
    employees:
      ssn:        BLOCK
      salary:     BLOCK
      name:       ALLOW
      department: ALLOW
      start_date: ALLOW
      email:      ANONYMIZE
""")


@pytest.fixture
def constitution_file(tmp_path):
    p = tmp_path / "constitution.yaml"
    p.write_text(CONSTITUTION_YAML)
    return str(p)


@pytest.fixture
def gov(constitution_file):
    from agents.governance_filter import GovernanceFilter
    return GovernanceFilter(constitution_path=constitution_file)


# ── Constitution loading ──────────────────────────────────────────────────────

class TestConstitutionLoading:

    def test_loads_finance_rules(self, gov):
        col_perms = gov.constitution.get("column_permissions", {})
        assert "finance" in col_perms
        assert "salaries" in col_perms["finance"]

    def test_loads_hr_rules(self, gov):
        col_perms = gov.constitution.get("column_permissions", {})
        assert "hr" in col_perms
        assert "employees" in col_perms["hr"]

    def test_missing_file_returns_empty(self, tmp_path):
        from agents.governance_filter import GovernanceFilter
        g = GovernanceFilter(constitution_path=str(tmp_path / "nonexistent.yaml"))
        assert g.constitution == {}


# ── RuleSet loading ───────────────────────────────────────────────────────────

class TestRuleSetLoading:

    def test_finance_employee_gets_correct_rules(self, gov):
        rs = gov.load_rules("alice", "finance", user_role="employee")
        assert rs.column_rules.get("salary") == "BLOCK"
        assert rs.column_rules.get("employee_id") == "ALLOW"

    def test_hr_employee_gets_correct_rules(self, gov):
        rs = gov.load_rules("bob", "hr", user_role="employee")
        assert rs.column_rules.get("ssn") == "BLOCK"
        assert rs.column_rules.get("name") == "ALLOW"
        assert rs.column_rules.get("email") == "ANONYMIZE"

    def test_unknown_dept_returns_empty_rules(self, gov):
        rs = gov.load_rules("charlie", "unknown_dept", user_role="employee")
        assert rs.column_rules == {}


# ── apply_rules — ALLOW / BLOCK / ANONYMIZE ───────────────────────────────────

class TestApplyRules:

    def test_allowed_field_passes_through(self, gov):
        rs = gov.load_rules("dave", "finance", user_role="employee")
        result = {"name": "Alice", "employee_id": "E001"}
        governed, log = gov.apply_rules(result, rs)
        assert governed["name"] == "Alice"
        assert governed["employee_id"] == "E001"

    def test_blocked_field_removed(self, gov):
        rs = gov.load_rules("dave", "finance", user_role="employee")
        result = {"salary": 90000, "name": "Alice"}
        governed, log = gov.apply_rules(result, rs)
        assert "salary" not in governed
        assert governed["name"] == "Alice"

    def test_anonymized_field_replaced(self, gov):
        rs = gov.load_rules("eve", "hr", user_role="employee")
        result = {"email": "alice@company.com", "name": "Alice"}
        governed, log = gov.apply_rules(result, rs)
        assert governed.get("email") == "[ANONYMIZED]"
        assert governed["name"] == "Alice"

    def test_ssn_blocked_for_all_employees(self, gov):
        rs = gov.load_rules("frank", "hr", user_role="employee")
        result = {"ssn": "123-45-6789", "name": "Bob"}
        governed, log = gov.apply_rules(result, rs)
        assert "ssn" not in governed

    def test_allow_manager_blocked_for_employee(self, gov):
        rs = gov.load_rules("grace", "finance", user_role="employee")
        result = {"bonus": 5000, "name": "Grace"}
        governed, log = gov.apply_rules(result, rs)
        assert "bonus" not in governed   # employee should not see bonus

    def test_allow_manager_visible_to_manager(self, gov):
        rs = gov.load_rules("henry", "finance", user_role="manager")
        result = {"bonus": 5000, "name": "Henry"}
        governed, log = gov.apply_rules(result, rs)
        assert governed.get("bonus") == 5000

    def test_allow_manager_visible_to_admin(self, gov):
        rs = gov.load_rules("irene", "finance", user_role="admin")
        result = {"bonus": 7000}
        governed, log = gov.apply_rules(result, rs)
        assert governed.get("bonus") == 7000

    def test_unknown_column_defaults_to_allow(self, gov):
        rs = gov.load_rules("jake", "finance", user_role="employee")
        result = {"mystery_column": "some_value"}
        governed, log = gov.apply_rules(result, rs)
        assert governed.get("mystery_column") == "some_value"

    def test_audit_log_entries_created(self, gov):
        rs = gov.load_rules("kate", "finance", user_role="employee")
        result = {"salary": 80000, "name": "Kate", "bonus": 2000}
        governed, log = gov.apply_rules(result, rs)
        actions = {entry["field"]: entry["action"] for entry in log}
        assert actions.get("salary") == "BLOCK"
        assert actions.get("name") == "ALLOW"

    def test_empty_result_returns_empty(self, gov):
        rs = gov.load_rules("leo", "finance", user_role="employee")
        governed, log = gov.apply_rules({}, rs)
        assert governed == {}
        assert log == []


# ── Department boundaries ─────────────────────────────────────────────────────

class TestDeptBoundary:

    def test_same_dept_is_clean(self, gov):
        assert gov.check_dept_boundary("finance", "finance") is True

    def test_cross_dept_is_violation(self, gov):
        assert gov.check_dept_boundary("hr", "finance") is False

    def test_dept_permitted_check(self, gov):
        perms = {"permitted_departments": ["finance", "hr"]}
        assert gov.is_dept_permitted(perms, "finance") is True
        assert gov.is_dept_permitted(perms, "legal") is False


# ── ALLOW_ROLE_MAP ────────────────────────────────────────────────────────────

class TestAllowRoleMap:

    def test_manager_suffix_allows_manager(self):
        from agents.governance_filter import ALLOW_ROLE_MAP
        assert "manager" in ALLOW_ROLE_MAP["manager"]

    def test_manager_suffix_allows_admin(self):
        from agents.governance_filter import ALLOW_ROLE_MAP
        assert "admin" in ALLOW_ROLE_MAP["manager"]

    def test_employee_not_in_manager_set(self):
        from agents.governance_filter import ALLOW_ROLE_MAP
        assert "employee" not in ALLOW_ROLE_MAP["manager"]

    def test_ceo_includes_admin(self):
        from agents.governance_filter import ALLOW_ROLE_MAP
        assert "admin" in ALLOW_ROLE_MAP["ceo"]
        assert "ceo" in ALLOW_ROLE_MAP["ceo"]

    def test_board_includes_board_member(self):
        from agents.governance_filter import ALLOW_ROLE_MAP
        assert "board_member" in ALLOW_ROLE_MAP["board"]

    def test_executive_excludes_employee(self):
        from agents.governance_filter import ALLOW_ROLE_MAP
        assert "employee" not in ALLOW_ROLE_MAP["executive"]
