import { describe, expect, it } from 'vitest';
import { formatValue, initials, toDateTimeLocal } from './format';

describe('workspace formatting', () => {
  it('formats financial values without losing the currency meaning', () => {
    expect(formatValue('arr', 240000)).toMatch(/\$240,000/);
  });

  it('creates stable organization and person initials', () => {
    expect(initials('Northstar Labs')).toBe('NL');
    expect(initials('  Maya   Chen ')).toBe('MC');
  });

  it('produces a browser-compatible local datetime value', () => {
    expect(toDateTimeLocal(new Date('2026-07-15T12:30:00Z'))).toMatch(/^2026-07-15T\d{2}:30$/);
  });
});
