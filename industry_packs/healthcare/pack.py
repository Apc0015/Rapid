"""
industry_packs/healthcare/pack.py — Healthcare Industry Pack

Pre-configured for hospitals, clinics, health networks, and digital health companies.

Strict governance showcase:
  • HIPAA PHI protection flagged on all data access
  • Audit logging for every record access
  • Compliance-first KPIs and risk templates
  • Clinical department presets

Departments enabled
───────────────────
  clinical (mapped to ops), compliance (mapped to legal), it, hr, finance, ops

KPIs seeded (11)
─────────────────
  Patient Satisfaction Score, Bed Occupancy Rate, HIPAA Compliance Score,
  Readmission Rate (30-day), Average Length of Stay, Staff-to-Patient Ratio,
  Incident Reporting Rate, Clinical Trial Enrolment, Claim Denial Rate,
  Employee Turnover Rate, On-Time Discharge Rate

Risks seeded (8)
─────────────────
  HIPAA violation, PHI data breach, Staffing shortage (critical),
  Regulatory audit failure, Medical device cybersecurity, Supply chain disruption,
  Malpractice exposure, EHR system downtime

Onboarding (8 steps)
─────────────────────
  Facility name → facility type → patient volume → accreditation body →
  EHR system → HIPAA officer contact → data residency → compliance frameworks
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
        name="Patient Satisfaction Score (HCAHPS)",
        unit="score",
        target_value="85",
        description="Hospital Consumer Assessment of Healthcare Providers and Systems score. National benchmark is ~75.",
        dept_id="ops",
        category="customer",
    ),
    KPITemplate(
        name="Bed Occupancy Rate",
        unit="%",
        target_value="85",
        description="Percentage of available beds occupied. Optimal range 80–90%.",
        dept_id="ops",
        category="operational",
    ),
    KPITemplate(
        name="HIPAA Compliance Score",
        unit="%",
        target_value="100",
        description="Internal audit score across HIPAA Privacy and Security Rules. Must maintain 100%.",
        dept_id="legal",
        category="quality",
    ),
    KPITemplate(
        name="30-Day Readmission Rate",
        unit="%",
        target_value="10",
        description="Percentage of patients readmitted within 30 days of discharge. CMS penalty threshold is 15%.",
        dept_id="ops",
        category="quality",
    ),
    KPITemplate(
        name="Average Length of Stay (ALOS)",
        unit="days",
        target_value="4.5",
        description="Mean inpatient stay duration. Reduction improves throughput and revenue.",
        dept_id="ops",
        category="operational",
    ),
    KPITemplate(
        name="Staff-to-Patient Ratio (Nursing)",
        unit="ratio",
        target_value="1:4",
        description="Nurse-to-patient ratio on general wards. ICU target is typically 1:2.",
        dept_id="hr",
        category="operational",
    ),
    KPITemplate(
        name="Incident Reporting Rate",
        unit="per 1000 days",
        target_value="5",
        description="Adverse events and near-misses reported per 1000 patient days. Higher reporting indicates safety culture.",
        dept_id="legal",
        category="quality",
    ),
    KPITemplate(
        name="Claim Denial Rate",
        unit="%",
        target_value="3",
        description="Percentage of insurance claims denied on first submission. Industry average is 5–10%.",
        dept_id="finance",
        category="financial",
    ),
    KPITemplate(
        name="Employee Turnover Rate (Clinical)",
        unit="%",
        target_value="10",
        description="Annual clinical staff turnover. Healthcare average is 20%; target below 10%.",
        dept_id="hr",
        category="operational",
    ),
    KPITemplate(
        name="On-Time Discharge Rate",
        unit="%",
        target_value="80",
        description="Percentage of patients discharged by planned time. Directly impacts bed availability.",
        dept_id="ops",
        category="operational",
    ),
    KPITemplate(
        name="Operating Margin",
        unit="%",
        target_value="5",
        description="Net operating income as a percentage of total revenue. Healthcare margin is typically 3–6%.",
        dept_id="finance",
        category="financial",
    ),
]


# ── Risk Templates ────────────────────────────────────────────────────────────

_RISKS: list[RiskTemplate] = [
    RiskTemplate(
        title="HIPAA Privacy Rule Violation",
        severity="critical",
        category="compliance",
        description="Unauthorised disclosure of Protected Health Information (PHI) leading to OCR investigation and fines of up to $1.9M per category per year.",
        mitigation="Mandatory HIPAA training for all staff, minimum necessary access policy, BAA with all vendors, annual risk assessment per 45 CFR §164.308.",
    ),
    RiskTemplate(
        title="PHI Data Breach",
        severity="critical",
        category="tech",
        description="Ransomware, insider threat, or misconfiguration exposing patient records triggering 60-day breach notification obligation.",
        mitigation="Encrypt PHI at rest (AES-256) and in transit (TLS 1.3), segment clinical networks, conduct monthly vulnerability scans, maintain incident response plan.",
    ),
    RiskTemplate(
        title="Critical Staffing Shortage",
        severity="critical",
        category="operational",
        description="Nursing or physician shortfall below safe staffing ratios, increasing patient safety risk and triggering regulatory scrutiny.",
        mitigation="Maintain 10% float pool, partnership with agency staffing firms, retention incentive programmes, cross-training for adjacent roles.",
    ),
    RiskTemplate(
        title="Regulatory Audit Failure (CMS / Joint Commission)",
        severity="high",
        category="compliance",
        description="Deficiencies identified during accreditation surveys or CMS Conditions of Participation review, risking Medicare/Medicaid reimbursement.",
        mitigation="Continuous readiness programme, mock surveys twice per year, immediate action on identified deficiencies, designated compliance officer.",
    ),
    RiskTemplate(
        title="Medical Device Cybersecurity Incident",
        severity="high",
        category="tech",
        description="Internet-connected medical devices (infusion pumps, imaging systems) compromised, risking patient safety and data integrity.",
        mitigation="Medical device inventory and patching programme, network segmentation, FDA/MITRE ATLAS threat modelling, vendor security review.",
    ),
    RiskTemplate(
        title="Supply Chain Disruption (Pharmaceuticals / PPE)",
        severity="high",
        category="operational",
        description="Shortage of critical medications, surgical supplies, or personal protective equipment disrupting patient care.",
        mitigation="Maintain 90-day strategic reserve for critical items, multi-supplier contracts, quarterly supply chain risk assessment.",
    ),
    RiskTemplate(
        title="Malpractice and Liability Exposure",
        severity="high",
        category="financial",
        description="Adverse clinical outcomes leading to litigation, reputational harm, and premium increases.",
        mitigation="Peer review programme, clinical documentation standards, patient safety huddles, proactive disclosure and apology policy.",
    ),
    RiskTemplate(
        title="EHR System Downtime",
        severity="high",
        category="tech",
        description="Electronic Health Record outage forcing manual downtime procedures, increasing medication error risk and delaying care.",
        mitigation="Downtime procedure training twice per year, offline EHR access capability, RTO < 4 hours, tested DR runbook.",
    ),
]


# ── Onboarding Steps ──────────────────────────────────────────────────────────

_ONBOARDING: list[OnboardingStep] = [
    OnboardingStep(
        step=1,
        key="facility_name",
        question="What is your facility or organisation name?",
        input_type="text",
        hint="E.g. 'St Mary's Medical Center' or 'HealthFirst Network'.",
    ),
    OnboardingStep(
        step=2,
        key="facility_type",
        question="What type of healthcare organisation are you?",
        input_type="select",
        options=[
            "Acute Care Hospital",
            "Community Hospital",
            "Health System / Network",
            "Outpatient / Ambulatory",
            "Long-Term Care / SNF",
            "Behavioural Health",
            "Digital Health / HealthTech",
            "Physician Practice / Group",
        ],
        hint="Used to calibrate KPI targets and risk templates.",
    ),
    OnboardingStep(
        step=3,
        key="patient_volume",
        question="What is your approximate annual patient volume or encounter count?",
        input_type="select",
        options=["Under 10,000", "10,000–50,000", "50,000–250,000", "250,000–1M", "Over 1M"],
    ),
    OnboardingStep(
        step=4,
        key="accreditation_body",
        question="Which accreditation body(s) do you report to?",
        input_type="multiselect",
        options=["The Joint Commission (TJC)", "DNV GL", "CIHQ", "CMS Conditions of Participation", "State Health Department", "NCQA", "URAC", "None"],
    ),
    OnboardingStep(
        step=5,
        key="ehr_system",
        question="Which Electronic Health Record (EHR) system do you use?",
        input_type="select",
        options=["Epic", "Cerner (Oracle Health)", "Meditech", "Allscripts", "athenahealth", "eClinicalWorks", "NextGen", "Other / Custom"],
        hint="RAPID can surface EHR-specific risk templates.",
    ),
    OnboardingStep(
        step=6,
        key="hipaa_officer",
        question="What is the name and email of your designated HIPAA Privacy Officer?",
        input_type="text",
        hint="Required for audit reports and breach notification workflows. Format: Name, email@org.com",
    ),
    OnboardingStep(
        step=7,
        key="data_residency",
        question="Where must patient data be stored?",
        input_type="select",
        options=["US only (HIPAA compliant AWS)", "On-premises / Private Cloud", "Hybrid (On-prem + US cloud)", "No restriction"],
        hint="RAPID will enforce the selected residency policy across all project databases.",
    ),
    OnboardingStep(
        step=8,
        key="compliance_frameworks",
        question="Which compliance frameworks must RAPID track and report on?",
        input_type="multiselect",
        options=["HIPAA Privacy Rule", "HIPAA Security Rule", "HITECH Act", "21st Century Cures Act", "CMS Conditions of Participation", "NIST CSF", "SOC 2", "State-specific regulations"],
        hint="RAPID will surface controls, evidence gaps, and audit readiness for each selected framework.",
    ),
]


# ── Pack Definition ───────────────────────────────────────────────────────────

HEALTHCARE_PACK = PackDefinition(
    pack_id          = "healthcare",
    name             = "Healthcare",
    description      = (
        "Strict governance showcase for hospitals, health systems, and digital health companies. "
        "Full HIPAA PHI protection, audit-every-access, clinical KPIs (patient satisfaction, "
        "readmission, bed occupancy), and compliance-first risk templates. "
        "Designed to onboard a healthcare organisation in under 4 hours."
    ),
    industry         = "Healthcare",
    version          = "1.0.0",
    departments      = ["ops", "legal", "it", "hr", "finance"],
    primary_dept     = "ops",
    kpi_templates    = _KPIS,
    risk_templates   = _RISKS,
    onboarding_steps = _ONBOARDING,
    governance_flags = {
        "hipaa":                  True,
        "phi_protection":         True,
        "audit_all_access":       True,
        "minimum_necessary":      True,   # HIPAA minimum-necessary standard
        "breach_notification":    True,   # 60-day notification workflow
        "data_encryption":        True,
        "soc2_controls":          False,
        "gdpr_tracking":          False,
        "data_residency_us_only": True,
        "baa_required":           True,   # Business Associate Agreement required for all vendors
    },
    skill_overrides  = {
        "extra_trigger_phrases": {
            "audit_report":   ["hipaa audit", "compliance report", "phi access report", "breach report"],
            "exec_dashboard": ["clinical dashboard", "hospital dashboard", "health system overview"],
            "org_overview":   ["facility overview", "health network report", "clinical portfolio"],
        }
    },
)


def _register(registry) -> None:
    registry.register(HEALTHCARE_PACK)
