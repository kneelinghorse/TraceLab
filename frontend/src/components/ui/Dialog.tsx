import { keepDialogFocus } from "@/lib/dialog-focus";
import { useEffect, useRef, type ReactNode } from "react";

/** Native modal semantics keep focus inside and restore it to the opener. */
export function Dialog({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (open && !dialog?.open) dialog?.showModal();
    if (!open && dialog?.open) dialog.close();
  }, [open]);
  return <dialog ref={ref} tabIndex={-1} onKeyDown={keepDialogFocus} aria-label={title} onCancel={event => { event.preventDefault(); onClose(); }} onClose={onClose} className="m-auto w-[calc(100%-2rem)] max-w-lg rounded-xl border border-line bg-surface p-6 text-foreground shadow-xl backdrop:bg-background/70">
    <h2 className="mb-4 text-xl font-semibold">{title}</h2>{children}
  </dialog>;
}
