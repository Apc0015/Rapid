import { ArrowRightLeft, Database, FileUp, Play, Plus, RefreshCw, Search, ShieldCheck, TimerReset, Workflow } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { AdminShell } from '../components/AdminShell';
import { Modal } from '../components/Modal';
import { EmptyState, LoadingState, StatusTag } from '../components/StatusTag';
import { useToast } from '../components/ToastProvider';
import { apiRequest, apiUpload } from '../lib/api';
import { getProfile } from '../lib/api';
import { capabilitiesFor } from '../lib/access';
import { formatDate } from '../lib/format';
import type { OperatingReport, OrganizationUnit } from '../types';

interface Department {
  key: string;
  name: string;
  lead: string;
  agents: string[];
  data_domains: string[];
}

interface Playbook {
  key: string;
  department: string;
  department_name: string;
  name: string;
  description: string;
}

interface RunStep {
  id: string;
  label: string;
  owner: string;
  risk_tier: string;
  status: string;
  evidence: unknown[];
}

interface RunEvent {
  id: string;
  event_type: string;
  actor: string;
  created_at: string;
}

interface TaskRun {
  id: string;
  subject_name: string;
  subject_email?: string;
  status: string;
  progress: { complete: number; total: number };
  steps: RunStep[];
  events: RunEvent[];
  escalation?: { reason: string } | null;
  playbook: { key: string; department: string; department_name?: string; name: string; description: string };
}

interface Dashboard {
  stats: { planned?: number; executing?: number; verifying?: number; escalated?: number; done?: number; autonomous_completion_rate?: number };
  departments?: Array<{ key: string; active_runs: number; escalations: number }>;
  runs: TaskRun[];
  escalations: TaskRun[];
}

interface DataSource {
  id: string;
  department: string;
  name: string;
  source_type: string;
  connector_type: string;
  classification: string;
  status: string;
  record_count: number;
  document_count: number;
}

interface Integration {
  id: string;
  department: string;
  provider_name: string;
  label: string;
  auth_mode: string;
  status: string;
}

interface Provider { key: string; name: string; category: string }
interface Citation { document_name: string; source_name: string; excerpt: string; classification: string; score: number }

export function OperationsPage() {
  const capabilities = capabilitiesFor(getProfile());
  const [departments, setDepartments] = useState<Department[]>([]);
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [units, setUnits] = useState<OrganizationUnit[]>([]);
  const [activeDepartment, setActiveDepartment] = useState('');
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [organizationSummary, setOrganizationSummary] = useState<Dashboard | null>(null);
  const [report, setReport] = useState<OperatingReport | null>(null);
  const [sources, setSources] = useState<DataSource[]>([]);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [selectedRun, setSelectedRun] = useState<TaskRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [runDialog, setRunDialog] = useState(false);
  const [sourceDialog, setSourceDialog] = useState(false);
  const [ingestSource, setIngestSource] = useState<DataSource | null>(null);
  const [integrationDialog, setIntegrationDialog] = useState(false);
  const [triggerConnection, setTriggerConnection] = useState<Integration | null>(null);
  const [scheduleConnection, setScheduleConnection] = useState<Integration | null>(null);
  const [handoffRun, setHandoffRun] = useState<TaskRun | null>(null);
  const [citations, setCitations] = useState<Citation[]>([]);
  const departmentRequest = useRef(0);
  const { notify } = useToast();

  const loadDepartment = useCallback(async (department: string, preserveRun = true, requestId = ++departmentRequest.current) => {
    if (!department) return;
    const [nextDashboard, nextReport, sourceData, integrationData] = await Promise.all([
      apiRequest<Dashboard>(`/organization/dashboard?department=${encodeURIComponent(department)}`),
      apiRequest<OperatingReport>(`/organization/reports/${department}`),
      apiRequest<{ sources: DataSource[] }>(`/organization/data/sources?department=${encodeURIComponent(department)}`),
      apiRequest<{ connections: Integration[] }>(`/organization/integrations/connections?department=${encodeURIComponent(department)}`),
    ]);
    if (requestId !== departmentRequest.current) return;
    setDashboard(nextDashboard); setReport(nextReport); setSources(sourceData.sources); setIntegrations(integrationData.connections);
    if (preserveRun && selectedRun?.playbook.department === department) {
      const detail = await apiRequest<{ run: TaskRun }>(`/organization/runs/${selectedRun.id}`);
      if (requestId !== departmentRequest.current) return;
      setSelectedRun(detail.run);
    }
  }, [selectedRun]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [departmentData, playbookData, summary, catalog, structure] = await Promise.all([
        apiRequest<{ departments: Department[] }>('/organization/departments'),
        apiRequest<{ playbooks: Playbook[] }>('/organization/playbooks'),
        apiRequest<Dashboard>('/organization/dashboard'),
        apiRequest<{ providers: Provider[] }>('/organization/integrations/catalog'),
        apiRequest<{ units: OrganizationUnit[] }>('/organization/structure'),
      ]);
      setDepartments(departmentData.departments); setPlaybooks(playbookData.playbooks); setOrganizationSummary(summary); setProviders(catalog.providers); setUnits(structure.units);
      const department = departmentData.departments.some((item) => item.key === activeDepartment) ? activeDepartment : departmentData.departments[0]?.key ?? '';
      setActiveDepartment(department);
      await loadDepartment(department);
    } catch (issue) { notify(issue instanceof Error ? issue.message : 'Operations console could not be loaded.'); }
    finally { setLoading(false); }
  }, [activeDepartment, loadDepartment, notify]);

  useEffect(() => { void load(); }, []);

  async function selectDepartment(department: string) {
    const requestId = ++departmentRequest.current;
    setActiveDepartment(department); setSelectedRun(null); setCitations([]); setLoading(true);
    try { await loadDepartment(department, false, requestId); }
    catch (issue) { notify(issue instanceof Error ? issue.message : 'Department workspace could not be loaded.'); }
    finally { if (requestId === departmentRequest.current) setLoading(false); }
  }

  async function selectRun(id: string) {
    try { const response = await apiRequest<{ run: TaskRun }>(`/organization/runs/${id}`); setSelectedRun(response.run); }
    catch (issue) { notify(issue instanceof Error ? issue.message : 'Run record could not be loaded.'); }
  }

  async function refreshAll(message?: string) {
    await load();
    if (message) notify(message);
  }

  async function advanceRun(run: TaskRun) {
    try {
      const response = await apiRequest<{ run: TaskRun }>(`/organization/runs/${run.id}/advance`, { method: 'POST' });
      setSelectedRun(response.run); await refreshAll(response.run.status === 'escalated' ? 'Executive approval is required before work continues.' : 'Safe steps executed and recorded.');
    } catch (issue) { notify(issue instanceof Error ? issue.message : 'Run could not be advanced.'); }
  }

  async function verifyRun(run: TaskRun) {
    try { const response = await apiRequest<{ run: TaskRun }>(`/organization/runs/${run.id}/verify`, { method: 'POST' }); setSelectedRun(response.run); await refreshAll('Independent verification passed.'); }
    catch (issue) { notify(issue instanceof Error ? issue.message : 'Run verification failed.'); }
  }

  async function decide(run: TaskRun, decision: 'approve' | 'reject') {
    try { const response = await apiRequest<{ run: TaskRun }>(`/organization/runs/${run.id}/escalation`, { method: 'POST', body: JSON.stringify({ decision, note: '' }) }); setSelectedRun(response.run); await refreshAll(`Executive decision recorded: ${decision}.`); }
    catch (issue) { notify(issue instanceof Error ? issue.message : 'Decision could not be recorded.'); }
  }

  async function createRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget); const details = String(form.get('details') ?? '').trim();
    try { const response = await apiRequest<{ run: TaskRun }>('/organization/runs', { method: 'POST', body: JSON.stringify({ playbook_key: form.get('playbook_key'), subject_name: form.get('subject_name'), subject_email: form.get('subject_email'), due_date: form.get('due_date') || null, details: details ? { context: details } : {} }) }); setRunDialog(false); setActiveDepartment(response.run.playbook.department); setSelectedRun(response.run); await loadDepartment(response.run.playbook.department); notify('Task run created and ready to advance.'); }
    catch (issue) { notify(issue instanceof Error ? issue.message : 'Task run could not be created.'); }
  }

  async function createSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    try { await apiRequest('/organization/data/sources', { method: 'POST', body: JSON.stringify({ department: activeDepartment, name: form.get('name'), source_type: form.get('source_type'), connector_type: form.get('connector_type'), classification: form.get('classification') }) }); setSourceDialog(false); await loadDepartment(activeDepartment); notify('Governed data source added.'); }
    catch (issue) { notify(issue instanceof Error ? issue.message : 'Data source could not be added.'); }
  }

  async function ingest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!ingestSource) return; const form = new FormData(event.currentTarget); const content = String(form.get('content') ?? '');
    try {
      if (ingestSource.source_type === 'structured') {
        const records = JSON.parse(content) as unknown;
        if (!Array.isArray(records)) throw new Error('Structured ingestion requires a JSON array of records.');
        await apiRequest(`/organization/data/sources/${ingestSource.id}/records`, { method: 'POST', body: JSON.stringify({ records }) });
      } else {
        const file = form.get('file');
        if (file instanceof File && file.size > 0) {
          const upload = new FormData(); upload.append('file', file);
          const response = await apiUpload<{ document: { pii_detected: boolean }; extraction: { method: string }; job: { id: string } }>(`/organization/data/sources/${ingestSource.id}/files`, upload);
          notify(`${response.extraction.method} extraction queued for indexing${response.document.pii_detected ? '; PII redaction applied' : ''}.`);
        } else {
          const response = await apiRequest<{ document: { pii_detected: boolean }; job: { id: string } }>(`/organization/data/sources/${ingestSource.id}/documents`, { method: 'POST', body: JSON.stringify({ name: form.get('name'), content }) });
          notify(`Document queued for indexing${response.document.pii_detected ? '; PII redaction applied' : ''}.`);
        }
      }
      setIngestSource(null); await loadDepartment(activeDepartment); if (ingestSource.source_type === 'structured') notify('Structured records ingested and scoped.');
    } catch (issue) { notify(issue instanceof Error ? issue.message : 'Source data could not be ingested.'); }
  }

  async function syncSource(source: DataSource) {
    try {
      const response = await apiRequest<{ job: { id: string; duplicate: boolean } }>(`/organization/data/sources/${source.id}/sync`, { method: 'POST', body: JSON.stringify({ idempotency_key: crypto.randomUUID() }) });
      notify(response.job.duplicate ? 'Existing source sync is already queued.' : 'Source sync queued with retry protection.');
    } catch (issue) { notify(issue instanceof Error ? issue.message : 'Source sync could not be queued.'); }
  }

  async function searchData(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    try { const response = await apiRequest<{ citations: Citation[] }>('/organization/data/search', { method: 'POST', body: JSON.stringify({ department: activeDepartment, query: form.get('query') }) }); setCitations(response.citations); }
    catch (issue) { notify(issue instanceof Error ? issue.message : 'Knowledge search failed.'); }
  }

  async function createIntegration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    try { await apiRequest('/organization/integrations/connections', { method: 'POST', body: JSON.stringify({ department: activeDepartment, provider: form.get('provider'), label: form.get('label'), auth_mode: 'sandbox' }) }); setIntegrationDialog(false); await loadDepartment(activeDepartment); notify('Sandbox integration added.'); }
    catch (issue) { notify(issue instanceof Error ? issue.message : 'Integration could not be added.'); }
  }

  async function testIntegration(id: string) {
    try { const response = await apiRequest<{ result: string }>(`/organization/integrations/connections/${id}/test`, { method: 'POST' }); await loadDepartment(activeDepartment); notify(response.result); }
    catch (issue) { notify(issue instanceof Error ? issue.message : 'Integration test failed.'); }
  }

  async function triggerIntegration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!triggerConnection) return; const form = new FormData(event.currentTarget);
    try { const response = await apiRequest<{ run: TaskRun; duplicate: boolean }>(`/organization/integrations/connections/${triggerConnection.id}/events`, { method: 'POST', body: JSON.stringify({ idempotency_key: crypto.randomUUID(), event_type: 'sandbox_event', playbook_key: form.get('playbook_key'), subject_name: form.get('subject_name'), payload: { source: 'react_operations_console' } }) }); setTriggerConnection(null); setSelectedRun(response.run); await refreshAll(response.duplicate ? 'Existing triggered run loaded.' : 'Integration event started a governed run.'); }
    catch (issue) { notify(issue instanceof Error ? issue.message : 'Integration event failed.'); }
  }

  async function createSchedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!scheduleConnection) return; const form = new FormData(event.currentTarget);
    try { const response = await apiRequest<{ schedule: { next_run_at: string } }>('/organization/integrations/schedules', { method: 'POST', body: JSON.stringify({ connection_id: scheduleConnection.id, playbook_key: form.get('playbook_key'), subject_name: form.get('subject_name'), interval_minutes: Number(form.get('interval_minutes')), payload: { source: 'react_operations_console' } }) }); setScheduleConnection(null); notify(`Schedule created. First dispatch: ${formatDate(response.schedule.next_run_at)}.`); }
    catch (issue) { notify(issue instanceof Error ? issue.message : 'Schedule could not be created.'); }
  }

  async function createHandoff(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!handoffRun) return; const form = new FormData(event.currentTarget); const context = String(form.get('context') ?? '').trim();
    try { const response = await apiRequest<{ run: TaskRun }>(`/organization/runs/${handoffRun.id}/handoff`, { method: 'POST', body: JSON.stringify({ playbook_key: form.get('playbook_key'), subject_name: form.get('subject_name'), details: context ? { context } : {} }) }); setHandoffRun(null); setSelectedRun(response.run); setActiveDepartment(response.run.playbook.department); await loadDepartment(response.run.playbook.department); notify('Verified work handed to the destination department.'); }
    catch (issue) { notify(issue instanceof Error ? issue.message : 'Handoff could not be created.'); }
  }

  const department = departments.find((item) => item.key === activeDepartment);
  const departmentPlaybooks = playbooks.filter((item) => item.department === activeDepartment);
  const stats = dashboard?.stats ?? {};
  const activeRuns = (stats.planned ?? 0) + (stats.executing ?? 0) + (stats.verifying ?? 0);
  const triggerPlaybooks = playbooks.filter((item) => item.department === triggerConnection?.department);
  const schedulePlaybooks = playbooks.filter((item) => item.department === scheduleConnection?.department);
  const handoffPlaybooks = playbooks.filter((item) => item.department !== handoffRun?.playbook.department);
  const departmentStats = useMemo(() => Object.fromEntries((organizationSummary?.departments ?? []).map((item) => [item.key, item])), [organizationSummary]);

  return (
    <AdminShell title={capabilities.configureTenant ? 'Organization operations' : 'Department operations'} description="Run governed department playbooks, inspect evidence, and control integrations from one console.">
      {loading && !dashboard ? <LoadingState /> : <>
        <div className="operations-toolbar"><div className="department-tabs" role="tablist" aria-label="Department scope">{departments.map((item) => { const summary = departmentStats[item.key]; return <button type="button" role="tab" aria-selected={activeDepartment === item.key} className={activeDepartment === item.key ? 'active' : ''} key={item.key} onClick={() => void selectDepartment(item.key)}>{item.name}{summary?.escalations ? <b>{summary.escalations}</b> : null}</button>; })}</div><div className="operations-commands"><button className="product-button secondary icon-only" title="Refresh operations" aria-label="Refresh operations" type="button" onClick={() => void refreshAll()}><RefreshCw size={14} /></button><button className="product-button primary" type="button" onClick={() => setRunDialog(true)}><Plus size={14} /> New task run</button></div></div>
        <section className="metric-strip operations-metrics"><article><span>Active runs</span><strong>{activeRuns}</strong><small>Executing or awaiting verification</small></article><article><span>Executive decisions</span><strong>{stats.escalated ?? 0}</strong><small>Consequential work awaiting review</small></article><article><span>Verified work</span><strong>{stats.done ?? 0}</strong><small>Completed task runs</small></article><article><span>Verified completion</span><strong>{stats.autonomous_completion_rate ?? 0}%</strong><small>Settled work completed successfully</small></article></section>
        <div className="operations-grid">
          <section className="workspace-section operations-runs"><div className="section-title"><div><h2>{department?.name ?? 'Department'} task runs</h2><p>Evidence-bearing work moving through approval gates.</p></div><Workflow size={17} className="section-icon" /></div><div className="run-list">{dashboard?.runs.length ? dashboard.runs.map((run) => <button className={`run-row${selectedRun?.id === run.id ? ' selected' : ''}`} data-run-id={run.id} type="button" key={run.id} onClick={() => void selectRun(run.id)}><span><strong>{run.playbook.name}: {run.subject_name}</strong><small>{run.progress.complete}/{run.progress.total} steps</small></span><StatusTag value={run.status} /></button>) : <EmptyState>No task runs in this department. Start a governed playbook when work arrives.</EmptyState>}</div></section>
          <aside className="workspace-section department-control"><div className="section-title"><div><h2>{department?.name ?? 'Department control'}</h2><p>{department?.lead}</p></div><ShieldCheck size={17} className="section-icon" /></div><h3>Agent team</h3><div className="domain-list">{department?.agents.map((agent) => <span key={agent}>{agent}</span>)}</div><h3>Approved data domains</h3><div className="domain-list">{department?.data_domains.map((domain) => <span key={domain}>{domain}</span>)}</div><h3>Governed playbooks</h3><div className="playbook-list">{departmentPlaybooks.map((item) => <button type="button" key={item.key} onClick={() => setRunDialog(true)}><span><strong>{item.name}</strong><small>{item.description}</small></span><Play size={13} /></button>)}</div></aside>
        </div>
        <section className="workspace-section escalation-section"><div className="section-title"><div><h2>{capabilities.approveExecutiveWork ? 'Executive approval queue' : 'Escalations'}</h2><p>{capabilities.approveExecutiveWork ? 'Consequential work remains blocked until an accountable user decides.' : 'Consequential work awaiting an executive decision.'}</p></div></div><div className="escalation-list">{dashboard?.escalations.length ? dashboard.escalations.map((run) => <article className="escalation-card" key={run.id}><div><strong>{run.playbook.name}: {run.subject_name}</strong><p>{run.escalation?.reason}</p></div>{capabilities.approveExecutiveWork ? <div className="escalation-actions"><button className="product-button secondary" type="button" onClick={() => void decide(run, 'reject')}>Decline</button><button className="product-button primary" type="button" onClick={() => void decide(run, 'approve')}>Approve</button></div> : <StatusTag value="awaiting executive" />}</article>) : <EmptyState>No open decisions for this department.</EmptyState>}</div></section>
        <section className="workspace-section operations-data"><div className="section-title"><div><h2>{department?.name} data sources</h2><p>OCR, PII redaction, tenant embeddings, and retry-safe indexing run before retrieval.</p></div><button className="product-button secondary" type="button" onClick={() => setSourceDialog(true)}><Plus size={14} /> Add source</button></div><div className="source-grid">{sources.length ? sources.map((source) => <article className="source-card" key={source.id}><div><Database size={16} /><StatusTag value={source.status} /></div><h3>{source.name}</h3><p>{source.source_type} · {source.connector_type} · {source.classification}</p><small>{source.record_count} records · {source.document_count} documents</small><div className="integration-actions"><button className="product-button secondary compact" type="button" onClick={() => setIngestSource(source)}><FileUp size={12} /> Ingest</button><button className="product-button secondary compact" type="button" onClick={() => void syncSource(source)}><RefreshCw size={12} /> Sync</button></div></article>) : <EmptyState>No sources yet. Add an approved source for this department.</EmptyState>}</div><form className="data-search" onSubmit={searchData}><label className="search-input-wrap"><Search size={15} /><input name="query" minLength={2} required placeholder="Search permitted department documents" /></label><button className="product-button secondary" type="submit">Search knowledge</button></form><div className="knowledge-results">{citations.map((citation, index) => <article className="search-result" key={`${citation.document_name}-${index}`}><span>{citation.classification}</span><div><strong>{citation.document_name} · {citation.source_name}</strong><p>{citation.excerpt}</p></div><small>Relevance {citation.score}</small></article>)}</div></section>
        <section className="workspace-section operations-integrations"><div className="section-title"><div><h2>{department?.name} integrations</h2><p>Sandbox connectors can trigger governed playbooks without external side effects.</p></div><button className="product-button secondary" type="button" onClick={() => setIntegrationDialog(true)}><Plus size={14} /> Add integration</button></div><div className="source-grid">{integrations.length ? integrations.map((item) => <article className="integration-card" key={item.id}><div><strong>{item.provider_name}</strong><StatusTag value={item.status} /></div><p>{item.label} · {item.auth_mode}</p><div className="integration-actions"><button className="product-button secondary compact" type="button" onClick={() => void testIntegration(item.id)}>Test</button><button className="product-button secondary compact" type="button" onClick={() => setScheduleConnection(item)}><TimerReset size={12} /> Schedule</button><button className="product-button primary compact" type="button" onClick={() => setTriggerConnection(item)}><Play size={12} /> Trigger</button></div></article>) : <EmptyState>No integrations yet. Add a sandbox connection to test event-triggered work.</EmptyState>}</div></section>
        {report ? <section className="workspace-section report-output operations-report"><div className="report-head"><div><p className="auth-kicker">Live operational report</p><h2>{report.department.name} operating report</h2><p>Generated {formatDate(report.generated_at)}</p></div><StatusTag value={report.sources.execution_mode} /></div><div className="report-metrics">{Object.entries(report.metrics).map(([key, value]) => <article key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{value}</strong></article>)}</div></section> : null}
        <section className="workspace-section run-audit"><div className="section-title"><div><h2>Run record</h2><p>{selectedRun ? `${selectedRun.id} · ${selectedRun.progress.complete}/${selectedRun.progress.total} steps` : 'Select a task run to inspect its evidence.'}</p></div></div>{selectedRun ? <div className="audit-grid"><div className="audit-summary"><h3>{selectedRun.playbook.name}: {selectedRun.subject_name}</h3><p>{selectedRun.playbook.description}</p><StatusTag value={selectedRun.status} /><div className="audit-actions">{['planned', 'executing'].includes(selectedRun.status) ? <button className="product-button primary" type="button" onClick={() => void advanceRun(selectedRun)}>Advance to next gate</button> : null}{selectedRun.status === 'verifying' ? <button className="product-button primary" type="button" onClick={() => void verifyRun(selectedRun)}>Run verification</button> : null}{selectedRun.status === 'done' ? <button className="product-button secondary" type="button" onClick={() => setHandoffRun(selectedRun)}><ArrowRightLeft size={14} /> Handoff to department</button> : null}</div></div><div><h3>Evidence checklist</h3><div className="step-list">{selectedRun.steps.map((step) => <article key={step.id}><div><strong>{step.label}</strong><small>{step.owner} · {step.risk_tier}{step.evidence.length ? ' · evidence recorded' : ''}</small></div><StatusTag value={step.status} /></article>)}</div><h3>Audit events</h3><div className="event-list">{selectedRun.events.map((event) => <article key={event.id}><strong>{event.event_type}</strong><small>{event.actor} · {formatDate(event.created_at)}</small></article>)}</div></div></div> : <EmptyState>Every agent action is recorded before verification can complete a run.</EmptyState>}</section>
        <section className="workspace-section structure-section"><div className="section-title"><div><h2>Structure and ownership</h2><p>Tenant organization units used for scope, membership, and reporting.</p></div></div><div className="structure-grid">{units.filter((unit) => unit.unit_type !== 'organization').map((unit) => <article key={unit.id}><strong>{unit.name}</strong><span>{unit.unit_type}{unit.department_key ? ` · ${unit.department_key}` : ''}</span><small>{unit.members.length} assigned members</small></article>)}</div></section>
      </>}

      <Modal open={runDialog} title="New task run" context="Create governed work" onClose={() => setRunDialog(false)}><form className="stack-form" onSubmit={createRun}><label className="admin-label">Playbook<select name="playbook_key" defaultValue={departmentPlaybooks[0]?.key}>{departmentPlaybooks.map((item) => <option key={item.key} value={item.key}>{item.name}</option>)}</select></label><label className="admin-label">Person, account, or work item<input name="subject_name" maxLength={160} required placeholder="July close, Priya Shah, or Acme account" /></label><label className="admin-label">Contact email<input name="subject_email" type="email" maxLength={254} /></label><label className="admin-label">Due date<input name="due_date" type="date" /></label><label className="admin-label">Context<textarea name="details" maxLength={1000} rows={4} /></label><p className="auth-foot">Sandbox execution records evidence but never contacts external systems.</p><button className="product-button primary" type="submit">Create task run</button></form></Modal>
      <Modal open={sourceDialog} title="Add governed source" context="Data source" size="small" onClose={() => setSourceDialog(false)}><form className="stack-form" onSubmit={createSource}><label className="admin-label">Source name<input name="name" maxLength={160} required placeholder="People handbook" /></label><label className="admin-label">Data type<select name="source_type" defaultValue="unstructured"><option value="unstructured">Documents and knowledge</option><option value="structured">Structured records</option></select></label><label className="admin-label">Connector type<select name="connector_type" defaultValue="manual"><option value="manual">Manual / sandbox</option><option value="database">Database connector</option><option value="storage">Drive or storage connector</option><option value="api">Application API connector</option></select></label><label className="admin-label">Classification<select name="classification" defaultValue="internal"><option value="internal">Internal</option><option value="confidential">Confidential</option>{capabilities.configureTenant ? <option value="restricted">Restricted</option> : null}</select></label><button className="product-button primary" type="submit">Add source</button></form></Modal>
      <Modal open={Boolean(ingestSource)} title={ingestSource?.source_type === 'structured' ? `Add ${ingestSource?.name} records` : `Add ${ingestSource?.name} knowledge`} context="Source ingestion" onClose={() => setIngestSource(null)}><form className="stack-form" onSubmit={ingest}>{ingestSource?.source_type !== 'structured' ? <><label className="admin-label">Document name<input name="name" maxLength={255} placeholder="Leave policy" /></label><label className="admin-label">Upload file<input name="file" type="file" accept=".txt,.md,.csv,.json,.pdf,.docx,.png,.jpg,.jpeg,.tiff,.bmp" /></label></> : null}<label className="admin-label">{ingestSource?.source_type === 'structured' ? 'Records (JSON array)' : 'Document content'}<textarea name="content" maxLength={2_000_000} rows={10} required={ingestSource?.source_type === 'structured'} placeholder={ingestSource?.source_type === 'structured' ? '[{"account":"Acme","stage":"qualified"}]' : 'Paste approved knowledge when not uploading a file.'} /></label><button className="product-button primary" type="submit">Ingest data</button></form></Modal>
      <Modal open={integrationDialog} title="Add sandbox connection" context="Integration" size="small" onClose={() => setIntegrationDialog(false)}><form className="stack-form" onSubmit={createIntegration}><label className="admin-label">Provider<select name="provider" defaultValue={providers[0]?.key}>{providers.map((item) => <option key={item.key} value={item.key}>{item.name} · {item.category}</option>)}</select></label><label className="admin-label">Connection label<input name="label" maxLength={160} required placeholder="Finance QuickBooks sandbox" /></label><p className="auth-foot">Live connections require OAuth or a secret-manager reference.</p><button className="product-button primary" type="submit">Add integration</button></form></Modal>
      <Modal open={Boolean(triggerConnection)} title="Trigger governed work" context={triggerConnection?.provider_name} size="small" onClose={() => setTriggerConnection(null)}><form className="stack-form" onSubmit={triggerIntegration}><label className="admin-label">Playbook<select name="playbook_key" defaultValue={triggerPlaybooks[0]?.key}>{triggerPlaybooks.map((item) => <option key={item.key} value={item.key}>{item.name}</option>)}</select></label><label className="admin-label">Work item<input name="subject_name" required maxLength={160} placeholder="Sandbox work item" /></label><button className="product-button primary" type="submit">Trigger run</button></form></Modal>
      <Modal open={Boolean(scheduleConnection)} title="Schedule governed work" context={scheduleConnection?.provider_name} size="small" onClose={() => setScheduleConnection(null)}><form className="stack-form" onSubmit={createSchedule}><label className="admin-label">Playbook<select name="playbook_key" defaultValue={schedulePlaybooks[0]?.key}>{schedulePlaybooks.map((item) => <option key={item.key} value={item.key}>{item.name}</option>)}</select></label><label className="admin-label">Work item<input name="subject_name" maxLength={160} required placeholder="Daily lead queue" /></label><label className="admin-label">Repeat every (minutes)<input name="interval_minutes" type="number" min={5} max={43_200} defaultValue={1440} required /></label><button className="product-button primary" type="submit">Create schedule</button></form></Modal>
      <Modal open={Boolean(handoffRun)} title="Route verified work" context="Cross-department handoff" size="small" onClose={() => setHandoffRun(null)}><form className="stack-form" onSubmit={createHandoff}><label className="admin-label">Target playbook<select name="playbook_key" defaultValue={handoffPlaybooks[0]?.key}>{handoffPlaybooks.map((item) => <option key={item.key} value={item.key}>{item.department_name} · {item.name}</option>)}</select></label><label className="admin-label">Work item<input name="subject_name" maxLength={160} required defaultValue={handoffRun?.subject_name} /></label><label className="admin-label">Context<textarea name="context" maxLength={1000} rows={4} /></label><button className="product-button primary" type="submit">Create handoff</button></form></Modal>
    </AdminShell>
  );
}
