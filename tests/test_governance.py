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
    from agents.system.governance_filter import GovernanceFilter
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
        from agents.system.governance_filter import GovernanceFilter
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
        from agents.system.governance_filter import ALLOW_ROLE_MAP
        assert "manager" in ALLOW_ROLE_MAP["manager"]

    def test_manager_suffix_allows_admin(self):
        from agents.system.governance_filter import ALLOW_ROLE_MAP
        assert "admin" in ALLOW_ROLE_MAP["manager"]

    def test_employee_not_in_manager_set(self):
        from agents.system.governance_filter import ALLOW_ROLE_MAP
        assert "employee" not in ALLOW_ROLE_MAP["manager"]

    def test_ceo_includes_admin(self):
        from agents.system.governance_filter import ALLOW_ROLE_MAP
        assert "admin" in ALLOW_ROLE_MAP["ceo"]
        assert "ceo" in ALLOW_ROLE_MAP["ceo"]

    def test_board_includes_board_member(self):
        from agents.system.governance_filter import ALLOW_ROLE_MAP
        assert "board_member" in ALLOW_ROLE_MAP["board"]

    def test_executive_excludes_employee(self):
        from agents.system.governance_filter import ALLOW_ROLE_MAP
        assert "employee" not in ALLOW_ROLE_MAP["executive"]


# ── Anonymization method dispatch ─────────────────────────────────────────────
# Constitution with all four anonymization methods to test each branch.

ANON_CONSTITUTION_YAML = textwrap.dedent("""
column_permissions:
  sales:
    customers:
      contact_email: ANONYMIZE
    employees:
      salary:        ANONYMIZE
    feedback_table:
      verbatim:      ANONYMIZE
    misc:
      unknown_col:   ANONYMIZE

aggregation_required:
  - table: customers
    column: contact_email
    method: hash_email
  - table: employees
    column: salary
    method: team_average
  - table: feedback_table
    column: verbatim
    method: paraphrase
""")


@pytest.fixture
def anon_constitution_file(tmp_path):
    p = tmp_path / "anon_constitution.yaml"
    p.write_text(ANON_CONSTITUTION_YAML)
    return str(p)


@pytest.fixture
def anon_gov(anon_constitution_file):
    from agents.system.governance_filter import GovernanceFilter
    return GovernanceFilter(constitution_path=anon_constitution_file)


class TestAnonymizationMethods:
    """Task 1 — verify per-method anonymization dispatch."""

    def test_hash_email_masks_correctly(self, anon_gov):
        """hash_email method: alice@company.com → a***@company.com"""
        rs = anon_gov.load_rules("u1", "sales", user_role="employee")
        result = {"contact_email": "alice@company.com"}
        governed, log = anon_gov.apply_rules(result, rs)
        assert governed["contact_email"] == "a***@company.com"
        assert log[0]["method"] == "hash_email"

    def test_hash_email_masks_different_address(self, anon_gov):
        """hash_email masks any email address, keeps domain intact."""
        rs = anon_gov.load_rules("u1", "sales", user_role="employee")
        result = {"contact_email": "bob@example.org"}
        governed, _ = anon_gov.apply_rules(result, rs)
        assert governed["contact_email"] == "b***@example.org"

    def test_hash_email_handles_invalid_email(self, anon_gov):
        """hash_email with no '@' falls back to [ANONYMIZED]."""
        rs = anon_gov.load_rules("u1", "sales", user_role="employee")
        result = {"contact_email": "not-an-email"}
        governed, _ = anon_gov.apply_rules(result, rs)
        assert governed["contact_email"] == "[ANONYMIZED]"

    def test_team_average_replaces_with_message(self, anon_gov):
        """team_average: individual value replaced with team-average notice."""
        rs = anon_gov.load_rules("u1", "sales", user_role="employee")
        result = {"salary": 95000}
        governed, log = anon_gov.apply_rules(result, rs)
        assert governed["salary"] == "[Team average only — contact your manager]"
        assert log[0]["method"] == "team_average"

    def test_paraphrase_replaces_with_notice(self, anon_gov):
        """paraphrase: verbatim text replaced with privacy notice."""
        rs = anon_gov.load_rules("u1", "sales", user_role="employee")
        result = {"verbatim": "The product is terrible and support never responds."}
        governed, log = anon_gov.apply_rules(result, rs)
        assert governed["verbatim"] == "[Paraphrased for privacy]"
        assert log[0]["method"] == "paraphrase"

    def test_default_fallback_when_no_agg_rule(self, anon_gov):
        """ANONYMIZE with no aggregation_required entry → [ANONYMIZED] fallback."""
        rs = anon_gov.load_rules("u1", "sales", user_role="employee")
        result = {"unknown_col": "some value"}
        governed, log = anon_gov.apply_rules(result, rs)
        assert governed["unknown_col"] == "[ANONYMIZED]"
        assert log[0]["method"] == "default"

    def test_existing_anonymize_test_still_passes(self, gov):
        """Regression: constitution WITHOUT aggregation_required still gives [ANONYMIZED]."""
        rs = gov.load_rules("eve", "hr", user_role="employee")
        result = {"email": "alice@company.com", "name": "Alice"}
        governed, _ = gov.apply_rules(result, rs)
        # test constitution has no aggregation_required → fallback [ANONYMIZED]
        assert governed.get("email") == "[ANONYMIZED]"
        assert governed["name"] == "Alice"

    def test_agg_method_lookup_built_at_init(self, anon_gov):
        """GovernanceFilter._agg_method is correctly built from constitution."""
        assert anon_gov._agg_method["contact_email"] == "hash_email"
        assert anon_gov._agg_method["salary"] == "team_average"
        assert anon_gov._agg_method["verbatim"] == "paraphrase"

    def test_empty_constitution_has_empty_agg_method(self):
        """Constitution with no aggregation_required → empty _agg_method dict."""
        from agents.system.governance_filter import GovernanceFilter
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write("column_permissions: {}\n")
            tmp = f.name
        try:
            g = GovernanceFilter(constitution_path=tmp)
            assert g._agg_method == {}
        finally:
            os.unlink(tmp)

    def test_mask_email_helper_directly(self):
        """Unit test the _mask_email helper function directly."""
        from agents.system.governance_filter import _mask_email
        assert _mask_email("alice@company.com") == "a***@company.com"
        assert _mask_email("z@domain.net") == "z***@domain.net"
        assert _mask_email("noemail") == "[ANONYMIZED]"
        assert _mask_email("") == "[ANONYMIZED]"
        assert _mask_email("@domain.com") == "***@domain.com"
