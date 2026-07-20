import { ArrowRight, CheckCircle2, LockKeyhole } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { apiRequest, getToken, saveSession } from '../lib/api';
import type { AuthResponse, Profile } from '../types';

export function BetaActivationPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const token = params.get('token') ?? '';
  if (getToken()) return <Navigate to="/workspace/overview" replace />;

  async function activate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get('password') ?? '');
    if (password !== String(form.get('confirm_password') ?? '')) { setError('Passwords do not match.'); return; }
    setBusy(true); setError('');
    try {
      const data = await apiRequest<AuthResponse>('/beta/activate', { method: 'POST', body: JSON.stringify({ token, password }) }, false);
      const profile: Profile = { name: data.name, role: data.role, tenant_id: data.tenant_id, username: data.user_id, permitted_departments: data.permitted_departments };
      saveSession(data.access_token, profile);
      navigate('/workspace/overview', { replace: true });
    } catch (issue) { setError(issue instanceof Error ? issue.message : 'This activation link could not be used.'); }
    finally { setBusy(false); }
  }

  return <main className="activation-page"><section className="activation-panel"><div className="product-brand"><span>R</span><strong>RAPID</strong></div><span className="activation-icon"><CheckCircle2 size={20} /></span><p className="auth-kicker">Beta workspace approved</p><h1>Set your founder password.</h1><p>Your workspace begins with isolated synthetic data. You will configure company connections from the administration area when your team is ready.</p>{token ? <form onSubmit={activate}><label>Choose password<input name="password" type="password" minLength={8} autoComplete="new-password" required /></label><label>Confirm password<input name="confirm_password" type="password" minLength={8} autoComplete="new-password" required /></label>{error ? <p className="form-error" role="alert">{error}</p> : null}<button className="product-button primary" type="submit" disabled={busy}>{busy ? 'Activating workspace...' : <>Activate workspace <ArrowRight size={14} /></>}</button></form> : <div className="portal-error"><strong>Activation link missing.</strong><p>Use the one-time link supplied with your beta approval.</p></div>}<small><LockKeyhole size={13} /> The activation link can be used once and expires after seven days.</small></section></main>;
}
