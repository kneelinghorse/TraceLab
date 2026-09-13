import type { ReactNode } from "react";
export function PageState({ state, title, children, onRetry }: { state: "loading" | "empty" | "error"; title: string; children?: ReactNode; onRetry?: () => void }) {
  return <div role={state === "error" ? "alert" : state === "loading" ? "status" : undefined} className={`panel my-4 p-6 ${state === "error" ? "border-danger-line bg-danger-surface text-danger" : "text-secondary"}`}><p className="font-medium">{title}</p>{children && <div className="mt-2 text-sm">{children}</div>}{onRetry && <button type="button" onClick={onRetry} className="mt-4 rounded-lg border border-current px-4 py-2 text-sm">Retry</button>}</div>;
}
