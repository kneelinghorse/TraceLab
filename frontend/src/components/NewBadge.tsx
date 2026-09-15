export function NewBadge({ total, className = "" }: { total: number; className?: string }) {
  if (total <= 0) return null;
  return <span data-testid="new-count" aria-hidden="true" className={`inline-flex min-w-5 items-center justify-center rounded-full bg-accent px-1.5 py-0.5 text-xs font-semibold leading-none text-on-accent ${className}`}>{total > 99 ? "99+" : total}</span>;
}
