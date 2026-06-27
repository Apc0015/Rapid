"""
CEO Agent — Strategic layer (sees all 10 departments).

The CEO agent is activated for:
  - Queries from users with role 'ceo' or 'admin'
  - Board-level or enterprise-wide queries
  - Multi-division escalations that no single C-Suite exec can resolve alone
"""

from agents.csuite.base_csuite_agent import BaseCsuiteAgent


class CEOAgent(BaseCsuiteAgent):
    exec_tag = "ceo"

    # CEO sees all 10 departments
    division_depts = [
        "finance",
        "hr",
        "legal",
        "sales",
        "marketing",
        "ops",
        "it",
        "procurement",
        "rd",
        "customer_success",
    ]

    bid_keywords = [
        "board pack",
        "company performance",
        "all departments",
        "enterprise-wide",
        "strategic overview",
        "overall company",
        "full picture",
        "executive summary",
        "ceo",
        "chief executive",
        "company-wide",
        "organisation-wide",
        "state of the business",
        "investor update",
    ]

    def _reply_style(self) -> str:
        return (
            "Deliver a board-level answer: one concise paragraph with the single most "
            "important insight, one key risk or opportunity, and one recommended action. "
            "Do not include raw numbers unless they are the headline metric. "
            "Tone: decisive and clear."
        )
