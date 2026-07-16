import { useEffect, useState, type ComponentType } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { LoadingState } from '../components/StatusTag';
import { useToast } from '../components/ToastProvider';
import { isWorkspaceView, VIEW_FEATURES, type WorkspaceView } from '../constants';
import { MeetingDialogs } from '../features/workspace/MeetingDialogs';
import { useWorkspaceData } from '../features/workspace/useWorkspaceData';
import { WORKSPACE_VIEW_COMPONENTS, type WorkspaceViewProps } from '../features/workspace/WorkspaceViews';
import { WorkspaceShell } from '../features/workspace/WorkspaceShell';
import { apiRequest, clearSession } from '../lib/api';
import type { Meeting } from '../types';

export function WorkspacePage() {
  const navigateRouter = useNavigate();
  const { view: routeView } = useParams();
  const view: WorkspaceView = isWorkspaceView(routeView) ? routeView : 'overview';
  const [includeRead, setIncludeRead] = useState(false);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [selectedMeeting, setSelectedMeeting] = useState<Meeting | null>(null);
  const [meetingOpen, setMeetingOpen] = useState(false);
  const [newMeetingOpen, setNewMeetingOpen] = useState(false);
  const [reportDepartment, setReportDepartment] = useState('hr');
  const [reportSignal, setReportSignal] = useState(0);
  const { data, loading, error, load, refreshOperations, refreshNotifications } = useWorkspaceData(includeRead);
  const { notify } = useToast();

  useEffect(() => {
    if (!isWorkspaceView(routeView)) navigateRouter('/workspace/overview', { replace: true });
  }, [navigateRouter, routeView]);

  useEffect(() => {
    const requiredFeature = VIEW_FEATURES[view];
    if (data && requiredFeature && !data.features.some((feature) => feature.key === requiredFeature && feature.enabled)) {
      navigateRouter('/workspace/overview', { replace: true });
      notify('This module is not enabled for this organization.');
    }
  }, [data, navigateRouter, notify, view]);

  function navigate(nextView: WorkspaceView) {
    navigateRouter(`/workspace/${nextView}`);
    setNavigationOpen(false);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  async function openMeeting(id: string) {
    try {
      const response = await apiRequest<{ meeting: Meeting }>(`/workspace/meetings/${id}`);
      setSelectedMeeting(response.meeting);
      setMeetingOpen(true);
    } catch (issue) { notify(issue instanceof Error ? issue.message : 'Meeting could not be opened.'); }
  }

  async function saveMeeting(id: string, payload: Record<string, unknown>) {
    try {
      await apiRequest(`/workspace/meetings/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
      setMeetingOpen(false);
      await refreshOperations();
      notify('Meeting record saved.');
    } catch (issue) { notify(issue instanceof Error ? issue.message : 'Meeting could not be saved.'); throw issue; }
  }

  async function createMeeting(payload: Record<string, unknown>) {
    try {
      await apiRequest('/workspace/meetings', { method: 'POST', body: JSON.stringify(payload) });
      setNewMeetingOpen(false);
      await refreshOperations();
      notify('Meeting scheduled.');
    } catch (issue) { notify(issue instanceof Error ? issue.message : 'Meeting could not be scheduled.'); throw issue; }
  }

  async function createAction(meetingId: string, payload: Record<string, unknown>) {
    try {
      await apiRequest(`/workspace/meetings/${meetingId}/actions`, { method: 'POST', body: JSON.stringify(payload) });
      await refreshOperations();
      await openMeeting(meetingId);
      notify('Action assigned.');
    } catch (issue) { notify(issue instanceof Error ? issue.message : 'Action could not be assigned.'); throw issue; }
  }

  async function changeAction(id: string, status: string) {
    try {
      await apiRequest(`/workspace/actions/${id}/status`, { method: 'POST', body: JSON.stringify({ status }) });
      await refreshOperations();
      if (selectedMeeting && meetingOpen) await openMeeting(selectedMeeting.id);
      notify('Action status updated.');
    } catch (issue) { notify(issue instanceof Error ? issue.message : 'Action status could not be updated.'); }
  }

  async function toggleIncludeRead() {
    const next = !includeRead;
    setIncludeRead(next);
    try { await refreshNotifications(next); }
    catch (issue) { notify(issue instanceof Error ? issue.message : 'Notifications could not be loaded.'); }
  }

  async function markNotification(id: string) {
    try {
      await apiRequest(`/workspace/notifications/${id}/read`, { method: 'POST' });
      await refreshNotifications(includeRead);
    } catch (issue) { notify(issue instanceof Error ? issue.message : 'Notification could not be updated.'); }
  }

  async function resetDemo() {
    if (!window.confirm('Restore Northstar Labs and remove all changes made in this demo?')) return;
    try {
      await apiRequest('/workspace/demo/reset', { method: 'POST' });
      setIncludeRead(false);
      await load();
      notify('Synthetic organization restored.');
    } catch (issue) { notify(issue instanceof Error ? issue.message : 'The demo could not be reset.'); }
  }

  function primaryAction() {
    if (view === 'meetings') setNewMeetingOpen(true);
    else if (view === 'reports') setReportSignal((signal) => signal + 1);
    else if (view === 'settings') navigateRouter('/admin/configuration');
  }

  function openDepartmentReport(department: string) {
    setReportDepartment(department);
    setReportSignal((signal) => signal + 1);
    navigate('reports');
  }

  function signOut() {
    clearSession();
    navigateRouter('/login', { replace: true });
  }

  function openRapidChat(prompt: string, context: WorkspaceView) {
    navigateRouter(`/workspace/chat?prompt=${encodeURIComponent(prompt)}&context=${encodeURIComponent(context)}`);
    setNavigationOpen(false);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  if (loading && !data) return <main className="product-page boot-state"><div className="boot-brand"><span>R</span><strong>RAPID</strong></div><LoadingState /></main>;
  if (error && !data) return <main className="product-page boot-state"><div className="portal-error"><strong>RAPID could not load this workspace.</strong><p id="portal-error-message">{error}</p><button id="retry-load" className="product-button secondary" type="button" onClick={() => void load()}>Retry</button></div></main>;
  if (!data) return null;

  const ViewComponent = WORKSPACE_VIEW_COMPONENTS[view] as ComponentType<WorkspaceViewProps>;
  const unread = data.notifications.filter((item) => !item.is_read).length;
  const viewProps: WorkspaceViewProps = {
    data,
    navigate,
    openMeeting,
    changeAction,
    openDepartmentReport,
    reportDepartment,
    setReportDepartment,
    reportSignal,
    includeRead,
    toggleIncludeRead,
    markNotification,
  };

  return (
    <>
      <WorkspaceShell overview={data.overview} view={view} notificationCount={unread} features={data.features} navigationOpen={navigationOpen} onNavigate={navigate} onNavigationOpen={setNavigationOpen} onReset={() => void resetDemo()} onPrimaryAction={primaryAction} onOpenChat={openRapidChat} onSignOut={signOut}>
        <ViewComponent {...viewProps} />
      </WorkspaceShell>
      <MeetingDialogs selectedMeeting={selectedMeeting} meetingOpen={meetingOpen} newMeetingOpen={newMeetingOpen} onMeetingClose={() => setMeetingOpen(false)} onNewMeetingClose={() => setNewMeetingOpen(false)} onSaveMeeting={saveMeeting} onCreateMeeting={createMeeting} onCreateAction={createAction} onChangeAction={changeAction} />
    </>
  );
}
