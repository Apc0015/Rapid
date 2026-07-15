export interface Profile {
  name?: string;
  role?: string;
  tenant_id?: string;
  username?: string;
}

export interface AuthResponse {
  access_token: string;
  profile?: Profile;
  name?: string;
  role?: string;
  user_id?: string;
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
}

export interface Readiness {
  status: string;
  checks: Record<string, { status: string }>;
}

export interface JobsResponse {
  stats: Record<string, number>;
  jobs?: unknown[];
}

export interface WorkspaceData {
  overview: WorkspaceOverview;
  meetings: Meeting[];
  actions: ActionItem[];
  records: BusinessRecord[];
  notifications: NotificationItem[];
  configuration: TenantConfiguration | null;
  readiness: Readiness | null;
  jobs: JobsResponse | null;
}

export interface SearchResult {
  type: string;
  title: string;
  subtitle?: string;
  data: Record<string, string | number | boolean | null>;
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
