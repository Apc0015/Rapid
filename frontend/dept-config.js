/**
 * RAPID — Department Configuration
 * Shared data for dept.html and org.html
 */

window.RAPID_DEPT = (function () {

  const DEPT = {
    finance: {
      key: 'finance', name: 'Finance Department', short: 'Finance',
      icon: 'chart',
      division: 'Commercial & Finance Division', div_key: 'commercial_finance',
      escalates: 'CFO', threshold: 65,
      accent: '#0D9488', accent_dim: 'rgba(13,148,136,0.12)',
      accent_border: 'rgba(13,148,136,0.25)', accent_shadow: 'rgba(13,148,136,0.28)',
      description: 'Revenue intelligence, budget management, P&L analysis, and cost optimization across the organization.',
      tables: [
        { name: 'financials',         desc: 'Revenue & P&L',       access: 'full' },
        { name: 'orders',             desc: 'Order ledger',         access: 'full' },
        { name: 'invoices',           desc: 'Invoice records',      access: 'full' },
        { name: 'budget_allocations', desc: 'Budget tracking',      access: 'full' },
        { name: 'expense_claims',     desc: 'Expense submissions',  access: 'dept' },
      ],
      docs: ['Quarterly Reports', 'Budget Plans', 'Expense Reports'],
      peers: [
        { id: 'legal',       name: 'Legal',       reason: 'Contract cost review' },
        { id: 'procurement', name: 'Procurement', reason: 'Vendor spend alignment' },
      ],
      agents: [
        { name: 'Financial Analyst', desc: 'Revenue & P&L analysis' },
        { name: 'Controller',        desc: 'Accounts & compliance' },
        { name: 'Budget Agent',      desc: 'Budget tracking & forecasting' },
        { name: 'Treasury Agent',    desc: 'Cash flow & liquidity' },
        { name: 'FPA Agent',         desc: 'Financial planning & analysis' },
      ],
    },
    hr: {
      key: 'hr', name: 'Human Resources', short: 'HR',
      icon: 'users',
      division: 'Commercial & Finance Division', div_key: 'commercial_finance',
      escalates: 'CFO', threshold: 65,
      accent: '#7C3AED', accent_dim: 'rgba(124,58,237,0.12)',
      accent_border: 'rgba(124,58,237,0.25)', accent_shadow: 'rgba(124,58,237,0.28)',
      description: 'People operations, talent acquisition, benefits administration, and organizational development.',
      tables: [
        { name: 'employees',           desc: 'Employee records',   access: 'dept' },
        { name: 'benefits_enrollment', desc: 'Benefits data',      access: 'dept' },
        { name: 'leave_records',       desc: 'PTO & leave',        access: 'dept' },
        { name: 'org_structure',       desc: 'Org chart data',     access: 'read' },
      ],
      docs: ['HR Policies', 'Employee Handbooks', 'Onboarding Guides', 'Training Programs'],
      peers: [
        { id: 'legal',   name: 'Legal',   reason: 'Employment law queries' },
        { id: 'finance', name: 'Finance', reason: 'Headcount cost queries' },
      ],
      agents: [
        { name: 'Recruitment Agent',        desc: 'Talent acquisition & pipeline' },
        { name: 'Compensation Agent',       desc: 'Pay structure & benchmarking' },
        { name: 'Learning & Dev Agent',     desc: 'Training & career growth' },
        { name: 'Employee Relations Agent', desc: 'Policies & conflict resolution' },
      ],
    },
    legal: {
      key: 'legal', name: 'Legal Department', short: 'Legal',
      icon: 'shield',
      division: 'Commercial & Finance Division', div_key: 'commercial_finance',
      escalates: 'CFO', threshold: 70,
      accent: '#D97706', accent_dim: 'rgba(217,119,6,0.12)',
      accent_border: 'rgba(217,119,6,0.25)', accent_shadow: 'rgba(217,119,6,0.28)',
      description: 'Contract management, compliance monitoring, regulatory filings, and enterprise risk mitigation.',
      tables: [
        { name: 'cases',               desc: 'Active legal cases', access: 'full' },
        { name: 'contracts_db',        desc: 'Contract repository',access: 'full' },
        { name: 'compliance_records',  desc: 'Compliance history', access: 'full' },
        { name: 'regulatory_filings',  desc: 'Reg filings',        access: 'full' },
      ],
      docs: ['Compliance Policies', 'Contract Templates', 'Regulations', 'GDPR Policies'],
      peers: [
        { id: 'finance',     name: 'Finance',     reason: 'Contract value & cost' },
        { id: 'hr',          name: 'HR',          reason: 'Employment matters' },
        { id: 'procurement', name: 'Procurement', reason: 'Vendor contracts' },
      ],
      agents: [
        { name: 'Contract Agent',   desc: 'Contract review & drafting' },
        { name: 'Compliance Agent', desc: 'Regulatory compliance checks' },
        { name: 'Risk Agent',       desc: 'Legal risk assessment' },
      ],
    },
    procurement: {
      key: 'procurement', name: 'Procurement Department', short: 'Procurement',
      icon: 'package',
      division: 'Commercial & Finance Division', div_key: 'commercial_finance',
      escalates: 'CFO', threshold: 65,
      accent: '#EA580C', accent_dim: 'rgba(234,88,12,0.12)',
      accent_border: 'rgba(234,88,12,0.25)', accent_shadow: 'rgba(234,88,12,0.28)',
      description: 'Vendor management, purchase orders, supplier evaluation, and procurement lifecycle automation.',
      tables: [
        { name: 'purchase_orders',    desc: 'PO records',       access: 'full' },
        { name: 'suppliers',          desc: 'Vendor directory', access: 'full' },
        { name: 'rfq_records',        desc: 'RFQ history',      access: 'full' },
        { name: 'vendor_evaluations', desc: 'Vendor scoring',   access: 'full' },
      ],
      docs: ['Procurement Policies', 'Supplier Guides', 'RFQ Templates'],
      peers: [
        { id: 'finance', name: 'Finance',    reason: 'Budget alignment' },
        { id: 'legal',   name: 'Legal',      reason: 'Contract review' },
        { id: 'ops',     name: 'Operations', reason: 'Operational requirements' },
      ],
      agents: [
        { name: 'Vendor Agent', desc: 'Supplier evaluation & selection' },
        { name: 'PO Agent',     desc: 'Purchase order management' },
        { name: 'RFQ Agent',    desc: 'Request for quotation processing' },
      ],
    },
    sales: {
      key: 'sales', name: 'Sales Department', short: 'Sales',
      icon: 'zap',
      division: 'Operations & Commercial Division', div_key: 'operations',
      escalates: 'COO', threshold: 60,
      accent: '#059669', accent_dim: 'rgba(5,150,105,0.12)',
      accent_border: 'rgba(5,150,105,0.25)', accent_shadow: 'rgba(5,150,105,0.28)',
      description: 'Pipeline intelligence, deal forecasting, customer relationship management, and revenue optimization.',
      tables: [
        { name: 'customers',            desc: 'Customer records', access: 'full' },
        { name: 'deals',                desc: 'Active deals',     access: 'full' },
        { name: 'sales_pipeline',       desc: 'Pipeline stages',  access: 'full' },
        { name: 'customer_interactions',desc: 'Interaction log',  access: 'full' },
      ],
      docs: ['Sales Playbook', 'Case Studies', 'Territory Plans'],
      peers: [
        { id: 'marketing', name: 'Marketing', reason: 'Campaign & lead alignment' },
        { id: 'finance',   name: 'Finance',   reason: 'Deal margin approval' },
        { id: 'legal',     name: 'Legal',     reason: 'Contract terms' },
      ],
      agents: [
        { name: 'Pipeline Agent',  desc: 'Deal stage & forecast' },
        { name: 'Territory Agent', desc: 'Territory planning & coverage' },
        { name: 'Customer Agent',  desc: 'Customer history & intelligence' },
      ],
    },
    marketing: {
      key: 'marketing', name: 'Marketing Department', short: 'Marketing',
      icon: 'megaphone',
      division: 'Operations & Commercial Division', div_key: 'operations',
      escalates: 'COO', threshold: 60,
      accent: '#E11D48', accent_dim: 'rgba(225,29,72,0.12)',
      accent_border: 'rgba(225,29,72,0.25)', accent_shadow: 'rgba(225,29,72,0.28)',
      description: 'Campaign analytics, lead generation, channel attribution, and market research intelligence.',
      tables: [
        { name: 'ad_spend',           desc: 'Advertising budget', access: 'full' },
        { name: 'campaign_analytics', desc: 'Campaign metrics',   access: 'full' },
        { name: 'lead_data',          desc: 'Lead scoring',       access: 'full' },
        { name: 'channel_performance',desc: 'Channel ROI',        access: 'full' },
      ],
      docs: ['Campaign Plans', 'Marketing Reports', 'Market Research'],
      peers: [
        { id: 'sales',           name: 'Sales',           reason: 'Pipeline & campaign alignment' },
        { id: 'customer_success',name: 'Customer Success',reason: 'NPS & retention insight' },
      ],
      agents: [
        { name: 'Campaign Agent',  desc: 'Campaign performance analysis' },
        { name: 'Lead Agent',      desc: 'Lead scoring & qualification' },
        { name: 'Analytics Agent', desc: 'Channel attribution & ROI' },
      ],
    },
    ops: {
      key: 'ops', name: 'Operations Department', short: 'Operations',
      icon: 'settings',
      division: 'Operations & Commercial Division', div_key: 'operations',
      escalates: 'COO', threshold: 65,
      accent: '#0284C7', accent_dim: 'rgba(2,132,199,0.12)',
      accent_border: 'rgba(2,132,199,0.25)', accent_shadow: 'rgba(2,132,199,0.28)',
      description: 'Process optimization, SLA management, logistics intelligence, and operational KPI tracking.',
      tables: [
        { name: 'operations',      desc: 'Ops records',    access: 'full' },
        { name: 'logistics',       desc: 'Logistics data', access: 'full' },
        { name: 'kpis',            desc: 'KPI metrics',    access: 'full' },
        { name: 'sla_records',     desc: 'SLA history',    access: 'full' },
        { name: 'vendor_contracts',desc: 'Vendor SLAs',    access: 'read' },
      ],
      docs: ['Process SOPs', 'KPI Reports', 'Operational Guides'],
      peers: [
        { id: 'it',          name: 'IT',          reason: 'Infrastructure & system queries' },
        { id: 'procurement', name: 'Procurement', reason: 'Vendor & supply queries' },
        { id: 'finance',     name: 'Finance',     reason: 'Operational cost queries' },
      ],
      agents: [
        { name: 'Process Agent',   desc: 'SOP & process optimization' },
        { name: 'KPI Agent',       desc: 'Performance metrics & reporting' },
        { name: 'Logistics Agent', desc: 'Supply chain & logistics' },
      ],
    },
    it: {
      key: 'it', name: 'Information Technology', short: 'IT',
      icon: 'cpu',
      division: 'Technology Division', div_key: 'technology',
      escalates: 'CTO', threshold: 65,
      accent: '#0891B2', accent_dim: 'rgba(8,145,178,0.12)',
      accent_border: 'rgba(8,145,178,0.25)', accent_shadow: 'rgba(8,145,178,0.28)',
      description: 'Systems management, access control, software licensing, and infrastructure monitoring.',
      tables: [
        { name: 'systems',              desc: 'System inventory',  access: 'full' },
        { name: 'access_requests',      desc: 'Access control log',access: 'full' },
        { name: 'software_licenses',    desc: 'License registry',  access: 'full' },
        { name: 'infrastructure_status',desc: 'Infra health',      access: 'full' },
      ],
      docs: ['IT Policies', 'System Guides', 'Security Policies'],
      peers: [
        { id: 'ops', name: 'Operations', reason: 'Operational system queries' },
        { id: 'rd',  name: 'R&D',        reason: 'Tech stack alignment' },
      ],
      agents: [
        { name: 'Systems Agent',  desc: 'Infrastructure & system status' },
        { name: 'Security Agent', desc: 'Access control & compliance' },
        { name: 'License Agent',  desc: 'Software asset management' },
      ],
    },
    rd: {
      key: 'rd', name: 'Research & Development', short: 'R&D',
      icon: 'flask',
      division: 'Technology Division', div_key: 'technology',
      escalates: 'CTO', threshold: 70,
      accent: '#4F46E5', accent_dim: 'rgba(79,70,229,0.12)',
      accent_border: 'rgba(79,70,229,0.25)', accent_shadow: 'rgba(79,70,229,0.28)',
      description: 'Research project management, IP documentation, experiment tracking, and innovation pipelines.',
      tables: [
        { name: 'rd_projects',     desc: 'Active projects', access: 'full' },
        { name: 'experiments',     desc: 'Experiment log',  access: 'full' },
        { name: 'ip_registry',     desc: 'IP assets',       access: 'full' },
        { name: 'research_budgets',desc: 'R&D spend',       access: 'dept' },
      ],
      docs: ['Project Briefs', 'Research Reports', 'IP Documentation'],
      peers: [
        { id: 'it',        name: 'IT',        reason: 'Infrastructure & tools' },
        { id: 'marketing', name: 'Marketing', reason: 'Product-market alignment' },
        { id: 'sales',     name: 'Sales',     reason: 'Product feedback' },
      ],
      agents: [
        { name: 'Research Agent',   desc: 'Project tracking & analysis' },
        { name: 'IP Agent',         desc: 'Intellectual property registry' },
        { name: 'Experiment Agent', desc: 'Hypothesis & results tracking' },
      ],
    },
    customer_success: {
      key: 'customer_success', name: 'Customer Success', short: 'CS',
      icon: 'heart',
      division: 'Operations & Commercial Division', div_key: 'operations',
      escalates: 'COO', threshold: 60,
      accent: '#16A34A', accent_dim: 'rgba(22,163,74,0.12)',
      accent_border: 'rgba(22,163,74,0.25)', accent_shadow: 'rgba(22,163,74,0.28)',
      description: 'Account health monitoring, NPS tracking, renewal pipeline intelligence, and escalation management.',
      tables: [
        { name: 'cs_accounts',     desc: 'Account health',    access: 'full' },
        { name: 'nps_scores',      desc: 'NPS & CSAT',        access: 'full' },
        { name: 'support_tickets', desc: 'Support history',   access: 'full' },
        { name: 'renewal_pipeline',desc: 'Renewal forecast',  access: 'full' },
      ],
      docs: ['CS Playbooks', 'Onboarding Guides', 'Escalation Guides'],
      peers: [
        { id: 'sales',     name: 'Sales',      reason: 'Renewal & expansion' },
        { id: 'marketing', name: 'Marketing',  reason: 'Retention campaigns' },
        { id: 'ops',       name: 'Operations', reason: 'Delivery & SLA issues' },
      ],
      agents: [
        { name: 'Account Health Agent', desc: 'Health score & churn risk' },
        { name: 'Onboarding Agent',     desc: 'New customer activation' },
        { name: 'Escalation Agent',     desc: 'Support escalation routing' },
      ],
    },
  };

  const DIVISIONS = {
    commercial_finance: {
      name: 'Commercial & Finance',
      full: 'Commercial & Finance Division',
      head: 'CFO',
      accent: '#0D9488',
      tint: 'rgba(13,148,136,0.04)',
      depts: ['finance', 'hr', 'legal', 'procurement'],
    },
    technology: {
      name: 'Technology',
      full: 'Technology Division',
      head: 'CTO',
      accent: '#4F46E5',
      tint: 'rgba(79,70,229,0.04)',
      depts: ['it', 'rd'],
    },
    operations: {
      name: 'Operations & Commercial',
      full: 'Operations & Commercial Division',
      head: 'COO',
      accent: '#059669',
      tint: 'rgba(5,150,105,0.04)',
      depts: ['ops', 'sales', 'marketing', 'customer_success'],
    },
  };

  const ACCESS_META = {
    full: { label: 'Full Access', cls: 'access-full' },
    read: { label: 'Read Only',   cls: 'access-read' },
    dept: { label: 'Dept Only',   cls: 'access-dept' },
    none: { label: 'Blocked',     cls: 'access-none' },
  };

  return { DEPT, DIVISIONS, ACCESS_META };
})();
