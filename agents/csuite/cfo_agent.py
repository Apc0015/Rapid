"""CFO Agent — Commercial & Finance Division (finance, hr, legal, procurement)."""

from agents.csuite.base_csuite_agent import BaseCsuiteAgent


class CFOAgent(BaseCsuiteAgent):
    exec_tag = "cfo"

    # From hierarchy.yaml → divisions.commercial_finance.departments
    division_depts = ["finance", "hr", "legal", "procurement"]

    bid_keywords = [
        "p&l",
        "ebitda",
        "cross-divisional revenue",
        "financial strategy",
        "budget across departments",
        "cash position",
        "headcount cost",
        "total compensation",
        "legal and financial",
        "procurement and finance",
        "operating expenditure",
        "company-wide financials",
        "cfo",
        "chief financial",
    ]

    def _reply_style(self) -> str:
        return (
            "Lead with the key financial metric or risk. "
            "Structure: headline figure → variance → driver → recommendation. "
            "Use finance-standard formatting: 2 d.p., M/K suffixes, YoY where relevant. "
            "Be precise and brief — no more than three short paragraphs."
        )
