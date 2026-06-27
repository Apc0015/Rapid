"""
industry_packs/tech_saas/pack.py — Technology & SaaS Industry Pack

Pre-configured for software companies, SaaS platforms, and technology startups.

Departments enabled
───────────────────
  it / engineering, product (mapped to rd), sales, marketing, finance, hr

KPIs seeded (12)
─────────────────
  MRR, ARR, Churn Rate, CAC, LTV, NPS Score, Sprint Velocity,
  Bug Escape Rate, System Uptime, Feature Adoption Rate,
  Time to Market, Employee Satisfaction

Risks seeded (8)
─────────────────
  Security breach, Technical debt accumulation, Key person dependency,
  Runway risk, Vendor lock-in, Regulatory non-compliance (GDPR/SOC2),
  Scaling failure, Competitive displacement

Onboarding (8 steps)
─────────────────────
  Company name → primary product → funding stage → team size →
  primary LLM → data residency preference → key metrics to track →
  compliance requirements
"""

from __future__ import annotations

from industry_packs.base_pack import (
    KPITemplate,
    OnboardingStep,
    PackDefinition,
    RiskTemplate,
)


# ── KPI Templates ─────────────────────────────────────────────────────────────

_KPIS: list[KPITemplate] = [
    KPITemplate(
        name="Monthly Recurring Revenue (MRR)",
        unit="$",
        target_value="100000",
        description="Total predictable monthly subscription revenue.",
        dept_id="finance",
        category="financial",
    ),
    KPITemplate(
        name="Annual Recurring Revenue (ARR)",
        unit="$",
        target_value="1200000",
        description="Annualised view of MRR — key SaaS health indicator.",
        dept_id="finance",
        category="financial",
    ),
    KPITemplate(
        name="Monthly Churn Rate",
        unit="%",
        target_value="2",
        description="Percentage of customers lost each month. Target ≤ 2%.",
        dept_id="sales",
        category="customer",
    ),
    KPITemplate(
        name="Customer Acquisition Cost (CAC)",
        unit="$",
        target_value="500",
        description="Average cost to acquire one new customer.",
        dept_id="marketing",
        category="financial",
    ),
    KPITemplate(
        name="Customer Lifetime Value (LTV)",
        unit="$",
        target_value="5000",
        description="Expected total revenue from a customer over their lifetime.",
        dept_id="sales",
        category="financial",
    ),
    KPITemplate(
        name="Net Promoter Score (NPS)",
        unit="score",
        target_value="50",
        description="Customer loyalty metric. Score of 50+ is excellent for SaaS.",
        dept_id="sales",
        category="customer",
    ),
    KPITemplate(
        name="Sprint Velocity",
        unit="points",
        target_value="40",
        description="Story points completed per sprint. Tracks engineering throughput.",
        dept_id="it",
        category="operational",
    ),
    KPITemplate(
        name="Bug Escape Rate",
        unit="%",
        target_value="5",
        description="Percentage of bugs that reach production undetected. Target ≤ 5%.",
        dept_id="it",
        category="quality",
    ),
    KPITemplate(
        name="System Uptime",
        unit="%",
        target_value="99.9",
        description="Service availability SLA. Target 99.9% (three nines).",
        dept_id="it",
        category="quality",
    ),
    KPITemplate(
        name="Feature Adoption Rate",
        unit="%",
        target_value="30",
        description="Percentage of users using a new feature within 30 days of launch.",
        dept_id="rd",
        category="customer",
    ),
    KPITemplate(
        name="Time to Market",
        unit="days",
        target_value="90",
        description="Average days from feature conception to production release.",
        dept_id="rd",
        category="operational",
    ),
    KPITemplate(
        name="Employee Net Promoter Score (eNPS)",
        unit="score",
        target_value="30",
        description="Employee loyalty and satisfaction score.",
        dept_id="hr",
        category="operational",
    ),
]


# ── Risk Templates ────────────────────────────────────────────────────────────

_RISKS: list[RiskTemplate] = [
    RiskTemplate(
        title="Data Security Breach",
        severity="critical",
        category="tech",
        description="Unauthorised access to customer or company data via breach, misconfiguration, or insider threat.",
        mitigation="Enforce MFA, encrypt data at rest and in transit, conduct quarterly pen tests, maintain incident response plan.",
    ),
    RiskTemplate(
        title="Technical Debt Accumulation",
        severity="high",
        category="tech",
        description="Rapid feature development without refactoring creates brittle systems that slow future delivery.",
        mitigation="Allocate 20% of each sprint to debt reduction, track debt backlog as a KPI, enforce code review standards.",
    ),
    RiskTemplate(
        title="Key Person Dependency",
        severity="high",
        category="operational",
        description="Critical systems or knowledge held by one or two individuals creates severe bus-factor risk.",
        mitigation="Pair programming, documentation requirements, cross-training rotations, knowledge base maintenance.",
    ),
    RiskTemplate(
        title="Cash Runway Risk",
        severity="critical",
        category="financial",
        description="Burn rate exceeds growth causing runway to fall below 12 months without funding secured.",
        mitigation="Monthly burn review, scenario planning, maintain 18-month runway target, diversify revenue streams.",
    ),
    RiskTemplate(
        title="Vendor Lock-in",
        severity="medium",
        category="tech",
        description="Heavy dependency on a single cloud provider, LLM vendor, or SaaS tool creates switching risk.",
        mitigation="Abstract vendor calls behind interfaces, evaluate multi-cloud strategy, maintain exit playbooks.",
    ),
    RiskTemplate(
        title="Regulatory Non-Compliance (GDPR / SOC2)",
        severity="high",
        category="compliance",
        description="Failure to meet data protection or security certification requirements leading to fines or lost deals.",
        mitigation="Appoint DPO, maintain data inventory, schedule annual SOC2 audit, automate compliance monitoring.",
    ),
    RiskTemplate(
        title="Infrastructure Scaling Failure",
        severity="high",
        category="tech",
        description="System unable to handle traffic spikes, causing downtime during critical growth periods.",
        mitigation="Load test at 10x current peak, implement auto-scaling, define SLOs with alerting and runbooks.",
    ),
    RiskTemplate(
        title="Competitive Displacement",
        severity="medium",
        category="operational",
        description="A well-funded competitor ships a comparable product faster, eroding market position.",
        mitigation="Maintain win/loss tracking, accelerate differentiating features, deepen customer relationships.",
    ),
]


# ── Onboarding Steps ──────────────────────────────────────────────────────────

_ONBOARDING: list[OnboardingStep] = [
    OnboardingStep(
        step=1,
        key="company_name",
        question="What is your company name?",
        input_type="text",
        hint="This will be displayed across all dashboards and reports.",
    ),
    OnboardingStep(
        step=2,
        key="primary_product",
        question="Describe your primary product or service in one sentence.",
        input_type="text",
        hint="E.g. 'B2B SaaS for construction project management'.",
    ),
    OnboardingStep(
        step=3,
        key="funding_stage",
        question="What is your current funding stage?",
        input_type="select",
        options=["Bootstrapped", "Pre-Seed", "Seed", "Series A", "Series B", "Series C+", "Public"],
        hint="Used to calibrate financial KPI targets.",
    ),
    OnboardingStep(
        step=4,
        key="team_size",
        question="How many full-time employees do you have?",
        input_type="select",
        options=["1–10", "11–50", "51–200", "201–500", "500+"],
    ),
    OnboardingStep(
        step=5,
        key="primary_llm",
        question="Which LLM do you want RAPID to use as its intelligence engine?",
        input_type="select",
        options=["Claude (Anthropic)", "GPT-4 (OpenAI)", "Gemini (Google)", "Llama 3 (Self-hosted)", "Mistral (Self-hosted)"],
        hint="You can change this later in Settings.",
    ),
    OnboardingStep(
        step=6,
        key="data_residency",
        question="Where should your data be stored?",
        input_type="select",
        options=["US (AWS us-east-1)", "EU (AWS eu-west-1)", "UK (AWS eu-west-2)", "On-premises", "No preference"],
        hint="Affects storage configuration and compliance.",
    ),
    OnboardingStep(
        step=7,
        key="key_metrics",
        question="Which metrics are most critical for your business right now?",
        input_type="multiselect",
        options=["MRR / ARR", "Churn Rate", "CAC & LTV", "NPS", "Sprint Velocity", "Uptime", "Burn Rate"],
        hint="Select all that apply. These will be highlighted on your executive dashboard.",
    ),
    OnboardingStep(
        step=8,
        key="compliance_requirements",
        question="Which compliance frameworks do you need to track?",
        input_type="multiselect",
        options=["SOC 2 Type I", "SOC 2 Type II", "ISO 27001", "GDPR", "CCPA", "PCI-DSS", "None currently"],
        required=False,
        hint="RAPID will surface relevant controls and risks for selected frameworks.",
    ),
]


# ── Pack Definition ───────────────────────────────────────────────────────────

TECH_SAAS_PACK = PackDefinition(
    pack_id          = "tech_saas",
    name             = "Technology & SaaS",
    description      = (
        "Pre-configured for software companies, SaaS platforms, and technology startups. "
        "Includes MRR/ARR tracking, sprint velocity, uptime SLAs, SOC2/GDPR compliance "
        "controls, and engineering + product KPIs. Onboarding time under 15 minutes."
    ),
    industry         = "Technology & SaaS",
    version          = "1.0.0",
    departments      = ["it", "rd", "sales", "marketing", "finance", "hr"],
    primary_dept     = "it",
    kpi_templates    = _KPIS,
    risk_templates   = _RISKS,
    onboarding_steps = _ONBOARDING,
    governance_flags = {
        "soc2_controls":    True,
        "gdpr_tracking":    True,
        "data_encryption":  True,
        "audit_api_access": True,
        "hipaa":            False,
    },
    skill_overrides  = {
        "extra_trigger_phrases": {
            "sprint_review":  ["sprint report", "velocity report", "engineering report"],
            "exec_dashboard": ["saas dashboard", "metrics dashboard", "investor dashboard"],
        }
    },
)


def _register(registry) -> None:
    registry.register(TECH_SAAS_PACK)
