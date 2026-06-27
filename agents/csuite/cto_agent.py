"""CTO Agent — Technology Division (it, rd)."""

from agents.csuite.base_csuite_agent import BaseCsuiteAgent


class CTOAgent(BaseCsuiteAgent):
    exec_tag = "cto"

    # From hierarchy.yaml → divisions.technology.departments
    division_depts = ["it", "rd"]

    bid_keywords = [
        "technology roadmap",
        "it and r&d",
        "tech debt",
        "infrastructure spend",
        "engineering capacity",
        "technology strategy",
        "platform stability",
        "r&d investment",
        "system reliability",
        "technical architecture",
        "cto",
        "chief technology",
        "innovation pipeline",
        "it infrastructure",
    ]

    def _reply_style(self) -> str:
        return (
            "Lead with the core technical finding or risk. "
            "Structure: current state → gap or opportunity → recommended action. "
            "Quantify where possible (uptime %, capacity %, cost). "
            "Keep language precise — avoid jargon the CFO or CEO would not know."
        )
