import { ArrowLeft, Building2, Menu, Network, Settings2, UsersRound, X } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';

export function AdminShell({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  const location = useLocation();
  const [navigationOpen, setNavigationOpen] = useState(false);
  const closeNavigation = () => setNavigationOpen(false);
  return (
    <div className="product-page product-shell portal-shell admin-shell">
      <aside className={`product-sidebar portal-sidebar${navigationOpen ? ' open' : ''}`}>
        <div className="portal-brand-row">
          <Link className="product-brand" to="/workspace/overview" onClick={closeNavigation}><span>R</span><strong>RAPID</strong></Link>
          <button className="icon-button icon-only mobile-only" type="button" aria-label="Close navigation" title="Close navigation" onClick={closeNavigation}><X size={15} /></button>
        </div>
        <div className="workspace-switcher"><span>NL</span><div><strong>Northstar Labs</strong><small>Administration</small></div></div>
        <nav className="product-nav portal-nav" aria-label="Administration navigation">
          <p className="nav-group-label">Product</p>
          <Link to="/workspace/overview" onClick={closeNavigation}><span><ArrowLeft size={13} /></span>Workspace</Link>
          <p className="nav-group-label">Administration</p>
          <Link className={location.pathname === '/admin/configuration' ? 'active' : ''} to="/admin/configuration" onClick={closeNavigation}><span><Settings2 size={13} /></span>Configuration</Link>
          <Link className={location.pathname === '/admin/users' ? 'active' : ''} to="/admin/users" onClick={closeNavigation}><span><UsersRound size={13} /></span>Users and access</Link>
          <Link className={location.pathname === '/operations' ? 'active' : ''} to="/operations" onClick={closeNavigation}><span><Network size={13} /></span>Operations console</Link>
        </nav>
        <div className="product-sidebar-footer"><Link to="/workspace/departments" onClick={closeNavigation}><Building2 size={14} /> Department directory</Link></div>
      </aside>
      <main className="product-main portal-main">
        <div className="mobile-topbar">
          <button className="icon-button icon-only" type="button" aria-label="Open navigation" title="Open navigation" onClick={() => setNavigationOpen(true)}><Menu size={16} /></button>
          <Link className="mobile-brand" to="/workspace/overview"><span>R</span>RAPID</Link>
          <Link className="icon-button icon-only" to="/workspace/overview" aria-label="Open workspace" title="Open workspace"><ArrowLeft size={16} /></Link>
        </div>
        <header className="workspace-header portal-header"><div><p className="auth-kicker">Tenant administration</p><h1>{title}</h1><p>{description}</p></div><span className="sandbox-badge">Synthetic demo</span></header>
        {children}
      </main>
      {navigationOpen ? <button className="navigation-scrim" type="button" aria-label="Close navigation" onClick={closeNavigation} /> : null}
    </div>
  );
}
