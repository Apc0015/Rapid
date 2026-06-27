"""IT Agent — system access, tools, software licenses, security policies, infrastructure."""

from agents.base.base_dept_agent import BaseDeptAgent
from models.nl_result import NLResult


class ITAgent(BaseDeptAgent):
    dept_tag = "it"
    doc_folders = ["it/policies/", "it/guides/", "it/security_policies/"]
    permitted_tables = ["systems", "access_requests", "software_licenses", "infrastructure_status"]

    bid_keywords = [
        "access", "system", "tool", "licence", "license", "it policy",
        "onboarding setup", "infrastructure", "security", "vpn", "laptop",
        "software", "hardware", "password", "account", "permission",
        "jira", "slack", "github", "confluence", "azure", "aws",
    ]
    partial_keywords = ["it", "tech", "computer", "device", "network"]

    def __init__(self):
        from agents.mesh.intra_dept_orchestrator import IntraDeptOrchestrator
        from agents.departments.it.employees import InfrastructureAgent, SecurityAgent, SupportAgent, DevOpsAgent
        self._intra = IntraDeptOrchestrator("it", [
            InfrastructureAgent(), SecurityAgent(), SupportAgent(), DevOpsAgent(),
        ])

    async def execute(self, query: str, user_permissions: dict):
        return await self._intra.handle(query, user_permissions)

    async def check_access_eligibility(
        self, user_id: str, system_name: str, user_permissions: dict
    ) -> dict:
        """
        Check Constitution rules and IT policies to determine eligibility.
        Returns {eligible: bool, reason: str, escalation_path: str}.
        """
        from agents.system.governance_filter import get_governance
        from infrastructure.db_master import get_db_master
        from infrastructure.llm_client import get_llm

        governance = get_governance()
        dept_permissions = governance.enrich_permissions_for_dept(user_permissions, self.dept_tag)
        db = get_db_master()

        # Query access_requests table for this system
        intent_query = f"What is the access request status for system '{system_name}' for user {user_id}?"
        try:
            schema = db.read_schema("it")
            intent = await db.extract_intent(intent_query)
            sql = await db.generate_sql(intent, schema, dept_permissions)
            db.validate_sql(sql, schema)
            raw = await db.execute_query(sql)
            governed, log = db.apply_governance(raw, dept_permissions, "it")
            nl = await db.convert_to_nl(governed, intent_query)
            db.destroy_raw_data(raw, governed)
            return {"eligible": True, "reason": nl, "escalation_path": "IT helpdesk"}
        except Exception as e:
            return {
                "eligible": False,
                "reason": f"Unable to determine eligibility: {e}",
                "escalation_path": "Contact IT helpdesk at it-support@company.com",
            }
