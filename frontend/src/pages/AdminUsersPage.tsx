import { Check, Copy, MailPlus, UserRoundPlus, X } from 'lucide-react';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { AdminShell } from '../components/AdminShell';
import { EmptyState, LoadingState, StatusTag } from '../components/StatusTag';
import { useToast } from '../components/ToastProvider';
import { DEPARTMENTS } from '../constants';
import { apiRequest } from '../lib/api';

interface Invitation {
  id: string;
  name: string;
  email: string;
  role: string;
  departments: string[];
  status: string;
}

interface BetaApplication {
  id: string;
  company_name: string;
  owner_name: string;
  owner_email: string;
  industry: string;
  website: string;
  use_case: string;
  status: string;
  created_at: string;
}

export function AdminUsersPage() {
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [betaApplications, setBetaApplications] = useState<BetaApplication[]>([]);
  const [betaReviewer, setBetaReviewer] = useState(false);
  const [activationLinks, setActivationLinks] = useState<Record<string, string>>({});
  const [reviewingId, setReviewingId] = useState('');
  const { notify } = useToast();
  const load = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      const response = await apiRequest<{ invitations: Invitation[] }>('/tenant-admin/invitations');
      setInvitations(response.invitations);
      const reviewer = await apiRequest<{ reviewer: boolean }>('/beta/reviewer-status').catch(() => ({ reviewer: false }));
      setBetaReviewer(reviewer.reviewer);
      if (reviewer.reviewer) {
        const applications = await apiRequest<{ applications: BetaApplication[] }>('/beta/applications');
        setBetaApplications(applications.applications);
      } else setBetaApplications([]);
    }
    catch (issue) {
      const message = issue instanceof Error ? issue.message : 'Invitations could not be loaded.';
      setLoadError(message); notify(message);
    }
    finally { setLoading(false); }
  }, [notify]);
  useEffect(() => { void load(); }, [load]);

  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const department = String(form.get('department') ?? '');
    try {
      await apiRequest('/tenant-admin/invitations', { method: 'POST', body: JSON.stringify({ name: form.get('name'), email: form.get('email'), role: form.get('role'), departments: department ? [department] : [] }) });
      event.currentTarget.reset(); notify('Invitation created.'); await load();
    } catch (issue) { notify(issue instanceof Error ? issue.message : 'Invitation could not be created.'); }
  }

  async function review(application: BetaApplication, decision: 'approve' | 'decline') {
    setReviewingId(application.id);
    try {
      const response = await apiRequest<{ activation_url?: string }>(`/beta/applications/${application.id}/${decision}`, { method: 'POST', body: JSON.stringify({ notes: '' }) });
      if (response.activation_url) {
        setActivationLinks((current) => ({ ...current, [application.id]: response.activation_url! }));
        notify(`Approved ${application.company_name}. Copy the activation link and send it to ${application.owner_email}.`);
      } else notify(`Declined ${application.company_name}.`);
      await load();
    } catch (issue) { notify(issue instanceof Error ? issue.message : 'The beta application could not be updated.'); }
    finally { setReviewingId(''); }
  }

  async function copyActivationLink(applicationId: string) {
    const link = activationLinks[applicationId];
    if (!link) return;
    try { await navigator.clipboard.writeText(link); notify('Activation link copied.'); }
    catch { notify('Copy the activation link from the field.'); }
  }

  return <AdminShell title="Users and access" description="Invite organization members with explicit roles and department scope.">{betaReviewer ? <section className="workspace-section beta-review-section"><div className="section-title"><div><h2>Private beta applications</h2><p>Approve a founder to provision their isolated sample workspace, then send the one-time activation link.</p></div></div><div className="beta-application-list">{loading ? <LoadingState compact /> : betaApplications.length ? betaApplications.map((item) => <article key={item.id}><div><div className="beta-application-head"><strong>{item.company_name}</strong><StatusTag value={item.status.replaceAll('_', ' ')} /></div><small>{item.owner_name} · {item.owner_email}{item.industry ? ` · ${item.industry}` : ''}</small>{item.website ? <a href={item.website} target="_blank" rel="noreferrer">{item.website}</a> : null}<p>{item.use_case || 'No operating goal supplied.'}</p>{activationLinks[item.id] ? <div className="beta-activation-delivery"><p>Copy and send this activation link now. It cannot be shown again.</p><div className="beta-activation-link"><input aria-label={`Activation link for ${item.company_name}`} readOnly value={activationLinks[item.id]} /><button className="icon-button icon-only" type="button" aria-label={`Copy activation link for ${item.company_name}`} title="Copy activation link" onClick={() => void copyActivationLink(item.id)}><Copy size={14} /></button></div></div> : null}</div>{item.status === 'pending_review' ? <div className="beta-review-actions"><button className="product-button secondary compact" type="button" disabled={reviewingId === item.id} onClick={() => void review(item, 'decline')}><X size={13} /> Decline</button><button className="product-button primary compact" type="button" disabled={reviewingId === item.id} onClick={() => void review(item, 'approve')}><Check size={13} /> {reviewingId === item.id ? 'Reviewing...' : 'Approve'}</button></div> : null}</article>) : <EmptyState>No beta applications are waiting for review.</EmptyState>}</div></section> : null}<section className="workspace-section"><div className="section-title"><div><h2>Invite user</h2><p>Invitations remain pending until the recipient completes account setup.</p></div><UserRoundPlus size={17} className="section-icon" /></div><form id="invite-form" className="invite-form" onSubmit={invite}><label className="admin-label">Name<input id="invite-name" name="name" required maxLength={160} /></label><label className="admin-label">Email<input id="invite-email" name="email" type="email" required maxLength={254} /></label><label className="admin-label">Role<select id="invite-role" name="role" defaultValue="employee"><option value="employee">Employee</option><option value="manager">Manager</option><option value="dept_head">Department head</option><option value="admin">Administrator</option></select></label><label className="admin-label">Department<select id="invite-department" name="department" defaultValue=""><option value="">No department scope</option>{Object.entries(DEPARTMENTS).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select></label><button className="product-button primary" type="submit"><MailPlus size={14} /> Create invitation</button></form></section><section className="workspace-section"><div className="section-title"><div><h2>Pending invitations</h2><p>Tenant-scoped access requests awaiting account setup.</p></div></div><div id="invitation-list" className="connection-list">{loading ? <LoadingState compact /> : loadError ? <div id="invitation-error" className="portal-error" role="alert"><strong>Invitations could not be loaded.</strong><p>{loadError}</p><button className="product-button secondary" type="button" onClick={() => void load()}>Retry</button></div> : invitations.length ? invitations.map((item) => <article className="connection-row" key={item.id ?? item.email}><div><strong>{item.name}</strong><small>{item.email} · {item.role.replaceAll('_', ' ')}{item.departments.length ? ` · ${item.departments.map((key) => DEPARTMENTS[key] ?? key).join(', ')}` : ''}</small></div><StatusTag value={item.status} /></article>) : <EmptyState>No invitations are pending.</EmptyState>}</div></section></AdminShell>;
}
