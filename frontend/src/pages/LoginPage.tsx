import { ArrowRight, Building2, Check, LockKeyhole } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { apiRequest, getToken, saveSession } from '../lib/api';
import type { AuthResponse, Profile } from '../types';

function enterSession(data: AuthResponse, navigate: ReturnType<typeof useNavigate>) {
  const profile: Profile = data.profile ?? {
    name: data.name,
    role: data.role,
    tenant_id: 'default',
    username: data.user_id,
  };
  saveSession(data.access_token, profile);
  navigate('/workspace/overview', { replace: true });
}

export function LoginPage() {
  const navigate = useNavigate();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState<'login' | 'demo' | ''>('');
  if (getToken()) return <Navigate to="/workspace/overview" replace />;

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setBusy('login');
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
      setBusy('');
    }
  }

  async function startDemo() {
    setError('');
    setBusy('demo');
    try {
      const data = await apiRequest<AuthResponse>('/people-ops/demo-session', { method: 'POST' }, false);
      enterSession(data, navigate);
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : 'Unable to start the demo.');
    } finally {
      setBusy('');
    }
  }

  return (
    <main className="auth-page auth-layout">
      <section className="auth-intro">
        <div className="product-brand auth-brand"><span>R</span><strong>RAPID</strong></div>
        <div className="auth-message">
          <p className="auth-kicker">Organization intelligence</p>
          <h1>Operate with clarity.</h1>
          <p>One governed workspace for meetings, decisions, workflows, data, and every department.</p>
        </div>
        <ul>
          <li><Check size={14} aria-hidden="true" /> Tenant-isolated workspace</li>
          <li><Check size={14} aria-hidden="true" /> Human approval for consequential work</li>
          <li><Check size={14} aria-hidden="true" /> Complete synthetic organization included</li>
        </ul>
      </section>
      <section className="auth-panel">
        <div className="auth-panel-inner">
          <div className="auth-panel-icon"><LockKeyhole size={18} aria-hidden="true" /></div>
          <p className="auth-kicker">Workspace access</p>
          <h2>Sign in to RAPID</h2>
          <p className="auth-copy">Use your organization account, or explore the complete synthetic organization first.</p>
          <form id="login-form" onSubmit={submitLogin}>
            <label>User ID<input id="user-id" name="user_id" autoComplete="username" required placeholder="Your user ID" /></label>
            <label>Password<input id="password" name="password" type="password" autoComplete="current-password" required placeholder="Your password" /></label>
            {error ? <p id="form-error" className="form-error" role="alert">{error}</p> : null}
            <button className="product-button primary" type="submit" disabled={Boolean(busy)}>
              {busy === 'login' ? 'Signing in…' : <>Sign in <ArrowRight size={14} aria-hidden="true" /></>}
            </button>
          </form>
          <div className="auth-divider"><span>or</span></div>
          <button id="demo-button" className="product-button secondary" type="button" onClick={startDemo} disabled={Boolean(busy)}>
            <Building2 size={15} aria-hidden="true" /> {busy === 'demo' ? 'Preparing workspace…' : 'Explore the synthetic organization'}
          </button>
          <p className="auth-foot">Demo mode uses synthetic Northstar Labs data and sandbox connectors only.</p>
        </div>
      </section>
    </main>
  );
}
