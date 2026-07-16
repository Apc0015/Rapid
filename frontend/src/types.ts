export interface Profile {
  name?: string;
  role?: string;
  tenant_id?: string;
  username?: string;
  permitted_departments?: string[];
  capabilities?: Record<string, boolean>;
}

export interface AuthResponse {
  access_token: string;
  profile?: Profile;
  name?: string;
  role?: string;
  user_id?: string;
  tenant_id?: string;
  permitted_departments?: string[];
}

export interface OrganizationSummary {
  tenant_id: string;
  name: string;
  industry: string;
  headquarters: string;
  employee_count: number;
}

export interface Meeting {
  id: string;
  title: string;
  meeting_type: string;
  department: string;
  starts_at: string;
  duration_minutes: number;
  status: string;
  facilitator: string;
  notes: string;
  recurrence: string;
  attendees: string[];
  agenda: string[];
  decisions: string[];
  actions?: ActionItem[];
}

export interface ActionItem {
  id: string;
  meeting_id: string;
  title: string;
  owner: string;
  department: string;
  due_date: string;
  status: string;
  priority: string;
}

export interface BusinessRecord {
  id: string;
  entity_type: string;
  department: string;
  name: string;
  data: Record<string, string | number | boolean | null>;
}

export interface DepartmentSummary {
  key: string;
  name: string;
  lead: string;
  status: string;
  open_actions: number;
}

export interface WorkspaceOverview {
  organization: OrganizationSummary;
  metrics: {
    employees: number;
    departments: number;
    open_actions: number;
    upcoming_meetings: number;
  };
  meetings: Meeting[];
  actions: ActionItem[];
  departments: DepartmentSummary[];
  record_catalog: Array<{ type: string; count: number }>;
  is_synthetic_demo: boolean;
}

export interface NotificationItem {
  id: string;
  title: string;
  message: string;
  severity: string;
  category: string;
  source_type: string;
  created_at: string;
  is_read: boolean;
}

export interface ModelConfiguration {
  provider: string;
  enabled: boolean;
  model_name: string;
  endpoint: string;
  credential_configured?: boolean;
}

export interface ConnectionConfiguration {
  connection_key: string;
  label: string;
  kind: string;
  status: string;
  enabled: boolean;
  credential_configured?: boolean;
  configuration: Record<string, string>;
}

export interface TenantConfiguration {
  features: Array<{ key: string; name: string; enabled: boolean }>;
  models: ModelConfiguration[];
  connections: ConnectionConfiguration[];
  operating_profile?: OperatingProfile;
  trust_summary?: TrustSummary;
}

export interface TrustSummary {
  boundary: TrustControl;
  runtime: TrustControl;
  connections: TrustControl;
  evidence: TrustControl;
  approvals: TrustControl;
}

export interface TrustControl {
  status: string;
  title: string;
  detail: string;
}

export interface OperatingProfile {
  profile_key: string;
  name: string;
  description: string;
  deployment_mode: string;
  deployment_policy: {
    name: string;
    description: string;
    data_residency: string;
    allowed_providers: string[];
    cloud_egress: string;
  };
  departments: string[];
  configured: boolean;
  updated_at?: string;
}

export interface OrganizationProfileOption {
  key: string;
  name: string;
  description: string;
  departments: string[];
  features: string[];
  industry_pack?: string | null;
  default_deployment: string;
}

export interface DeploymentModeOption {
  key: string;
  name: string;
  description: string;
  data_residency: string;
  allowed_providers: string[];
  cloud_egress: string;
}

export interface TenantFeature {
  key: string;
  enabled: boolean;
}

export interface Readiness {
  status: string;
  checks: Record<string, { status: string }>;
}

export interface JobsResponse {
  stats: Record<string, number>;
  jobs?: unknown[];
  workers?: {
    status: string;
    active_count: number;
    max_age_seconds: number;
    workers: Array<{ worker_id: string; started_at: string; last_seen_at: string }>;
  };
}

export interface WorkspaceData {
  overview: WorkspaceOverview;
  meetings: Meeting[];
  actions: ActionItem[];
  records: BusinessRecord[];
  notifications: NotificationItem[];
  configuration: TenantConfiguration | null;
  features: TenantFeature[];
  readiness: Readiness | null;
  jobs: JobsResponse | null;
}

export interface SearchResult {
  type: string;
  title: string;
  subtitle?: string;
  data: Record<string, string | number | boolean | null>;
}

export interface IntelligenceEvidence {
  kind: 'workspace_record' | 'knowledge' | 'project_data';
  title: string;
  excerpt: string;
  department?: string | null;
  classification?: string | null;
}

export interface IntelligenceAnswer {
  id: string;
  answer: string;
  confidence: number;
  warning?: string | null;
  departments: string[];
  action: string;
  provider?: string | null;
  mode: 'organization_agent' | 'project_agent' | 'portfolio_agent' | 'scoped_evidence_fallback' | 'workspace_brief';
  evidence: IntelligenceEvidence[];
  scope?: string;
  sources?: string[];
  data_gaps?: string[];
  agent?: string | null;
  duration_ms?: number | null;
}

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  metadata?: {
    response?: IntelligenceAnswer;
    workspace_view?: string | null;
    department?: string | null;
  };
}

export interface OperatingReport {
  department: { key: string; name: string };
  generated_at: string;
  metrics: Record<string, string | number>;
  sources: { structured: string[]; unstructured?: string[]; execution_mode: string };
  recent_runs: Array<{ id: string; subject_name: string; status: string; playbook: { name: string } }>;
}

export interface OrganizationUnit {
  id: string;
  parent_id: string | null;
  unit_type: string;
  name: string;
  department_key: string | null;
  members: unknown[];
}

export interface RegisteredProject {
  project_id: string;
  name: string;
  description?: string | null;
  primary_dept_id?: string | null;
  status?: string | null;
  priority?: string | null;
  project_type?: string | null;
  target_end_date?: string | null;
  member_role?: string | null;
}

export interface ProjectHealth {
  status?: string;
  message?: string;
  metadata?: Record<string, string | number | boolean | null>;
  kpis?: Array<{ kpi_name: string; current_value: string | number | null; target_value: string | number | null; status: string; unit?: string | null }>;
  upcoming_milestones?: Array<{ name: string; due_date?: string | null; status: string }>;
  open_risks?: Array<{ title: string; probability?: string | number | null; impact?: string | number | null; status: string }>;
}

export interface AgentSkill {
  skill_id: string;
  dept_id: string;
  description: string;
  output_format: string;
  triggers?: string[];
}

export interface LibraryDocument {
  doc_id: string;
  title: string;
  file_format: string;
  project_id?: string | null;
  report_type?: string | null;
  produced_by?: string | null;
  dept_id?: string | null;
  access_level: string;
  page_count?: number;
  status: string;
  created_at: string;
  download_url?: string;
}

export interface ProjectIntelligenceAnswer {
  query_id: string;
  answer: string;
  confidence: number;
  sources: string[];
  data_gaps: string[];
  mode_used: string;
  duration_ms: number;
  agent_used: string;
  domain_intent: string;
}

export interface ProjectMember {
  user_id: string;
  dept_id: string;
  role: string;
  access_level: string;
  joined_at?: string;
}

export interface PortalUser {
  login_key: string;
  rapid_user_id: string;
  name: string;
  email: string;
  role: string;
  division?: string | null;
  permitted_departments: string[];
}

export interface AgentAction {
  action_id: string;
  project_id: string;
  agent_dept: string;
  action_type: string;
  category: string;
  title: string;
  description: string;
  reasoning: string;
  output_file_path?: string | null;
  priority: string;
  status: string;
  created_at: string;
}

export interface ProjectDocument {
  doc_id?: string;
  title: string;
  file_format?: string;
  report_type?: string;
  pages?: number;
  produced_by?: string;
  created_at: string;
  download_url?: string;
}

export interface PortfolioIntelligenceAnswer {
  answer: string;
  confidence: number;
  projects_used: string[];
  data_gaps: string[];
  project_count: number;
  duration_ms: number;
}
