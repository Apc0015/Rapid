import {
  BarChart3,
  Bell,
  BookOpen,
  BriefcaseBusiness,
  Building2,
  CalendarDays,
  CheckSquare2,
  ChevronRight,
  CircleUserRound,
  FolderKanban,
  LayoutDashboard,
  MessageSquareText,
  Menu,
  Search,
  Settings,
  ShieldCheck,
  TicketCheck,
  UsersRound,
  X,
  type LucideIcon,
} from 'lucide-react';
import { type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { VIEW_FEATURES, VIEW_META, type WorkspaceView } from '../../constants';
import { IntelligenceDock } from '../intelligence/IntelligenceDock';
import { initials } from '../../lib/format';
import { capabilitiesFor } from '../../lib/access';
import { getProfile } from '../../lib/api';
import type { TenantFeature, WorkspaceOverview } from '../../types';

interface NavItem {
  view: WorkspaceView;
  label: string;
  icon: LucideIcon;
}

const groups: Array<{ label: string; items: NavItem[] }> = [
  { label: 'Workspace', items: [
    { view: 'overview', label: 'Overview', icon: LayoutDashboard },
    { view: 'meetings', label: 'Meetings', icon: CalendarDays },
    { view: 'actions', label: 'Actions', icon: CheckSquare2 },
  ] },
  { label: 'Organization', items: [
    { view: 'people', label: 'People', icon: UsersRound },
    { view: 'crm', label: 'CRM', icon: BriefcaseBusiness },
    { view: 'projects', label: 'Projects', icon: FolderKanban },
    { view: 'tickets', label: 'Tickets', icon: TicketCheck },
    { view: 'departments', label: 'Departments', icon: Building2 },
  ] },
  { label: 'Intelligence', items: [
    { view: 'chat', label: 'Chat', icon: MessageSquareText },
    { view: 'reports', label: 'Reports', icon: BarChart3 },
    { view: 'library', label: 'Library', icon: BookOpen },
    { view: 'search', label: 'Search', icon: Search },
    { view: 'notifications', label: 'Notifications', icon: Bell },
  ] },
];

const intelligenceViews = new Set<WorkspaceView>([
  'overview', 'meetings', 'actions', 'people', 'crm', 'projects', 'tickets', 'departments', 'notifications',
]);

interface WorkspaceShellProps {
  overview: WorkspaceOverview;
  view: WorkspaceView;
  notificationCount: number;
  features: TenantFeature[];
  navigationOpen: boolean;
  onNavigate: (view: WorkspaceView) => void;
  onNavigationOpen: (open: boolean) => void;
  onReset: () => void;
  onPrimaryAction: () => void;
  onOpenChat: (prompt: string, context: WorkspaceView) => void;
  onSignOut: () => void;
  children: ReactNode;
}

export function WorkspaceShell({
  overview,
  view,
  notificationCount,
  features,
  navigationOpen,
  onNavigate,
  onNavigationOpen,
  onReset,
  onPrimaryAction,
  onOpenChat,
  onSignOut,
  children,
}: WorkspaceShellProps) {
  const meta = VIEW_META[view];
  const capabilities = capabilitiesFor(getProfile());
  const primaryLabel = view === 'meetings' && capabilities.operateDepartment ? 'Schedule meeting' : view === 'reports' ? 'Generate report' : view === 'settings' && capabilities.configureTenant ? 'Open admin portal' : '';

  return (
    <div className="product-page product-shell portal-shell">
      <aside id="portal-sidebar" className={`product-sidebar portal-sidebar${navigationOpen ? ' open' : ''}`}>
        <div className="portal-brand-row">
          <button className="product-brand brand-button" type="button" onClick={() => onNavigate('overview')}><span>R</span><strong>RAPID</strong></button>
          <button className="icon-button icon-only mobile-only" type="button" aria-label="Close navigation" title="Close navigation" onClick={() => onNavigationOpen(false)}><X size={15} /></button>
        </div>
        <div className="workspace-switcher">
          <span id="organization-initials">{initials(overview.organization.name)}</span>
          <div><strong id="organization-name">{overview.organization.name}</strong><small>Organization portal</small></div>
          <ChevronRight size={13} aria-hidden="true" />
        </div>
        <nav className="product-nav portal-nav" aria-label="Product navigation">
          {groups.map((group) => {
            const items = group.items.filter((item) => isViewEnabled(item.view, features));
            if (!items.length) return null;
            return <div className="nav-group" key={group.label}>
              <p className="nav-group-label">{group.label}</p>
              {items.map(({ view: itemView, label, icon: Icon }) => (
                <button
                  key={itemView}
                  type="button"
                  className={view === itemView ? 'active' : ''}
                  data-view={itemView}
                  onClick={() => onNavigate(itemView)}
                >
                  <span><Icon size={13} strokeWidth={1.8} aria-hidden="true" /></span>
                  {label}
                  {itemView === 'notifications' && notificationCount > 0 ? <b id="notification-count">{notificationCount}</b> : null}
                </button>
              ))}
            </div>;
          })}
        </nav>
        <div className="product-sidebar-footer">
          {capabilities.operateDepartment ? <Link to="/operations"><ShieldCheck size={14} aria-hidden="true" /> Department operations</Link> : null}
          <button className={view === 'settings' ? 'active' : ''} data-view="settings" type="button" onClick={() => onNavigate('settings')}><Settings size={14} aria-hidden="true" /> Settings</button>
          <button type="button" onClick={onSignOut}><CircleUserRound size={14} aria-hidden="true" /> Sign out</button>
        </div>
      </aside>

      <main className="product-main portal-main">
        <div className="mobile-topbar">
          <button id="open-navigation" className="icon-button icon-only" type="button" aria-label="Open navigation" title="Open navigation" onClick={() => onNavigationOpen(true)}><Menu size={16} /></button>
          <button className="mobile-brand brand-button" type="button" onClick={() => onNavigate('overview')}><span>R</span>RAPID</button>
          <button className="icon-button icon-only" type="button" aria-label="Search" title="Search" onClick={() => onNavigate('search')}><Search size={16} /></button>
        </div>
        <header className="workspace-header portal-header">
          <div><p id="view-kicker" className="auth-kicker">{meta.context}</p><h1 id="view-title">{meta.title}</h1><p id="view-subtitle">{meta.description}</p></div>
          <div className="header-actions">
            <span className="sandbox-badge"><ShieldCheck size={12} /> Synthetic demo</span>
            {capabilities.resetDemo ? <button id="reset-demo" className="product-button secondary" type="button" onClick={onReset}>Reset demo</button> : null}
            {primaryLabel ? <button id="primary-action" className="product-button primary" type="button" onClick={onPrimaryAction}>{primaryLabel}</button> : null}
          </div>
        </header>
        {intelligenceViews.has(view) ? <IntelligenceDock key={view} view={view} onOpenChat={onOpenChat} /> : null}
        {children}
      </main>
      {navigationOpen ? <button className="navigation-scrim" type="button" aria-label="Close navigation" onClick={() => onNavigationOpen(false)} /> : null}
    </div>
  );
}

function isViewEnabled(view: WorkspaceView, features: TenantFeature[]): boolean {
  const requiredFeature = VIEW_FEATURES[view];
  return !requiredFeature || features.some((feature) => feature.key === requiredFeature && feature.enabled);
}
