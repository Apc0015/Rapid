import { useState, type FormEvent } from 'react';
import { Modal } from '../../components/Modal';
import { EmptyState } from '../../components/StatusTag';
import { DEPARTMENTS } from '../../constants';
import { formatDate, toDateTimeLocal } from '../../lib/format';
import type { ActionItem, Meeting } from '../../types';
import { ActionRow } from './WorkspaceViews';

const CADENCE_OPTIONS = [
  ['none', 'Does not repeat'],
  ['daily', 'Daily'],
  ['weekly', 'Weekly'],
  ['biweekly', 'Every two weeks'],
  ['monthly', 'Monthly'],
  ['quarterly', 'Quarterly'],
];

interface MeetingDialogsProps {
  selectedMeeting: Meeting | null;
  meetingOpen: boolean;
  newMeetingOpen: boolean;
  onMeetingClose: () => void;
  onNewMeetingClose: () => void;
  onSaveMeeting: (meetingId: string, payload: Record<string, unknown>) => Promise<void>;
  onCreateMeeting: (payload: Record<string, unknown>) => Promise<void>;
  onCreateAction: (meetingId: string, payload: Record<string, unknown>) => Promise<void>;
  onChangeAction: (id: string, status: string) => Promise<void>;
}

export function MeetingDialogs({
  selectedMeeting,
  meetingOpen,
  newMeetingOpen,
  onMeetingClose,
  onNewMeetingClose,
  onSaveMeeting,
  onCreateMeeting,
  onCreateAction,
  onChangeAction,
}: MeetingDialogsProps) {
  const [actionOpen, setActionOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  async function saveMeeting(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedMeeting) return;
    const form = new FormData(event.currentTarget);
    setSaving(true);
    try {
      await onSaveMeeting(selectedMeeting.id, {
        title: form.get('title'),
        facilitator: form.get('facilitator'),
        status: form.get('status'),
        recurrence: form.get('recurrence'),
        duration_minutes: Number(form.get('duration_minutes')),
        attendees: String(form.get('attendees') ?? '').split(',').map((item) => item.trim()).filter(Boolean),
        agenda: String(form.get('agenda') ?? '').split('\n').map((item) => item.trim()).filter(Boolean),
        notes: form.get('notes'),
        decisions: String(form.get('decisions') ?? '').split('\n').map((item) => item.trim()).filter(Boolean),
      });
    } finally { setSaving(false); }
  }

  async function createMeeting(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const facilitator = String(form.get('facilitator') ?? '').trim();
    const attendees = String(form.get('attendees') ?? '').split(',').map((item) => item.trim()).filter(Boolean);
    if (!attendees.includes(facilitator)) attendees.unshift(facilitator);
    setSaving(true);
    try {
      await onCreateMeeting({
        title: form.get('title'),
        meeting_type: 'Operating review',
        department: form.get('department'),
        starts_at: new Date(String(form.get('starts_at'))).toISOString(),
        duration_minutes: Number(form.get('duration_minutes')),
        facilitator,
        attendees,
        agenda: String(form.get('agenda') ?? '').split('\n').map((item) => item.trim()).filter(Boolean),
        recurrence: form.get('recurrence'),
      });
      event.currentTarget.reset();
    } finally { setSaving(false); }
  }

  async function createAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedMeeting) return;
    const form = new FormData(event.currentTarget);
    setSaving(true);
    try {
      await onCreateAction(selectedMeeting.id, {
        title: form.get('title'),
        owner: form.get('owner'),
        department: form.get('department'),
        due_date: new Date(`${String(form.get('due_date'))}T17:00:00`).toISOString(),
        priority: form.get('priority'),
      });
      setActionOpen(false);
      event.currentTarget.reset();
    } finally { setSaving(false); }
  }

  const nextHour = new Date(Date.now() + 3_600_000);
  nextHour.setMinutes(0, 0, 0);
  const actionDue = new Date(Date.now() + 3 * 86_400_000).toISOString().slice(0, 10);

  return (
    <>
      <Modal
        id="meeting-dialog"
        open={meetingOpen && Boolean(selectedMeeting)}
        title={selectedMeeting?.title ?? 'Meeting'}
        context="Meeting record"
        description={selectedMeeting ? `${formatDate(selectedMeeting.starts_at)} · ${DEPARTMENTS[selectedMeeting.department] ?? 'Organization-wide'}` : ''}
        onClose={onMeetingClose}
        labelledBy="meeting-edit-title"
      >
        {selectedMeeting ? <form id="meeting-edit-form" key={`${selectedMeeting.id}-${selectedMeeting.notes}`} onSubmit={saveMeeting}>
          <div className="form-grid">
            <label className="admin-label span-2">Title<input id="meeting-title" name="title" maxLength={160} required defaultValue={selectedMeeting.title} /></label>
            <label className="admin-label">Facilitator<input id="meeting-facilitator" name="facilitator" maxLength={160} required defaultValue={selectedMeeting.facilitator} /></label>
            <label className="admin-label">Status<select id="meeting-status" name="status" defaultValue={selectedMeeting.status}><option value="scheduled">Scheduled</option><option value="in_progress">In progress</option><option value="completed">Completed</option><option value="cancelled">Cancelled</option></select></label>
            <label className="admin-label">Cadence<select id="meeting-recurrence" name="recurrence" defaultValue={selectedMeeting.recurrence || 'none'}>{CADENCE_OPTIONS.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
            <label className="admin-label">Duration<input id="meeting-duration" name="duration_minutes" type="number" min={15} max={480} required defaultValue={selectedMeeting.duration_minutes} /></label>
            <label className="admin-label span-2">Participants<input id="meeting-attendees" name="attendees" defaultValue={selectedMeeting.attendees.join(', ')} placeholder="Comma-separated names" /></label>
            <label className="admin-label span-2">Agenda<textarea id="meeting-agenda" name="agenda" rows={3} defaultValue={selectedMeeting.agenda.join('\n')} placeholder="One item per line" required /></label>
            <label className="admin-label span-2">Notes<textarea id="meeting-notes" name="notes" rows={5} defaultValue={selectedMeeting.notes} placeholder="Capture context and evidence" /></label>
            <label className="admin-label span-2">Decisions<textarea id="meeting-decisions" name="decisions" rows={3} defaultValue={selectedMeeting.decisions.join('\n')} placeholder="One decision per line" /></label>
          </div>
          <div className="dialog-actions"><button id="open-action-form" className="product-button secondary" type="button" onClick={() => setActionOpen(true)}>Assign action</button><button className="product-button primary" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save meeting'}</button></div>
          <section className="meeting-actions-section"><h3>Assigned actions</h3><div id="meeting-actions-list" className="action-list">{selectedMeeting.actions?.length ? selectedMeeting.actions.map((action: ActionItem) => <ActionRow action={action} key={action.id} onChange={onChangeAction} />) : <EmptyState>No actions have been assigned from this meeting.</EmptyState>}</div></section>
        </form> : null}
      </Modal>

      <Modal id="action-dialog" open={actionOpen && Boolean(selectedMeeting)} title="Assign an action" context="Meeting follow-up" size="small" onClose={() => setActionOpen(false)}>
        <form id="meeting-action-form" className="stack-form" onSubmit={createAction}>
          <label className="admin-label">Action title<input id="new-action-title" name="title" maxLength={240} required /></label>
          <label className="admin-label">Owner<input id="new-action-owner" name="owner" maxLength={160} required defaultValue={selectedMeeting?.facilitator} /></label>
          <label className="admin-label">Department<select id="new-action-department" name="department" required defaultValue={selectedMeeting?.department || 'ops'}>{Object.entries(DEPARTMENTS).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label>
          <label className="admin-label">Due date<input id="new-action-due" name="due_date" type="date" required defaultValue={actionDue} /></label>
          <label className="admin-label">Priority<select id="new-action-priority" name="priority" defaultValue="medium"><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label>
          <button className="product-button primary" type="submit" disabled={saving}>{saving ? 'Creating…' : 'Create action'}</button>
        </form>
      </Modal>

      <Modal id="new-meeting-dialog" open={newMeetingOpen} title="Schedule a meeting" context="Operating cadence" onClose={onNewMeetingClose}>
        <form id="new-meeting-form" onSubmit={createMeeting}>
          <div className="form-grid">
            <label className="admin-label span-2">Title<input id="new-meeting-title" name="title" required maxLength={160} placeholder="Weekly operating review" /></label>
            <label className="admin-label">Department<select id="new-meeting-department" name="department" defaultValue=""><option value="">Organization-wide</option>{Object.entries(DEPARTMENTS).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label>
            <label className="admin-label">Cadence<select id="new-meeting-recurrence" name="recurrence" defaultValue="none">{CADENCE_OPTIONS.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
            <label className="admin-label">Start time<input id="new-meeting-starts-at" name="starts_at" type="datetime-local" required defaultValue={toDateTimeLocal(nextHour)} /></label>
            <label className="admin-label">Duration<input id="new-meeting-duration" name="duration_minutes" type="number" min={15} max={480} defaultValue={30} required /></label>
            <label className="admin-label span-2">Facilitator<input id="new-meeting-facilitator" name="facilitator" required maxLength={160} defaultValue="Maya Chen" /></label>
            <label className="admin-label span-2">Participants<input id="new-meeting-attendees" name="attendees" maxLength={500} placeholder="Maya Chen, Arjun Rao" /></label>
            <label className="admin-label span-2">Agenda<textarea id="new-meeting-agenda" name="agenda" rows={3} required placeholder="One item per line" /></label>
          </div>
          <div className="dialog-actions"><button className="product-button primary" type="submit" disabled={saving}>{saving ? 'Scheduling…' : 'Schedule meeting'}</button></div>
        </form>
      </Modal>
    </>
  );
}
