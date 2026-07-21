"""
tests/test_governance_boundaries.py — the hard governance gate.

These are the cross-department-boundary and cross-permission tests RAPID's
promise depends on: sensitive data must be removed BEFORE it can reach a role or
department that may not see it. Every assertion here is written to FAIL if
governance is ever bypassed — flip `default_action` to ALLOW, skip the filter,
or widen a rule, and a raw sensitive value shows up in governed output and the
build goes red.

Enforcement is structural: it runs through GovernanceFilter reading
constitution.yaml, not through an instruction in an LLM prompt. CI runs every
test under tests/, so these are a hard merge gate into main.
"""
import textwrap

import pytest


# A realistic constitution. HR carries the most sensitive columns; finance shows
# how the SAME column is governed differently by role (ALLOW_MANAGER). Deny by
# default, so anything not listed is hidden until someone explicitly allows it.
CONSTITUTION_YAML = textwrap.dedent("""
governance:
  default_action: BLOCK
column_permissions:
  hr:
    employees:
      name:              ALLOW
      department:        ALLOW
      salary:            ANONYMIZE
      ssn:               BLOCK
      performance_score: BLOCK
  finance:
    budgets:
      dept:          ALLOW
      salary_budget: ALLOW_MANAGER
""")

# One raw HR row as it would come back from the database, BEFORE governance.
RAW_HR_EMPLOYEE = {
    "name": "Dana Lee",
    "department": "engineering",
    "salary": 184000,
    "ssn": "555-12-3456",
    "performance_score": "PIP",
    "bank_account": "GB29NWBK60161331926819",  # unlisted → must fail closed to BLOCK
}


@pytest.fixture
def gov(tmp_path):
    p = tmp_path / "constitution.yaml"
    p.write_text(CONSTITUTION_YAML)
    from agents.system.governance_filter import GovernanceFilter
    return GovernanceFilter(constitution_path=str(p))


def _govern_hr_row(gov, role):
    rules = gov.load_rules(user_id="u", dept_tag="hr", user_role=role)
    governed, _log = gov.apply_rules(RAW_HR_EMPLOYEE, rules)
    return governed


def _flatten(governed: dict) -> str:
    """Everything the caller would actually receive, as one string to scan."""
    return " ".join(str(v) for v in governed.values())


class TestCrossDepartmentBoundary:
    """A user scoped to one department must never receive another department's
    protected data — checked before any retrieval runs."""

    def test_marketing_user_is_not_permitted_the_hr_department(self, gov):
        perms = gov.get_user_permissions("mkt-user", "employee", permitted_depts=["marketing"])
        # The structural gate: HR is refused up front; marketing is allowed.
        assert gov.is_dept_permitted(perms, "hr") is False
        assert gov.is_dept_permitted(perms, "marketing") is True

    def test_hr_data_reaching_a_marketing_agent_is_a_boundary_violation(self, gov):
        # Defense in depth behind the permission gate: if HR-sourced data ever
        # arrived at a marketing agent, the boundary check catches it.
        assert gov.check_dept_boundary(result_dept="hr", requesting_dept="marketing") is False
        assert gov.check_dept_boundary(result_dept="hr", requesting_dept="hr") is True


class TestCrossPermission:
    """The SAME row governed differently by role: sensitive fields never leak to a
    role that may not see them, but non-sensitive fields still flow."""

    def test_employee_never_receives_raw_salary_ssn_or_performance(self, gov):
        governed = _govern_hr_row(gov, "employee")
        received = _flatten(governed)

        # The leak guard: raw sensitive values must be ABSENT. If governance is
        # bypassed, these strings reappear and the test fails.
        assert "555-12-3456" not in received      # ssn — BLOCK
        assert "184000" not in received           # salary — ANONYMIZE
        assert "PIP" not in received              # performance_score — BLOCK
        assert "GB29NWBK60161331926819" not in received  # unlisted — default BLOCK

        # BLOCK removes the key entirely; ANONYMIZE keeps a masked placeholder.
        assert "ssn" not in governed
        assert "performance_score" not in governed
        assert "bank_account" not in governed
        assert "salary" in governed and "184000" not in str(governed["salary"])

        # Non-sensitive fields are untouched.
        assert governed.get("name") == "Dana Lee"
        assert governed.get("department") == "engineering"

    def test_allow_manager_column_is_visible_to_manager_but_not_employee(self, gov):
        raw_budget = {"dept": "growth", "salary_budget": 750000}
        governed_employee, _ = gov.apply_rules(raw_budget, gov.load_rules("u", "finance", "employee"))
        governed_manager, _ = gov.apply_rules(raw_budget, gov.load_rules("u", "finance", "manager"))

        assert "salary_budget" not in governed_employee          # ALLOW_MANAGER → hidden from employee
        assert governed_manager.get("salary_budget") == 750000    # visible to manager
        assert governed_employee.get("dept") == "growth"          # non-sensitive still flows


class TestFailClosed:
    """Deny-by-default is the safety net: a brand-new sensitive column is hidden
    until someone explicitly allows it."""

    def test_default_action_is_block(self, gov):
        assert gov.default_action == "BLOCK"

    def test_unlisted_column_is_denied_by_default(self, gov):
        governed = _govern_hr_row(gov, "employee")
        assert "bank_account" not in governed

    def test_a_governance_block_is_recorded_for_audit(self, gov):
        # Every BLOCK is captured so it can be persisted to the audit ledger.
        _govern_hr_row(gov, "employee")
        actions = gov.get_pending_audit_actions()
        blocked_fields = {a.get("field") for a in actions if a.get("action", "").startswith("BLOCK")}
        assert "ssn" in blocked_fields
        assert "performance_score" in blocked_fields
        assert "bank_account" in blocked_fields  # the deny-by-default block is audited too
