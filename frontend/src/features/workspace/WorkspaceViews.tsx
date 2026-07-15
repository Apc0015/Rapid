import { ArrowUpRight, Search as SearchIcon } from 'lucide-react';
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { DEPARTMENTS, type WorkspaceView } from '../../constants';
import { apiRequest, getProfile } from '../../lib/api';
import { formatDate, formatTime, formatValue, initials } from '../../lib/format';
import type {
  ActionItem,
  BusinessRecord,
  Meeting,
  NotificationItem,
  OperatingReport,
  SearchResult,
  WorkspaceData,
} from '../../types';
import { EmptyState, LoadingState, StatusTag } from '../../components/StatusTag';
import { useToast } from '../../components/ToastProvider';
import { Link } from 'react-router-dom';

export interface WorkspaceViewProps {
  data: WorkspaceData;
  navigate: (view: WorkspaceView) => void;
  openMeeting: (id: string) => void;
  changeAction: (id: string, status: string) => Promise<void>;
  openDepartmentReport: (department: string) => void;
  reportDepartment: string;
  setReportDepartment: (department: string) => void;
  reportSignal: number;
  includeRead: boolean;
  toggleIncludeRead: () => Promise<void>;
  markNotification: (id: string) => Promise<void>;
}

function countLabel(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`;
}

function SegmentedControl({ value, options, onChange, id }: { value: string; options: Array<[string, string]>; onChange: (value: string) => void; id?: string }) {
  return <div className="segmented-control" id={id}>{options.map(([key, label]) => <button key={key} className={value === key ? 'active' : ''} type="button" data-status={key} data-type={key} data-priority={key} onClick={() => onChange(key)}>{label}</button>)}</div>;
}

export function MeetingList({ meetings, onOpen, expanded = false }: { meetings: Meeting[]; onOpen: (id: string) => void; expanded?: boolean }) {
  if (!meetings.length) return <EmptyState>No meetings match this view.</EmptyState>;
  return (
    <div className={`meeting-list${expanded ? ' expanded-list' : ''}`}>
      {meetings.map((meeting) => (
        <button className="meeting-row" data-meeting={meeting.id} key={meeting.id} type="button" onClick={() => onOpen(meeting.id)}>
          <span className="meeting-date"><strong>{formatDate(meeting.starts_at, false)}</strong><small>{formatTime(meeting.starts_at)}</small></span>
          <span className="meeting-title"><strong>{meeting.title}</strong><small>{meeting.meeting_type} · {meeting.department ? DEPARTMENTS[meeting.department] ?? meeting.department : 'Organization-wide'}{meeting.recurrence !== 'none' ? ` · ${meeting.recurrence}` : ''}</small></span>
          <StatusTag value={meeting.status} />
        </button>
      ))}
    </div>
  );
}

export function ActionRow({ action, onChange }: { action: ActionItem; onChange: (id: string, status: string) => Promise<void> }) {
  return (
    <article className="action-row">
      <div><strong>{action.title}</strong><small>{action.owner} · {DEPARTMENTS[action.department] ?? action.department} · due {formatDate(action.due_date, false)}</small></div>
      <div className="action-controls">
        <span className={`priority ${action.priority}`}>{action.priority}</span>
        <select data-action={action.id} aria-label={`Status for ${action.title}`} value={action.status} onChange={(event) => void onChange(action.id, event.target.value)}>
          <option value="open">Open</option><option value="in_progress">In progress</option><option value="done">Done</option>
        </select>
      </div>
    </article>
  );
}

export function OverviewView({ data, navigate, openMeeting, changeAction, openDepartmentReport }: WorkspaceViewProps) {
  const { overview, meetings, actions } = data;
  const openActions = actions.filter((action) => action.status !== 'done').slice(0, 5);
  return (
    <section className="portal-view active" data-portal-view="overview">
      <div className="metric-strip">
        <article><span>People</span><strong id="metric-employees">{overview.metrics.employees}</strong><small>Active organization records</small></article>
        <article><span>Departments</span><strong id="metric-departments">{overview.metrics.departments}</strong><small>Agent teams enabled</small></article>
        <article><span>Open actions</span><strong id="metric-actions">{overview.metrics.open_actions}</strong><small>Cross-team commitments</small></article>
        <article><span>Upcoming meetings</span><strong id="metric-meetings">{overview.metrics.upcoming_meetings}</strong><small>Scheduled operating cadence</small></article>
      </div>
      <section className="workspace-section record-panel">
        <div className="section-title"><div><h2>Business records</h2><p>Linked data across every operational domain.</p></div><button className="text-button" type="button" onClick={() => navigate('search')}>Search all</button></div>
        <div id="records-catalog" className="record-catalog">
          {overview.record_catalog.map((record) => <button className="record-count" data-record-type={record.type} key={record.type} type="button" onClick={() => ['customer', 'lead', 'deal'].includes(record.type) ? navigate('crm') : record.type === 'employee' ? navigate('people') : record.type === 'project' ? navigate('projects') : record.type === 'ticket' ? navigate('tickets') : navigate('search')}><strong>{record.count}</strong><span>{record.type.replaceAll('_', ' ')}</span></button>)}
        </div>
      </section>
      <div className="workspace-grid">
        <section className="workspace-section"><div className="section-title"><div><h2>Upcoming meetings</h2><p>Decision forums across the organization.</p></div><button className="text-button" type="button" onClick={() => navigate('meetings')}>View calendar</button></div><div id="overview-meetings"><MeetingList meetings={meetings.filter((meeting) => meeting.status === 'scheduled').slice(0, 4)} onOpen={openMeeting} /></div></section>
        <aside className="workspace-section"><div className="section-title"><div><h2>Priority actions</h2><p>Commitments needing attention.</p></div><button className="text-button" type="button" onClick={() => navigate('actions')}>View queue</button></div><div id="overview-actions" className="action-list">{openActions.length ? openActions.map((action) => <ActionRow key={action.id} action={action} onChange={changeAction} />) : <EmptyState>No open actions.</EmptyState>}</div></aside>
      </div>
      <section className="workspace-section overview-departments"><div className="section-title"><div><h2>Department health</h2><p>Ten operating teams in one governed workspace.</p></div><button className="text-button" type="button" onClick={() => navigate('departments')}>Open departments</button></div><div id="overview-departments" className="department-grid">{overview.departments.map((department) => <button className="department-summary" data-report-department={department.key} key={department.key} type="button" onClick={() => openDepartmentReport(department.key)}><span className={`signal-dot ${department.status}`} /><div><strong>{department.name}</strong><small>{department.lead}</small></div><b>{department.open_actions} open</b></button>)}</div></section>
    </section>
  );
}

export function MeetingsView({ data, openMeeting }: WorkspaceViewProps) {
  const [status, setStatus] = useState('all');
  const meetings = status === 'all' ? data.meetings : data.meetings.filter((meeting) => meeting.status === status);
  return <section className="portal-view active" data-portal-view="meetings"><div className="toolbar"><SegmentedControl id="meeting-filter" value={status} onChange={setStatus} options={[[ 'all', 'All' ], [ 'scheduled', 'Upcoming' ], [ 'completed', 'Completed' ]]} /><span id="meeting-total" className="result-count">{countLabel(meetings.length, 'meeting')}</span></div><div id="meetings-list"><MeetingList meetings={meetings} onOpen={openMeeting} expanded /></div></section>;
}

export function ActionsView({ data, changeAction }: WorkspaceViewProps) {
  const [status, setStatus] = useState('active');
  const actions = data.actions.filter((action) => status === 'active' ? action.status !== 'done' : action.status === status);
  return <section className="portal-view active" data-portal-view="actions"><div className="toolbar"><SegmentedControl id="action-filter" value={status} onChange={setStatus} options={[[ 'active', 'Active' ], [ 'open', 'Open' ], [ 'in_progress', 'In progress' ], [ 'done', 'Done' ]]} /><span id="action-total" className="result-count">{countLabel(actions.length, 'action')}</span></div><section className="workspace-section"><div id="actions-list" className="action-list">{actions.length ? actions.map((action) => <ActionRow key={action.id} action={action} onChange={changeAction} />) : <EmptyState>No actions match this status.</EmptyState>}</div></section></section>;
}

export function PeopleView({ data }: WorkspaceViewProps) {
  const [query, setQuery] = useState('');
  const people = data.records.filter((record) => record.entity_type === 'employee').filter((record) => `${record.name} ${record.department} ${JSON.stringify(record.data)}`.toLowerCase().includes(query.toLowerCase()));
  return <section className="portal-view active" data-portal-view="people"><div className="toolbar"><label className="filter-input"><span>Filter people</span><input id="people-filter" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Name, role, or department" /></label><span id="people-total" className="result-count">{countLabel(people.length, 'directory record')}</span></div><section className="workspace-section table-section"><div className="table-scroll" role="region" aria-label="People directory table" tabIndex={0}><table className="portal-table"><thead><tr><th>Person</th><th>Role</th><th>Department</th><th>Location</th><th>Reports to</th></tr></thead><tbody id="people-table">{people.map((person) => <tr key={person.id}><td><div className="person-cell"><span>{initials(person.name)}</span><strong>{person.name}</strong></div></td><td>{formatValue('title', person.data.title)}</td><td>{DEPARTMENTS[person.department] ?? person.department}</td><td>{formatValue('location', person.data.location)}</td><td>{formatValue('manager', person.data.manager)}</td></tr>)}</tbody></table>{people.length ? null : <EmptyState>No people match this filter.</EmptyState>}</div></section></section>;
}

function EntityCard({ record, fields }: { record: BusinessRecord; fields: string[] }) {
  return <article className="entity-card"><div className="entity-card-head"><span>{record.entity_type.replaceAll('_', ' ')}</span>{record.data.status ? <StatusTag value={String(record.data.status)} /> : null}</div><h3>{record.name}</h3><dl>{fields.filter((key) => record.data[key] !== undefined).map((key) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{formatValue(key, record.data[key])}</dd></div>)}</dl><footer>{DEPARTMENTS[record.department] ?? record.department}</footer></article>;
}

export function CrmView({ data }: WorkspaceViewProps) {
  const [type, setType] = useState('all');
  const records = data.records.filter((record) => ['customer', 'lead', 'deal'].includes(record.entity_type) && (type === 'all' || record.entity_type === type));
  return <section className="portal-view active" data-portal-view="crm"><div className="toolbar"><SegmentedControl id="crm-filter" value={type} onChange={setType} options={[[ 'all', 'All records' ], [ 'customer', 'Customers' ], [ 'lead', 'Leads' ], [ 'deal', 'Deals' ]]} /><span id="crm-total" className="result-count">{countLabel(records.length, 'CRM record')}</span></div><div id="crm-list" className="entity-grid">{records.length ? records.map((record) => <EntityCard key={record.id} record={record} fields={['segment', 'stage', 'health', 'owner', 'arr', 'value', 'renewal']} />) : <EmptyState>No CRM records match this view.</EmptyState>}</div></section>;
}

export function ProjectsView({ data }: WorkspaceViewProps) {
  const [query, setQuery] = useState('');
  const projects = data.records.filter((record) => record.entity_type === 'project').filter((record) => `${record.name} ${JSON.stringify(record.data)}`.toLowerCase().includes(query.toLowerCase()));
  return <section className="portal-view active" data-portal-view="projects"><div className="toolbar"><label className="filter-input"><span>Filter projects</span><input id="project-filter" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Project, owner, or status" /></label><span id="project-total" className="result-count">{countLabel(projects.length, 'project')}</span></div><div id="projects-list" className="entity-grid">{projects.length ? projects.map((record) => <EntityCard key={record.id} record={record} fields={['status', 'owner', 'target']} />) : <EmptyState>No projects match this filter.</EmptyState>}</div></section>;
}

export function TicketsView({ data }: WorkspaceViewProps) {
  const [priority, setPriority] = useState('all');
  const tickets = data.records.filter((record) => record.entity_type === 'ticket' && (priority === 'all' || record.data.priority === priority));
  return <section className="portal-view active" data-portal-view="tickets"><div className="toolbar"><SegmentedControl id="ticket-filter" value={priority} onChange={setPriority} options={[[ 'all', 'All' ], [ 'high', 'High priority' ], [ 'medium', 'Medium' ]]} /><span id="ticket-total" className="result-count">{countLabel(tickets.length, 'ticket')}</span></div><section className="workspace-section table-section"><div className="table-scroll" role="region" aria-label="Service tickets table" tabIndex={0}><table className="portal-table"><thead><tr><th>Ticket</th><th>Department</th><th>Priority</th><th>Status</th><th>Owner</th></tr></thead><tbody id="tickets-table">{tickets.map((ticket) => <tr key={ticket.id}><td><strong>{ticket.name}</strong></td><td>{DEPARTMENTS[ticket.department] ?? ticket.department}</td><td><span className={`priority ${ticket.data.priority}`}>{ticket.data.priority}</span></td><td><StatusTag value={String(ticket.data.status)} /></td><td>{formatValue('owner', ticket.data.owner)}</td></tr>)}</tbody></table>{tickets.length ? null : <EmptyState>No tickets match this priority.</EmptyState>}</div></section></section>;
}

export function DepartmentsView({ data, openDepartmentReport }: WorkspaceViewProps) {
  return <section className="portal-view active" data-portal-view="departments"><div id="departments-list" className="department-directory">{data.overview.departments.map((department) => <article className="department-card" key={department.key}><header><span className={`signal-dot ${department.status}`} /><div><p>{department.key.toUpperCase()}</p><h2>{department.name}</h2></div><StatusTag value={department.status} /></header><dl><div><dt>Department lead</dt><dd>{department.lead}</dd></div><div><dt>Open commitments</dt><dd>{department.open_actions}</dd></div><div><dt>Operating mode</dt><dd>Governed agent team</dd></div></dl><button className="product-button secondary" data-report-department={department.key} type="button" onClick={() => openDepartmentReport(department.key)}>Open operating report</button></article>)}</div></section>;
}

export function ReportsView({ reportDepartment, setReportDepartment, reportSignal }: WorkspaceViewProps) {
  const [report, setReport] = useState<OperatingReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  async function generate() {
    setLoading(true); setError('');
    try { setReport(await apiRequest<OperatingReport>(`/organization/reports/${reportDepartment}`)); }
    catch (issue) { setError(issue instanceof Error ? issue.message : 'Report generation failed.'); }
    finally { setLoading(false); }
  }
  useEffect(() => { if (reportSignal > 0) void generate(); }, [reportSignal]); // reportSignal is the explicit product-shell command.
  return <section className="portal-view active" data-portal-view="reports"><div className="report-layout"><aside className="report-selector workspace-section"><label className="admin-label">Department<select id="report-department" value={reportDepartment} onChange={(event) => setReportDepartment(event.target.value)}>{Object.entries(DEPARTMENTS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><button id="generate-report" className="product-button primary" type="button" onClick={() => void generate()} disabled={loading}>{loading ? 'Generating…' : 'Generate report'}</button><p>Reports use tenant-scoped workflow evidence and approved department sources.</p></aside><section id="report-output" className="workspace-section report-output">{loading ? <LoadingState compact /> : error ? <div className="portal-error"><strong>Report generation failed.</strong><p>{error}</p></div> : report ? <><div className="report-head"><div><p className="auth-kicker">{report.department.name}</p><h2>Operating report</h2><p>Generated {formatDate(report.generated_at)}</p></div><StatusTag value={report.sources.execution_mode} /></div><div className="report-metrics">{Object.entries(report.metrics).map(([key, value]) => <article key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{value}</strong></article>)}</div><section><h3>Approved data domains</h3><div className="domain-list">{report.sources.structured.map((domain) => <span key={domain}>{domain}</span>)}</div></section><section><h3>Recent workflow runs</h3>{report.recent_runs.length ? report.recent_runs.map((run) => <div className="report-run" key={run.id}><div><strong>{run.subject_name}</strong><small>{run.playbook.name}</small></div><StatusTag value={run.status} /></div>) : <EmptyState>No workflow runs have been recorded for this department yet.</EmptyState>}</section></> : <EmptyState>Choose a department to generate its operating report.</EmptyState>}</section></div></section>;
}

export function SearchView() {
  const [query, setQuery] = useState('');
  const [summary, setSummary] = useState('Search is permission-aware and limited to this organization.');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  async function search(event: FormEvent) {
    event.preventDefault(); setLoading(true); setSummary(`Searching for “${query}”…`);
    try { const response = await apiRequest<{ count: number; results: SearchResult[] }>(`/workspace/search?q=${encodeURIComponent(query.trim())}&limit=50`); setResults(response.results); setSummary(`${response.count} result${response.count === 1 ? '' : 's'} across this organization`); }
    catch (issue) { setSummary(issue instanceof Error ? issue.message : 'Search could not be completed.'); setResults([]); }
    finally { setLoading(false); }
  }
  return <section className="portal-view active" data-portal-view="search"><form id="global-search-form" className="global-search" onSubmit={search}><label><span>Search the organization</span><div className="search-input-wrap"><SearchIcon size={15} aria-hidden="true" /><input id="global-search-input" type="search" minLength={2} required autoComplete="off" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search people, customers, projects, meetings, and actions" /></div></label><button className="product-button primary" type="submit" disabled={loading}>{loading ? 'Searching…' : 'Search'}</button></form><div id="search-summary" className="search-summary">{summary}</div><div id="search-results" className="search-results">{loading ? <LoadingState compact /> : results.map((item, index) => <article className="search-result" key={`${item.type}-${item.title}-${index}`}><span>{item.type.replaceAll('_', ' ')}</span><div><strong>{item.title}</strong><p>{item.subtitle ?? ''}</p></div>{item.data.status ? <StatusTag value={String(item.data.status)} /> : null}</article>)}</div></section>;
}

export function NotificationsView({ data, includeRead, toggleIncludeRead, markNotification }: WorkspaceViewProps) {
  return <section className="portal-view active" data-portal-view="notifications"><div className="toolbar"><span id="notification-total" className="result-count">{countLabel(data.notifications.length, 'notification')}</span><button id="show-read-notifications" className="product-button secondary compact" type="button" onClick={() => void toggleIncludeRead()}>{includeRead ? 'Hide read' : 'Show read'}</button></div><div id="notifications-list" className="notification-list">{data.notifications.length ? data.notifications.map((item: NotificationItem) => <article className={`notification-row${item.is_read ? ' read' : ''}`} key={item.id}><span className={`notification-severity ${item.severity}`} /><div><div className="notification-title"><strong>{item.title}</strong><StatusTag value={item.category} /></div><p>{item.message}</p><small>{formatDate(item.created_at)} · {item.source_type.replaceAll('_', ' ')}</small></div>{item.is_read ? <span className="read-label">Read</span> : <button className="product-button secondary compact" data-notification={item.id} type="button" onClick={() => void markNotification(item.id)}>Mark read</button>}</article>) : <EmptyState>{includeRead ? 'There are no notifications.' : 'You are caught up.'}</EmptyState>}</div></section>;
}

export function SettingsView({ data }: WorkspaceViewProps) {
  const profile = getProfile();
  const checks = data.readiness?.checks ?? {};
  const jobStats = data.jobs?.stats ?? {};
  const account = [['Name', profile.name ?? 'Demo CEO'], ['Role', profile.role ?? 'ceo'], ['Organization', data.overview.organization.name], ['Workspace', data.overview.organization.industry]];
  return <section className="portal-view active" data-portal-view="settings"><div className="settings-grid"><section className="workspace-section"><div className="section-title"><div><h2>Account</h2><p>Your current workspace identity.</p></div></div><dl id="account-details" className="detail-list">{account.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value).replaceAll('_', ' ')}</dd></div>)}</dl></section><section className="workspace-section"><div className="section-title"><div><h2>AI runtime</h2><p>Configured organization model providers.</p></div></div><div id="settings-models" className="connection-list">{data.configuration ? data.configuration.models.map((model) => <article className="connection-row" key={model.provider}><div><strong>{model.provider}</strong><small>{model.model_name || 'No model selected'} · {model.endpoint || 'No endpoint'}</small></div><StatusTag value={model.enabled ? 'enabled' : 'disabled'} /></article>) : <EmptyState>Administrator access is required to view model configuration.</EmptyState>}</div></section><section className="workspace-section settings-wide"><div className="section-title"><div><h2>Platform readiness</h2><p>API dependencies and durable background processing.</p></div></div><div id="settings-runtime" className="runtime-grid"><article><span>API</span><strong>{data.readiness?.status ?? 'unavailable'}</strong></article>{Object.entries(checks).map(([name, check]) => <article key={name}><span>{name.replaceAll('_', ' ')}</span><strong>{check.status}</strong></article>)}<article><span>Queued jobs</span><strong>{jobStats.queued ?? 0}</strong></article><article><span>Retries</span><strong>{jobStats.retry ?? 0}</strong></article><article><span>Dead letters</span><strong className={jobStats.dead_letter ? 'text-error' : ''}>{jobStats.dead_letter ?? 0}</strong></article></div></section><section className="workspace-section settings-wide"><div className="section-title"><div><h2>Organization connections</h2><p>SSO, databases, collaboration, and knowledge storage.</p></div><Link className="text-button" to="/admin/configuration">Manage configuration <ArrowUpRight size={12} /></Link></div><div id="settings-connections" className="connection-list">{data.configuration ? data.configuration.connections.map((connection) => <article className="connection-row" key={connection.connection_key}><div><strong>{connection.label}</strong><small>{connection.kind} · {connection.configuration.provider ?? connection.configuration.engine ?? 'not configured'}</small></div><StatusTag value={connection.status} /></article>) : <EmptyState>Administrator access is required to view connections.</EmptyState>}</div></section><section className="workspace-section settings-wide"><div className="section-title"><div><h2>Administration</h2><p>Manage access, teams, and service configuration.</p></div></div><div className="settings-actions"><Link className="product-button secondary" to="/admin/users">Users and invitations</Link><Link className="product-button secondary" to="/admin/configuration">Tenant configuration</Link><Link className="product-button secondary" to="/operations">Operations console</Link></div></section></div></section>;
}

export const WORKSPACE_VIEW_COMPONENTS = {
  overview: OverviewView,
  meetings: MeetingsView,
  actions: ActionsView,
  people: PeopleView,
  crm: CrmView,
  projects: ProjectsView,
  tickets: TicketsView,
  departments: DepartmentsView,
  reports: ReportsView,
  search: SearchView,
  notifications: NotificationsView,
  settings: SettingsView,
} as const;
