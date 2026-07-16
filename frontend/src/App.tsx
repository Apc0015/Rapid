import { useEffect, type ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import { ToastProvider } from './components/ToastProvider';
import { getProfile, getToken } from './lib/api';
import { capabilitiesFor } from './lib/access';
import { AdminConfigurationPage } from './pages/AdminConfigurationPage';
import { AdminIntegrationsPage } from './pages/AdminIntegrationsPage';
import { AdminUsersPage } from './pages/AdminUsersPage';
import { BetaLandingPage } from './pages/BetaLandingPage';
import { BetaActivationPage } from './pages/BetaActivationPage';
import { LoginPage } from './pages/LoginPage';
import { OperationsPage } from './pages/OperationsPage';
import { OrganizationStartPage } from './pages/OrganizationStartPage';
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

function CapabilityRoute({ capability, children }: { capability: keyof ReturnType<typeof capabilitiesFor>; children: ReactNode }) {
  if (!getToken()) return <Navigate to="/login" replace />;
  if (!capabilitiesFor(getProfile())[capability]) return <Navigate to="/workspace/overview" replace />;
  return children;
}

function RootRoute() {
  return <Navigate to={getToken() ? '/workspace/overview' : '/beta'} replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <Routes>
          <Route path="/" element={<RootRoute />} />
          <Route path="/beta" element={<BetaLandingPage />} />
          <Route path="/activate" element={<BetaActivationPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/start" element={<OrganizationStartPage />} />
          <Route path="/workspace/:view?" element={<ProtectedRoute><WorkspacePage /></ProtectedRoute>} />
          <Route path="/admin/configuration" element={<CapabilityRoute capability="configureTenant"><AdminConfigurationPage /></CapabilityRoute>} />
          <Route path="/admin/integrations" element={<CapabilityRoute capability="configureTenant"><AdminIntegrationsPage /></CapabilityRoute>} />
          <Route path="/admin/users" element={<CapabilityRoute capability="manageUsers"><AdminUsersPage /></CapabilityRoute>} />
          <Route path="/operations" element={<CapabilityRoute capability="operateDepartment"><OperationsPage /></CapabilityRoute>} />
          <Route path="*" element={<RootRoute />} />
        </Routes>
      </ToastProvider>
    </BrowserRouter>
  );
}
