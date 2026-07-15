import { MailPlus, UserRoundPlus } from 'lucide-react';
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

export function AdminUsersPage() {
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [loading, setLoading] = useState(true);
  const { notify } = useToast();
  const load = useCallback(async () => {
    setLoading(true);
    try { const response = await apiRequest<{ invitations: Invitation[] }>('/tenant-admin/invitations'); setInvitations(response.invitations); }
    catch (issue) { notify(issue instanceof Error ? issue.message : 'Invitations could not be loaded.'); }
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

  return <AdminShell title="Users and access" description="Invite organization members with explicit roles and department scope."><section className="workspace-section"><div className="section-title"><div><h2>Invite user</h2><p>Invitations remain pending until the recipient completes account setup.</p></div><UserRoundPlus size={17} className="section-icon" /></div><form id="invite-form" className="invite-form" onSubmit={invite}><label className="admin-label">Name<input id="invite-name" name="name" required maxLength={160} /></label><label className="admin-label">Email<input id="invite-email" name="email" type="email" required maxLength={254} /></label><label className="admin-label">Role<select id="invite-role" name="role" defaultValue="employee"><option value="employee">Employee</option><option value="manager">Manager</option><option value="dept_head">Department head</option><option value="admin">Administrator</option></select></label><label className="admin-label">Department<select id="invite-department" name="department" defaultValue=""><option value="">No department scope</option>{Object.entries(DEPARTMENTS).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select></label><button className="product-button primary" type="submit"><MailPlus size={14} /> Create invitation</button></form></section><section className="workspace-section"><div className="section-title"><div><h2>Pending invitations</h2><p>Tenant-scoped access requests awaiting account setup.</p></div></div><div id="invitation-list" className="connection-list">{loading ? <LoadingState compact /> : invitations.length ? invitations.map((item) => <article className="connection-row" key={item.id ?? item.email}><div><strong>{item.name}</strong><small>{item.email} · {item.role.replaceAll('_', ' ')}{item.departments.length ? ` · ${item.departments.map((key) => DEPARTMENTS[key] ?? key).join(', ')}` : ''}</small></div><StatusTag value={item.status} /></article>) : <EmptyState>No invitations are pending.</EmptyState>}</div></section></AdminShell>;
}
