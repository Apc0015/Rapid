import { beforeEach, describe, expect, it } from 'vitest';
import { clearSession, getProfile, getToken, saveSession } from './api';

describe('browser session storage', () => {
  beforeEach(() => localStorage.clear());

  it('stores and clears the tenant session as one operation', () => {
    saveSession('token-value', { name: 'Maya Chen', role: 'ceo', tenant_id: 'demo' });
    expect(getToken()).toBe('token-value');
    expect(getProfile()).toMatchObject({ name: 'Maya Chen', tenant_id: 'demo' });
    clearSession();
    expect(getToken()).toBe('');
    expect(getProfile()).toEqual({});
  });

  it('does not crash on malformed profile storage', () => {
    localStorage.setItem('rapid_profile', '{bad json');
    expect(getProfile()).toEqual({});
  });
});
