import { useState } from "react";
import { unreadBadge } from "@/lib/api/inbox";

/** Visual count only; the owning link carries the accessible name "Inbox, N unread". */
export function UnreadBadge({ total, className = "" }: { total: number; className?: string }) {
  if (total <= 0) return null;
  return <span aria-hidden="true" data-testid="inbox-unread" className={`inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-accent px-1.5 text-xs font-semibold leading-5 text-on-accent ${className}`}>{unreadBadge(total)}</span>;
}

/** Polite announcement of unread increases only; first loads and decreases stay silent. */
export function InboxAnnouncer({ total }: { total: number | undefined }) {
  const [tracked, setTracked] = useState<{ total: number | undefined; message: string }>({ total: undefined, message: "" });
  if (total !== undefined && total !== tracked.total) {
    const increased = tracked.total !== undefined && total > tracked.total;
    setTracked({ total, message: increased ? `${total} unread inbox ${total === 1 ? "item" : "items"}` : "" });
  }
  return <p role="status" aria-live="polite" className="sr-only">{tracked.message}</p>;
}
