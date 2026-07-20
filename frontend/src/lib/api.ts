import type { Profile } from '../types';

export const TOKEN_KEY = 'rapid_people_ops_token';
export const PROFILE_KEY = 'rapid_profile';

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export function getApiBaseUrl(): string {
  if (window.RAPID_API_URL) return window.RAPID_API_URL.replace(/\/$/, '');
  const configured = document.querySelector<HTMLMetaElement>('meta[name="rapid-api"]')?.content;
  if (configured) return configured.replace(/\/$/, '');
  return import.meta.env.DEV ? 'http://localhost:8000' : `${window.location.origin}/api`;
}

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? '';
}

export function getProfile(): Profile {
  try {
    return JSON.parse(localStorage.getItem(PROFILE_KEY) ?? '{}') as Profile;
  } catch {
    return {};
  }
}

export function saveSession(token: string, profile: Profile): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
  localStorage.setItem('rapid_user', JSON.stringify(profile));
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(PROFILE_KEY);
  localStorage.removeItem('rapid_user');
}

export async function apiRequest<T>(path: string, options: RequestInit = {}, authenticated = true): Promise<T> {
  const token = getToken();
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(authenticated && token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  const body = (await response.json().catch(() => ({}))) as { detail?: string };
  if (response.status === 401 && authenticated) {
    clearSession();
    window.dispatchEvent(new Event('rapid:unauthorized'));
  }
  if (!response.ok) throw new ApiError(body.detail || 'The request could not be completed.', response.status);
  return body as T;
}

export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const token = getToken();
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  const body = (await response.json().catch(() => ({}))) as { detail?: string };
  if (response.status === 401) {
    clearSession();
    window.dispatchEvent(new Event('rapid:unauthorized'));
  }
  if (!response.ok) throw new ApiError(body.detail || 'The upload could not be completed.', response.status);
  return body as T;
}

export async function downloadFile(path: string, filename: string): Promise<void> {
  const token = getToken();
  const response = await fetch(`${getApiBaseUrl()}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new ApiError(body.detail || 'The document could not be downloaded.', response.status);
  }
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = filename; anchor.click();
  URL.revokeObjectURL(url);
}
