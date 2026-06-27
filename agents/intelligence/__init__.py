"""
agents/intelligence — Agent Intelligence Layer

Complete implementation of domain-specific agent intelligence for all 10 departments.

Each department has a specialized agent class that inherits from BaseAgentIntelligence
and overrides abstract methods with domain-specific business logic, decision rules,
entity extraction, and validation.

Department Agents:
  1. FinanceAgent - Revenue, budgeting, fraud detection, financial health
  2. SalesAgent - Deal analysis, pipeline health, customer insights, competitive threats
  3. HRAgent - Retention risk, hiring needs, compensation, compliance, culture
  4. LegalAgent - Contract review, compliance, risk assessment, IP protection
  5. MarketingAgent - Campaign performance, engagement, brand health, market trends
  6. OperationsAgent - Process optimization, quality, cost reduction, capacity planning
  7. ITAgent - Infrastructure, security, uptime, incident response
  8. ProcurementAgent - Vendor management, cost control, contract terms, spend analysis
  9. RDAgent - Product innovation, research progress, development pipeline, tech evaluation
  10. CustomerSuccessAgent - Customer health, satisfaction, retention, churn prediction

Base Class:
  BaseAgentIntelligence - Abstract base with:
    - DomainIntent classification (15+ department-specific intents)
    - QueryAnalysis (parse query into actionable components)
    - SkillPlan (select and sequence skills for execution)
    - Result validation (domain rules, governance, format, reasonableness)
    - Decision explanation and recording

Integration with CapabilityEngine:
  - Agents use CapabilityEngine for skill execution
  - SmartAgent class orchestrates full pipeline
  - Each agent specialized for their department

Usage:
  from agents.intelligence import FinanceAgent
  from agents.capabilities import CapabilityEngine

  engine = CapabilityEngine()
  engine.setup()

  finance_agent = FinanceAgent(engine)
  result = await finance_agent.execute("What is Q3 revenue?", {})
"""

# Base intelligence class
from agents.intelligence.base_agent_intelligence import (
    BaseAgentIntelligence,
    DomainIntent,
    DomainKnowledge,
    QueryAnalysis,
    SkillPlan,
    SmartAgent,
)

# Department agents
from agents.intelligence.finance_agent import FinanceAgent
from agents.intelligence.sales_agent import SalesAgent
from agents.intelligence.hr_agent import HRAgent
from agents.intelligence.legal_agent import LegalAgent
from agents.intelligence.marketing_agent import MarketingAgent
from agents.intelligence.operations_agent import OperationsAgent
from agents.intelligence.it_agent import ITAgent
from agents.intelligence.procurement_agent import ProcurementAgent
from agents.intelligence.rd_agent import RDAgent
from agents.intelligence.customer_success_agent import CustomerSuccessAgent

__all__ = [
    # Base classes
    "BaseAgentIntelligence",
    "DomainIntent",
    "DomainKnowledge",
    "QueryAnalysis",
    "SkillPlan",
    "SmartAgent",
    # Department agents
    "FinanceAgent",
    "SalesAgent",
    "HRAgent",
    "LegalAgent",
    "MarketingAgent",
    "OperationsAgent",
    "ITAgent",
    "ProcurementAgent",
    "RDAgent",
    "CustomerSuccessAgent",
]

# Convenience mapping for department -> agent class
DEPARTMENT_AGENTS = {
    "finance": FinanceAgent,
    "sales": SalesAgent,
    "hr": HRAgent,
    "legal": LegalAgent,
    "marketing": MarketingAgent,
    "operations": OperationsAgent,
    "it": ITAgent,
    "procurement": ProcurementAgent,
    "rd": RDAgent,
    "customer_success": CustomerSuccessAgent,
}
