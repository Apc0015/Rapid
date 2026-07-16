import { CheckCircle2, CircleAlert, Link2, Plus, ShieldCheck } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { AdminShell } from '../components/AdminShell';
import { Modal } from '../components/Modal';
import { EmptyState, LoadingState, StatusTag } from '../components/StatusTag';
import { useToast } from '../components/ToastProvider';
import { DEPARTMENTS } from '../constants';
import { apiRequest } from '../lib/api';

interface Provider {
  key: string;
  name: string;
  category: string;
  auth_modes: string[];
}

interface IntegrationConnection {
  id: string;
  department: string;
  provider: string;
  provider_name: string;
  label: string;
  auth_mode: string;
  status: string;
  credential_configured: boolean;
}

interface OAuthStart {
  authorization_url: string;
  expires_in: number;
  connection_id: string;
}

const authLabels: Record<string, string> = {
  sandbox: 'Sandbox evaluation',
  oauth: 'OAuth',
  service_account: 'Service account reference',
  api_key_ref: 'API key reference',
  app_secret_ref: 'App secret reference',
  secret_ref: 'Secret reference',
};

export function AdminIntegrationsPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [connections, setConnections] = useState<IntegrationConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [oauth, setOAuth] = useState<OAuthStart | null>(null);
  const { notify } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [catalog, registered] = await Promise.all([
        apiRequest<{ providers: Provider[] }>('/organization/integrations/catalog'),
        apiRequest<{ connections: IntegrationConnection[] }>('/organization/integrations/connections'),
      ]);
      setProviders(catalog.providers);
      setConnections(registered.connections);
    } catch (issue) {
      notify(issue instanceof Error ? issue.message : 'Integrations could not be loaded.');
    } finally { setLoading(false); }
  }, [notify]);

  useEffect(() => { void load(); }, [load]);

  async function createConnection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const authMode = String(form.get('auth_mode') ?? 'sandbox');
    const scopes = String(form.get('scopes') ?? '').split(/[,\s]+/).map((item) => item.trim()).filter(Boolean);
    const config = authMode === 'oauth' ? {
      client_id: String(form.get('client_id') ?? '').trim(),
      client_secret_ref: String(form.get('credential_ref') ?? '').trim(),
      authorize_url: String(form.get('authorize_url') ?? '').trim(),
      token_url: String(form.get('token_url') ?? '').trim(),
      redirect_uri: String(form.get('redirect_uri') ?? '').trim(),
      scopes,
    } : {};
    try {
      await apiRequest('/organization/integrations/connections', {
        method: 'POST',
        body: JSON.stringify({
          department: form.get('department'), provider: form.get('provider'), label: form.get('label'),
          auth_mode: authMode, credential_ref: form.get('credential_ref'), config,
        }),
      });
      setDialogOpen(false);
      notify(authMode === 'sandbox' ? 'Sandbox integration added.' : 'Connection recorded. Complete verification before using live data.');
      await load();
    } catch (issue) { notify(issue instanceof Error ? issue.message : 'Integration could not be created.'); }
  }

  async function testConnection(connection: IntegrationConnection) {
    try {
      const response = await apiRequest<{ result: string }>(`/organization/integrations/connections/${connection.id}/test`, { method: 'POST' });
      notify(response.result);
      await load();
    } catch (issue) { notify(issue instanceof Error ? issue.message : 'Connection check could not be completed.'); }
  }

  async function beginOAuth(connection: IntegrationConnection) {
    try {
      const response = await apiRequest<OAuthStart>(`/organization/integrations/connections/${connection.id}/oauth/start`, { method: 'POST' });
      setOAuth(response);
    } catch (issue) { notify(issue instanceof Error ? issue.message : 'OAuth setup could not be started.'); }
  }

  return <AdminShell title="Integration setup" description="Prepare approved startup tools through tenant-scoped credentials, explicit data boundaries, and governed workflows.">
    <section className="workspace-section startup-integration-intro">
      <div><span className="integration-intro-icon"><ShieldCheck size={17} /></span><div><h2>Connect deliberately</h2><p>Sandbox connections use sample events. Live setup records a tenant-scoped credential reference and provider authorization; it does not claim a production data sync until that provider adapter is enabled.</p></div></div>
      <button id="add-integration" className="product-button primary" type="button" onClick={() => { setOAuth(null); setDialogOpen(true); }}><Plus size={14} /> Add connection</button>
    </section>
    <section className="workspace-section">
      <div className="section-title"><div><h2>Configured connections</h2><p>Each connection belongs to one work area and can only trigger its permitted governed playbooks.</p></div><Link2 size={17} className="section-icon" /></div>
      {loading ? <LoadingState /> : <div id="integration-list" className="startup-integration-grid">{connections.length ? connections.map((connection) => <article className="startup-integration-card" key={connection.id}><div className="startup-integration-card-head"><div><span>{connection.provider_name}</span><strong>{connection.label}</strong></div><StatusTag value={connection.status} /></div><p>{DEPARTMENTS[connection.department] ?? connection.department} · {authLabels[connection.auth_mode] ?? connection.auth_mode.replaceAll('_', ' ')}</p><small>{connection.auth_mode === 'sandbox' ? 'Uses sample events only. No customer system is connected.' : connection.credential_configured ? 'Provider setup is recorded. RAPID will not report a live data sync until the adapter validates it.' : 'A secret reference is required before live setup can continue.'}</small><div className="startup-integration-actions"><button className="product-button secondary compact" type="button" onClick={() => void testConnection(connection)}>Check setup</button>{connection.auth_mode === 'oauth' ? <button className="product-button primary compact" type="button" onClick={() => void beginOAuth(connection)}>Connect with OAuth</button> : null}</div></article>) : <EmptyState>No tools configured yet. Add a sandbox tool to explore governed workflows before adding production data.</EmptyState>}</div>}
    </section>
    <section className="workspace-section integration-catalog-section"><div className="section-title"><div><h2>Connection templates</h2><p>These templates support sandbox workflows and provider setup. Enable a production sync only after its adapter has been validated for your tenant.</p></div></div><div className="startup-provider-list">{providers.map((provider) => <article key={provider.key}><strong>{provider.name}</strong><span>{provider.category}</span><small>{provider.auth_modes.map((mode) => authLabels[mode] ?? mode).join(' · ')}</small></article>)}</div></section>

    <Modal open={dialogOpen} title="Add startup integration" context="Tenant-scoped connection" size="large" onClose={() => setDialogOpen(false)}>
      <IntegrationForm providers={providers} onSubmit={createConnection} />
    </Modal>
    <Modal open={Boolean(oauth)} title="Complete OAuth connection" context="Provider authorization" size="small" onClose={() => setOAuth(null)}>
      {oauth ? <div className="stack-form"><p className="auth-foot">RAPID created a short-lived, tenant-scoped OAuth state. Continue only in the provider account you intend to connect.</p><a className="product-button primary" href={oauth.authorization_url}>Continue to provider <CheckCircle2 size={14} /></a><p className="auth-foot">This authorization link expires in {Math.ceil(oauth.expires_in / 60)} minutes.</p></div> : null}
    </Modal>
  </AdminShell>;
}

function IntegrationForm({ providers, onSubmit }: { providers: Provider[]; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) {
  const [providerKey, setProviderKey] = useState('');
  const [authMode, setAuthMode] = useState('sandbox');
  const provider = useMemo(() => providers.find((item) => item.key === providerKey) ?? providers[0], [providerKey, providers]);
  useEffect(() => { if (provider && !provider.auth_modes.includes(authMode)) setAuthMode(provider.auth_modes[0] ?? 'sandbox'); }, [authMode, provider]);
  const live = authMode !== 'sandbox';
  return <form className="stack-form integration-form" onSubmit={onSubmit}>
    <label className="admin-label">Tool<select name="provider" value={provider?.key ?? ''} onChange={(event) => setProviderKey(event.target.value)}>{providers.map((item) => <option key={item.key} value={item.key}>{item.name} · {item.category}</option>)}</select></label>
    <label className="admin-label">Work area<select name="department" defaultValue="it">{Object.entries(DEPARTMENTS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    <label className="admin-label">Connection name<input name="label" required maxLength={160} placeholder="Engineering GitHub" /></label>
    <label className="admin-label">Connection mode<select name="auth_mode" value={authMode} onChange={(event) => setAuthMode(event.target.value)}>{(provider?.auth_modes ?? ['sandbox']).map((mode) => <option key={mode} value={mode}>{authLabels[mode] ?? mode}</option>)}</select></label>
    {live ? <><label className="admin-label">Secret-manager reference<input name="credential_ref" required maxLength={255} placeholder="vault://rapid/startup/provider" /></label>{authMode === 'oauth' ? <><label className="admin-label">OAuth client ID<input name="client_id" required maxLength={255} placeholder="Provider OAuth client ID" /></label><label className="admin-label">Authorization URL<input name="authorize_url" type="url" required placeholder="https://provider.example.com/oauth/authorize" /></label><label className="admin-label">Token URL<input name="token_url" type="url" required placeholder="https://provider.example.com/oauth/token" /></label><label className="admin-label">Callback URL<input name="redirect_uri" type="url" required placeholder="https://api.yourcompany.com/organization/integrations/oauth/callback" /></label><label className="admin-label">Scopes<input name="scopes" maxLength={500} placeholder="read:records, read:events" /></label></> : null}</> : <p className="integration-form-note"><CircleAlert size={14} /> Sandbox mode uses no credential and cannot access customer systems.</p>}
    <button className="product-button primary" type="submit" disabled={!provider}>{live ? 'Record live connection' : 'Add sandbox integration'}</button>
  </form>;
}
