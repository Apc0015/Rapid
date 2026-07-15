import { ArrowLeft, Building2, Network, Settings2, UsersRound } from 'lucide-react';
import { type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';

export function AdminShell({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  const location = useLocation();
  return (
    <div className="product-page product-shell portal-shell admin-shell">
      <aside className="product-sidebar portal-sidebar">
        <Link className="product-brand" to="/workspace/overview"><span>R</span><strong>RAPID</strong></Link>
        <div className="workspace-switcher"><span>NL</span><div><strong>Northstar Labs</strong><small>Administration</small></div></div>
        <nav className="product-nav portal-nav" aria-label="Administration navigation">
          <p className="nav-group-label">Product</p>
          <Link to="/workspace/overview"><span><ArrowLeft size={13} /></span>Workspace</Link>
          <p className="nav-group-label">Administration</p>
          <Link className={location.pathname === '/admin/configuration' ? 'active' : ''} to="/admin/configuration"><span><Settings2 size={13} /></span>Configuration</Link>
          <Link className={location.pathname === '/admin/users' ? 'active' : ''} to="/admin/users"><span><UsersRound size={13} /></span>Users and access</Link>
          <Link className={location.pathname === '/operations' ? 'active' : ''} to="/operations"><span><Network size={13} /></span>Operations console</Link>
        </nav>
        <div className="product-sidebar-footer"><Link to="/workspace/departments"><Building2 size={14} /> Department directory</Link></div>
      </aside>
      <main className="product-main portal-main">
        <header className="workspace-header portal-header"><div><p className="auth-kicker">Tenant administration</p><h1>{title}</h1><p>{description}</p></div><span className="sandbox-badge">Synthetic demo</span></header>
        {children}
      </main>
    </div>
  );
}
