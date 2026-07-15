import { ArrowUpRight, BookOpen, Download, FileText, Pencil, Plus, RefreshCw, Search as SearchIcon, Sparkles, UsersRound } from 'lucide-react';
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { DEPARTMENTS, type WorkspaceView } from '../../constants';
import { apiRequest, downloadFile, getProfile } from '../../lib/api';
import { formatDate, formatTime, formatValue, initials } from '../../lib/format';
import type {
  AgentAction,
  ActionItem,
  BusinessRecord,
  AgentSkill,
  LibraryDocument,
  Meeting,
  NotificationItem,
  OperatingReport,
  PortfolioIntelligenceAnswer,
  ProjectDocument,
  ProjectHealth,
  ProjectIntelligenceAnswer,
  ProjectMember,
  PortalUser,
  RegisteredProject,
  SearchResult,
  WorkspaceData,
} from '../../types';
import { EmptyState, LoadingState, StatusTag } from '../../components/StatusTag';
import { Modal } from '../../components/Modal';
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
      <section className="metric-strip overview-metrics" aria-label="Organization snapshot">
        <article><span>People</span><strong id="metric-employees">{overview.metrics.employees}</strong><small>Active organization records</small></article>
        <article><span>Departments</span><strong id="metric-departments">{overview.metrics.departments}</strong><small>Agent teams enabled</small></article>
        <article><span>Open actions</span><strong id="metric-actions">{overview.metrics.open_actions}</strong><small>Cross-team commitments</small></article>
        <article><span>Upcoming meetings</span><strong id="metric-meetings">{overview.metrics.upcoming_meetings}</strong><small>Scheduled operating cadence</small></article>
      </section>
      <div className="workspace-grid overview-workboard">
        <section className="workspace-section overview-priorities"><div className="section-title"><div><p className="section-context">Operating focus</p><h2>Priority actions</h2><p>Commitments that need a decision or owner update.</p></div><button className="text-button" type="button" onClick={() => navigate('actions')}>View queue</button></div><div id="overview-actions" className="action-list">{openActions.length ? openActions.map((action) => <ActionRow key={action.id} action={action} onChange={changeAction} />) : <EmptyState>No open actions.</EmptyState>}</div></section>
        <section className="workspace-section overview-meetings"><div className="section-title"><div><p className="section-context">Operating cadence</p><h2>Upcoming meetings</h2><p>Decision forums across the organization.</p></div><button className="text-button" type="button" onClick={() => navigate('meetings')}>View calendar</button></div><div id="overview-meetings"><MeetingList meetings={meetings.filter((meeting) => meeting.status === 'scheduled').slice(0, 4)} onOpen={openMeeting} /></div></section>
      </div>
      <section className="workspace-section overview-departments"><div className="section-title"><div><p className="section-context">Organization index</p><h2>Department health</h2><p>Ten operating teams in one governed workspace.</p></div><button className="text-button" type="button" onClick={() => navigate('departments')}>Open departments</button></div><div id="overview-departments" className="department-grid">{overview.departments.map((department) => <button className="department-summary" data-report-department={department.key} key={department.key} type="button" onClick={() => openDepartmentReport(department.key)}><span className={`signal-dot ${department.status}`} /><div><strong>{department.name}</strong><small>{department.lead}</small></div><b>{department.open_actions} open</b></button>)}</div></section>
      <section className="overview-records" aria-label="Business record catalog">
        <div><strong>Business records</strong><span>Connected operational data</span></div>
        <div id="records-catalog" className="record-catalog">
          {overview.record_catalog.map((record) => <button className="record-count" data-record-type={record.type} key={record.type} type="button" onClick={() => ['customer', 'lead', 'deal'].includes(record.type) ? navigate('crm') : record.type === 'employee' ? navigate('people') : record.type === 'project' ? navigate('projects') : record.type === 'ticket' ? navigate('tickets') : navigate('search')}><strong>{record.count}</strong><span>{record.type.replaceAll('_', ' ')}</span></button>)}
        </div>
        <button className="text-button" type="button" onClick={() => navigate('search')}>Search all</button>
      </section>
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

function projectDepartment(project: RegisteredProject): string {
  return DEPARTMENTS[project.primary_dept_id ?? ''] ?? project.primary_dept_id ?? 'Organization-wide';
}

function ProjectIntelligence({ projects, onRefresh }: { projects: RegisteredProject[]; onRefresh: () => Promise<void> }) {
  const { notify } = useToast();
  const [selectedId, setSelectedId] = useState('');
  const [health, setHealth] = useState<ProjectHealth | null>(null);
  const [skills, setSkills] = useState<AgentSkill[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [question, setQuestion] = useState('');
  const [mode, setMode] = useState('analysis');
  const [answer, setAnswer] = useState<ProjectIntelligenceAnswer | null>(null);
  const [asking, setAsking] = useState(false);
  const [documents, setDocuments] = useState<ProjectDocument[]>([]);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [users, setUsers] = useState<PortalUser[]>([]);
  const [pendingActions, setPendingActions] = useState<AgentAction[]>([]);
  const [approvedActions, setApprovedActions] = useState<AgentAction[]>([]);
  const [teamOpen, setTeamOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [portfolioOpen, setPortfolioOpen] = useState(false);
  const [rejectingAction, setRejectingAction] = useState<AgentAction | null>(null);
  const [portfolioAnswer, setPortfolioAnswer] = useState<PortfolioIntelligenceAnswer | null>(null);
  const [skillOutput, setSkillOutput] = useState<{ title: string; message?: string; preview?: string; download_url?: string; action_id?: string } | null>(null);

  useEffect(() => { if (!selectedId && projects[0]) setSelectedId(projects[0].project_id); }, [projects, selectedId]);
  useEffect(() => {
    if (!selectedId) return;
    let active = true;
    setLoading(true); setError(''); setHealth(null); setSkills([]); setAnswer(null);
    void Promise.all([
      apiRequest<{ health: ProjectHealth }>(`/projects/${selectedId}/status`),
      apiRequest<{ skills: AgentSkill[] }>(`/projects/${selectedId}/skills/available`),
      apiRequest<{ documents: ProjectDocument[] }>(`/projects/${selectedId}/documents`),
      apiRequest<{ members: ProjectMember[] }>(`/projects/${selectedId}`),
      apiRequest<{ users: PortalUser[] }>('/users/list').catch(() => ({ users: [] })),
      apiRequest<{ actions: AgentAction[] }>('/actions?status=pending&limit=100').catch(() => ({ actions: [] })),
      apiRequest<{ actions: AgentAction[] }>('/actions?status=approved&limit=100').catch(() => ({ actions: [] })),
    ]).then(([healthResponse, skillResponse, documentResponse, projectResponse, userResponse, pendingResponse, approvedResponse]) => {
      if (!active) return;
      setHealth(healthResponse.health); setSkills(skillResponse.skills); setDocuments(documentResponse.documents); setMembers(projectResponse.members); setUsers(userResponse.users);
      setPendingActions(pendingResponse.actions.filter((action) => action.project_id === selectedId));
      setApprovedActions(approvedResponse.actions.filter((action) => action.project_id === selectedId));
    }).catch((issue) => {
      if (active) setError(issue instanceof Error ? issue.message : 'Project intelligence could not load.');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [selectedId]);

  async function askProject(event: FormEvent) {
    event.preventDefault();
    if (!selectedId || !question.trim()) return;
    setAsking(true); setError(''); setAnswer(null);
    try {
      const result = await apiRequest<ProjectIntelligenceAnswer>(`/projects/${selectedId}/query`, {
        method: 'POST', body: JSON.stringify({ query: question.trim(), mode }),
      });
      setAnswer(result);
    } catch (issue) { setError(issue instanceof Error ? issue.message : 'The project agent could not complete that request.'); }
    finally { setAsking(false); }
  }

  async function executeSkill(skill: AgentSkill) {
    if (!selectedId) return;
    setError(''); setSkillOutput(null);
    try {
      const output = await apiRequest<{ title: string; message?: string; preview?: string; download_url?: string; action_id?: string }>(`/projects/${selectedId}/skills/execute`, { method: 'POST', body: JSON.stringify({ skill_id: skill.skill_id, params: {}, enqueue_action: true }) });
      setSkillOutput(output);
      if (output.action_id) {
        const actions = await apiRequest<{ actions: AgentAction[] }>('/actions?status=pending&limit=100');
        setPendingActions(actions.actions.filter((action) => action.project_id === selectedId));
      }
      notify('Skill output is ready for human review.');
    } catch (issue) { setError(issue instanceof Error ? issue.message : 'The skill could not run.'); }
  }

  async function updateProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selectedId) return; const form = new FormData(event.currentTarget);
    try {
      await apiRequest(`/projects/${selectedId}`, { method: 'PATCH', body: JSON.stringify({ name: form.get('name'), description: form.get('description'), status: form.get('status'), priority: form.get('priority'), target_end_date: form.get('target_end_date') || null }) });
      setEditOpen(false); await onRefresh();
    } catch (issue) { setError(issue instanceof Error ? issue.message : 'Project could not be updated.'); }
  }

  async function addMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selectedId) return; const form = new FormData(event.currentTarget);
    try {
      await apiRequest(`/projects/${selectedId}/members`, { method: 'POST', body: JSON.stringify({ user_id: form.get('user_id'), dept_id: form.get('dept_id'), role: form.get('role'), access_level: form.get('access_level') }) });
      const response = await apiRequest<{ members: ProjectMember[] }>(`/projects/${selectedId}`); setMembers(response.members); event.currentTarget.reset();
    } catch (issue) { setError(issue instanceof Error ? issue.message : 'Member could not be added.'); }
  }

  async function removeMember(member: ProjectMember) {
    if (!selectedId) return;
    try { await apiRequest(`/projects/${selectedId}/members/${encodeURIComponent(member.user_id)}`, { method: 'DELETE' }); setMembers((current) => current.filter((item) => item.user_id !== member.user_id)); }
    catch (issue) { setError(issue instanceof Error ? issue.message : 'Member could not be removed.'); }
  }

  async function approveAction(action: AgentAction) {
    try {
      const response = await apiRequest<{ action: AgentAction }>(`/actions/${action.action_id}/approve`, { method: 'POST', body: JSON.stringify({}) });
      const approved = response.action;
      setPendingActions((current) => current.filter((item) => item.action_id !== action.action_id));
      setApprovedActions((current) => [approved, ...current.filter((item) => item.action_id !== action.action_id)]);
      if (skillOutput?.action_id === action.action_id && action.output_file_path) {
        const filename = action.output_file_path.split(/[\\/]/).pop();
        if (filename) setSkillOutput((current) => current ? { ...current, message: 'Approved and ready to distribute.', download_url: `/projects/${action.project_id}/skills/download/${encodeURIComponent(filename)}` } : current);
      }
      notify('Output approved and recorded.');
    } catch (issue) { setError(issue instanceof Error ? issue.message : 'The output could not be approved.'); }
  }

  async function rejectAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!rejectingAction) return;
    const form = new FormData(event.currentTarget);
    const reason = String(form.get('reason') || '').trim();
    try {
      await apiRequest(`/actions/${rejectingAction.action_id}/reject`, { method: 'POST', body: JSON.stringify({ reason }) });
      setPendingActions((current) => current.filter((item) => item.action_id !== rejectingAction.action_id));
      setRejectingAction(null);
      notify('Output rejected with reviewer feedback.');
    } catch (issue) { setError(issue instanceof Error ? issue.message : 'The output could not be rejected.'); }
  }

  async function analyzePortfolio(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget); const projectIds = form.getAll('project_ids').map(String);
    try { setPortfolioAnswer(await apiRequest<PortfolioIntelligenceAnswer>('/projects/portfolio/query', { method: 'POST', body: JSON.stringify({ query: form.get('query'), project_ids: projectIds }) })); }
    catch (issue) { setError(issue instanceof Error ? issue.message : 'Portfolio analysis could not run.'); }
  }

  if (!projects.length) return <section className="workspace-section project-intelligence-empty"><div className="section-title"><div><p className="section-context">Connected projects</p><h2>Project intelligence</h2><p>Project-aware agents activate after a project data space is provisioned.</p></div><Sparkles size={17} className="section-icon" /></div><EmptyState>Create a project to provision its isolated data space and agent team.</EmptyState></section>;

  const selected = projects.find((project) => project.project_id === selectedId);
  const leadRisk = health?.open_risks?.[0];
  const availableUsers = users.filter((user) => user.rapid_user_id && !members.some((member) => member.user_id === user.rapid_user_id));
  const memberName = (member: ProjectMember) => users.find((user) => user.rapid_user_id === member.user_id)?.name ?? member.user_id;
  return <><section className="workspace-section project-intelligence"><div className="section-title"><div><p className="section-context">Connected projects</p><h2>Project intelligence</h2><p>Ask a scoped agent, review live health, and use only skills permitted for the selected project.</p></div><div className="project-command-bar"><button className="icon-button icon-only" type="button" aria-label="Edit project" title="Edit project" onClick={() => setEditOpen(true)}><Pencil size={14} /></button><button className="icon-button icon-only" type="button" aria-label="Manage project team" title="Manage project team" onClick={() => setTeamOpen(true)}><UsersRound size={14} /></button><button className="product-button secondary compact" type="button" onClick={() => setPortfolioOpen(true)}>Portfolio</button></div></div>
    <div className="project-intelligence-layout">
      <div className="project-registry" role="list" aria-label="Registered projects">{projects.map((project) => <button className={project.project_id === selectedId ? 'selected' : ''} key={project.project_id} type="button" onClick={() => setSelectedId(project.project_id)}><span><strong>{project.name}</strong><small>{projectDepartment(project)} · {project.member_role ?? 'member'}</small></span><StatusTag value={project.status} /></button>)}</div>
      <div className="project-intelligence-detail">
        {loading ? <LoadingState compact /> : error ? <div className="portal-error"><strong>Project intelligence is unavailable.</strong><p>{error}</p></div> : selected ? <>
          <div className="project-health-head"><div><h3>{selected.name}</h3><p>{selected.description || `${projectDepartment(selected)} project workspace`}</p></div><div><StatusTag value={selected.priority} /><StatusTag value={selected.status} /></div></div>
          {health?.status ? <div className="project-data-note">{health.message || 'This project data space is ready for configuration.'}</div> : <div className="project-health-grid">{health?.kpis?.slice(0, 3).map((kpi) => <article key={kpi.kpi_name}><span>{kpi.kpi_name}</span><strong>{formatValue('value', kpi.current_value)}</strong><small>{kpi.target_value === null || kpi.target_value === undefined ? kpi.status : `Target ${formatValue('value', kpi.target_value)}`}</small></article>)}{leadRisk ? <article><span>Open risks</span><strong>{health?.open_risks?.length}</strong><small>{leadRisk.title}</small></article> : null}</div>}
          <form id="project-intelligence-form" className="project-query-form" onSubmit={askProject}><label><span>Ask about this project</span><textarea id="project-intelligence-question" value={question} onChange={(event) => setQuestion(event.target.value)} minLength={2} required placeholder="Identify the current delivery risks" /></label><div><select aria-label="Project analysis mode" value={mode} onChange={(event) => setMode(event.target.value)}><option value="query">Question</option><option value="analysis">Analysis</option><option value="planning">Plan</option><option value="reporting">Report</option></select><button className="product-button primary" type="submit" disabled={asking}>{asking ? 'Analyzing…' : 'Ask project agent'}</button></div></form>
          {answer ? <section id="project-intelligence-output" className="project-answer"><div><strong>Scoped answer</strong><span>{Math.round(answer.confidence * 100)}% confidence · {answer.agent_used.replaceAll('_', ' ')}</span></div><p>{answer.answer}</p>{answer.data_gaps.length ? <small>Data gaps: {answer.data_gaps.join(' · ')}</small> : null}</section> : null}
          <div className="project-documents"><div><h3>Generated documents</h3><p>{documents.length} outputs available to this project.</p></div>{documents.length ? <ul>{documents.slice(0, 4).map((document) => <li key={`${document.title}-${document.created_at}`}><span><strong>{document.title}</strong><small>{document.file_format || 'file'} · {formatDate(document.created_at, false)}</small></span>{document.download_url ? <button className="icon-button icon-only" type="button" aria-label={`Download ${document.title}`} title="Download document" onClick={() => void downloadFile(document.download_url!, document.title)}><Download size={13} /></button> : null}</li>)}</ul> : <small>No generated documents yet.</small>}</div>
          <div className="project-skills"><div><h3>Available agent skills</h3><p>{skills.length} skills are permitted for this project’s department.</p></div><ul>{skills.slice(0, 6).map((skill) => <li key={skill.skill_id}><span><strong>{skill.skill_id.replaceAll('_', ' ')}</strong><small>{skill.description || 'Generated output with review controls.'}</small></span><div><em>{skill.output_format}</em><button className="icon-button icon-only" type="button" aria-label={`Run ${skill.skill_id}`} title="Run skill" onClick={() => void executeSkill(skill)}><Sparkles size={13} /></button></div></li>)}</ul></div>
          {skillOutput ? <section className="project-answer"><div><strong>{skillOutput.title}</strong><span>{skillOutput.download_url ? 'Approved output' : 'Queued for review'}</span></div><p>{skillOutput.message || skillOutput.preview || 'Skill output generated.'}</p>{skillOutput.download_url ? <button className="product-button secondary compact" type="button" onClick={() => void downloadFile(skillOutput.download_url!, skillOutput.title)}><Download size={13} /> Download approved output</button> : null}</section> : null}
          <section className="project-approvals"><div><h3>Review queue</h3><p>{pendingActions.length} generated output{pendingActions.length === 1 ? '' : 's'} awaiting a reviewer.</p></div>{pendingActions.length ? <ul>{pendingActions.map((action) => <li key={action.action_id}><div><strong>{action.title}</strong><small>{action.agent_dept} · {formatDate(action.created_at, false)} · {action.priority} priority</small><p>{action.description || action.reasoning || 'Review this generated output before distribution.'}</p></div><div className="approval-actions"><button className="product-button secondary compact" type="button" onClick={() => void approveAction(action)}>Approve</button><button className="text-button danger-button" type="button" onClick={() => setRejectingAction(action)}>Reject</button></div></li>)}</ul> : <small>No outputs need a decision.</small>}{approvedActions.filter((action) => action.output_file_path).length ? <div className="approved-output-list"><strong>Ready to distribute</strong>{approvedActions.filter((action) => action.output_file_path).slice(0, 4).map((action) => { const filename = action.output_file_path?.split(/[\\/]/).pop(); return <button key={action.action_id} className="text-button" type="button" disabled={!filename} onClick={() => filename && void downloadFile(`/projects/${action.project_id}/skills/download/${encodeURIComponent(filename)}`, action.title)}>{action.title}<Download size={12} /></button>; })}</div> : null}</section>
        </> : null}
      </div>
    </div>
  </section><Modal id="project-edit-dialog" open={editOpen} onClose={() => setEditOpen(false)} title="Edit project" context="Project configuration"><form className="stack-form" onSubmit={updateProject}><label className="admin-label">Name<input name="name" defaultValue={selected?.name ?? ''} required /></label><label className="admin-label">Description<textarea name="description" defaultValue={selected?.description ?? ''} /></label><label className="admin-label">Status<select name="status" defaultValue={selected?.status ?? 'active'}><option value="active">Active</option><option value="on_hold">On hold</option><option value="completed">Completed</option></select></label><label className="admin-label">Priority<select name="priority" defaultValue={selected?.priority ?? 'medium'}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label><label className="admin-label">Target date<input name="target_end_date" type="date" defaultValue={selected?.target_end_date?.slice(0, 10) ?? ''} /></label><button className="product-button primary" type="submit">Save project</button></form></Modal><Modal id="project-team-dialog" open={teamOpen} onClose={() => setTeamOpen(false)} title="Project team" context="Scoped access"><form className="project-member-form" onSubmit={addMember}><label className="admin-label">Person<select name="user_id" required disabled={!availableUsers.length}><option value="">{availableUsers.length ? 'Select a person' : 'No eligible people available'}</option>{availableUsers.map((user) => <option key={user.rapid_user_id} value={user.rapid_user_id}>{user.name} · {user.role.replaceAll('_', ' ')}</option>)}</select></label><label className="admin-label">Department<select name="dept_id" defaultValue={selected?.primary_dept_id ?? 'ops'}>{Object.entries(DEPARTMENTS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><label className="admin-label">Role<select name="role" defaultValue="member"><option value="owner">Owner</option><option value="manager">Manager</option><option value="member">Member</option><option value="viewer">Viewer</option></select></label><label className="admin-label">Access<select name="access_level" defaultValue="standard"><option value="full">Full</option><option value="manager">Manager</option><option value="standard">Standard</option><option value="readonly">Read only</option></select></label><button className="product-button primary" type="submit" disabled={!availableUsers.length}>Add member</button></form><div className="member-list">{members.map((member) => <article key={member.user_id}><div><strong>{memberName(member)}</strong><small>{member.role} · {member.access_level} · {DEPARTMENTS[member.dept_id] ?? member.dept_id}</small></div><button className="product-button secondary compact" type="button" onClick={() => void removeMember(member)}>Remove</button></article>)}</div></Modal><Modal id="project-reject-dialog" open={Boolean(rejectingAction)} onClose={() => setRejectingAction(null)} title="Reject generated output" context={rejectingAction?.title ?? 'Reviewer feedback'}><form className="stack-form" onSubmit={rejectAction}><label className="admin-label">Reason<textarea name="reason" minLength={3} required placeholder="Explain what must change before this can be approved." /></label><button className="product-button primary" type="submit">Reject output</button></form></Modal><Modal id="portfolio-dialog" open={portfolioOpen} onClose={() => setPortfolioOpen(false)} title="Portfolio analysis" context="Cross-project intelligence"><form className="stack-form" onSubmit={analyzePortfolio}><label className="admin-label">Question<textarea name="query" minLength={2} required placeholder="Which projects need executive attention?" /></label><fieldset className="project-picker"><legend>Projects in scope</legend>{projects.map((project) => <label key={project.project_id}><input name="project_ids" type="checkbox" value={project.project_id} defaultChecked />{project.name}</label>)}</fieldset><button className="product-button primary" type="submit">Analyze portfolio</button></form>{portfolioAnswer ? <section className="project-answer"><div><strong>Portfolio answer</strong><span>{Math.round(portfolioAnswer.confidence * 100)}% confidence</span></div><p>{portfolioAnswer.answer}</p>{portfolioAnswer.data_gaps.length ? <small>Data gaps: {portfolioAnswer.data_gaps.join(' · ')}</small> : null}</section> : null}</Modal></>;
}

export function ProjectsView({ data }: WorkspaceViewProps) {
  const [query, setQuery] = useState('');
  const [registeredProjects, setRegisteredProjects] = useState<RegisteredProject[]>([]);
  const [registryError, setRegistryError] = useState('');
  const [registryLoading, setRegistryLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const projects = data.records.filter((record) => record.entity_type === 'project').filter((record) => `${record.name} ${JSON.stringify(record.data)}`.toLowerCase().includes(query.toLowerCase()));
  async function loadRegistry() {
    setRegistryLoading(true); setRegistryError('');
    try { setRegisteredProjects((await apiRequest<{ projects: RegisteredProject[] }>('/projects')).projects); }
    catch (issue) { setRegistryError(issue instanceof Error ? issue.message : 'Project registry could not load.'); }
    finally { setRegistryLoading(false); }
  }
  useEffect(() => { void loadRegistry(); }, []);
  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    try {
      await apiRequest('/projects', { method: 'POST', body: JSON.stringify({ name: form.get('name'), description: form.get('description') || null, dept_id: form.get('dept_id'), project_type: form.get('project_type'), priority: form.get('priority'), target_end_date: form.get('target_end_date') || null }) });
      setCreateOpen(false); await loadRegistry();
    } catch (issue) { setRegistryError(issue instanceof Error ? issue.message : 'Project could not be created.'); }
  }
  return <><section className="portal-view active" data-portal-view="projects"><div className="toolbar"><label className="filter-input"><span>Filter demo projects</span><input id="project-filter" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Project, owner, or status" /></label><span id="project-total" className="result-count">{countLabel(projects.length, 'demo project')}</span><button id="create-project" className="product-button primary" type="button" onClick={() => setCreateOpen(true)}><Plus size={14} /> New project</button></div><div id="projects-list" className="entity-grid">{projects.length ? projects.map((record) => <EntityCard key={record.id} record={record} fields={['status', 'owner', 'target']} />) : <EmptyState>No projects match this filter.</EmptyState>}</div><div id="project-registry-status" aria-live="polite">{registryLoading ? <LoadingState compact /> : registryError ? <div className="portal-error"><strong>Project registry unavailable.</strong><p>{registryError}</p></div> : <ProjectIntelligence projects={registeredProjects} onRefresh={loadRegistry} />}</div></section><Modal id="create-project-dialog" open={createOpen} onClose={() => setCreateOpen(false)} title="New project" context="Provision a governed workspace"><form className="stack-form" onSubmit={createProject}><label className="admin-label">Name<input name="name" required maxLength={160} /></label><label className="admin-label">Description<textarea name="description" maxLength={2000} /></label><label className="admin-label">Department<select name="dept_id" defaultValue="ops">{Object.entries(DEPARTMENTS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><label className="admin-label">Project type<select name="project_type" defaultValue="single_dept"><option value="single_dept">Single department</option><option value="cross_dept">Cross-functional</option></select></label><label className="admin-label">Priority<select name="priority" defaultValue="medium"><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label><label className="admin-label">Target date<input name="target_end_date" type="date" /></label><button className="product-button primary" type="submit">Create project</button></form></Modal></>;
}

export function LibraryView() {
  const [documents, setDocuments] = useState<LibraryDocument[]>([]);
  const [skills, setSkills] = useState<AgentSkill[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [syncing, setSyncing] = useState(false);
  const { notify } = useToast();

  async function load(search = '') {
    setLoading(true); setError('');
    const libraryPath = search.trim() ? `/library/search?q=${encodeURIComponent(search.trim())}` : '/library';
    const [libraryResult, skillResult] = await Promise.allSettled([
      apiRequest<{ documents: LibraryDocument[] }>(libraryPath),
      apiRequest<{ skills: AgentSkill[] }>('/skills/catalog'),
    ]);
    if (libraryResult.status === 'fulfilled') setDocuments(libraryResult.value.documents);
    else setError(libraryResult.reason instanceof Error ? libraryResult.reason.message : 'Document library could not load.');
    if (skillResult.status === 'fulfilled') setSkills(skillResult.value.skills);
    else if (libraryResult.status !== 'rejected') setError(skillResult.reason instanceof Error ? skillResult.reason.message : 'Skill catalog could not load.');
    setLoading(false);
  }

  useEffect(() => { void load(); }, []);
  async function search(event: FormEvent) { event.preventDefault(); await load(query); }
  async function syncLibrary() {
    setSyncing(true);
    try { const result = await apiRequest<{ message: string }>('/library/sync', { method: 'POST' }); notify(result.message); await load(query); }
    catch (issue) { notify(issue instanceof Error ? issue.message : 'Library sync could not start.'); }
    finally { setSyncing(false); }
  }

  return <section className="portal-view active" data-portal-view="library"><div className="library-toolbar"><form id="library-search-form" className="filter-input" onSubmit={search}><label><span>Search documents</span><input id="library-search-input" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Title, report type, department" /></label><button className="icon-button icon-only" type="submit" aria-label="Search library" title="Search library"><SearchIcon size={15} /></button></form><div><button className="icon-button icon-only" type="button" aria-label="Reload library" title="Reload library" onClick={() => void load(query)}><RefreshCw size={14} /></button><button id="sync-library" className="product-button secondary" type="button" disabled={syncing} onClick={() => void syncLibrary()}>{syncing ? 'Syncing…' : 'Sync library'}</button></div></div>
    {error ? <div className="portal-error library-error"><strong>Library service unavailable.</strong><p>{error}</p></div> : null}
    <div className="library-layout"><section className="workspace-section library-documents"><div className="section-title"><div><p className="section-context">Approved organization knowledge</p><h2>Documents</h2><p>Files remain tenant-scoped and preserve the project or department that produced them.</p></div><FileText size={17} className="section-icon" /></div>{loading ? <LoadingState compact /> : documents.length ? <div className="table-scroll" role="region" aria-label="Document library" tabIndex={0}><table className="portal-table"><thead><tr><th>Document</th><th>Source</th><th>Format</th><th>Access</th><th>Created</th></tr></thead><tbody id="library-documents">{documents.map((document) => <tr key={document.doc_id}><td><strong>{document.title}</strong><small>{document.report_type || 'Agent-generated document'}</small></td><td>{document.dept_id ? DEPARTMENTS[document.dept_id] ?? document.dept_id : document.project_id ?? 'Organization'}</td><td><span className="format-tag">{document.file_format}</span></td><td><StatusTag value={document.access_level} /></td><td>{formatDate(document.created_at, false)}</td></tr>)}</tbody></table></div> : <EmptyState>{query ? 'No approved documents match this search.' : 'No approved documents have been added yet.'}</EmptyState>}</section>
      <section className="workspace-section skill-catalog"><div className="section-title"><div><p className="section-context">Agent capabilities</p><h2>Skill catalog</h2><p>Output stays under human review before distribution.</p></div><BookOpen size={17} className="section-icon" /></div>{loading ? <LoadingState compact /> : skills.length ? <div id="skill-catalog" className="skill-list">{skills.map((skill) => <article key={skill.skill_id}><div><strong>{skill.skill_id.replaceAll('_', ' ')}</strong><p>{skill.description || 'A governed project agent skill.'}</p><small>{skill.dept_id === 'all' ? 'Available to every department' : DEPARTMENTS[skill.dept_id] ?? skill.dept_id}</small></div><span>{skill.output_format}</span></article>)}</div> : <EmptyState>No skills are available in this tenant.</EmptyState>}</section></div>
  </section>;
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
  const workers = data.jobs?.workers;
  const account = [['Name', profile.name ?? 'Demo CEO'], ['Role', profile.role ?? 'ceo'], ['Organization', data.overview.organization.name], ['Workspace', data.overview.organization.industry]];
  return <section className="portal-view active" data-portal-view="settings"><div className="settings-grid"><section className="workspace-section"><div className="section-title"><div><h2>Account</h2><p>Your current workspace identity.</p></div></div><dl id="account-details" className="detail-list">{account.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value).replaceAll('_', ' ')}</dd></div>)}</dl></section><section className="workspace-section"><div className="section-title"><div><h2>AI runtime</h2><p>Configured organization model providers.</p></div></div><div id="settings-models" className="connection-list">{data.configuration ? data.configuration.models.map((model) => <article className="connection-row" key={model.provider}><div><strong>{model.provider}</strong><small>{model.model_name || 'No model selected'} · {model.endpoint || 'No endpoint'}</small></div><StatusTag value={model.enabled ? 'enabled' : 'disabled'} /></article>) : <EmptyState>Administrator access is required to view model configuration.</EmptyState>}</div></section><section className="workspace-section settings-wide"><div className="section-title"><div><h2>Platform readiness</h2><p>API dependencies and durable background processing.</p></div></div><div id="settings-runtime" className="runtime-grid"><article><span>API</span><strong>{data.readiness?.status ?? 'unavailable'}</strong></article>{Object.entries(checks).map(([name, check]) => <article key={name}><span>{name.replaceAll('_', ' ')}</span><strong>{check.status}</strong></article>)}<article><span>Active workers</span><strong className={workers?.active_count ? '' : 'text-error'}>{workers?.active_count ?? 0}</strong></article><article><span>Queued jobs</span><strong>{jobStats.queued ?? 0}</strong></article><article><span>Retries</span><strong>{jobStats.retry ?? 0}</strong></article><article><span>Dead letters</span><strong className={jobStats.dead_letter ? 'text-error' : ''}>{jobStats.dead_letter ?? 0}</strong></article></div></section><section className="workspace-section settings-wide"><div className="section-title"><div><h2>Organization connections</h2><p>SSO, databases, collaboration, and knowledge storage.</p></div><Link className="text-button" to="/admin/configuration">Manage configuration <ArrowUpRight size={12} /></Link></div><div id="settings-connections" className="connection-list">{data.configuration ? data.configuration.connections.map((connection) => <article className="connection-row" key={connection.connection_key}><div><strong>{connection.label}</strong><small>{connection.kind} · {connection.configuration.provider ?? connection.configuration.engine ?? 'not configured'}</small></div><StatusTag value={connection.status} /></article>) : <EmptyState>Administrator access is required to view connections.</EmptyState>}</div></section><section className="workspace-section settings-wide"><div className="section-title"><div><h2>Administration</h2><p>Manage access, teams, and service configuration.</p></div></div><div className="settings-actions"><Link className="product-button secondary" to="/admin/users">Users and invitations</Link><Link className="product-button secondary" to="/admin/configuration">Tenant configuration</Link><Link className="product-button secondary" to="/operations">Operations console</Link></div></section></div></section>;
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
  library: LibraryView,
  search: SearchView,
  notifications: NotificationsView,
  settings: SettingsView,
} as const;
