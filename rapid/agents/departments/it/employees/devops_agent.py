"""DevOps Agent — deployments, CI/CD, release management, monitoring."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class DevOpsAgent(BaseEmployeeAgent):
    dept_tag        = "it"
    role_title      = "DevOps Engineer"
    specialization  = "Deployments, CI/CD pipelines, release management, monitoring, alerting"
    skills          = []
    tools_available = ["search_documents", "query_database"]
    permitted_tables = []
    doc_folders     = ["it/devops/", "it/runbooks/"]
    bid_keywords    = [
        "deployment", "release", "ci/cd", "pipeline", "build",
        "devops", "monitoring", "alerting", "rollback", "downtime",
        "change management", "environment", "staging", "production",
    ]
