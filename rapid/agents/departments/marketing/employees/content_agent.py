"""Content Agent — content strategy, SEO, thought leadership, content performance."""
from agents.base.base_employee_agent import BaseEmployeeAgent
class ContentAgent(BaseEmployeeAgent):
    dept_tag        = "marketing"
    role_title      = "Content Strategist"
    specialization  = "Content strategy, SEO performance, thought leadership, content pipeline"
    skills          = []
    tools_available = ["search_documents", "query_database"]
    permitted_tables = []
    doc_folders     = ["marketing/content/", "marketing/strategy/"]
    bid_keywords    = [
        "content", "seo", "blog", "whitepaper", "webinar",
        "thought leadership", "organic traffic", "keyword", "content calendar",
        "copywriting", "editorial", "publishing", "engagement rate",
    ]
