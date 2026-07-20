import { ArrowRight, Check, LockKeyhole } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { apiRequest, getToken, saveSession } from '../lib/api';
import type { AuthResponse, Profile } from '../types';

function enterSession(data: AuthResponse, navigate: ReturnType<typeof useNavigate>) {
  const profile: Profile = data.profile ?? {
    name: data.name,
    role: data.role,
    tenant_id: data.tenant_id ?? 'default',
    username: data.user_id,
    permitted_departments: data.permitted_departments,
  };
  saveSession(data.access_token, profile);
  navigate('/workspace/overview', { replace: true });
}

export function LoginPage() {
  const navigate = useNavigate();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  if (getToken()) return <Navigate to="/workspace/overview" replace />;

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setBusy(true);
    const form = new FormData(event.currentTarget);
    try {
      const data = await apiRequest<AuthResponse>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ user_id: form.get('user_id'), password: form.get('password') }),
      }, false);
      enterSession(data, navigate);
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : 'Unable to sign in.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page auth-layout">
      <section className="auth-intro">
        <div className="product-brand auth-brand"><span>R</span><strong>RAPID</strong></div>
        <div className="auth-message">
          <p className="auth-kicker">Startup operating workspace</p>
          <h1>Know what matters. Move work forward.</h1>
          <p>One workspace for the product, customers, decisions, delivery, and work your startup needs to keep moving.</p>
        </div>
        <ul>
          <li><Check size={14} aria-hidden="true" /> Isolated workspace and data boundary</li>
          <li><Check size={14} aria-hidden="true" /> Human approval for consequential work</li>
          <li><Check size={14} aria-hidden="true" /> Startup sample workspace included</li>
        </ul>
      </section>
      <section className="auth-panel">
        <div className="auth-panel-inner">
          <div className="auth-panel-icon"><LockKeyhole size={18} aria-hidden="true" /></div>
          <p className="auth-kicker">Workspace access</p>
          <h2>Sign in to RAPID</h2>
          <p className="auth-copy">Use the founder account or invitation issued for your approved beta workspace.</p>
          <form id="login-form" onSubmit={submitLogin}>
            <label>User ID<input id="user-id" name="user_id" autoComplete="username" required placeholder="Your user ID" /></label>
            <label>Password<input id="password" name="password" type="password" autoComplete="current-password" required placeholder="Your password" /></label>
            {error ? <p id="form-error" className="form-error" role="alert">{error}</p> : null}
            <button className="product-button primary" type="submit" disabled={busy}>
              {busy ? 'Signing in…' : <>Sign in <ArrowRight size={14} aria-hidden="true" /></>}
            </button>
          </form>
          <button className="auth-start-link" type="button" onClick={() => navigate('/start')}>Request private beta access <ArrowRight size={13} aria-hidden="true" /></button>
          <p className="auth-foot">Private beta workspaces begin with synthetic data and sandbox connectors only.</p>
        </div>
      </section>
    </main>
  );
}
