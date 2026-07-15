import { Bot, Database, Plus, Settings2 } from 'lucide-react';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { AdminShell } from '../components/AdminShell';
import { Modal } from '../components/Modal';
import { EmptyState, LoadingState, StatusTag } from '../components/StatusTag';
import { useToast } from '../components/ToastProvider';
import { apiRequest } from '../lib/api';
import type { ConnectionConfiguration, ModelConfiguration, OrganizationUnit, TenantConfiguration } from '../types';

export function AdminConfigurationPage() {
  const [configuration, setConfiguration] = useState<TenantConfiguration | null>(null);
  const [units, setUnits] = useState<OrganizationUnit[]>([]);
  const [loading, setLoading] = useState(true);
  const [model, setModel] = useState<ModelConfiguration | null>(null);
  const [connection, setConnection] = useState<ConnectionConfiguration | null>(null);
  const { notify } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nextConfiguration, structure] = await Promise.all([
        apiRequest<TenantConfiguration>('/tenant-admin/configuration'),
        apiRequest<{ units: OrganizationUnit[] }>('/organization/structure'),
      ]);
      setConfiguration(nextConfiguration);
      setUnits(structure.units);
    } catch (issue) { notify(issue instanceof Error ? issue.message : 'Configuration could not be loaded.'); }
    finally { setLoading(false); }
  }, [notify]);

  useEffect(() => { void load(); }, [load]);

  async function updateFeature(key: string, enabled: boolean) {
    try {
      await apiRequest(`/tenant-admin/features/${key}`, { method: 'PUT', body: JSON.stringify({ enabled }) });
      await load(); notify('Module setting saved.');
    } catch (issue) { notify(issue instanceof Error ? issue.message : 'Module setting could not be saved.'); await load(); }
  }

  async function saveModel(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!model) return;
    const form = new FormData(event.currentTarget);
    try {
      await apiRequest(`/tenant-admin/models/${model.provider}`, { method: 'PUT', body: JSON.stringify({
        enabled: form.get('enabled') === 'on',
        model_name: form.get('model_name'),
        endpoint: form.get('endpoint'),
        credential_ref: form.get('credential_ref'),
      }) });
      setModel(null); await load(); notify(`${model.provider} configuration saved.`);
    } catch (issue) { notify(issue instanceof Error ? issue.message : 'Model configuration could not be saved.'); }
  }

  async function saveConnection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!connection) return;
    const form = new FormData(event.currentTarget);
    const provider = String(form.get('provider') ?? '').trim();
    try {
      await apiRequest(`/tenant-admin/connections/${connection.connection_key}`, { method: 'PUT', body: JSON.stringify({
        kind: connection.kind,
        enabled: form.get('enabled') === 'on',
        label: form.get('label'),
        configuration: connection.kind === 'database' ? { engine: provider } : { provider },
        credential_ref: form.get('credential_ref'),
      }) });
      setConnection(null); await load(); notify('Connection configuration saved.');
    } catch (issue) { notify(issue instanceof Error ? issue.message : 'Connection configuration could not be saved.'); }
  }

  async function createTeam(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await apiRequest('/organization/structure/units', { method: 'POST', body: JSON.stringify({ parent_id: form.get('parent_id'), name: form.get('name'), unit_type: 'team' }) });
      event.currentTarget.reset(); await load(); notify('Team created.');
    } catch (issue) { notify(issue instanceof Error ? issue.message : 'Team could not be created.'); }
  }

  const departments = units.filter((unit) => unit.unit_type === 'department');
  const teams = units.filter((unit) => unit.unit_type === 'team');

  return (
    <AdminShell title="Configure your organization" description="Enable RAPID services now. Connect production systems only when your organization is ready.">
      {loading && !configuration ? <LoadingState /> : configuration ? <>
        <section id="configuration" className="workspace-section">
          <div className="section-title"><div><h2>Product modules</h2><p>Choose which common portal capabilities your users can access.</p></div><Settings2 size={17} className="section-icon" /></div>
          <div id="features-list" className="admin-grid">{configuration.features.map((feature) => <article className="admin-card" key={feature.key}><div><strong>{feature.name}</strong><small>{feature.enabled ? 'Available in the common portal' : 'Hidden from organization users'}</small></div><label className="switch"><input data-feature={feature.key} type="checkbox" checked={feature.enabled} aria-label={`Enable ${feature.name}`} onChange={(event) => void updateFeature(feature.key, event.target.checked)} /><span /></label></article>)}</div>
        </section>
        <section className="workspace-section">
          <div className="section-title"><div><h2>AI runtime</h2><p>Ollama supports local models. OpenRouter activates after a secret reference is configured.</p></div><Bot size={17} className="section-icon" /></div>
          <div id="models-list" className="admin-grid">{configuration.models.map((item) => <article className="admin-card" key={item.provider}><div><strong>{item.provider === 'ollama' ? 'Ollama' : 'OpenRouter'}</strong><small>{item.enabled ? `${item.model_name || 'Model required'} · enabled` : 'Not enabled'}{item.credential_configured ? ' · secret reference set' : ''}</small></div><button className="product-button secondary" data-model={item.provider} type="button" onClick={() => setModel(item)}>Configure</button></article>)}</div>
        </section>
        <section className="workspace-section">
          <div className="section-title"><div><h2>Organization connections</h2><p>Define SSO, databases, storage, and integrations without placing secrets in RAPID.</p></div><Database size={17} className="section-icon" /></div>
          <div id="connections-list" className="connection-list">{configuration.connections.map((item) => <article className="connection-row" key={item.connection_key}><div><strong>{item.label}</strong><small>{item.kind} · {item.status}{item.credential_configured ? ' · secret reference set' : ''}</small></div><div className="connection-actions"><StatusTag value={item.status} /><button className="product-button secondary" data-connection={item.connection_key} type="button" onClick={() => setConnection(item)}>Configure</button></div></article>)}</div>
        </section>
        <section className="workspace-section">
          <div className="section-title"><div><h2>Teams and departments</h2><p>Create operational teams under a department. Membership remains tenant-scoped.</p></div></div>
          <form id="team-form" className="team-form" onSubmit={createTeam}><label className="admin-label">Department<select id="team-parent" name="parent_id" required>{departments.map((unit) => <option key={unit.id} value={unit.id}>{unit.name}</option>)}</select></label><label className="admin-label">Team name<input id="team-name" name="name" required maxLength={160} placeholder="Enterprise accounts" /></label><button className="product-button primary" type="submit"><Plus size={14} /> Create team</button></form>
          <div id="teams-list" className="connection-list">{teams.length ? teams.map((unit) => <article className="connection-row" key={unit.id}><div><strong>{unit.name}</strong><small>{unit.members.length} member{unit.members.length === 1 ? '' : 's'} assigned</small></div></article>) : <EmptyState>No teams configured yet.</EmptyState>}</div>
        </section>
      </> : <div className="portal-error"><strong>Configuration unavailable.</strong><p>Confirm that this account has tenant administrator access.</p></div>}

      <Modal open={Boolean(model)} title={`Configure ${model?.provider ?? 'model'}`} context="AI runtime" size="small" onClose={() => setModel(null)}>
        {model ? <form className="stack-form" onSubmit={saveModel}><label className="admin-label">Model name<input name="model_name" required defaultValue={model.model_name} placeholder={model.provider === 'ollama' ? 'llama3.2' : 'openai/gpt-4o-mini'} /></label><label className="admin-label">Endpoint<input name="endpoint" type="url" required defaultValue={model.endpoint} /></label>{model.provider === 'openrouter' ? <label className="admin-label">Secret-manager reference<input name="credential_ref" placeholder="vault://rapid/openrouter" /></label> : null}<label className="admin-check"><input name="enabled" type="checkbox" defaultChecked={model.enabled} /> Enable this provider</label><p className="auth-foot">Only one provider is active at a time. Enabling this provider disables the other runtime.</p><button className="product-button primary" type="submit">Save model</button></form> : null}
      </Modal>

      <Modal open={Boolean(connection)} title={`Configure ${connection?.label ?? 'connection'}`} context="Connection configuration" size="small" onClose={() => setConnection(null)}>
        {connection ? <form id="connection-form" className="stack-form" onSubmit={saveConnection}><label className="admin-label">Connection label<input name="label" maxLength={160} required defaultValue={connection.label} /></label><label className="admin-label">Provider or engine<input name="provider" maxLength={120} defaultValue={connection.configuration.provider ?? connection.configuration.engine ?? ''} placeholder="postgres, okta, slack, or local_sandbox" /></label><label className="admin-label">Secret-manager reference<input name="credential_ref" maxLength={255} placeholder="vault://rapid/customer/connection" /></label><label className="admin-check"><input name="enabled" type="checkbox" defaultChecked={connection.enabled} /> Enable after configuration</label><p className="auth-foot">Passwords, tokens, and API keys are rejected. Reference a secret held by your organization.</p><button className="product-button primary" type="submit">Save connection</button></form> : null}
      </Modal>
    </AdminShell>
  );
}
