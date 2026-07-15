import { useEffect, type ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import { ToastProvider } from './components/ToastProvider';
import { getToken } from './lib/api';
import { AdminConfigurationPage } from './pages/AdminConfigurationPage';
import { AdminUsersPage } from './pages/AdminUsersPage';
import { LoginPage } from './pages/LoginPage';
import { OperationsPage } from './pages/OperationsPage';
import { WorkspacePage } from './pages/WorkspacePage';

function ProtectedRoute({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  useEffect(() => {
    const handleUnauthorized = () => navigate('/login', { replace: true });
    window.addEventListener('rapid:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('rapid:unauthorized', handleUnauthorized);
  }, [navigate]);
  return getToken() ? children : <Navigate to="/login" replace />;
}

function LegacyRoute({ to }: { to: string }) {
  return <Navigate to={to} replace />;
}

function RootRoute() {
  return <Navigate to={getToken() ? '/workspace/overview' : '/login'} replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <Routes>
          <Route path="/" element={<RootRoute />} />
          <Route path="/index.html" element={<RootRoute />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/login.html" element={<LegacyRoute to="/login" />} />
          <Route path="/workspace.html" element={<LegacyRoute to="/workspace/overview" />} />
          <Route path="/admin-portal.html" element={<LegacyRoute to="/admin/configuration" />} />
          <Route path="/admin-users.html" element={<LegacyRoute to="/admin/users" />} />
          <Route path="/organization.html" element={<LegacyRoute to="/operations" />} />
          <Route path="/people-ops.html" element={<LegacyRoute to="/workspace/people" />} />
          <Route path="/app.html" element={<LegacyRoute to="/workspace/overview" />} />
          <Route path="/admin.html" element={<LegacyRoute to="/admin/configuration" />} />
          <Route path="/dept.html" element={<LegacyRoute to="/workspace/departments" />} />
          <Route path="/org.html" element={<LegacyRoute to="/workspace/people" />} />
          <Route path="/onboarding.html" element={<LegacyRoute to="/login" />} />
          <Route path="/workspace/:view?" element={<ProtectedRoute><WorkspacePage /></ProtectedRoute>} />
          <Route path="/admin/configuration" element={<ProtectedRoute><AdminConfigurationPage /></ProtectedRoute>} />
          <Route path="/admin/users" element={<ProtectedRoute><AdminUsersPage /></ProtectedRoute>} />
          <Route path="/operations" element={<ProtectedRoute><OperationsPage /></ProtectedRoute>} />
          <Route path="*" element={<RootRoute />} />
        </Routes>
      </ToastProvider>
    </BrowserRouter>
  );
}
