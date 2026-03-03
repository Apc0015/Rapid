"""
D1 — Information Extractor

Determines what data fields are conceptually needed to answer the user's intent.
Has NO database access. Reasons purely about the question.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional
from app.services.llm_service import LLMManager

logger = logging.getLogger(__name__)


@dataclass
class InformationRequirements:
    data_concepts: List[str]        # e.g. ["employee salary", "department name"]
    filters: List[str]              # e.g. ["department=Finance", "year=2024"]
    aggregations: List[str]         # e.g. ["average", "count", "sum"]
    sort_preference: Optional[str]  # e.g. "descending by amount"
    row_limit_hint: int = 100       # conservative default


class InformationExtractor:
    """
    D1 — extracts information requirements from user intent.
    No DB access whatsoever.
    """

    def __init__(self, llm_manager: LLMManager):
        self.llm = llm_manager

    async def extract(self, raw_query: str) -> InformationRequirements:
        prompt = f"""You are analyzing what data is needed to answer a user question.

User question: "{raw_query}"

Identify the data concepts needed WITHOUT writing SQL or assuming table/column names.

Respond with ONLY valid JSON in this exact format:
{{
  "data_concepts": ["concept 1", "concept 2"],
  "filters": ["filter condition 1", "filter condition 2"],
  "aggregations": ["aggregate function needed"],
  "sort_preference": "sort description or null",
  "row_limit_hint": 100
}}

Examples:
- "What are average salaries by department?" → data_concepts: ["employee salary", "department name"], aggregations: ["average"]
- "Which customers haven't paid in 60 days?" → data_concepts: ["customer identifier", "payment date", "invoice amount"], filters: ["payment date > 60 days ago"]
- "Top 10 products by revenue last quarter" → data_concepts: ["product name", "revenue"], filters: ["last quarter"], aggregations: ["sum"], sort_preference: "descending by revenue", row_limit_hint: 10"""

        try:
            raw = await self.llm.chat(prompt, max_tokens=400, temperature=0.0)
            # Extract JSON from response
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(raw[start:end])
                return InformationRequirements(
                    data_concepts=data.get("data_concepts", [raw_query]),
                    filters=data.get("filters", []),
                    aggregations=data.get("aggregations", []),
                    sort_preference=data.get("sort_preference"),
                    row_limit_hint=int(data.get("row_limit_hint", 100)),
                )
        except Exception as e:
            logger.warning("D1 extraction failed, using fallback: %s", e)

        # Fallback: treat the whole query as the data concept
        return InformationRequirements(
            data_concepts=[raw_query],
            filters=[],
            aggregations=[],
            sort_preference=None,
            row_limit_hint=100,
        )
