import { useEffect, useRef, useState } from "react";
import { Dialog } from "./Dialog";
import { Toast } from "./Toast";
import { apiErrorMessage } from "@/lib/api/errors";

/** Await an explicit decision before a caller performs its mutation. */
export function useFeedback() {
  const [question, setQuestion] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ message: string; tone: "error" | "success" } | null>(null);
  const pending = useRef<((accepted: boolean) => void) | null>(null);
  useEffect(() => () => { pending.current?.(false); pending.current = null; }, []);
  function askConfirmation(message: string): Promise<boolean> {
    if (pending.current) return Promise.resolve(false);
    setQuestion(message);
    return new Promise(resolve => { pending.current = resolve; });
  }
  function decide(accepted: boolean) {
    const resolve = pending.current;
    pending.current = null;
    setQuestion(null);
    resolve?.(accepted);
  }
  function notify(message: unknown, tone: "error" | "success" = "error") {
    setNotice({ message: typeof message === "string" ? apiErrorMessage(new Error(message)) : apiErrorMessage(message), tone });
  }
  const feedback = <>
    <Dialog open={question !== null} title="Confirm action" onClose={() => decide(false)}>
      <p className="break-words text-secondary">{question}</p>
      <div className="mt-5 flex flex-wrap justify-end gap-3"><button type="button" autoFocus className="rounded-lg border border-line-strong px-4 py-2" onClick={() => decide(false)}>Cancel</button><button type="button" className="rounded-lg bg-danger-surface px-4 py-2 text-danger" onClick={() => decide(true)}>Continue</button></div>
    </Dialog>
    {notice && <Toast {...notice} onDismiss={() => setNotice(null)} />}
  </>;
  return { askConfirmation, notify, feedback };
}
