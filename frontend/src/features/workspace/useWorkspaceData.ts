import { useCallback, useEffect, useState } from 'react';
import { apiRequest } from '../../lib/api';
import type {
  ActionItem,
  JobsResponse,
  Meeting,
  NotificationItem,
  Readiness,
  TenantConfiguration,
  TenantFeature,
  WorkspaceData,
  WorkspaceOverview,
  BusinessRecord,
} from '../../types';

interface WorkspaceState {
  data: WorkspaceData | null;
  loading: boolean;
  error: string;
  load: () => Promise<void>;
  refreshOperations: () => Promise<void>;
  refreshNotifications: (includeRead: boolean) => Promise<void>;
}

export function useWorkspaceData(includeRead: boolean): WorkspaceState {
  const [data, setData] = useState<WorkspaceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [overview, meetings, actions, records, notifications, configuration, features, readiness, jobs] = await Promise.all([
        apiRequest<WorkspaceOverview>('/workspace/overview'),
        apiRequest<{ meetings: Meeting[] }>('/workspace/meetings'),
        apiRequest<{ actions: ActionItem[] }>('/workspace/actions'),
        apiRequest<{ records: BusinessRecord[] }>('/workspace/records'),
        apiRequest<{ notifications: NotificationItem[] }>(`/workspace/notifications?include_read=${includeRead}`),
        apiRequest<TenantConfiguration>('/tenant-admin/configuration').catch(() => null),
        apiRequest<{ features: TenantFeature[] }>('/tenant-admin/features'),
        apiRequest<Readiness>('/health/ready').catch(() => null),
        apiRequest<JobsResponse>('/jobs?limit=10').catch(() => null),
      ]);
      setData({
        overview,
        meetings: meetings.meetings,
        actions: actions.actions,
        records: records.records,
        notifications: notifications.notifications,
        configuration,
        features: features.features,
        readiness,
        jobs,
      });
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : 'RAPID could not load this workspace.');
    } finally {
      setLoading(false);
    }
  }, [includeRead]);

  const refreshOperations = useCallback(async () => {
    const [overview, meetings, actions] = await Promise.all([
      apiRequest<WorkspaceOverview>('/workspace/overview'),
      apiRequest<{ meetings: Meeting[] }>('/workspace/meetings'),
      apiRequest<{ actions: ActionItem[] }>('/workspace/actions'),
    ]);
    setData((current) => current ? { ...current, overview, meetings: meetings.meetings, actions: actions.actions } : current);
  }, []);

  const refreshNotifications = useCallback(async (showRead: boolean) => {
    const response = await apiRequest<{ notifications: NotificationItem[] }>(`/workspace/notifications?include_read=${showRead}`);
    setData((current) => current ? { ...current, notifications: response.notifications } : current);
  }, []);

  useEffect(() => { void load(); }, [load]);

  return { data, loading, error, load, refreshOperations, refreshNotifications };
}
