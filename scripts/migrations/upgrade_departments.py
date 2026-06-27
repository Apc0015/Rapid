#!/usr/bin/env python3
"""
RAPID — Department Upgrade Script
Adds 30 new industry-standard tables + updates 10 existing tables.
Generates realistic synthetic data for all 2,130 employees.
Run from RAPID root: python3 scripts/upgrade_departments.py
"""

import random
import sqlite3
import json
import csv
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

random.seed(99)

# ── Paths ──────────────────────────────────────────────────────────────────────
RAPID_DIR  = Path(__file__).parent.parent
DB_PATH    = RAPID_DIR / "data" / "db" / "rapid.db"
CSV_DIR    = RAPID_DIR / "data" / "csv_exports"
SCHEMA_DIR = RAPID_DIR / "data" / "schema"
TMP_DB     = Path("/tmp/rapid_upgrade.db")

CSV_DIR.mkdir(parents=True, exist_ok=True)

# ── Helpers ────────────────────────────────────────────────────────────────────

def rdate(start="2022-01-01", end="2025-12-31"):
    s = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end,   "%Y-%m-%d")
    return (s + timedelta(days=random.randint(0, (e - s).days))).strftime("%Y-%m-%d")

def rdatetime(start="2023-01-01", end="2025-12-31"):
    return rdate(start, end) + f" {random.randint(8,18):02d}:{random.randint(0,59):02d}:00"

def rperiod():
    y = random.choice([2023, 2024, 2025])
    q = random.randint(1, 4)
    return f"{y}-Q{q}"

def rchoice(lst): return random.choice(lst)
def rfloat(lo, hi, dp=2): return round(random.uniform(lo, hi), dp)
def rint(lo, hi): return random.randint(lo, hi)

DEPTS = ["Engineering","Sales","Operations","Customer Success","IT",
         "R&D","Marketing","Finance","HR","Procurement","Legal"]
REGIONS = ["North America","Europe","Asia Pacific","Latin America","Middle East"]
CHANNELS = ["Email","LinkedIn","Google Ads","Webinar","Referral","SEO","Events","Cold Call"]
INDUSTRIES = ["Technology","Finance","Healthcare","Manufacturing","Retail","Education","Energy"]

print("=" * 60)
print("RAPID Department Upgrade — Starting")
print("=" * 60)

# ── Connect to temp DB, copy existing data ─────────────────────────────────────
print("\n[1/5] Preparing database...")
shutil.copy(str(DB_PATH), str(TMP_DB))
conn = sqlite3.connect(str(TMP_DB))
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA foreign_keys=OFF")

# Get existing employee IDs
try:
    emp_ids = [r[0] for r in conn.execute("SELECT id FROM employees").fetchall()]
    if not emp_ids:
        emp_ids = list(range(1, 2131))
except:
    emp_ids = list(range(1, 2131))

print(f"   Found {len(emp_ids)} employees")

# Get existing supplier IDs
try:
    sup_ids = [r[0] for r in conn.execute("SELECT supplier_id FROM suppliers").fetchall()]
except:
    sup_ids = [f"SUP-{i:04d}" for i in range(1, 201)]

# Get existing customer IDs
try:
    cust_ids = [r[0] for r in conn.execute("SELECT customer_id FROM customers").fetchall()]
except:
    cust_ids = [f"CUST-{i:04d}" for i in range(1, 501)]

# Get existing account IDs
try:
    acct_ids = [r[0] for r in conn.execute("SELECT account_id FROM cs_accounts").fetchall()]
except:
    acct_ids = [f"ACC-{i:04d}" for i in range(1, 221)]

# Get existing project IDs
try:
    proj_ids = [r[0] for r in conn.execute("SELECT project_id FROM rd_projects").fetchall()]
except:
    proj_ids = [f"PRJ-{i:04d}" for i in range(1, 51)]

print("   Employee/Customer/Supplier IDs loaded ✓")

# ══════════════════════════════════════════════════════════════════════════════
# HR DEPARTMENT
# ══════════════════════════════════════════════════════════════════════════════
print("\n[2/5] HR Department...")

# ── Update employees table ─────────────────────────────────────────────────────
print("   Updating employees table...")
for col, defn in [
    ("gender",            "TEXT DEFAULT 'Not Specified'"),
    ("nationality",       "TEXT DEFAULT 'US'"),
    ("employment_type",   "TEXT DEFAULT 'Full-Time'"),
    ("work_location",     "TEXT DEFAULT 'Office'"),
    ("remote_status",     "TEXT DEFAULT 'On-Site'"),
    ("flight_risk_score", "REAL DEFAULT 0.0"),
    ("engagement_score",  "REAL DEFAULT 7.0"),
    ("tenure_months",     "INTEGER DEFAULT 0"),
    ("exit_reason",       "TEXT"),
    ("ethnicity",         "TEXT DEFAULT 'Not Disclosed'"),
]:
    try:
        conn.execute(f"ALTER TABLE employees ADD COLUMN {col} {defn}")
    except: pass

genders = ["Male","Female","Non-Binary","Prefer Not to Say"]
emp_types = ["Full-Time","Part-Time","Contract","Intern"]
locations = ["Office","Remote","Hybrid"]
ethnicities = ["Asian","Black","Hispanic","White","Mixed","Not Disclosed"]
nationalities = ["US","UK","India","Canada","Germany","Australia","Singapore"]

for eid in emp_ids:
    conn.execute("""UPDATE employees SET
        gender=?, nationality=?, employment_type=?, work_location=?,
        remote_status=?, flight_risk_score=?, engagement_score=?, tenure_months=?,
        ethnicity=?
        WHERE id=?""", (
        rchoice(genders), rchoice(nationalities), rchoice(emp_types),
        rchoice(locations), rchoice(["On-Site","Remote","Hybrid"]),
        rfloat(0.0, 1.0), rfloat(4.0, 10.0), rint(1, 120),
        rchoice(ethnicities), eid
    ))
conn.commit()
print("   employees updated ✓")

# ── recruitment_pipeline ───────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS recruitment_pipeline")
conn.execute("""CREATE TABLE recruitment_pipeline (
    req_id          TEXT PRIMARY KEY,
    job_title       TEXT,
    department      TEXT,
    hiring_manager  TEXT,
    open_date       TEXT,
    close_date      TEXT,
    status          TEXT,
    source_channel  TEXT,
    applicants      INTEGER,
    interviews      INTEGER,
    offers_extended INTEGER,
    offers_accepted INTEGER,
    time_to_fill    INTEGER,
    cost_per_hire   REAL,
    hired_employee_id TEXT
)""")
titles = ["Software Engineer","Data Analyst","Product Manager","Sales Rep",
          "HR Business Partner","Finance Manager","Legal Counsel","DevOps Engineer",
          "Marketing Manager","Procurement Specialist","Customer Success Manager"]
rows = []
for i in range(1, 301):
    appl = rint(20, 200)
    intvw = rint(5, min(appl, 30))
    offers = rint(1, min(intvw, 5))
    accepted = rint(0, offers)
    ttf = rint(14, 90)
    rows.append((
        f"REQ-{i:04d}", rchoice(titles), rchoice(DEPTS), f"Manager-{rint(1,50)}",
        rdate("2023-01-01","2025-06-01"), rdate("2023-02-01","2025-09-01"),
        rchoice(["Open","Filled","Cancelled","On Hold"]),
        rchoice(CHANNELS), appl, intvw, offers, accepted, ttf,
        rfloat(2000, 15000), rchoice(emp_ids) if accepted else None
    ))
conn.executemany("INSERT INTO recruitment_pipeline VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   recruitment_pipeline: {len(rows)} rows ✓")

# ── performance_reviews ────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS performance_reviews")
conn.execute("""CREATE TABLE performance_reviews (
    review_id       TEXT PRIMARY KEY,
    employee_id     TEXT,
    period          TEXT,
    rating          REAL,
    goals_set       INTEGER,
    goals_met       INTEGER,
    goals_pct       REAL,
    reviewer_id     TEXT,
    review_date     TEXT,
    next_review     TEXT,
    strengths       TEXT,
    development_area TEXT,
    promotion_flag  INTEGER
)""")
strengths_list = ["Leadership","Communication","Technical Skills","Problem Solving",
                   "Teamwork","Innovation","Customer Focus","Analytical Thinking"]
dev_areas = ["Public Speaking","Strategic Thinking","Data Analysis","Project Management",
              "Cross-functional Collaboration","Delegation","Time Management"]
rows = []
sample_emps = random.sample(emp_ids, min(2000, len(emp_ids)))
for i, eid in enumerate(sample_emps):
    period = rchoice(["2023-H1","2023-H2","2024-H1","2024-H2","2025-H1"])
    rating = rfloat(1.0, 5.0)
    goals = rint(3, 8)
    met = rint(0, goals)
    rows.append((
        f"REV-{i+1:05d}", eid, period, rating, goals, met,
        round(met/goals*100, 1), rchoice(emp_ids), rdate("2023-01-01","2025-09-01"),
        rdate("2025-06-01","2026-06-01"),
        rchoice(strengths_list), rchoice(dev_areas), 1 if rating >= 4.5 else 0
    ))
conn.executemany("INSERT INTO performance_reviews VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   performance_reviews: {len(rows)} rows ✓")

# ── succession_planning ────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS succession_planning")
conn.execute("""CREATE TABLE succession_planning (
    plan_id         TEXT PRIMARY KEY,
    critical_role   TEXT,
    department      TEXT,
    incumbent_id    TEXT,
    successor_id    TEXT,
    readiness       TEXT,
    development_plan TEXT,
    risk_level      TEXT,
    updated_date    TEXT
)""")
readiness = ["Ready Now","Ready in 1 Year","Ready in 2-3 Years","Not Ready"]
risk_levels = ["High","Medium","Low"]
rows = []
for i in range(1, 151):
    rows.append((
        f"SUCC-{i:04d}", rchoice(titles), rchoice(DEPTS),
        rchoice(emp_ids), rchoice(emp_ids),
        rchoice(readiness), f"Development plan {i}",
        rchoice(risk_levels), rdate("2024-01-01","2025-09-01")
    ))
conn.executemany("INSERT INTO succession_planning VALUES (?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   succession_planning: {len(rows)} rows ✓")

# ── dei_metrics ────────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS dei_metrics")
conn.execute("""CREATE TABLE dei_metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    period          TEXT,
    department      TEXT,
    total_headcount INTEGER,
    female_pct      REAL,
    male_pct        REAL,
    nonbinary_pct   REAL,
    minority_pct    REAL,
    pay_gap_pct     REAL,
    inclusion_score REAL,
    promotion_equity_score REAL
)""")
rows = []
for dept in DEPTS:
    for period in ["2023-Q4","2024-Q2","2024-Q4","2025-Q2"]:
        f_pct = rfloat(25, 55)
        m_pct = rfloat(40, 70)
        nb = round(100 - f_pct - m_pct, 1)
        if nb < 0: nb = 1.0
        rows.append((
            period, dept, rint(50, 400), f_pct, m_pct, nb,
            rfloat(20, 50), rfloat(-15, 5), rfloat(5.0, 9.5), rfloat(5.0, 9.5)
        ))
conn.executemany("INSERT INTO dei_metrics (period,department,total_headcount,female_pct,male_pct,nonbinary_pct,minority_pct,pay_gap_pct,inclusion_score,promotion_equity_score) VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   dei_metrics: {len(rows)} rows ✓")

# ── training_records ───────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS training_records")
conn.execute("""CREATE TABLE training_records (
    training_id     TEXT PRIMARY KEY,
    employee_id     TEXT,
    course_name     TEXT,
    category        TEXT,
    hours           REAL,
    completion_date TEXT,
    certification   TEXT,
    cost            REAL,
    provider        TEXT,
    score           REAL
)""")
courses = [("Python for Data","Technical",40,"Python Cert","Coursera"),
           ("Leadership 101","Leadership",16,None,"Internal"),
           ("GDPR Compliance","Compliance",8,"GDPR Cert","LegalEdge"),
           ("Project Management","Management",24,"PMP Prep","PMI"),
           ("AWS Cloud Practitioner","Technical",32,"AWS-CP","AWS"),
           ("Sales Methodology","Sales",16,None,"Salesforce"),
           ("Cybersecurity Essentials","Security",12,"SecPro","SANS"),
           ("Finance for Non-Finance","Finance",8,None,"Internal"),
           ("Agile Scrum Master","Technical",24,"CSM","Scrum Alliance"),
           ("Communication Skills","Soft Skills",8,None,"Internal")]
rows = []
sample = random.sample(emp_ids, min(1800, len(emp_ids)))
for i, eid in enumerate(sample):
    course = rchoice(courses)
    rows.append((
        f"TRN-{i+1:05d}", eid, course[0], course[1], course[2],
        rdate("2023-01-01","2025-09-01"), course[3],
        rfloat(0, 2000), course[4], rfloat(60, 100)
    ))
conn.executemany("INSERT INTO training_records VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   training_records: {len(rows)} rows ✓")

# ── hr_kpis ────────────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS hr_kpis")
conn.execute("""CREATE TABLE hr_kpis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT, kpi_name TEXT, current_value REAL,
    target_value REAL, unit TEXT, trend TEXT, status TEXT
)""")
hr_kpi_data = [
    ("Time to Fill (days)", 38, 30, "days", "down", "yellow"),
    ("Cost Per Hire ($)", 4200, 4000, "$", "up", "yellow"),
    ("Turnover Rate (%)", 12.5, 10.0, "%", "down", "yellow"),
    ("Engagement Score", 7.8, 8.0, "score", "up", "green"),
    ("Training Hours/Employee", 24, 20, "hours", "up", "green"),
    ("Offer Acceptance Rate (%)", 78, 80, "%", "flat", "yellow"),
    ("Internal Mobility Rate (%)", 22, 25, "%", "up", "yellow"),
    ("Absenteeism Rate (%)", 3.2, 3.0, "%", "flat", "green"),
]
rows = []
for period in ["2024-Q3","2024-Q4","2025-Q1","2025-Q2"]:
    for name, cur, tgt, unit, trend, status in hr_kpi_data:
        noise = rfloat(0.9, 1.1)
        rows.append((period, name, round(cur*noise,1), tgt, unit, trend, status))
conn.executemany("INSERT INTO hr_kpis (period,kpi_name,current_value,target_value,unit,trend,status) VALUES (?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   hr_kpis: {len(rows)} rows ✓")

# ══════════════════════════════════════════════════════════════════════════════
# FINANCE DEPARTMENT
# ══════════════════════════════════════════════════════════════════════════════
print("\n   Finance Department...")

# Update financials
for col, defn in [
    ("ebitda",              "REAL DEFAULT 0"),
    ("operating_cash_flow", "REAL DEFAULT 0"),
    ("free_cash_flow",      "REAL DEFAULT 0"),
    ("forecast_amount",     "REAL DEFAULT 0"),
    ("forecast_accuracy_pct","REAL DEFAULT 0"),
    ("close_cycle_days",    "INTEGER DEFAULT 0"),
]:
    try: conn.execute(f"ALTER TABLE financials ADD COLUMN {col} {defn}")
    except: pass

for row in conn.execute("SELECT id, revenue, gross_margin, operating_expenses FROM financials").fetchall():
    rid, rev, gm, opex = row
    ebitda = round(rev * rfloat(0.08, 0.25), 2)
    ocf    = round(ebitda * rfloat(0.7, 1.1), 2)
    fcf    = round(ocf - rfloat(50000, 500000), 2)
    fcast  = round(rev * rfloat(0.95, 1.05), 2)
    acc    = rfloat(80, 98)
    close  = rint(5, 15)
    conn.execute("UPDATE financials SET ebitda=?,operating_cash_flow=?,free_cash_flow=?,forecast_amount=?,forecast_accuracy_pct=?,close_cycle_days=? WHERE id=?",
                 (ebitda, ocf, fcf, fcast, acc, close, rid))
conn.commit()
print("   financials updated ✓")

# ── accounts_receivable ────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS accounts_receivable")
conn.execute("""CREATE TABLE accounts_receivable (
    invoice_id      TEXT PRIMARY KEY,
    customer_id     TEXT,
    customer_name   TEXT,
    amount          REAL,
    issue_date      TEXT,
    due_date        TEXT,
    paid_date       TEXT,
    days_outstanding INTEGER,
    aging_bucket    TEXT,
    status          TEXT,
    payment_method  TEXT
)""")
aging = ["0-30","31-60","61-90","90+"]
statuses = ["Paid","Outstanding","Overdue","Written Off"]
rows = []
companies = [f"Company-{i}" for i in range(1,200)]
for i in range(1, 801):
    issue = rdate("2024-01-01","2025-09-01")
    due   = (datetime.strptime(issue,"%Y-%m-%d") + timedelta(days=30)).strftime("%Y-%m-%d")
    dos   = rint(0, 120)
    bucket = "0-30" if dos<=30 else "31-60" if dos<=60 else "61-90" if dos<=90 else "90+"
    paid_d = rdate(issue, "2025-09-30") if dos < 90 else None
    rows.append((
        f"INV-AR-{i:04d}", rchoice(cust_ids) if cust_ids else f"CUST-{i:04d}",
        rchoice(companies), rfloat(1000, 500000), issue, due, paid_d,
        dos, bucket, rchoice(statuses), rchoice(["Bank Transfer","Check","Card","ACH"])
    ))
conn.executemany("INSERT INTO accounts_receivable VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   accounts_receivable: {len(rows)} rows ✓")

# ── cash_flow_statement ────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS cash_flow_statement")
conn.execute("""CREATE TABLE cash_flow_statement (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    period          TEXT,
    operating_cf    REAL,
    investing_cf    REAL,
    financing_cf    REAL,
    net_change      REAL,
    opening_balance REAL,
    closing_balance REAL
)""")
rows = []
balance = 5000000.0
for period in ["2023-Q1","2023-Q2","2023-Q3","2023-Q4",
               "2024-Q1","2024-Q2","2024-Q3","2024-Q4",
               "2025-Q1","2025-Q2"]:
    ocf = rfloat(500000, 3000000)
    icf = rfloat(-2000000, -100000)
    fcf = rfloat(-500000, 500000)
    net = ocf + icf + fcf
    closing = balance + net
    rows.append((period, ocf, icf, fcf, net, balance, closing))
    balance = closing
conn.executemany("INSERT INTO cash_flow_statement (period,operating_cf,investing_cf,financing_cf,net_change,opening_balance,closing_balance) VALUES (?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   cash_flow_statement: {len(rows)} rows ✓")

# ── financial_close_log ────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS financial_close_log")
conn.execute("""CREATE TABLE financial_close_log (
    close_id            TEXT PRIMARY KEY,
    period              TEXT,
    close_start_date    TEXT,
    close_end_date      TEXT,
    cycle_days          INTEGER,
    reconciliations     INTEGER,
    auto_reconciled_pct REAL,
    exceptions_count    INTEGER,
    completed_by        TEXT,
    status              TEXT
)""")
rows = []
for i, period in enumerate(["2023-Q1","2023-Q2","2023-Q3","2023-Q4",
                              "2024-Q1","2024-Q2","2024-Q3","2024-Q4","2025-Q1","2025-Q2"]):
    rows.append((
        f"CLOSE-{i+1:04d}", period,
        rdate("2023-01-01","2025-09-01"), rdate("2023-01-10","2025-09-15"),
        rint(5, 15), rint(200, 800), rfloat(70, 95),
        rint(0, 20), f"CFO-{rint(1,5)}", rchoice(["Completed","In Progress","Delayed"])
    ))
conn.executemany("INSERT INTO financial_close_log VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   financial_close_log: {len(rows)} rows ✓")

# ── tax_compliance ─────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS tax_compliance")
conn.execute("""CREATE TABLE tax_compliance (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    period          TEXT,
    jurisdiction    TEXT,
    tax_type        TEXT,
    liability       REAL,
    filing_deadline TEXT,
    filed_date      TEXT,
    status          TEXT,
    penalty_amount  REAL
)""")
jurisdictions = ["US Federal","California","New York","UK","Germany","Singapore","Canada"]
tax_types     = ["Corporate Income","VAT/GST","Payroll","Sales Tax","Property"]
rows = []
for period in ["2023","2024","2025"]:
    for j in jurisdictions:
        for tt in random.sample(tax_types, 2):
            deadline = f"{period}-04-15"
            filed    = rdate(f"{period}-03-01", f"{period}-05-01")
            status   = "Filed" if filed <= deadline else "Late Filed"
            rows.append((
                period, j, tt, rfloat(10000, 5000000),
                deadline, filed, status,
                rfloat(0, 50000) if status == "Late Filed" else 0.0
            ))
conn.executemany("INSERT INTO tax_compliance (period,jurisdiction,tax_type,liability,filing_deadline,filed_date,status,penalty_amount) VALUES (?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   tax_compliance: {len(rows)} rows ✓")

# ── finance_kpis ───────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS finance_kpis")
conn.execute("""CREATE TABLE finance_kpis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT, kpi_name TEXT, current_value REAL,
    target_value REAL, unit TEXT, trend TEXT, status TEXT
)""")
fin_kpis = [
    ("Gross Profit Margin (%)", 42.5, 45.0, "%", "up", "yellow"),
    ("Net Profit Margin (%)", 18.2, 20.0, "%", "up", "yellow"),
    ("Days Sales Outstanding", 38, 30, "days", "down", "red"),
    ("Current Ratio", 1.8, 2.0, "ratio", "up", "green"),
    ("Debt-to-Equity Ratio", 0.45, 0.40, "ratio", "down", "yellow"),
    ("Budget Variance (%)", -3.2, 0.0, "%", "up", "yellow"),
    ("Forecast Accuracy (%)", 88.5, 92.0, "%", "up", "yellow"),
    ("Close Cycle Days", 8, 5, "days", "down", "yellow"),
    ("Free Cash Flow ($M)", 12.4, 15.0, "$M", "up", "yellow"),
    ("Operating Cash Flow ($M)", 18.6, 20.0, "$M", "up", "green"),
]
rows = []
for period in ["2024-Q3","2024-Q4","2025-Q1","2025-Q2"]:
    for name, cur, tgt, unit, trend, status in fin_kpis:
        rows.append((period, name, round(cur*rfloat(0.9,1.1),2), tgt, unit, trend, status))
conn.executemany("INSERT INTO finance_kpis (period,kpi_name,current_value,target_value,unit,trend,status) VALUES (?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   finance_kpis: {len(rows)} rows ✓")

# ══════════════════════════════════════════════════════════════════════════════
# SALES DEPARTMENT
# ══════════════════════════════════════════════════════════════════════════════
print("\n   Sales Department...")

# Update deals
for col, defn in [
    ("deal_type",         "TEXT DEFAULT 'New'"),
    ("acv",               "REAL DEFAULT 0"),
    ("tcv",               "REAL DEFAULT 0"),
    ("discount_pct",      "REAL DEFAULT 0"),
    ("lost_reason",       "TEXT"),
    ("forecast_category", "TEXT DEFAULT 'Pipeline'"),
    ("days_in_stage",     "INTEGER DEFAULT 0"),
    ("source",            "TEXT DEFAULT 'Inbound'"),
]:
    try: conn.execute(f"ALTER TABLE deals ADD COLUMN {col} {defn}")
    except: pass

for row in conn.execute("SELECT deal_id, value, stage FROM deals").fetchall():
    did, val, stage = row
    acv = round(val * rfloat(0.8, 1.0), 2)
    conn.execute("""UPDATE deals SET
        deal_type=?, acv=?, tcv=?, discount_pct=?,
        lost_reason=?, forecast_category=?, days_in_stage=?, source=?
        WHERE deal_id=?""", (
        rchoice(["New","Expansion","Renewal"]),
        acv, round(acv * rfloat(1.0, 3.0), 2),
        rfloat(0, 25),
        rchoice(["Price","Competition","No Budget","Timing",None]),
        rchoice(["Commit","Best Case","Pipeline","Omitted"]),
        rint(1, 90), rchoice(["Inbound","Outbound","Referral","Partner"]), did
    ))
conn.commit()
print("   deals updated ✓")

# Update customers
for col, defn in [
    ("company_size",       "TEXT DEFAULT 'Mid-Market'"),
    ("decision_maker",     "TEXT"),
    ("buying_committee",   "INTEGER DEFAULT 1"),
    ("contract_start",     "TEXT"),
    ("contract_end",       "TEXT"),
    ("arr",                "REAL DEFAULT 0"),
]:
    try: conn.execute(f"ALTER TABLE customers ADD COLUMN {col} {defn}")
    except: pass

for cid in cust_ids:
    conn.execute("""UPDATE customers SET
        company_size=?, decision_maker=?, buying_committee=?,
        contract_start=?, contract_end=?, arr=? WHERE customer_id=?""", (
        rchoice(["SMB","Mid-Market","Enterprise","Strategic"]),
        f"Contact-{rint(1,50)}", rint(1, 8),
        rdate("2022-01-01","2024-12-01"),
        rdate("2024-01-01","2027-12-31"),
        rfloat(10000, 2000000), cid
    ))
conn.commit()
print("   customers updated ✓")

# ── sales_activities ───────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS sales_activities")
conn.execute("""CREATE TABLE sales_activities (
    activity_id     TEXT PRIMARY KEY,
    rep_id          TEXT,
    deal_id         TEXT,
    activity_date   TEXT,
    type            TEXT,
    outcome         TEXT,
    duration_mins   INTEGER,
    notes           TEXT
)""")
act_types    = ["Call","Email","Meeting","Demo","Proposal","Follow-Up","LinkedIn"]
outcomes     = ["Positive","Neutral","Negative","No Response","Next Step Set"]
rows = []
for i in range(1, 3001):
    rows.append((
        f"ACT-{i:05d}", f"REP-{rint(1,50):03d}",
        rchoice(cust_ids) if cust_ids else f"CUST-{rint(1,500):04d}",
        rdate("2024-01-01","2025-09-01"),
        rchoice(act_types), rchoice(outcomes),
        rint(5, 120), f"Activity note {i}"
    ))
conn.executemany("INSERT INTO sales_activities VALUES (?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   sales_activities: {len(rows)} rows ✓")

# ── quota_attainment ───────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS quota_attainment")
conn.execute("""CREATE TABLE quota_attainment (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rep_id          TEXT,
    period          TEXT,
    quota_assigned  REAL,
    quota_attained  REAL,
    attainment_pct  REAL,
    rank            INTEGER,
    territory       TEXT
)""")
territories = ["North America East","North America West","Europe","APAC","LATAM","Middle East"]
rows = []
for rep in range(1, 101):
    for period in ["2024-Q1","2024-Q2","2024-Q3","2024-Q4","2025-Q1","2025-Q2"]:
        quota    = rfloat(100000, 500000)
        attained = quota * rfloat(0.3, 1.5)
        rows.append((
            f"REP-{rep:03d}", period, round(quota, 2),
            round(attained, 2), round(attained/quota*100, 1),
            rint(1, 100), rchoice(territories)
        ))
conn.executemany("INSERT INTO quota_attainment (rep_id,period,quota_assigned,quota_attained,attainment_pct,rank,territory) VALUES (?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   quota_attainment: {len(rows)} rows ✓")

# ── sales_forecast ─────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS sales_forecast")
conn.execute("""CREATE TABLE sales_forecast (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    period              TEXT,
    rep_id              TEXT,
    committed           REAL,
    best_case           REAL,
    pipeline_total      REAL,
    pipeline_coverage   REAL,
    actual_closed       REAL,
    forecast_accuracy   REAL
)""")
rows = []
for period in ["2024-Q3","2024-Q4","2025-Q1","2025-Q2"]:
    for rep in range(1, 51):
        commit   = rfloat(50000, 300000)
        best     = commit * rfloat(1.1, 1.5)
        pipeline = best * rfloat(2.5, 4.5)
        actual   = commit * rfloat(0.7, 1.3)
        acc      = round(100 - abs(actual - commit) / commit * 100, 1)
        rows.append((
            period, f"REP-{rep:03d}", round(commit,2), round(best,2),
            round(pipeline,2), round(pipeline/commit,1),
            round(actual,2), max(0, acc)
        ))
conn.executemany("INSERT INTO sales_forecast (period,rep_id,committed,best_case,pipeline_total,pipeline_coverage,actual_closed,forecast_accuracy) VALUES (?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   sales_forecast: {len(rows)} rows ✓")

# ── sales_kpis ─────────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS sales_kpis")
conn.execute("""CREATE TABLE sales_kpis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT, kpi_name TEXT, current_value REAL,
    target_value REAL, unit TEXT, trend TEXT, status TEXT
)""")
sales_kpi_data = [
    ("Win Rate (%)", 32.0, 35.0, "%", "up", "yellow"),
    ("Avg Deal Size ($)", 85000, 100000, "$", "up", "yellow"),
    ("Sales Cycle (days)", 72, 60, "days", "down", "yellow"),
    ("Quota Attainment (%)", 78, 100, "%", "up", "red"),
    ("Pipeline Coverage", 3.2, 4.0, "ratio", "up", "yellow"),
    ("Forecast Accuracy (%)", 82, 90, "%", "up", "yellow"),
    ("Pipeline Velocity ($)", 125000, 150000, "$", "up", "yellow"),
]
rows = []
for period in ["2024-Q3","2024-Q4","2025-Q1","2025-Q2"]:
    for name, cur, tgt, unit, trend, status in sales_kpi_data:
        rows.append((period, name, round(cur*rfloat(0.9,1.1),2), tgt, unit, trend, status))
conn.executemany("INSERT INTO sales_kpis (period,kpi_name,current_value,target_value,unit,trend,status) VALUES (?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   sales_kpis: {len(rows)} rows ✓")

# ══════════════════════════════════════════════════════════════════════════════
# MARKETING DEPARTMENT
# ══════════════════════════════════════════════════════════════════════════════
print("\n   Marketing Department...")

# Update lead_data
for col, defn in [
    ("score",            "INTEGER DEFAULT 0"),
    ("mql_date",         "TEXT"),
    ("sql_date",         "TEXT"),
    ("converted",        "INTEGER DEFAULT 0"),
    ("first_touch",      "TEXT"),
    ("last_touch",       "TEXT"),
    ("lifecycle_stage",  "TEXT DEFAULT 'Lead'"),
    ("company",          "TEXT"),
    ("job_title",        "TEXT"),
]:
    try: conn.execute(f"ALTER TABLE lead_data ADD COLUMN {col} {defn}")
    except: pass

stages = ["Lead","MQL","SQL","Opportunity","Customer"]
for row in conn.execute("SELECT lead_id FROM lead_data").fetchall():
    lid = row[0]
    mql = rdate("2024-01-01","2025-06-01")
    sql = rdate(mql,"2025-09-01") if random.random()>0.4 else None
    conn.execute("""UPDATE lead_data SET score=?,mql_date=?,sql_date=?,converted=?,
        first_touch=?,last_touch=?,lifecycle_stage=?,company=?,job_title=? WHERE lead_id=?""", (
        rint(10, 100), mql, sql, 1 if sql else 0,
        rchoice(CHANNELS), rchoice(CHANNELS), rchoice(stages),
        f"Company-{rint(1,200)}", rchoice(["VP Sales","CTO","CFO","Director","Manager"]), lid
    ))
conn.commit()
print("   lead_data updated ✓")

# ── email_campaigns ────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS email_campaigns")
conn.execute("""CREATE TABLE email_campaigns (
    campaign_id     TEXT PRIMARY KEY,
    name            TEXT,
    type            TEXT,
    send_date       TEXT,
    list_size       INTEGER,
    delivered       INTEGER,
    opens           INTEGER,
    clicks          INTEGER,
    unsubscribes    INTEGER,
    open_rate       REAL,
    click_rate      REAL,
    unsubscribe_rate REAL,
    revenue_attributed REAL
)""")
rows = []
campaign_types = ["Newsletter","Nurture","Product Launch","Event Invite","Re-engagement","Promotional"]
for i in range(1, 201):
    sent = rint(1000, 50000)
    deliv = int(sent * rfloat(0.95, 0.99))
    opens = int(deliv * rfloat(0.15, 0.35))
    clicks = int(opens * rfloat(0.05, 0.25))
    unsubs = int(deliv * rfloat(0.001, 0.01))
    rows.append((
        f"EMAIL-{i:04d}", f"Campaign {i}", rchoice(campaign_types),
        rdate("2023-01-01","2025-09-01"), sent, deliv, opens, clicks, unsubs,
        round(opens/deliv*100, 2), round(clicks/deliv*100, 2),
        round(unsubs/deliv*100, 3), rfloat(0, 50000)
    ))
conn.executemany("INSERT INTO email_campaigns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   email_campaigns: {len(rows)} rows ✓")

# ── brand_sentiment ────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS brand_sentiment")
conn.execute("""CREATE TABLE brand_sentiment (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    period          TEXT,
    platform        TEXT,
    total_mentions  INTEGER,
    positive_pct    REAL,
    negative_pct    REAL,
    neutral_pct     REAL,
    sentiment_score REAL,
    share_of_voice  REAL,
    top_topic       TEXT
)""")
platforms = ["Twitter/X","LinkedIn","Reddit","News","G2","Gartner Peer Insights","Trustpilot"]
topics    = ["Product Quality","Customer Support","Pricing","Innovation","Reliability","Integration"]
rows = []
for period in ["2024-Q1","2024-Q2","2024-Q3","2024-Q4","2025-Q1","2025-Q2"]:
    for platform in platforms:
        pos = rfloat(40, 70)
        neg = rfloat(5, 25)
        neu = round(100 - pos - neg, 1)
        rows.append((
            period, platform, rint(100, 10000),
            pos, neg, neu, rfloat(5.0, 9.0),
            rfloat(5, 35), rchoice(topics)
        ))
conn.executemany("INSERT INTO brand_sentiment (period,platform,total_mentions,positive_pct,negative_pct,neutral_pct,sentiment_score,share_of_voice,top_topic) VALUES (?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   brand_sentiment: {len(rows)} rows ✓")

# ── web_analytics ──────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS web_analytics")
conn.execute("""CREATE TABLE web_analytics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT,
    sessions        INTEGER,
    unique_visitors INTEGER,
    bounce_rate     REAL,
    avg_duration_secs INTEGER,
    pages_per_session REAL,
    new_visitor_pct REAL,
    conversion_rate REAL,
    top_source      TEXT,
    organic_pct     REAL
)""")
rows = []
sources = ["Organic Search","Paid Search","Social","Direct","Referral","Email"]
for i in range(180):
    d = (datetime(2025,1,1) - timedelta(days=i*2)).strftime("%Y-%m-%d")
    sess = rint(500, 20000)
    rows.append((
        d, sess, int(sess*rfloat(0.6,0.9)), rfloat(30, 60),
        rint(60, 300), rfloat(1.5, 4.5), rfloat(40, 65),
        rfloat(1.5, 8.0), rchoice(sources), rfloat(25, 60)
    ))
conn.executemany("INSERT INTO web_analytics (date,sessions,unique_visitors,bounce_rate,avg_duration_secs,pages_per_session,new_visitor_pct,conversion_rate,top_source,organic_pct) VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   web_analytics: {len(rows)} rows ✓")

# ── marketing_kpis ─────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS marketing_kpis")
conn.execute("""CREATE TABLE marketing_kpis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT, kpi_name TEXT, current_value REAL,
    target_value REAL, unit TEXT, trend TEXT, status TEXT
)""")
mkt_kpis = [
    ("CAC ($)", 1250, 1000, "$", "down", "yellow"),
    ("MQLs Generated", 842, 1000, "count", "up", "yellow"),
    ("MQL to SQL Rate (%)", 38.5, 40.0, "%", "up", "yellow"),
    ("ROAS", 4.2, 5.0, "ratio", "up", "yellow"),
    ("Website Conversion Rate (%)", 3.8, 4.5, "%", "up", "yellow"),
    ("NPS Score", 42, 50, "score", "up", "yellow"),
    ("Brand Sentiment (%positive)", 62, 70, "%", "up", "yellow"),
    ("Email Open Rate (%)", 24.5, 25.0, "%", "flat", "green"),
]
rows = []
for period in ["2024-Q3","2024-Q4","2025-Q1","2025-Q2"]:
    for name, cur, tgt, unit, trend, status in mkt_kpis:
        rows.append((period, name, round(cur*rfloat(0.9,1.1),2), tgt, unit, trend, status))
conn.executemany("INSERT INTO marketing_kpis (period,kpi_name,current_value,target_value,unit,trend,status) VALUES (?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   marketing_kpis: {len(rows)} rows ✓")

# ══════════════════════════════════════════════════════════════════════════════
# IT DEPARTMENT
# ══════════════════════════════════════════════════════════════════════════════
print("\n   IT Department...")

# Update systems
for col, defn in [
    ("uptime_pct",        "REAL DEFAULT 99.9"),
    ("cpu_utilization",   "REAL DEFAULT 0"),
    ("memory_pct",        "REAL DEFAULT 0"),
    ("storage_used_pct",  "REAL DEFAULT 0"),
    ("last_patched",      "TEXT"),
    ("patch_compliance",  "REAL DEFAULT 0"),
    ("environment",       "TEXT DEFAULT 'Production'"),
]:
    try: conn.execute(f"ALTER TABLE systems ADD COLUMN {col} {defn}")
    except: pass

for row in conn.execute("SELECT system_id FROM systems").fetchall():
    sid = row[0]
    conn.execute("""UPDATE systems SET uptime_pct=?,cpu_utilization=?,memory_pct=?,
        storage_used_pct=?,last_patched=?,patch_compliance=?,environment=? WHERE system_id=?""", (
        rfloat(95.0, 99.99), rfloat(10, 85), rfloat(20, 90),
        rfloat(15, 88), rdate("2024-01-01","2025-09-01"),
        rfloat(80, 100), rchoice(["Production","Staging","Development","DR"]), sid
    ))
conn.commit()
print("   systems updated ✓")

# ── it_incidents ───────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS it_incidents")
conn.execute("""CREATE TABLE it_incidents (
    ticket_id       TEXT PRIMARY KEY,
    type            TEXT,
    priority        TEXT,
    category        TEXT,
    raised_by       TEXT,
    assigned_to     TEXT,
    created_at      TEXT,
    acknowledged_at TEXT,
    resolved_at     TEXT,
    mtta_mins       INTEGER,
    mttr_hours      REAL,
    first_contact_resolved INTEGER,
    sla_target_hrs  INTEGER,
    sla_met         INTEGER,
    csat_score      REAL,
    root_cause      TEXT
)""")
ticket_types = ["Incident","Service Request","Problem","Change"]
priorities   = ["P1-Critical","P2-High","P3-Medium","P4-Low"]
categories   = ["Network","Hardware","Software","Security","Access","Email","Database","Cloud"]
root_causes  = ["Human Error","Software Bug","Hardware Failure","Configuration","Capacity","Vendor","Unknown"]
rows = []
for i in range(1, 2001):
    prio = rchoice(priorities)
    sla  = {"P1-Critical":4,"P2-High":8,"P3-Medium":24,"P4-Low":72}[prio]
    mttr = rfloat(0.5, sla * 1.5)
    mtta = rint(1, 60)
    created = rdatetime("2024-01-01","2025-09-01")
    rows.append((
        f"TKT-{i:05d}", rchoice(ticket_types), prio, rchoice(categories),
        f"user_{rint(1,500)}", f"agent_{rint(1,50)}", created,
        created, rdate("2024-01-01","2025-09-30"), mtta, round(mttr,2),
        1 if random.random()>0.35 else 0, sla,
        1 if mttr <= sla else 0,
        rfloat(3.0, 5.0) if random.random()>0.3 else None,
        rchoice(root_causes)
    ))
conn.executemany("INSERT INTO it_incidents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   it_incidents: {len(rows)} rows ✓")

# ── it_assets ──────────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS it_assets")
conn.execute("""CREATE TABLE it_assets (
    asset_id        TEXT PRIMARY KEY,
    asset_type      TEXT,
    brand           TEXT,
    model           TEXT,
    serial_number   TEXT,
    assigned_to     TEXT,
    department      TEXT,
    purchase_date   TEXT,
    warranty_expiry TEXT,
    asset_value     REAL,
    status          TEXT,
    location        TEXT
)""")
asset_types = ["Laptop","Desktop","Monitor","Phone","Tablet","Server","Network Switch","Printer"]
brands      = ["Apple","Dell","HP","Lenovo","Cisco","Samsung","Microsoft"]
rows = []
for i, eid in enumerate(random.sample(emp_ids, min(1500, len(emp_ids)))):
    atype = rchoice(asset_types)
    pur   = rdate("2020-01-01","2024-12-01")
    exp   = (datetime.strptime(pur,"%Y-%m-%d") + timedelta(days=365*3)).strftime("%Y-%m-%d")
    rows.append((
        f"ASSET-{i+1:05d}", atype, rchoice(brands),
        f"Model-{rint(100,999)}", f"SN-{rint(100000,999999)}",
        eid, rchoice(DEPTS), pur, exp, rfloat(200, 5000),
        rchoice(["Active","In Repair","Retired","In Storage"]),
        rchoice(["HQ","Remote","Branch Office"])
    ))
conn.executemany("INSERT INTO it_assets VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   it_assets: {len(rows)} rows ✓")

# ── security_events ────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS security_events")
conn.execute("""CREATE TABLE security_events (
    event_id        TEXT PRIMARY KEY,
    event_date      TEXT,
    type            TEXT,
    severity        TEXT,
    affected_system TEXT,
    source_ip       TEXT,
    detected_by     TEXT,
    resolved        INTEGER,
    resolution_hrs  REAL,
    patch_applied   INTEGER,
    incident_report TEXT
)""")
sec_types  = ["Phishing Attempt","Malware Detection","Unauthorized Access","Data Exfiltration",
               "DDoS","Vulnerability Scan","Password Breach","Insider Threat"]
severities = ["Critical","High","Medium","Low","Informational"]
detectors  = ["SIEM","Endpoint Detection","Firewall","User Report","Vulnerability Scanner","IDS/IPS"]
rows = []
for i in range(1, 501):
    resolved = 1 if random.random() > 0.1 else 0
    rows.append((
        f"SEC-{i:04d}", rdate("2023-01-01","2025-09-01"),
        rchoice(sec_types), rchoice(severities),
        f"SYS-{rint(1,50):03d}",
        f"{rint(1,255)}.{rint(1,255)}.{rint(1,255)}.{rint(1,255)}",
        rchoice(detectors), resolved,
        rfloat(0.5, 72) if resolved else None,
        1 if random.random()>0.3 else 0, f"IR-{i:04d}" if resolved else None
    ))
conn.executemany("INSERT INTO security_events VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   security_events: {len(rows)} rows ✓")

# ── change_requests ────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS change_requests")
conn.execute("""CREATE TABLE change_requests (
    change_id       TEXT PRIMARY KEY,
    title           TEXT,
    type            TEXT,
    risk_level      TEXT,
    requested_by    TEXT,
    approved_by     TEXT,
    requested_date  TEXT,
    approved_date   TEXT,
    implemented_date TEXT,
    status          TEXT,
    success         INTEGER,
    rollback_required INTEGER,
    downtime_mins   INTEGER
)""")
chg_types = ["Standard","Normal","Emergency","Major"]
rows = []
for i in range(1, 401):
    req  = rdate("2023-01-01","2025-08-01")
    appr = rdate(req,"2025-09-01")
    impl = rdate(appr,"2025-09-30")
    success = 1 if random.random()>0.1 else 0
    rows.append((
        f"CHG-{i:04d}", f"Change Request {i}",
        rchoice(chg_types), rchoice(["High","Medium","Low"]),
        f"REQ-{rint(1,100):03d}", f"MGR-{rint(1,20):03d}",
        req, appr, impl,
        rchoice(["Completed","In Progress","Failed","Cancelled"]),
        success, 0 if success else 1, rint(0, 240)
    ))
conn.executemany("INSERT INTO change_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   change_requests: {len(rows)} rows ✓")

# ── it_kpis ────────────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS it_kpis")
conn.execute("""CREATE TABLE it_kpis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT, kpi_name TEXT, current_value REAL,
    target_value REAL, unit TEXT, trend TEXT, status TEXT
)""")
it_kpi_data = [
    ("MTTR (hours)", 6.2, 4.0, "hours", "down", "yellow"),
    ("First Contact Resolution (%)", 74.5, 80.0, "%", "up", "yellow"),
    ("SLA Compliance (%)", 91.2, 95.0, "%", "up", "yellow"),
    ("System Uptime (%)", 99.7, 99.9, "%", "up", "green"),
    ("Patch Compliance (%)", 87.3, 95.0, "%", "up", "yellow"),
    ("Ticket Volume (monthly)", 1842, 1500, "count", "down", "yellow"),
    ("CSAT Score", 4.1, 4.5, "score", "up", "yellow"),
    ("Change Success Rate (%)", 94.5, 97.0, "%", "up", "green"),
    ("Security Incidents", 12, 5, "count", "down", "red"),
    ("Cost Per Ticket ($)", 28.5, 25.0, "$", "down", "yellow"),
]
rows = []
for period in ["2024-Q3","2024-Q4","2025-Q1","2025-Q2"]:
    for name, cur, tgt, unit, trend, status in it_kpi_data:
        rows.append((period, name, round(cur*rfloat(0.9,1.1),2), tgt, unit, trend, status))
conn.executemany("INSERT INTO it_kpis (period,kpi_name,current_value,target_value,unit,trend,status) VALUES (?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   it_kpis: {len(rows)} rows ✓")

# ══════════════════════════════════════════════════════════════════════════════
# OPERATIONS DEPARTMENT
# ══════════════════════════════════════════════════════════════════════════════
print("\n   Operations Department...")

# Update logistics
for col, defn in [
    ("freight_cost",       "REAL DEFAULT 0"),
    ("on_time_flag",       "INTEGER DEFAULT 1"),
    ("delay_reason",       "TEXT"),
    ("actual_delivery",    "TEXT"),
    ("weight_kg",          "REAL DEFAULT 0"),
]:
    try: conn.execute(f"ALTER TABLE logistics ADD COLUMN {col} {defn}")
    except: pass

for row in conn.execute("SELECT shipment_id FROM logistics").fetchall():
    sid = row[0]
    on_time = 1 if random.random()>0.2 else 0
    conn.execute("""UPDATE logistics SET freight_cost=?,on_time_flag=?,delay_reason=?,
        actual_delivery=?,weight_kg=? WHERE shipment_id=?""", (
        rfloat(50, 5000), on_time,
        rchoice(["Weather","Customs","Carrier Delay",None]) if not on_time else None,
        rdate("2024-01-01","2025-09-30"), rfloat(1, 5000), sid
    ))
conn.commit()
print("   logistics updated ✓")

# ── production_metrics ─────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS production_metrics")
conn.execute("""CREATE TABLE production_metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT,
    facility_id     TEXT,
    shift           TEXT,
    units_produced  INTEGER,
    units_target    INTEGER,
    defect_rate     REAL,
    yield_rate      REAL,
    oee_score       REAL,
    downtime_mins   INTEGER,
    planned_downtime INTEGER,
    unplanned_downtime INTEGER
)""")
facilities = [f"FAC-{i:02d}" for i in range(1,6)]
rows = []
for i in range(500):
    d = (datetime(2025,1,1) - timedelta(days=i)).strftime("%Y-%m-%d")
    for facility in random.sample(facilities, 2):
        target = rint(500, 2000)
        produced = int(target * rfloat(0.8, 1.05))
        defect = rfloat(0.5, 5.0)
        dt_total = rint(0, 120)
        rows.append((
            d, facility, rchoice(["Morning","Afternoon","Night"]),
            produced, target, defect, round(100-defect,2),
            rfloat(65, 95), dt_total, rint(0, dt_total), rint(0, dt_total//2)
        ))
conn.executemany("INSERT INTO production_metrics (date,facility_id,shift,units_produced,units_target,defect_rate,yield_rate,oee_score,downtime_mins,planned_downtime,unplanned_downtime) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   production_metrics: {len(rows)} rows ✓")

# ── inventory ──────────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS inventory")
conn.execute("""CREATE TABLE inventory (
    sku             TEXT PRIMARY KEY,
    product_name    TEXT,
    category        TEXT,
    quantity_on_hand INTEGER,
    reorder_point   INTEGER,
    reorder_qty     INTEGER,
    lead_time_days  INTEGER,
    unit_cost       REAL,
    total_value     REAL,
    turnover_ratio  REAL,
    stockout_events INTEGER,
    warehouse       TEXT
)""")
categories = ["Raw Materials","WIP","Finished Goods","Spare Parts","Packaging","Office Supplies"]
warehouses = ["WH-North","WH-South","WH-East","WH-West","WH-Central"]
rows = []
for i in range(1, 401):
    qty    = rint(0, 5000)
    reorder= rint(50, 500)
    cost   = rfloat(1, 500)
    rows.append((
        f"SKU-{i:05d}", f"Product-{i}", rchoice(categories),
        qty, reorder, reorder*2, rint(1, 30),
        cost, round(qty*cost, 2), rfloat(2, 20),
        rint(0, 10), rchoice(warehouses)
    ))
conn.executemany("INSERT INTO inventory VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   inventory: {len(rows)} rows ✓")

# ── quality_control ────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS quality_control")
conn.execute("""CREATE TABLE quality_control (
    inspection_id   TEXT PRIMARY KEY,
    date            TEXT,
    product_id      TEXT,
    batch_id        TEXT,
    units_inspected INTEGER,
    units_passed    INTEGER,
    defects_found   INTEGER,
    pass_rate       REAL,
    return_rate     REAL,
    inspector       TEXT,
    disposition     TEXT
)""")
dispositions = ["Accepted","Rejected","Rework","Quarantine"]
rows = []
for i in range(1, 601):
    inspected = rint(100, 1000)
    defects   = rint(0, int(inspected*0.1))
    passed    = inspected - defects
    rows.append((
        f"QC-{i:05d}", rdate("2023-01-01","2025-09-01"),
        f"SKU-{rint(1,400):05d}", f"BATCH-{rint(1,200):04d}",
        inspected, passed, defects,
        round(passed/inspected*100, 2), rfloat(0, 5),
        f"Inspector-{rint(1,20):02d}", rchoice(dispositions)
    ))
conn.executemany("INSERT INTO quality_control VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   quality_control: {len(rows)} rows ✓")

# ── facility_metrics ───────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS facility_metrics")
conn.execute("""CREATE TABLE facility_metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    period          TEXT,
    facility_id     TEXT,
    energy_kwh      REAL,
    energy_cost     REAL,
    maintenance_cost REAL,
    safety_incidents INTEGER,
    capacity_util_pct REAL,
    sq_footage      INTEGER,
    headcount       INTEGER
)""")
rows = []
for facility in facilities:
    for period in ["2023-Q1","2023-Q2","2023-Q3","2023-Q4",
                   "2024-Q1","2024-Q2","2024-Q3","2024-Q4","2025-Q1","2025-Q2"]:
        kwh = rfloat(50000, 500000)
        rows.append((
            period, facility, kwh, round(kwh*0.12, 2),
            rfloat(5000, 100000), rint(0, 5),
            rfloat(60, 98), rint(10000, 100000), rint(50, 500)
        ))
conn.executemany("INSERT INTO facility_metrics (period,facility_id,energy_kwh,energy_cost,maintenance_cost,safety_incidents,capacity_util_pct,sq_footage,headcount) VALUES (?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   facility_metrics: {len(rows)} rows ✓")

# ── ops_kpis ───────────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS ops_kpis")
conn.execute("""CREATE TABLE ops_kpis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT, kpi_name TEXT, current_value REAL,
    target_value REAL, unit TEXT, trend TEXT, status TEXT
)""")
ops_kpi_data = [
    ("OEE Score (%)", 82.3, 85.0, "%", "up", "yellow"),
    ("On-Time Delivery (%)", 94.2, 98.0, "%", "up", "yellow"),
    ("Defect Rate (%)", 2.1, 1.0, "%", "down", "yellow"),
    ("Inventory Turnover", 8.5, 10.0, "ratio", "up", "yellow"),
    ("Capacity Utilization (%)", 78.4, 85.0, "%", "up", "yellow"),
    ("Safety Incidents", 3, 0, "count", "down", "yellow"),
    ("Operating Cost/Unit ($)", 24.5, 22.0, "$", "down", "yellow"),
    ("Stockout Rate (%)", 2.8, 1.0, "%", "down", "red"),
]
rows = []
for period in ["2024-Q3","2024-Q4","2025-Q1","2025-Q2"]:
    for name, cur, tgt, unit, trend, status in ops_kpi_data:
        rows.append((period, name, round(cur*rfloat(0.9,1.1),2), tgt, unit, trend, status))
conn.executemany("INSERT INTO ops_kpis (period,kpi_name,current_value,target_value,unit,trend,status) VALUES (?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   ops_kpis: {len(rows)} rows ✓")

# ══════════════════════════════════════════════════════════════════════════════
# PROCUREMENT DEPARTMENT
# ══════════════════════════════════════════════════════════════════════════════
print("\n   Procurement Department...")

# Update purchase_orders
for col, defn in [
    ("po_cycle_days",     "INTEGER DEFAULT 0"),
    ("requisition_date",  "TEXT"),
    ("maverick_flag",     "INTEGER DEFAULT 0"),
    ("unit_price",        "REAL DEFAULT 0"),
    ("quantity",          "INTEGER DEFAULT 1"),
    ("item_description",  "TEXT"),
]:
    try: conn.execute(f"ALTER TABLE purchase_orders ADD COLUMN {col} {defn}")
    except: pass

for row in conn.execute("SELECT po_id, raised_date FROM purchase_orders").fetchall():
    pid, raised = row
    req_date = rdate("2022-01-01", raised if raised else "2025-01-01")
    conn.execute("""UPDATE purchase_orders SET po_cycle_days=?,requisition_date=?,
        maverick_flag=?,unit_price=?,quantity=?,item_description=? WHERE po_id=?""", (
        rint(1, 20), req_date, 1 if random.random()<0.08 else 0,
        rfloat(10, 50000), rint(1, 500), f"Item description for {pid}", pid
    ))
conn.commit()
print("   purchase_orders updated ✓")

# Update suppliers
for col, defn in [
    ("risk_rating",       "TEXT DEFAULT 'Low'"),
    ("esg_score",         "REAL DEFAULT 0"),
    ("diversity_certified","INTEGER DEFAULT 0"),
    ("carbon_footprint",  "REAL DEFAULT 0"),
    ("payment_terms",     "TEXT DEFAULT 'Net 30'"),
    ("lead_time_days",    "INTEGER DEFAULT 0"),
]:
    try: conn.execute(f"ALTER TABLE suppliers ADD COLUMN {col} {defn}")
    except: pass

for sid in sup_ids:
    conn.execute("""UPDATE suppliers SET risk_rating=?,esg_score=?,diversity_certified=?,
        carbon_footprint=?,payment_terms=?,lead_time_days=? WHERE supplier_id=?""", (
        rchoice(["Low","Medium","High","Critical"]),
        rfloat(30, 95), 1 if random.random()>0.7 else 0,
        rfloat(10, 5000), rchoice(["Net 15","Net 30","Net 45","Net 60"]),
        rint(1, 60), sid
    ))
conn.commit()
print("   suppliers updated ✓")

# ── spend_analytics ────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS spend_analytics")
conn.execute("""CREATE TABLE spend_analytics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    period          TEXT,
    category        TEXT,
    department      TEXT,
    supplier_id     TEXT,
    amount          REAL,
    contract_spend  INTEGER,
    maverick_flag   INTEGER,
    savings_achieved REAL,
    payment_terms   TEXT
)""")
spend_cats = ["IT Software","IT Hardware","Professional Services","Marketing",
              "Facilities","Travel","Raw Materials","Logistics","Legal","HR Services"]
rows = []
for i in range(1, 1001):
    rows.append((
        rperiod(), rchoice(spend_cats), rchoice(DEPTS),
        rchoice(sup_ids) if sup_ids else f"SUP-{rint(1,200):04d}",
        rfloat(1000, 500000), 1 if random.random()>0.15 else 0,
        1 if random.random()<0.08 else 0,
        rfloat(0, 50000), rchoice(["Net 15","Net 30","Net 45","Net 60"])
    ))
conn.executemany("INSERT INTO spend_analytics (period,category,department,supplier_id,amount,contract_spend,maverick_flag,savings_achieved,payment_terms) VALUES (?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   spend_analytics: {len(rows)} rows ✓")

# ── sourcing_events ────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS sourcing_events")
conn.execute("""CREATE TABLE sourcing_events (
    event_id        TEXT PRIMARY KEY,
    category        TEXT,
    description     TEXT,
    bidders_invited INTEGER,
    responses       INTEGER,
    awarded_to      TEXT,
    award_value     REAL,
    savings_pct     REAL,
    method          TEXT,
    start_date      TEXT,
    close_date      TEXT,
    status          TEXT
)""")
methods = ["Open Tender","RFP","RFQ","Sole Source","Framework","e-Auction"]
rows = []
for i in range(1, 301):
    bidders = rint(2, 12)
    rows.append((
        f"SRC-{i:04d}", rchoice(spend_cats), f"Sourcing event {i}",
        bidders, rint(1, bidders),
        rchoice(sup_ids) if sup_ids else f"SUP-{rint(1,200):04d}",
        rfloat(10000, 2000000), rfloat(2, 25),
        rchoice(methods), rdate("2023-01-01","2025-06-01"),
        rdate("2023-03-01","2025-09-01"),
        rchoice(["Completed","In Progress","Cancelled","Awarded"])
    ))
conn.executemany("INSERT INTO sourcing_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   sourcing_events: {len(rows)} rows ✓")

# ── supplier_contracts ─────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS supplier_contracts")
conn.execute("""CREATE TABLE supplier_contracts (
    contract_id     TEXT PRIMARY KEY,
    supplier_id     TEXT,
    category        TEXT,
    contract_type   TEXT,
    value           REAL,
    start_date      TEXT,
    end_date        TEXT,
    auto_renewal    INTEGER,
    compliance_pct  REAL,
    status          TEXT,
    owner           TEXT
)""")
contract_types = ["Master Service Agreement","Purchase Agreement","Framework","SLA","NDA","Subscription"]
rows = []
for i in range(1, 301):
    start = rdate("2020-01-01","2024-01-01")
    end   = rdate("2024-06-01","2027-12-31")
    rows.append((
        f"CON-{i:04d}", rchoice(sup_ids) if sup_ids else f"SUP-{rint(1,200):04d}",
        rchoice(spend_cats), rchoice(contract_types),
        rfloat(10000, 5000000), start, end,
        1 if random.random()>0.4 else 0, rfloat(75, 100),
        rchoice(["Active","Expiring Soon","Expired","Terminated","Under Negotiation"]),
        f"Procurement-{rint(1,30):02d}"
    ))
conn.executemany("INSERT INTO supplier_contracts VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   supplier_contracts: {len(rows)} rows ✓")

# ── procurement_kpis ───────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS procurement_kpis")
conn.execute("""CREATE TABLE procurement_kpis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT, kpi_name TEXT, current_value REAL,
    target_value REAL, unit TEXT, trend TEXT, status TEXT
)""")
proc_kpis = [
    ("Spend Under Management (%)", 72.5, 85.0, "%", "up", "yellow"),
    ("Cost Savings ($M)", 2.4, 3.0, "$M", "up", "yellow"),
    ("Maverick Spend (%)", 8.2, 5.0, "%", "down", "red"),
    ("PO Cycle Time (days)", 6.8, 5.0, "days", "down", "yellow"),
    ("Supplier On-Time Delivery (%)", 91.4, 95.0, "%", "up", "yellow"),
    ("Supplier Defect Rate (%)", 2.3, 1.0, "%", "down", "yellow"),
    ("Contract Compliance (%)", 84.2, 90.0, "%", "up", "yellow"),
    ("Supplier Diversity (%)", 18.5, 25.0, "%", "up", "yellow"),
]
rows = []
for period in ["2024-Q3","2024-Q4","2025-Q1","2025-Q2"]:
    for name, cur, tgt, unit, trend, status in proc_kpis:
        rows.append((period, name, round(cur*rfloat(0.9,1.1),2), tgt, unit, trend, status))
conn.executemany("INSERT INTO procurement_kpis (period,kpi_name,current_value,target_value,unit,trend,status) VALUES (?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   procurement_kpis: {len(rows)} rows ✓")

# ══════════════════════════════════════════════════════════════════════════════
# LEGAL DEPARTMENT
# ══════════════════════════════════════════════════════════════════════════════
print("\n   Legal Department...")

# Update cases
for col, defn in [
    ("assigned_attorney",  "TEXT"),
    ("external_counsel",   "TEXT"),
    ("claim_amount",       "REAL DEFAULT 0"),
    ("estimated_liability","REAL DEFAULT 0"),
    ("win_flag",           "INTEGER"),
    ("hours_spent",        "REAL DEFAULT 0"),
    ("jurisdiction",       "TEXT"),
]:
    try: conn.execute(f"ALTER TABLE cases ADD COLUMN {col} {defn}")
    except: pass

for row in conn.execute("SELECT case_id FROM cases").fetchall():
    cid = row[0]
    conn.execute("""UPDATE cases SET assigned_attorney=?,external_counsel=?,
        claim_amount=?,estimated_liability=?,win_flag=?,hours_spent=?,jurisdiction=?
        WHERE case_id=?""", (
        f"Attorney-{rint(1,15):02d}",
        rchoice(["Kirkland & Ellis","Latham & Watkins","Jones Day","Baker McKenzie",None]),
        rfloat(10000, 10000000), rfloat(5000, 5000000),
        rchoice([0,1,None]), rfloat(1, 500),
        rchoice(["US Federal","California","New York","UK","EU","Singapore"]), cid
    ))
conn.commit()
print("   cases updated ✓")

# Update contracts_db
for col, defn in [
    ("review_time_days",   "INTEGER DEFAULT 0"),
    ("risk_level",         "TEXT DEFAULT 'Low'"),
    ("signed_status",      "TEXT DEFAULT 'Signed'"),
    ("counterparty_type",  "TEXT DEFAULT 'Vendor'"),
    ("auto_renewal",       "INTEGER DEFAULT 0"),
    ("responsible_attorney","TEXT"),
]:
    try: conn.execute(f"ALTER TABLE contracts_db ADD COLUMN {col} {defn}")
    except: pass

for row in conn.execute("SELECT contract_id FROM contracts_db").fetchall():
    cid = row[0]
    conn.execute("""UPDATE contracts_db SET review_time_days=?,risk_level=?,signed_status=?,
        counterparty_type=?,auto_renewal=?,responsible_attorney=? WHERE contract_id=?""", (
        rint(1, 45), rchoice(["Low","Medium","High","Critical"]),
        rchoice(["Signed","Pending","Under Review","Executed"]),
        rchoice(["Vendor","Customer","Partner","Employee","Regulator"]),
        1 if random.random()>0.5 else 0, f"Attorney-{rint(1,15):02d}", cid
    ))
conn.commit()
print("   contracts_db updated ✓")

# ── legal_spend ────────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS legal_spend")
conn.execute("""CREATE TABLE legal_spend (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id       TEXT,
    law_firm        TEXT,
    invoice_date    TEXT,
    hours_billed    REAL,
    rate_per_hour   REAL,
    amount          REAL,
    matter_type     TEXT,
    approved        INTEGER,
    budget_amount   REAL
)""")
law_firms    = ["Kirkland & Ellis","Latham & Watkins","Jones Day","Baker McKenzie",
                "Skadden","Clifford Chance","Linklaters","Allen & Overy","Internal"]
matter_types = ["Litigation","Contract","Compliance","IP","M&A","Employment","Regulatory"]
rows = []
for i in range(1, 601):
    hours = rfloat(1, 200)
    rate  = rfloat(200, 800)
    rows.append((
        f"MATTER-{rint(1,200):04d}", rchoice(law_firms),
        rdate("2023-01-01","2025-09-01"),
        hours, rate, round(hours*rate, 2),
        rchoice(matter_types), 1 if random.random()>0.05 else 0,
        rfloat(10000, 500000)
    ))
conn.executemany("INSERT INTO legal_spend (matter_id,law_firm,invoice_date,hours_billed,rate_per_hour,amount,matter_type,approved,budget_amount) VALUES (?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   legal_spend: {len(rows)} rows ✓")

# ── ip_portfolio ───────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS ip_portfolio")
conn.execute("""CREATE TABLE ip_portfolio (
    patent_id           TEXT PRIMARY KEY,
    title               TEXT,
    type                TEXT,
    filing_date         TEXT,
    grant_date          TEXT,
    jurisdiction        TEXT,
    status              TEXT,
    annuity_due_date    TEXT,
    licensing_revenue   REAL,
    inventors           TEXT,
    technology_area     TEXT
)""")
ip_types   = ["Utility Patent","Design Patent","Trademark","Copyright","Trade Secret"]
ip_status  = ["Granted","Pending","Abandoned","Licensed","Under Opposition"]
tech_areas = ["AI/ML","Cloud Computing","Security","IoT","Blockchain","Data Analytics","UI/UX"]
rows = []
for i in range(1, 151):
    filed = rdate("2015-01-01","2024-12-01")
    grant = rdate(filed,"2025-06-01") if random.random()>0.3 else None
    rows.append((
        f"PAT-{i:04d}", f"Patent Title {i}", rchoice(ip_types),
        filed, grant, rchoice(["US","EU","UK","China","Japan","India","Global"]),
        rchoice(ip_status), rdate("2025-01-01","2030-12-31"),
        rfloat(0, 500000) if random.random()>0.7 else 0.0,
        f"Inventor-{rint(1,50)}", rchoice(tech_areas)
    ))
conn.executemany("INSERT INTO ip_portfolio VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   ip_portfolio: {len(rows)} rows ✓")

# ── regulatory_tracker ─────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS regulatory_tracker")
conn.execute("""CREATE TABLE regulatory_tracker (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    regulation      TEXT,
    jurisdiction    TEXT,
    category        TEXT,
    deadline        TEXT,
    responsible     TEXT,
    status          TEXT,
    training_pct    REAL,
    last_audit_date TEXT,
    next_audit_date TEXT,
    risk_level      TEXT
)""")
regulations = ["GDPR","CCPA","SOX","HIPAA","ISO 27001","PCI DSS","OSHA","FCPA",
                "Anti-Bribery","Data Residency","Employment Law","ESG Reporting"]
reg_cats    = ["Data Privacy","Financial","Security","Environmental","Labor","Anti-Corruption"]
rows = []
for reg in regulations:
    for jurisdiction in random.sample(["US","EU","UK","Singapore","Canada"], 2):
        rows.append((
            reg, jurisdiction, rchoice(reg_cats),
            rdate("2025-01-01","2026-12-31"), f"Legal-{rint(1,10):02d}",
            rchoice(["Compliant","At Risk","Non-Compliant","Under Review"]),
            rfloat(60, 100), rdate("2024-01-01","2025-06-01"),
            rdate("2025-06-01","2026-06-01"), rchoice(["High","Medium","Low"])
        ))
conn.executemany("INSERT INTO regulatory_tracker (regulation,jurisdiction,category,deadline,responsible,status,training_pct,last_audit_date,next_audit_date,risk_level) VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   regulatory_tracker: {len(rows)} rows ✓")

# ── legal_kpis ─────────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS legal_kpis")
conn.execute("""CREATE TABLE legal_kpis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT, kpi_name TEXT, current_value REAL,
    target_value REAL, unit TEXT, trend TEXT, status TEXT
)""")
legal_kpi_data = [
    ("Legal Spend/Revenue (%)", 0.8, 0.6, "%", "down", "yellow"),
    ("Contract Review Time (days)", 12.4, 7.0, "days", "down", "yellow"),
    ("Matter Cycle Time (days)", 45.2, 30.0, "days", "down", "yellow"),
    ("Litigation Win Rate (%)", 68.5, 75.0, "%", "up", "yellow"),
    ("Compliance Training (%)", 88.2, 95.0, "%", "up", "yellow"),
    ("Open Matters", 124, 100, "count", "down", "yellow"),
    ("Outside Counsel Spend (%)", 42.5, 35.0, "%", "down", "yellow"),
    ("Contracts Expiring 90d", 18, 10, "count", "down", "yellow"),
]
rows = []
for period in ["2024-Q3","2024-Q4","2025-Q1","2025-Q2"]:
    for name, cur, tgt, unit, trend, status in legal_kpi_data:
        rows.append((period, name, round(cur*rfloat(0.9,1.1),2), tgt, unit, trend, status))
conn.executemany("INSERT INTO legal_kpis (period,kpi_name,current_value,target_value,unit,trend,status) VALUES (?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   legal_kpis: {len(rows)} rows ✓")

# ══════════════════════════════════════════════════════════════════════════════
# R&D DEPARTMENT
# ══════════════════════════════════════════════════════════════════════════════
print("\n   R&D Department...")

# Update rd_projects
for col, defn in [
    ("stage",              "TEXT DEFAULT 'Development'"),
    ("rd_spend_pct_rev",   "REAL DEFAULT 0"),
    ("time_to_market_days","INTEGER DEFAULT 0"),
    ("collab_type",        "TEXT"),
    ("university_partner", "TEXT"),
]:
    try: conn.execute(f"ALTER TABLE rd_projects ADD COLUMN {col} {defn}")
    except: pass

stages = ["Ideation","Prototype","Testing","Validation","Launch","Post-Launch"]
collabs= ["Internal Only","University","Open Source","Industry Consortium","Startup Partnership"]
unis   = ["MIT","Stanford","Carnegie Mellon","ETH Zurich","Oxford","None"]
for row in conn.execute("SELECT project_id FROM rd_projects").fetchall():
    pid = row[0]
    conn.execute("""UPDATE rd_projects SET stage=?,rd_spend_pct_rev=?,
        time_to_market_days=?,collab_type=?,university_partner=? WHERE project_id=?""", (
        rchoice(stages), rfloat(3, 20), rint(90, 730),
        rchoice(collabs), rchoice(unis), pid
    ))
conn.commit()
print("   rd_projects updated ✓")

# ── innovation_pipeline ────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS innovation_pipeline")
conn.execute("""CREATE TABLE innovation_pipeline (
    idea_id         TEXT PRIMARY KEY,
    title           TEXT,
    submitted_by    TEXT,
    submit_date     TEXT,
    category        TEXT,
    stage           TEXT,
    potential_revenue REAL,
    implementation_cost REAL,
    roi_estimate    REAL,
    approved        INTEGER,
    approved_date   TEXT,
    champion        TEXT
)""")
idea_cats = ["Product Feature","Process Improvement","Cost Reduction","New Market",
              "Technology Platform","Customer Experience","Sustainability"]
idea_stages = ["Submitted","Under Review","Approved","In Development","Piloting","Launched","Rejected"]
rows = []
for i in range(1, 301):
    pot_rev = rfloat(10000, 5000000)
    impl    = rfloat(5000, 1000000)
    rows.append((
        f"IDEA-{i:04d}", f"Innovation Idea {i}",
        rchoice(emp_ids), rdate("2023-01-01","2025-09-01"),
        rchoice(idea_cats), rchoice(idea_stages),
        pot_rev, impl, round((pot_rev - impl)/impl*100, 1),
        1 if random.random()>0.4 else 0, rdate("2023-03-01","2025-09-01"),
        rchoice(emp_ids)
    ))
conn.executemany("INSERT INTO innovation_pipeline VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   innovation_pipeline: {len(rows)} rows ✓")

# ── rd_talent ──────────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS rd_talent")
conn.execute("""CREATE TABLE rd_talent (
    researcher_id   TEXT PRIMARY KEY,
    employee_id     TEXT,
    specialization  TEXT,
    phd_flag        INTEGER,
    publications    INTEGER,
    patents_filed   INTEGER,
    citations       INTEGER,
    conferences     INTEGER,
    h_index         INTEGER,
    joined_date     TEXT
)""")
specs = ["Machine Learning","Computer Vision","NLP","Cybersecurity","Quantum Computing",
         "Biotech","Materials Science","Robotics","Data Engineering","Human-Computer Interaction"]
rows = []
sample_rd = random.sample(emp_ids, min(175, len(emp_ids)))
for i, eid in enumerate(sample_rd):
    rows.append((
        f"RES-{i+1:04d}", eid, rchoice(specs),
        1 if random.random()>0.4 else 0,
        rint(0, 50), rint(0, 15), rint(0, 500),
        rint(0, 20), rint(0, 25), rdate("2015-01-01","2024-12-01")
    ))
conn.executemany("INSERT INTO rd_talent VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   rd_talent: {len(rows)} rows ✓")

# ── rd_kpis ────────────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS rd_kpis")
conn.execute("""CREATE TABLE rd_kpis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT, kpi_name TEXT, current_value REAL,
    target_value REAL, unit TEXT, trend TEXT, status TEXT
)""")
rd_kpi_data = [
    ("R&D Spend/Revenue (%)", 11.2, 12.0, "%", "up", "green"),
    ("Time to Market (days)", 285, 240, "days", "down", "yellow"),
    ("Patent Applications/Year", 18, 25, "count", "up", "yellow"),
    ("R&D ROI (%)", 180, 200, "%", "up", "yellow"),
    ("New Product Revenue (%)", 28.5, 35.0, "%", "up", "yellow"),
    ("Project On-Time (%)", 72.4, 80.0, "%", "up", "yellow"),
    ("Experiment Success Rate (%)", 34.2, 40.0, "%", "up", "yellow"),
    ("Ideas in Pipeline", 45, 60, "count", "up", "yellow"),
]
rows = []
for period in ["2024-Q3","2024-Q4","2025-Q1","2025-Q2"]:
    for name, cur, tgt, unit, trend, status in rd_kpi_data:
        rows.append((period, name, round(cur*rfloat(0.9,1.1),2), tgt, unit, trend, status))
conn.executemany("INSERT INTO rd_kpis (period,kpi_name,current_value,target_value,unit,trend,status) VALUES (?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   rd_kpis: {len(rows)} rows ✓")

# ══════════════════════════════════════════════════════════════════════════════
# CUSTOMER SUCCESS DEPARTMENT
# ══════════════════════════════════════════════════════════════════════════════
print("\n   Customer Success Department...")

# Update cs_accounts
for col, defn in [
    ("mrr",               "REAL DEFAULT 0"),
    ("nrr_pct",           "REAL DEFAULT 100"),
    ("churn_risk_score",  "REAL DEFAULT 0"),
    ("last_login_date",   "TEXT"),
    ("feature_adoption",  "REAL DEFAULT 0"),
    ("mau",               "INTEGER DEFAULT 0"),
    ("time_to_value_days","INTEGER DEFAULT 0"),
    ("onboarding_done",   "INTEGER DEFAULT 0"),
    ("last_qbr_date",     "TEXT"),
    ("csm_owner",         "TEXT"),
]:
    try: conn.execute(f"ALTER TABLE cs_accounts ADD COLUMN {col} {defn}")
    except: pass

for row in conn.execute("SELECT account_id, arr FROM cs_accounts").fetchall():
    aid, arr = row
    mrr = round((arr or rfloat(10000,500000))/12, 2)
    conn.execute("""UPDATE cs_accounts SET mrr=?,nrr_pct=?,churn_risk_score=?,
        last_login_date=?,feature_adoption=?,mau=?,time_to_value_days=?,
        onboarding_done=?,last_qbr_date=?,csm_owner=? WHERE account_id=?""", (
        mrr, rfloat(85, 140), rfloat(0, 1),
        rdate("2025-01-01","2025-09-30"), rfloat(20, 95),
        rint(5, 2000), rint(7, 90), 1 if random.random()>0.1 else 0,
        rdate("2024-06-01","2025-09-01"), f"CSM-{rint(1,20):02d}", aid
    ))
conn.commit()
print("   cs_accounts updated ✓")

# ── churn_log ──────────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS churn_log")
conn.execute("""CREATE TABLE churn_log (
    churn_id        TEXT PRIMARY KEY,
    account_id      TEXT,
    churn_date      TEXT,
    arr_churned     REAL,
    mrr_churned     REAL,
    churn_reason    TEXT,
    churn_type      TEXT,
    early_warning   INTEGER,
    recovery_tried  INTEGER,
    csm_owner       TEXT
)""")
churn_reasons = ["Price/Budget","Competitor","Product Gap","Poor Adoption","Company Shutdown",
                  "Merger/Acquisition","Service Issues","Outgrown Product"]
rows = []
for i in range(1, 101):
    arr = rfloat(5000, 200000)
    rows.append((
        f"CHN-{i:04d}", rchoice(acct_ids) if acct_ids else f"ACC-{rint(1,220):04d}",
        rdate("2023-01-01","2025-09-01"), arr, round(arr/12, 2),
        rchoice(churn_reasons), rchoice(["Voluntary","Involuntary","Downsell"]),
        1 if random.random()>0.4 else 0, 1 if random.random()>0.3 else 0,
        f"CSM-{rint(1,20):02d}"
    ))
conn.executemany("INSERT INTO churn_log VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   churn_log: {len(rows)} rows ✓")

# ── product_usage ──────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS product_usage")
conn.execute("""CREATE TABLE product_usage (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      TEXT,
    date            TEXT,
    mau             INTEGER,
    dau             INTEGER,
    sessions_per_week REAL,
    features_used   INTEGER,
    total_features  INTEGER,
    adoption_pct    REAL,
    time_on_platform_mins REAL,
    api_calls       INTEGER
)""")
rows = []
sample_accts = random.sample(acct_ids, min(100, len(acct_ids))) if acct_ids else [f"ACC-{i:04d}" for i in range(1,101)]
for aid in sample_accts:
    for i in range(12):
        d = (datetime(2025,1,1) - timedelta(days=i*30)).strftime("%Y-%m-%d")
        mau = rint(5, 500)
        total_feat = 25
        feat_used  = rint(3, total_feat)
        rows.append((
            aid, d, mau, int(mau*rfloat(0.1,0.5)),
            rfloat(2, 20), feat_used, total_feat,
            round(feat_used/total_feat*100, 1),
            rfloat(10, 300), rint(100, 50000)
        ))
conn.executemany("INSERT INTO product_usage (account_id,date,mau,dau,sessions_per_week,features_used,total_features,adoption_pct,time_on_platform_mins,api_calls) VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   product_usage: {len(rows)} rows ✓")

# ── onboarding_tracker ─────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS onboarding_tracker")
conn.execute("""CREATE TABLE onboarding_tracker (
    onboarding_id   TEXT PRIMARY KEY,
    account_id      TEXT,
    start_date      TEXT,
    target_date     TEXT,
    actual_date     TEXT,
    milestones_total INTEGER,
    milestones_met  INTEGER,
    completion_pct  REAL,
    time_to_value   INTEGER,
    csm_assigned    TEXT,
    status          TEXT,
    health          TEXT
)""")
rows = []
for i, aid in enumerate(acct_ids[:200] if acct_ids else [f"ACC-{j:04d}" for j in range(1,201)]):
    start   = rdate("2022-01-01","2025-06-01")
    target  = (datetime.strptime(start,"%Y-%m-%d") + timedelta(days=30)).strftime("%Y-%m-%d")
    actual  = rdate(start, "2025-09-01") if random.random()>0.1 else None
    m_total = 8
    m_met   = rint(0, m_total)
    rows.append((
        f"ONB-{i+1:04d}", aid, start, target, actual,
        m_total, m_met, round(m_met/m_total*100,1),
        rint(7, 60), f"CSM-{rint(1,20):02d}",
        rchoice(["Completed","In Progress","At Risk","Stalled"]),
        rchoice(["Green","Yellow","Red"])
    ))
conn.executemany("INSERT INTO onboarding_tracker VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   onboarding_tracker: {len(rows)} rows ✓")

# ── expansion_revenue ──────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS expansion_revenue")
conn.execute("""CREATE TABLE expansion_revenue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      TEXT,
    date            TEXT,
    type            TEXT,
    arr_added       REAL,
    mrr_added       REAL,
    product_added   TEXT,
    csm_initiated   INTEGER,
    close_date      TEXT
)""")
exp_types = ["Upsell","Cross-Sell","Seat Expansion","Module Add-On","Premium Upgrade"]
products  = ["Analytics Module","Security Add-On","API Access","Premium Support",
             "Additional Users","Enterprise Features","Data Storage"]
rows = []
for i in range(1, 201):
    arr = rfloat(1000, 100000)
    rows.append((
        rchoice(acct_ids) if acct_ids else f"ACC-{rint(1,220):04d}",
        rdate("2023-01-01","2025-09-01"), rchoice(exp_types),
        arr, round(arr/12, 2), rchoice(products),
        1 if random.random()>0.4 else 0, rdate("2023-02-01","2025-09-30")
    ))
conn.executemany("INSERT INTO expansion_revenue (account_id,date,type,arr_added,mrr_added,product_added,csm_initiated,close_date) VALUES (?,?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   expansion_revenue: {len(rows)} rows ✓")

# ── cs_kpis ────────────────────────────────────────────────────────────────────
conn.execute("DROP TABLE IF EXISTS cs_kpis")
conn.execute("""CREATE TABLE cs_kpis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT, kpi_name TEXT, current_value REAL,
    target_value REAL, unit TEXT, trend TEXT, status TEXT
)""")
cs_kpi_data = [
    ("Net Revenue Retention (%)", 108.5, 115.0, "%", "up", "yellow"),
    ("Gross Retention (%)", 88.2, 90.0, "%", "up", "yellow"),
    ("Churn Rate (%)", 2.8, 2.0, "%", "down", "yellow"),
    ("NPS Score", 38, 50, "score", "up", "yellow"),
    ("CSAT Score", 4.2, 4.5, "score", "up", "yellow"),
    ("Customer Health (% green)", 68.5, 75.0, "%", "up", "yellow"),
    ("Time to Value (days)", 24, 14, "days", "down", "yellow"),
    ("Renewal Rate (%)", 87.4, 92.0, "%", "up", "yellow"),
    ("Expansion Revenue ($M)", 1.8, 2.5, "$M", "up", "yellow"),
    ("Onboarding Completion (%)", 84.5, 90.0, "%", "up", "yellow"),
]
rows = []
for period in ["2024-Q3","2024-Q4","2025-Q1","2025-Q2"]:
    for name, cur, tgt, unit, trend, status in cs_kpi_data:
        rows.append((period, name, round(cur*rfloat(0.9,1.1),2), tgt, unit, trend, status))
conn.executemany("INSERT INTO cs_kpis (period,kpi_name,current_value,target_value,unit,trend,status) VALUES (?,?,?,?,?,?,?)", rows)
conn.commit()
print(f"   cs_kpis: {len(rows)} rows ✓")

# ══════════════════════════════════════════════════════════════════════════════
# EXPORT ALL NEW TABLES TO CSV
# ══════════════════════════════════════════════════════════════════════════════
print("\n[3/5] Exporting all tables to CSV...")
all_tables = [t[0] for t in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()]

exported = 0
for table in all_tables:
    try:
        rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()
        cols = [c[1] for c in conn.execute(f'PRAGMA table_info("{table}")'). fetchall()]
        csv_path = CSV_DIR / f"{table}.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(cols)
            writer.writerows(rows)
        exported += 1
    except Exception as e:
        print(f"   Warning: Could not export {table}: {e}")

print(f"   Exported {exported}/{len(all_tables)} tables to CSV ✓")

# ══════════════════════════════════════════════════════════════════════════════
# COPY BACK TO RAPID DB
# ══════════════════════════════════════════════════════════════════════════════
print("\n[4/5] Copying upgraded database back...")
conn.close()
shutil.copy(str(TMP_DB), str(DB_PATH))
print(f"   Copied to {DB_PATH} ✓")

# ══════════════════════════════════════════════════════════════════════════════
# VERIFY
# ══════════════════════════════════════════════════════════════════════════════
print("\n[5/5] Verification...")
conn2 = sqlite3.connect(str(TMP_DB))
tables = conn2.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
total_rows = 0
for t in tables:
    name = t[0]
    count = conn2.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
    total_rows += count
    print(f"   {name:<35} {count:>6} rows")
conn2.close()

print(f"\n{'='*60}")
print(f"UPGRADE COMPLETE")
print(f"  Tables: {len(tables)}")
print(f"  Total rows: {total_rows:,}")
print(f"  CSVs: {CSV_DIR}")
print(f"{'='*60}")
