"""
Seed script — populates SQLite with sample data for all 7 departments.
Run once: python seed_db.py
"""

import sqlite3
from pathlib import Path
import config

def seed():
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    c = conn.cursor()

    # ── HR ────────────────────────────────────────────────────────────────────
    c.executescript("""
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY, name TEXT, department TEXT, role TEXT,
        hire_date TEXT, salary REAL, performance_score REAL, disciplinary_flag INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS benefits_enrollment (
        id INTEGER PRIMARY KEY, employee_id INTEGER, plan_name TEXT,
        coverage_level TEXT, monthly_premium REAL, enrolled_date TEXT
    );
    CREATE TABLE IF NOT EXISTS leave_records (
        id INTEGER PRIMARY KEY, employee_id INTEGER, leave_type TEXT,
        start_date TEXT, end_date TEXT, days INTEGER, approved INTEGER, approved_by TEXT
    );
    CREATE TABLE IF NOT EXISTS org_structure (
        id INTEGER PRIMARY KEY, department TEXT, manager_name TEXT,
        headcount INTEGER, budget_headcount INTEGER
    );
    """)

    c.executemany("INSERT OR IGNORE INTO employees VALUES (?,?,?,?,?,?,?,?)", [
        (1, "Alice Chen",     "Engineering",  "Manager",        "2020-03-01", 95000, 4.5, 0),
        (2, "Bob Smith",      "Engineering",  "Engineer",       "2021-06-15", 72000, 3.8, 0),
        (3, "Carol Davies",   "Finance",      "Finance Analyst","2019-09-10", 68000, 4.2, 0),
        (4, "Dave Kumar",     "Sales",        "Sales Rep",      "2022-01-20", 60000, 3.5, 0),
        (5, "Emma Wilson",    "Marketing",    "Marketing Mgr",  "2020-11-05", 78000, 4.0, 0),
        (6, "Frank Lee",      "Engineering",  "Engineer",       "2023-04-01", 70000, 3.9, 0),
        (7, "Grace Patel",    "HR",           "HR Manager",     "2018-07-15", 75000, 4.7, 0),
        (8, "Henry Brown",    "Legal",        "Counsel",        "2021-02-28", 90000, 4.3, 0),
        (9, "Iris Zhang",     "Operations",   "Ops Analyst",    "2022-08-10", 65000, 4.1, 0),
        (10,"James Moore",    "IT",           "IT Engineer",    "2020-05-20", 73000, 4.0, 0),
    ])

    c.executemany("INSERT OR IGNORE INTO benefits_enrollment VALUES (?,?,?,?,?,?)", [
        (1, 1, "Family",    "Full",     320.0, "2020-03-01"),
        (2, 2, "Standard",  "Partial",  180.0, "2021-06-15"),
        (3, 3, "Standard",  "Full",     180.0, "2019-09-10"),
        (4, 4, "Basic",     "Individual",90.0, "2022-01-20"),
        (5, 5, "Standard",  "Full",     180.0, "2020-11-05"),
    ])

    c.executemany("INSERT OR IGNORE INTO leave_records VALUES (?,?,?,?,?,?,?,?)", [
        (1, 2, "Annual",      "2026-07-01", "2026-07-10", 7,  1, "Alice Chen"),
        (2, 4, "Sick",        "2026-03-10", "2026-03-11", 1,  1, "HR auto"),
        (3, 6, "Annual",      "2026-08-15", "2026-08-22", 5,  1, "Alice Chen"),
        (4, 5, "Parental",    "2026-05-01", "2026-11-01", 130,1, "HR"),
    ])

    c.executemany("INSERT OR IGNORE INTO org_structure VALUES (?,?,?,?,?)", [
        (1, "Engineering",  "Alice Chen",   3,  4),
        (2, "Finance",      "Carol Davies", 2,  3),
        (3, "Sales",        "Dave Kumar",   2,  3),
        (4, "Marketing",    "Emma Wilson",  2,  2),
        (5, "HR",           "Grace Patel",  1,  2),
        (6, "Legal",        "Henry Brown",  1,  2),
        (7, "Operations",   "Iris Zhang",   1,  2),
        (8, "IT",           "James Moore",  1,  2),
    ])

    # ── Finance ───────────────────────────────────────────────────────────────
    c.executescript("""
    CREATE TABLE IF NOT EXISTS financials (
        id INTEGER PRIMARY KEY, period TEXT, revenue REAL, gross_margin REAL,
        net_income REAL, operating_expenses REAL, salary_budget REAL, executive_comp REAL
    );
    CREATE TABLE IF NOT EXISTS orders (
        order_id TEXT PRIMARY KEY, customer_id TEXT, amount REAL, status TEXT, created_at TEXT, product TEXT
    );
    CREATE TABLE IF NOT EXISTS invoices (
        invoice_id TEXT PRIMARY KEY, vendor TEXT, amount REAL, due_date TEXT, paid INTEGER, category TEXT
    );
    CREATE TABLE IF NOT EXISTS budget_allocations (
        id INTEGER PRIMARY KEY, department TEXT, allocated REAL, spent REAL, remaining REAL, variance REAL, period TEXT
    );
    """)

    c.executemany("INSERT OR IGNORE INTO financials VALUES (?,?,?,?,?,?,?,?)", [
        (1, "Q1 2026", 2100000, 1260000, 420000, 840000, 650000, 120000),
        (2, "Q2 2026", 2350000, 1410000, 470000, 940000, 650000, 120000),
        (3, "Q3 2026", 2600000, 1560000, 520000, 1040000, 680000, 120000),
    ])

    c.executemany("INSERT OR IGNORE INTO budget_allocations VALUES (?,?,?,?,?,?,?)", [
        (1, "Engineering",  500000, 380000, 120000, -20000, "2026"),
        (2, "Marketing",    300000, 220000,  80000,  10000, "2026"),
        (3, "Sales",        400000, 310000,  90000,   5000, "2026"),
        (4, "Operations",   200000, 155000,  45000,   0,    "2026"),
    ])

    # ── Sales ─────────────────────────────────────────────────────────────────
    c.executescript("""
    CREATE TABLE IF NOT EXISTS customers (
        customer_id TEXT PRIMARY KEY, company_name TEXT, industry TEXT,
        region TEXT, contact_email TEXT, health_score REAL
    );
    CREATE TABLE IF NOT EXISTS deals (
        deal_id TEXT PRIMARY KEY, customer_id TEXT, stage TEXT,
        value REAL, close_date TEXT, owner TEXT, probability REAL
    );
    CREATE TABLE IF NOT EXISTS sales_pipeline (
        stage TEXT PRIMARY KEY, count INTEGER, total_value REAL, avg_deal_size REAL
    );
    CREATE TABLE IF NOT EXISTS customer_interactions (
        interaction_id TEXT PRIMARY KEY, customer_id TEXT, type TEXT, date TEXT, outcome TEXT, notes TEXT
    );
    """)

    c.executemany("INSERT OR IGNORE INTO customers VALUES (?,?,?,?,?,?)", [
        ("C001", "Acme Corp",     "Manufacturing", "North",  "acme@acme.com",    8.5),
        ("C002", "BetaTech",      "Technology",    "South",  "info@betatech.io", 7.2),
        ("C003", "GammaMed",      "Healthcare",    "East",   "hello@gammamed.co",9.1),
        ("C004", "DeltaRetail",   "Retail",        "West",   "sales@delta.com",  6.8),
    ])

    c.executemany("INSERT OR IGNORE INTO deals VALUES (?,?,?,?,?,?,?)", [
        ("D001", "C001", "Negotiation",  85000, "2026-06-30", "Dave Kumar", 0.75),
        ("D002", "C002", "Proposal",     42000, "2026-07-15", "Dave Kumar", 0.50),
        ("D003", "C003", "Closed Won",  120000, "2026-04-01", "Dave Kumar", 1.00),
        ("D004", "C004", "Discovery",    28000, "2026-08-30", "Dave Kumar", 0.30),
    ])

    c.executemany("INSERT OR IGNORE INTO sales_pipeline VALUES (?,?,?,?)", [
        ("Discovery",    3,  84000,  28000),
        ("Proposal",     2,  84000,  42000),
        ("Negotiation",  1,  85000,  85000),
        ("Closed Won",   4, 480000, 120000),
    ])

    # ── Marketing ─────────────────────────────────────────────────────────────
    c.executescript("""
    CREATE TABLE IF NOT EXISTS ad_spend (
        id INTEGER PRIMARY KEY, channel TEXT, spend REAL, period TEXT, campaign_id TEXT
    );
    CREATE TABLE IF NOT EXISTS campaign_analytics (
        campaign_id TEXT PRIMARY KEY, name TEXT, impressions INTEGER,
        clicks INTEGER, conversions INTEGER, ctr REAL, roas REAL, period TEXT
    );
    CREATE TABLE IF NOT EXISTS lead_data (
        lead_id TEXT PRIMARY KEY, source TEXT, status TEXT, created_at TEXT, contact_email TEXT
    );
    CREATE TABLE IF NOT EXISTS channel_performance (
        channel TEXT PRIMARY KEY, leads INTEGER, spend REAL, cpl REAL
    );
    """)

    c.executemany("INSERT OR IGNORE INTO ad_spend VALUES (?,?,?,?,?)", [
        (1, "Google Ads",  45000, "Q1 2026", "CAM001"),
        (2, "LinkedIn",    28000, "Q1 2026", "CAM002"),
        (3, "Meta",        18000, "Q1 2026", "CAM001"),
        (4, "Google Ads",  50000, "Q2 2026", "CAM003"),
    ])

    c.executemany("INSERT OR IGNORE INTO campaign_analytics VALUES (?,?,?,?,?,?,?,?)", [
        ("CAM001", "Spring Launch",    850000, 12000, 480, 1.41, 3.2, "Q1 2026"),
        ("CAM002", "B2B Outreach",     120000,  3600, 180, 3.00, 2.8, "Q1 2026"),
        ("CAM003", "Summer Campaign",  920000, 13800, 552, 1.50, 3.5, "Q2 2026"),
    ])

    c.executemany("INSERT OR IGNORE INTO channel_performance VALUES (?,?,?,?)", [
        ("Google Ads",  620, 95000, 153),
        ("LinkedIn",    180, 28000, 156),
        ("Meta",        210, 18000,  86),
    ])

    # ── Operations ────────────────────────────────────────────────────────────
    c.executescript("""
    CREATE TABLE IF NOT EXISTS kpis (
        id INTEGER PRIMARY KEY, metric TEXT, value REAL, target REAL, period TEXT, status TEXT, department TEXT
    );
    CREATE TABLE IF NOT EXISTS sla_records (
        id INTEGER PRIMARY KEY, service TEXT, target_uptime REAL,
        actual_uptime REAL, breaches INTEGER, period TEXT, penalty_clause TEXT
    );
    """)

    c.executemany("INSERT OR IGNORE INTO kpis VALUES (?,?,?,?,?,?,?)", [
        (1, "Customer Satisfaction",  4.3, 4.5, "Q1 2026", "Below Target", "Operations"),
        (2, "Order Fulfilment Rate",  97.2,98.0,"Q1 2026", "Below Target", "Operations"),
        (3, "Avg Delivery Days",      3.2, 3.0, "Q1 2026", "Below Target", "Operations"),
        (4, "System Uptime",          99.8,99.9,"Q1 2026", "On Track",     "IT"),
    ])

    c.executemany("INSERT OR IGNORE INTO sla_records VALUES (?,?,?,?,?,?,?)", [
        (1, "Delivery Service",   98.0, 97.2, 2, "Q1 2026", "[CONFIDENTIAL]"),
        (2, "Cloud Infrastructure",99.9,99.8, 0, "Q1 2026", "[CONFIDENTIAL]"),
    ])

    # ── IT ────────────────────────────────────────────────────────────────────
    c.executescript("""
    CREATE TABLE IF NOT EXISTS systems (
        system_id TEXT PRIMARY KEY, name TEXT, status TEXT, owner TEXT, last_maintenance TEXT
    );
    CREATE TABLE IF NOT EXISTS access_requests (
        request_id TEXT PRIMARY KEY, user_id TEXT, system_name TEXT,
        request_status TEXT, approval_date TEXT, approver TEXT, credentials TEXT
    );
    CREATE TABLE IF NOT EXISTS software_licenses (
        id INTEGER PRIMARY KEY, software TEXT, seats_total INTEGER,
        seats_used INTEGER, expiry TEXT, cost_per_seat REAL, vendor TEXT
    );
    CREATE TABLE IF NOT EXISTS infrastructure_status (
        id INTEGER PRIMARY KEY, component TEXT, status TEXT, last_checked TEXT, uptime_pct REAL
    );
    """)

    c.executemany("INSERT OR IGNORE INTO systems VALUES (?,?,?,?,?)", [
        ("SYS001", "Jira",         "Active",  "James Moore", "2026-01-15"),
        ("SYS002", "Slack",        "Active",  "James Moore", "2026-02-10"),
        ("SYS003", "GitHub",       "Active",  "James Moore", "2026-01-20"),
        ("SYS004", "Salesforce",   "Active",  "James Moore", "2026-03-05"),
    ])

    c.executemany("INSERT OR IGNORE INTO software_licenses VALUES (?,?,?,?,?,?,?)", [
        (1, "Microsoft 365",  100, 87, "2027-01-31",  22.0, "Microsoft"),
        (2, "Slack",           80, 74, "2026-12-31",  12.5, "Salesforce"),
        (3, "GitHub Teams",    50, 42, "2026-09-30",  21.0, "GitHub"),
        (4, "Jira Software",   50, 38, "2027-03-31",  15.25,"Atlassian"),
    ])

    c.executemany("INSERT OR IGNORE INTO infrastructure_status VALUES (?,?,?,?,?)", [
        (1, "API Gateway",     "Healthy",  "2026-04-05 08:00", 99.9),
        (2, "Database Cluster","Healthy",  "2026-04-05 08:00", 99.8),
        (3, "CDN",             "Healthy",  "2026-04-05 08:00", 100.0),
        (4, "Auth Service",    "Healthy",  "2026-04-05 08:00", 99.9),
    ])

    # ── Legal ─────────────────────────────────────────────────────────────────
    c.executescript("""
    CREATE TABLE IF NOT EXISTS cases (
        case_id TEXT PRIMARY KEY, case_type TEXT, status TEXT,
        opened_date TEXT, resolution TEXT, litigation_details TEXT, settlement_amount REAL
    );
    CREATE TABLE IF NOT EXISTS contracts_db (
        contract_id TEXT PRIMARY KEY, vendor TEXT, type TEXT,
        effective_date TEXT, expiry_date TEXT, value REAL, terms TEXT
    );
    CREATE TABLE IF NOT EXISTS compliance_records (
        id INTEGER PRIMARY KEY, regulation TEXT, status TEXT,
        last_review TEXT, next_review TEXT, notes TEXT
    );
    """)

    c.executemany("INSERT OR IGNORE INTO compliance_records VALUES (?,?,?,?,?,?)", [
        (1, "GDPR",      "Compliant",     "2026-01-15", "2026-07-15", "Annual DPA review completed"),
        (2, "ISO 27001", "In Progress",   "2025-10-01", "2026-06-01", "Certification audit scheduled"),
        (3, "SOC 2",     "Compliant",     "2026-02-01", "2027-02-01", "Type II audit passed"),
    ])

    c.executemany("INSERT OR IGNORE INTO contracts_db VALUES (?,?,?,?,?,?,?)", [
        ("CON001", "AWS",         "Cloud Services", "2025-01-01", "2027-12-31", 180000, "[CONFIDENTIAL]"),
        ("CON002", "PensionCo",   "Pension Admin",  "2020-04-01", "2030-03-31",  24000, "[CONFIDENTIAL]"),
    ])

    # ── Finance (missing tables) ───────────────────────────────────────────────
    c.executescript("""
    CREATE TABLE IF NOT EXISTS expense_claims (
        claim_id TEXT PRIMARY KEY, employee_id INTEGER, category TEXT,
        amount REAL, submitted_date TEXT, status TEXT, approved_by TEXT, notes TEXT
    );
    """)

    c.executemany("INSERT OR IGNORE INTO expense_claims VALUES (?,?,?,?,?,?,?,?)", [
        ("EXP001", 2, "Travel",        420.50, "2026-03-15", "Approved",  "Alice Chen",  "Client visit London"),
        ("EXP002", 4, "Entertainment", 185.00, "2026-03-20", "Approved",  "Dave Kumar",  "Client lunch"),
        ("EXP003", 5, "Software",       89.00, "2026-03-25", "Pending",   None,           "Design tool subscription"),
        ("EXP004", 6, "Travel",        310.00, "2026-04-01", "Approved",  "Alice Chen",  "Conference travel"),
        ("EXP005", 9, "Training",      750.00, "2026-04-02", "Approved",  "Grace Patel", "Operations certification"),
    ])

    # ── Legal (missing tables) ─────────────────────────────────────────────────
    c.executescript("""
    CREATE TABLE IF NOT EXISTS regulatory_filings (
        filing_id TEXT PRIMARY KEY, regulation TEXT, filing_type TEXT,
        submitted_date TEXT, deadline TEXT, status TEXT, submitted_by TEXT, notes TEXT
    );
    """)

    c.executemany("INSERT OR IGNORE INTO regulatory_filings VALUES (?,?,?,?,?,?,?,?)", [
        ("RF001", "GDPR",       "Annual DPA Report",        "2026-01-10", "2026-01-31", "Submitted", "Henry Brown", "On time"),
        ("RF002", "Companies Act","Annual Return",           "2026-02-28", "2026-03-31", "Submitted", "Henry Brown", "Filed early"),
        ("RF003", "ISO 27001",  "Certification Audit Prep", "2026-03-01", "2026-06-01", "In Progress","Henry Brown", "Audit scheduled June"),
        ("RF004", "FCA",        "Conduct Report",           None,         "2026-07-31", "Pending",   "Henry Brown", "Due Q3"),
    ])

    # ── Operations (missing tables) ────────────────────────────────────────────
    c.executescript("""
    CREATE TABLE IF NOT EXISTS operations (
        process_id TEXT PRIMARY KEY, name TEXT, owner TEXT,
        status TEXT, last_reviewed TEXT, category TEXT, documentation_url TEXT
    );
    CREATE TABLE IF NOT EXISTS logistics (
        shipment_id TEXT PRIMARY KEY, origin TEXT, destination TEXT,
        status TEXT, carrier TEXT, eta TEXT, weight_kg REAL, cost REAL
    );
    CREATE TABLE IF NOT EXISTS vendor_contracts (
        contract_id TEXT PRIMARY KEY, vendor TEXT, service TEXT,
        start_date TEXT, end_date TEXT, value REAL, pricing_terms TEXT, renewal_type TEXT
    );
    """)

    c.executemany("INSERT OR IGNORE INTO operations VALUES (?,?,?,?,?,?,?)", [
        ("PROC001", "Order Fulfilment",       "Iris Zhang",  "Active",     "2026-02-01", "Logistics",  "ops/sops/order_fulfilment.txt"),
        ("PROC002", "Supplier Onboarding",    "Iris Zhang",  "Active",     "2026-01-15", "Procurement","ops/sops/supplier_onboarding.txt"),
        ("PROC003", "Quality Control Check",  "Iris Zhang",  "Active",     "2026-03-01", "Quality",    "ops/sops/quality_control.txt"),
        ("PROC004", "SLA Breach Escalation",  "Iris Zhang",  "Under Review","2026-03-20","Service",    "ops/sops/sla_escalation.txt"),
    ])

    c.executemany("INSERT OR IGNORE INTO logistics VALUES (?,?,?,?,?,?,?,?)", [
        ("SHP001", "London Warehouse",  "Manchester HQ",  "Delivered",   "DHL",   "2026-03-28", 45.5,  320.0),
        ("SHP002", "Birmingham Depot",  "Leeds Office",   "In Transit",  "UPS",   "2026-04-07",  8.2,   95.0),
        ("SHP003", "Manchester HQ",     "Edinburgh Branch","Processing", "FedEx", "2026-04-10", 12.0,  140.0),
        ("SHP004", "Glasgow Supplier",  "London Warehouse","In Transit", "DPD",   "2026-04-09", 200.0, 850.0),
    ])

    c.executemany("INSERT OR IGNORE INTO vendor_contracts VALUES (?,?,?,?,?,?,?,?)", [
        ("VC001", "DHL",          "Logistics",          "2025-01-01", "2026-12-31", 95000,  "[CONFIDENTIAL]", "Annual"),
        ("VC002", "Servicemaster", "Facilities",        "2024-06-01", "2026-05-31", 36000,  "[CONFIDENTIAL]", "Biennial"),
        ("VC003", "CloudOps Ltd",  "Managed IT Ops",    "2025-04-01", "2027-03-31", 120000, "[CONFIDENTIAL]", "Biennial"),
        ("VC004", "SecureStore",   "Data Archiving",    "2026-01-01", "2028-12-31", 18000,  "[CONFIDENTIAL]", "3-Year"),
    ])

    # ── Procurement ───────────────────────────────────────────────────────────
    c.executescript("""
    CREATE TABLE IF NOT EXISTS purchase_orders (
        po_id TEXT PRIMARY KEY, supplier_id TEXT, department TEXT,
        amount REAL, status TEXT, raised_date TEXT, approved_by TEXT, delivery_date TEXT, category TEXT
    );
    CREATE TABLE IF NOT EXISTS suppliers (
        supplier_id TEXT PRIMARY KEY, name TEXT, category TEXT, country TEXT,
        contact_email TEXT, status TEXT, rating REAL, spend_ytd REAL, on_preferred_list INTEGER
    );
    CREATE TABLE IF NOT EXISTS rfq_records (
        rfq_id TEXT PRIMARY KEY, item TEXT, suppliers_invited INTEGER,
        responses_received INTEGER, awarded_to TEXT, award_value REAL, raised_date TEXT, status TEXT
    );
    CREATE TABLE IF NOT EXISTS vendor_evaluations (
        eval_id TEXT PRIMARY KEY, supplier_id TEXT, period TEXT,
        quality_score REAL, delivery_score REAL, price_score REAL, overall_score REAL, reviewed_by TEXT
    );
    """)

    c.executemany("INSERT OR IGNORE INTO suppliers VALUES (?,?,?,?,?,?,?,?,?)", [
        ("SUP001", "Acme Supplies",      "Office",      "UK",  "orders@acme.com",    "Active",      4.2, 28000, 1),
        ("SUP002", "TechParts Ltd",      "Hardware",    "UK",  "sales@techparts.co", "Active",      4.5, 62000, 1),
        ("SUP003", "GlobalPrint Co",     "Marketing",   "DE",  "info@globalprint.de","Active",      3.9, 15000, 0),
        ("SUP004", "FurniturePro",       "Facilities",  "UK",  "hello@furniturep.co","Active",      4.1, 41000, 1),
        ("SUP005", "CloudServe GmbH",    "Software",    "DE",  "sales@cloudserve.de","Under Review",3.6, 9000,  0),
    ])

    c.executemany("INSERT OR IGNORE INTO purchase_orders VALUES (?,?,?,?,?,?,?,?,?)", [
        ("PO001", "SUP001", "Operations",   4800,  "Approved",  "2026-02-10", "Iris Zhang",  "2026-02-20", "Office Supplies"),
        ("PO002", "SUP002", "IT",           18500, "Approved",  "2026-02-28", "James Moore", "2026-03-15", "Hardware"),
        ("PO003", "SUP003", "Marketing",    7200,  "Approved",  "2026-03-05", "Emma Wilson", "2026-03-25", "Print Media"),
        ("PO004", "SUP004", "HR",           22000, "Pending",   "2026-03-20", None,           None,         "Office Furniture"),
        ("PO005", "SUP005", "Engineering",  5500,  "In Review", "2026-04-01", None,           None,         "Software Licence"),
    ])

    c.executemany("INSERT OR IGNORE INTO rfq_records VALUES (?,?,?,?,?,?,?,?)", [
        ("RFQ001", "Laptop Fleet Refresh",      5, 4, "SUP002", 74000, "2026-01-15", "Closed"),
        ("RFQ002", "Office Refit Furniture",    4, 3, "SUP004", 22000, "2026-02-10", "Closed"),
        ("RFQ003", "Print Campaign Materials",  3, 3, "SUP003",  7200, "2026-02-28", "Closed"),
        ("RFQ004", "Cloud Storage Expansion",   4, 2, None,      None,  "2026-03-20", "Open"),
    ])

    c.executemany("INSERT OR IGNORE INTO vendor_evaluations VALUES (?,?,?,?,?,?,?,?)", [
        ("EVL001", "SUP001", "Q1 2026", 4.2, 4.0, 4.3, 4.2, "Iris Zhang"),
        ("EVL002", "SUP002", "Q1 2026", 4.6, 4.5, 4.3, 4.5, "James Moore"),
        ("EVL003", "SUP003", "Q1 2026", 3.8, 4.1, 3.8, 3.9, "Emma Wilson"),
        ("EVL004", "SUP004", "Q1 2026", 4.2, 3.9, 4.1, 4.1, "Iris Zhang"),
    ])

    # ── R&D ───────────────────────────────────────────────────────────────────
    c.executescript("""
    CREATE TABLE IF NOT EXISTS rd_projects (
        project_id TEXT PRIMARY KEY, name TEXT, lead TEXT, department TEXT,
        status TEXT, start_date TEXT, target_date TEXT, budget REAL, spend_to_date REAL, priority TEXT
    );
    CREATE TABLE IF NOT EXISTS experiments (
        exp_id TEXT PRIMARY KEY, project_id TEXT, name TEXT,
        hypothesis TEXT, status TEXT, outcome TEXT, started_date TEXT, completed_date TEXT
    );
    CREATE TABLE IF NOT EXISTS ip_registry (
        ip_id TEXT PRIMARY KEY, title TEXT, type TEXT, project_id TEXT,
        filed_date TEXT, status TEXT, jurisdiction TEXT, owner TEXT
    );
    CREATE TABLE IF NOT EXISTS research_budgets (
        id INTEGER PRIMARY KEY, department TEXT, period TEXT,
        allocated REAL, spent REAL, remaining REAL, category TEXT
    );
    """)

    c.executemany("INSERT OR IGNORE INTO rd_projects VALUES (?,?,?,?,?,?,?,?,?,?)", [
        ("RD001", "AI Query Optimiser",       "Alice Chen", "Engineering", "Active",      "2026-01-05", "2026-09-30", 180000, 62000, "High"),
        ("RD002", "Predictive Churn Model",   "Dave Kumar", "Sales",       "Active",      "2026-02-01", "2026-07-31", 95000,  28000, "High"),
        ("RD003", "Carbon Offset Tracker",    "Iris Zhang", "Operations",  "Discovery",   "2026-03-01", "2026-12-31", 60000,  5000,  "Medium"),
        ("RD004", "Voice Search Integration", "James Moore","IT",          "Paused",      "2025-10-01", "2026-06-30", 40000,  31000, "Low"),
        ("RD005", "Personalisation Engine",   "Emma Wilson","Marketing",   "Active",      "2026-02-15", "2026-10-31", 120000, 44000, "High"),
    ])

    c.executemany("INSERT OR IGNORE INTO experiments VALUES (?,?,?,?,?,?,?,?)", [
        ("EXP001", "RD001", "Embedding Cache Test",    "Caching reduces latency >30%",          "Completed", "Confirmed — 34% improvement", "2026-01-20", "2026-02-15"),
        ("EXP002", "RD001", "Hybrid Retrieval A/B",    "RRF outperforms pure vector by >10%",   "Completed", "Confirmed — 12% improvement", "2026-02-20", "2026-03-10"),
        ("EXP003", "RD002", "Churn Signal Baseline",   "Engagement score predicts churn 60d out","Active",   None,                          "2026-02-15", None),
        ("EXP004", "RD005", "Segment Personalisation", "Segmented content lifts CTR by 20%",    "Active",   None,                          "2026-03-01", None),
    ])

    c.executemany("INSERT OR IGNORE INTO ip_registry VALUES (?,?,?,?,?,?,?,?)", [
        ("IP001", "Adaptive Query Routing Algorithm", "Patent",    "RD001", "2026-03-15", "Filed",   "UK + EU", "Company"),
        ("IP002", "Churn Prediction Signal Model",    "Copyright", "RD002", "2026-02-01", "Registered","UK",   "Company"),
        ("IP003", "Personalisation Engine Core",      "Patent",    "RD005", "2026-04-01", "Pending", "UK",      "Company"),
    ])

    c.executemany("INSERT OR IGNORE INTO research_budgets VALUES (?,?,?,?,?,?,?)", [
        (1, "Engineering",  "2026", 180000, 62000,  118000, "AI/ML Research"),
        (2, "Sales",        "2026",  95000, 28000,   67000, "Predictive Analytics"),
        (3, "Operations",   "2026",  60000,  5000,   55000, "Sustainability"),
        (4, "Marketing",    "2026", 120000, 44000,   76000, "Personalisation"),
        (5, "IT",           "2026",  40000, 31000,    9000, "Voice & Search"),
    ])

    # ── Customer Success ──────────────────────────────────────────────────────
    c.executescript("""
    CREATE TABLE IF NOT EXISTS cs_accounts (
        account_id TEXT PRIMARY KEY, company_name TEXT, csm_owner TEXT,
        health_score REAL, arr REAL, tier TEXT, onboarded_date TEXT, renewal_date TEXT, risk_flag INTEGER
    );
    CREATE TABLE IF NOT EXISTS nps_scores (
        id INTEGER PRIMARY KEY, account_id TEXT, score INTEGER,
        category TEXT, submitted_date TEXT, verbatim TEXT
    );
    CREATE TABLE IF NOT EXISTS support_tickets (
        ticket_id TEXT PRIMARY KEY, account_id TEXT, subject TEXT,
        priority TEXT, status TEXT, created_date TEXT, resolved_date TEXT, csat_score REAL
    );
    CREATE TABLE IF NOT EXISTS renewal_pipeline (
        renewal_id TEXT PRIMARY KEY, account_id TEXT, arr REAL,
        renewal_date TEXT, stage TEXT, probability REAL, csm_owner TEXT, notes TEXT
    );
    """)

    c.executemany("INSERT OR IGNORE INTO cs_accounts VALUES (?,?,?,?,?,?,?,?,?)", [
        ("ACC001", "Acme Corp",    "Sarah Blake",  8.5, 85000,  "Enterprise", "2024-03-01", "2027-03-01", 0),
        ("ACC002", "BetaTech",     "Sarah Blake",  7.2, 42000,  "Business",   "2024-06-15", "2026-06-15", 0),
        ("ACC003", "GammaMed",     "Tom Richards", 9.1, 120000, "Enterprise", "2023-09-01", "2026-09-01", 0),
        ("ACC004", "DeltaRetail",  "Tom Richards", 5.4, 28000,  "Starter",    "2025-01-10", "2026-01-10", 1),
        ("ACC005", "EpsilonFin",   "Sarah Blake",  6.8, 65000,  "Business",   "2024-11-01", "2026-11-01", 0),
    ])

    c.executemany("INSERT OR IGNORE INTO nps_scores VALUES (?,?,?,?,?,?)", [
        (1, "ACC001", 9,  "Promoter",  "2026-03-01", "Great product, very responsive team"),
        (2, "ACC002", 7,  "Passive",   "2026-03-05", "Works well, minor onboarding friction"),
        (3, "ACC003", 10, "Promoter",  "2026-03-10", "Best in class — highly recommend"),
        (4, "ACC004", 4,  "Detractor", "2026-03-12", "Support response times need improvement"),
        (5, "ACC005", 8,  "Promoter",  "2026-03-20", "Solid platform, good value"),
    ])

    c.executemany("INSERT OR IGNORE INTO support_tickets VALUES (?,?,?,?,?,?,?,?)", [
        ("TKT001", "ACC004", "Login issue after update",       "High",   "Resolved", "2026-03-10", "2026-03-11", 3.0),
        ("TKT002", "ACC002", "API rate limit queries",         "Medium", "Resolved", "2026-03-15", "2026-03-16", 4.5),
        ("TKT003", "ACC001", "Custom report configuration",    "Low",    "Resolved", "2026-03-18", "2026-03-20", 5.0),
        ("TKT004", "ACC004", "Data export failing",            "High",   "Open",     "2026-04-02", None,          None),
        ("TKT005", "ACC003", "SSO integration assistance",     "Medium", "In Progress","2026-04-03",None,          None),
    ])

    c.executemany("INSERT OR IGNORE INTO renewal_pipeline VALUES (?,?,?,?,?,?,?,?)", [
        ("REN001", "ACC002", 42000,  "2026-06-15", "Negotiation",  0.80, "Sarah Blake",  "Multi-year proposal sent"),
        ("REN002", "ACC003", 120000, "2026-09-01", "Early Renewal", 0.95, "Tom Richards", "Champion keen to expand"),
        ("REN003", "ACC004", 28000,  "2026-01-10", "At Risk",       0.40, "Tom Richards", "Escalated — support issues"),
        ("REN004", "ACC005", 65000,  "2026-11-01", "Discovery",     0.70, "Sarah Blake",  "Initial renewal conversation done"),
    ])

    conn.commit()
    conn.close()
    print(f"✓ Database seeded at {config.DB_PATH}")


if __name__ == "__main__":
    seed()
