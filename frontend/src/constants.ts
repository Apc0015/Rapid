export const DEPARTMENTS: Record<string, string> = {
  hr: 'People Ops',
  finance: 'Finance',
  legal: 'Legal',
  sales: 'Sales',
  marketing: 'Marketing',
  ops: 'Operations',
  it: 'IT',
  procurement: 'Procurement',
  rd: 'R&D / Product',
  customer_success: 'Customer Success',
};

export const WORKSPACE_VIEWS = [
  'overview',
  'meetings',
  'actions',
  'people',
  'crm',
  'projects',
  'tickets',
  'departments',
  'chat',
  'reports',
  'library',
  'search',
  'notifications',
  'settings',
] as const;

export type WorkspaceView = (typeof WORKSPACE_VIEWS)[number];

export const VIEW_META: Record<WorkspaceView, { context: string; title: string; description: string }> = {
  overview: { context: 'Startup workspace', title: 'Overview', description: 'A current picture of the work, decisions, and risks that need attention.' },
  meetings: { context: 'Meetings and decisions', title: 'Meetings', description: 'Plan cadence, invite participants, capture evidence, and assign follow-up.' },
  actions: { context: 'Commitment tracking', title: 'Action queue', description: 'Every decision has an owner, due date, and visible status.' },
  people: { context: 'Organization directory', title: 'People', description: 'Roles, reporting lines, locations, and department membership.' },
  crm: { context: 'Customer operations', title: 'CRM', description: 'Customers, leads, opportunities, health, and commercial context.' },
  projects: { context: 'Delivery portfolio', title: 'Projects', description: 'Cross-functional initiatives, owners, status, and target dates.' },
  tickets: { context: 'Service operations', title: 'Tickets', description: 'Operational, customer, and IT issues requiring resolution.' },
  departments: { context: 'Operating teams', title: 'Departments', description: 'Focused work areas that prepare insights and work through reviewable playbooks.' },
  chat: { context: 'Startup intelligence', title: 'Chat with RAPID', description: 'Ask questions, investigate evidence, and prepare the next piece of work.' },
  reports: { context: 'Evidence and reporting', title: 'Reports', description: 'Generate department operating reports from scoped evidence.' },
  library: { context: 'Governed knowledge', title: 'Library', description: 'Approved documents and agent skills available to this organization.' },
  search: { context: 'Startup intelligence', title: 'Search', description: 'Find connected records inside your workspace and permission boundary.' },
  notifications: { context: 'Attention center', title: 'Notifications', description: 'Risks, approvals, incidents, and decisions requiring awareness.' },
  settings: { context: 'Workspace administration', title: 'Settings', description: 'Account, AI runtime, workspace services, and company connections.' },
};

export const isWorkspaceView = (value?: string): value is WorkspaceView =>
  WORKSPACE_VIEWS.includes(value as WorkspaceView);

export const VIEW_FEATURES: Partial<Record<WorkspaceView, string>> = {
  meetings: 'meetings',
  actions: 'workflows',
  people: 'people',
  crm: 'crm',
  projects: 'projects',
  tickets: 'tickets',
  departments: 'people',
  reports: 'reports',
  library: 'knowledge',
  search: 'knowledge',
  notifications: 'workflows',
};
