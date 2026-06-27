from __future__ import annotations
"""Marketing Agent — campaigns, ad spend, channel analytics, lead generation."""

import config
from agents.base.base_dept_agent import BaseDeptAgent
from models.bid_object import BidObject
from models.nl_result import NLResult


class MarketingAgent(BaseDeptAgent):
    dept_tag = "marketing"
    doc_folders = ["marketing/campaigns/", "marketing/reports/", "marketing/market_research/"]
    permitted_tables = ["ad_spend", "campaign_analytics", "lead_data", "channel_performance"]

    bid_keywords = [
        "campaign", "spend", "impressions", "ctr", "leads", "channel",
        "marketing", "ad", "advertisement", "roas", "roi", "cpl",
        "conversion", "brand", "content", "social media", "email campaign",
        "seo", "sem", "attribution",
    ]
    partial_keywords = ["market", "audience", "traffic", "engagement"]

    def __init__(self):
        from agents.mesh.intra_dept_orchestrator import IntraDeptOrchestrator
        from agents.departments.marketing.employees import CampaignAgent, ContentAgent, BrandAgent
        self._intra = IntraDeptOrchestrator("marketing", [
            CampaignAgent(), ContentAgent(), BrandAgent(),
        ])

    async def execute(self, query: str, user_permissions: dict):
        return await self._intra.handle(query, user_permissions)

    async def bid(self, query: str) -> BidObject:
        bid = await super().bid(query)
        # Marketing often needs external benchmarks — flag for web supplementation
        q_lower = query.lower()
        if any(w in q_lower for w in ("benchmark", "industry", "market share", "competitor")):
            bid.needs_web_fallback = True
            bid.caveats = "External market benchmarks may supplement internal data."
        return bid

    async def handle_external_benchmark(self, query: str, internal_result: NLResult) -> NLResult:
        """
        If internal data confidence is below threshold, flag for Web Agent supplementation.
        Web Agent will retrieve industry benchmarks to complement the answer.
        """
        if internal_result.confidence < config.HIGH_CONF:
            internal_result.summary += (
                "\n\n📊 Note: External market benchmarks may provide additional context. "
                "Web search supplementation is available for industry comparison data."
            )
            internal_result.needs_web = True
        return internal_result
