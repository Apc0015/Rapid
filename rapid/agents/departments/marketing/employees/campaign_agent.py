"""Campaign Agent — campaign performance, ROI, attribution, lead generation."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class CampaignAgent(BaseEmployeeAgent):
    dept_tag        = "marketing"
    role_title      = "Campaign Manager"
    specialization  = "Campaign performance, ROI, attribution modelling, lead generation metrics"
    skills          = []
    tools_available = ["query_database", "calculate", "search_documents"]
    permitted_tables = []
    doc_folders     = ["marketing/campaigns/", "marketing/reports/"]
    bid_keywords    = [
        "campaign", "roi", "attribution", "lead generation", "cpl",
        "cost per lead", "cpc", "click through", "conversion rate",
        "campaign performance", "ad spend", "impressions", "reach",
    ]
