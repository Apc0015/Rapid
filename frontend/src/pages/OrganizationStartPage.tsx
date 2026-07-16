import { ArrowLeft, ArrowRight, Check, Clock3, LockKeyhole } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { apiRequest, getToken } from '../lib/api';

interface ApplicationResponse { application_id: string; status: string }

export function OrganizationStartPage() {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [submitted, setSubmitted] = useState(false);
  if (getToken()) return <Navigate to="/workspace/overview" replace />;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(''); setBusy(true);
    const form = new FormData(event.currentTarget);
    try {
      await apiRequest<ApplicationResponse>('/beta/applications', {
        method: 'POST',
        body: JSON.stringify({
          company_name: form.get('company_name'), owner_name: form.get('owner_name'), owner_email: form.get('owner_email'),
          industry: form.get('industry'), website: form.get('website'), use_case: form.get('use_case'),
        }),
      }, false);
      setSubmitted(true);
    } catch (issue) { setError(issue instanceof Error ? issue.message : 'Your beta request could not be submitted.'); }
    finally { setBusy(false); }
  }

  return <main className="start-page">
    <header className="start-topbar"><button className="product-brand brand-button" type="button" onClick={() => navigate('/beta')}><span>R</span><strong>RAPID</strong></button><button className="text-button" type="button" onClick={() => navigate('/login')}><ArrowLeft size={14} /> Sign in</button></header>
    <div className="start-layout beta-application-layout">
      <section className="start-intro"><p className="auth-kicker">RAPID private beta</p><h1>Request a workspace for your startup.</h1><p>Tell us what your team is building and where operating work is getting stuck. We review every request before creating an isolated evaluation workspace.</p><div className="start-promises"><span><Check size={14} /> No production database or connector required</span><span><Check size={14} /> Synthetic startup workspace ready after approval</span><span><Check size={14} /> Founder controls access and data connections</span></div></section>
      {submitted ? <section className="beta-pending-state" role="status"><span className="beta-pending-icon"><Clock3 size={20} /></span><p className="section-context">Request received</p><h2>Your beta request is waiting for review.</h2><p>When approved, the RAPID beta reviewer will send a one-time activation link so you can set your password and enter the sample workspace.</p><div><button className="product-button primary" type="button" onClick={() => navigate('/beta')}>Back to RAPID</button><button className="text-button" type="button" onClick={() => navigate('/login')}>Already have an invite?</button></div></section> : <form className="start-form beta-application-form" onSubmit={submit}>
        <div className="start-section"><div><p className="section-context">Your startup</p><h2>Who will use RAPID?</h2></div><div className="start-field-grid"><label>Company name<input name="company_name" required maxLength={160} placeholder="Acme Studio" /></label><label>Industry<input name="industry" maxLength={100} placeholder="Software, services, commerce..." /></label><label>Your name<input name="owner_name" required maxLength={160} placeholder="Name" autoComplete="name" /></label><label>Work email<input name="owner_email" type="email" required maxLength={254} placeholder="you@company.com" autoComplete="email" /></label><label className="full-field">Website <input name="website" type="url" maxLength={255} placeholder="https://yourcompany.com (optional)" /></label></div></div>
        <div className="start-section"><div><p className="section-context">What to test</p><h2>Where do you need operating clarity?</h2></div><label className="beta-use-case">What should RAPID help your team coordinate?<textarea name="use_case" rows={5} maxLength={1000} required placeholder="For example: weekly product and customer reviews, follow-through on decisions, and a clearer view of delivery risk." /></label></div>
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        <div className="start-submit"><p><LockKeyhole size={14} /> Your application creates no account and stores no password. An approved founder receives a separate one-time activation link.</p><button className="product-button primary" type="submit" disabled={busy}>{busy ? 'Submitting request...' : <>Request beta access <ArrowRight size={14} /></>}</button></div>
      </form>}
    </div>
  </main>;
}
