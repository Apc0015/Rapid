"""COO Agent — Operations & Commercial Division (ops, sales, marketing, customer_success)."""

from agents.csuite.base_csuite_agent import BaseCsuiteAgent


class COOAgent(BaseCsuiteAgent):
    exec_tag = "coo"

    # From hierarchy.yaml → divisions.operations.departments
    division_depts = ["ops", "sales", "marketing", "customer_success"]

    bid_keywords = [
        "operational efficiency",
        "cross-functional headcount",
        "company-wide attrition",
        "sales and operations",
        "marketing and sales",
        "customer and operations",
        "go-to-market",
        "revenue operations",
        "supply chain",
        "customer retention",
        "nps and pipeline",
        "coo",
        "chief operating",
        "operational performance",
        "cross-departmental ops",
    ]

    def _reply_style(self) -> str:
        return (
            "Lead with the operational metric that most directly answers the question. "
            "Structure: performance snapshot → bottleneck or risk → next action. "
            "Highlight cross-functional dependencies where relevant. "
            "Be direct and action-oriented."
        )
