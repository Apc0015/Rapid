export function StatusTag({ value }: { value?: string | null }) {
  const status = String(value || 'unknown').toLowerCase();
  return <span className={`status-tag ${status}`}>{status.replaceAll('_', ' ')}</span>;
}

export function EmptyState({ children }: { children: string }) {
  return <div className="product-empty">{children}</div>;
}

export function LoadingState({ compact = false }: { compact?: boolean }) {
  return <div id={compact ? undefined : 'portal-loading'} className={`portal-loading${compact ? ' inline' : ''}`} aria-live="polite"><div /><div /><div /></div>;
}
