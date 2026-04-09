"""Onboarding Agent — new customer onboarding, time-to-value, activation."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class OnboardingAgent(BaseEmployeeAgent):
    dept_tag        = "customer_success"
    role_title      = "Onboarding Specialist"
    specialization  = "New customer onboarding, time-to-value, product activation, implementation"
    skills          = []
    tools_available = ["search_documents", "query_database"]
    permitted_tables = []
    doc_folders     = ["customer_success/onboarding/", "customer_success/playbooks/"]
    bid_keywords    = [
        "onboarding", "time to value", "ttv", "activation",
        "implementation", "go-live", "setup", "configuration",
        "new customer", "kickoff", "training", "adoption",
    ]
