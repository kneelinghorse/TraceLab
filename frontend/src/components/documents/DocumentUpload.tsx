import Link from "next/link";
import { useState } from "react";
import { documentsApi } from "@/lib/api/documents";

type UploadItem = {
  id: string; file: File; documentId?: string; percent: number | null;
  phase: "queued" | "uploading" | "processing" | "uploaded" | "completed" | "failed";
  error?: string;
};
const labels = { queued: "Ready", uploading: "Uploading — awaiting server acceptance", processing: "Processing", uploaded: "Uploaded", completed: "Processing completed", failed: "Needs attention" };

/** A failed file never prevents another file from being uploaded. */
export function DocumentUpload({ projectId, onComplete, onBusyChange }: {
  projectId: string; onComplete?: () => void | Promise<unknown>; onBusyChange?: (busy: boolean) => void;
}) {
  const [items, setItems] = useState<UploadItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [autoProcess, setAutoProcess] = useState(true);
  const [refreshError, setRefreshError] = useState(false);
  function add(files: File[]) {
    if (busy) return;
    setItems(previous => [...previous, ...files.map(file => ({ id: crypto.randomUUID(), file, phase: "queued" as const, percent: null }))]);
  }
  function patch(id: string, update: Partial<UploadItem>) {
    setItems(previous => previous.map(item => item.id === id ? { ...item, ...update } : item));
  }
  async function run(selected: UploadItem[]) {
    if (busy || !projectId) return;
    setBusy(true); onBusyChange?.(true); setRefreshError(false);
    try {
      for (const item of selected) {
        let documentId = item.documentId;
        try {
          if (!documentId) {
            patch(item.id, { phase: "uploading", error: undefined, percent: null });
            const result = await documentsApi.uploadDocument(projectId, item.file, (loaded, total) => {
              patch(item.id, { percent: total && total > 0 ? Math.min(100, Math.round(100 * loaded / total)) : null });
            });
            documentId = result.id;
            patch(item.id, { documentId, phase: "uploaded" });
          }
          if (autoProcess || item.documentId) {
            patch(item.id, { phase: "processing", error: undefined });
            const result = await documentsApi.processDocument(documentId);
            const failed = Object.entries(result.stages ?? {}).filter(([, stage]) => stage.status === "failed").map(([name]) => name);
            if (failed.length) throw new Error(`Processing needs attention: ${failed.join(", ")}.`);
            if (result.status !== "completed") throw new Error(result.error || `Processing reported: ${result.status || "unknown"}. Inspect the document before retrying.`);
            patch(item.id, { phase: "completed" });
          }
        } catch (error) {
          patch(item.id, { documentId, phase: "failed", error: error instanceof Error ? error.message : "Upload failed." });
        }
      }
      try { await onComplete?.(); } catch { setRefreshError(true); }
    } finally { setBusy(false); onBusyChange?.(false); }
  }
  return <section className="panel space-y-4 p-5" aria-label="Upload documents">
    <div><h2 className="text-lg font-semibold">Upload documents</h2><p className="mt-1 text-sm text-secondary">Each file keeps its own result. Processing starts after the server accepts the upload.</p></div>
    <div className="rounded-lg border border-dashed border-line-strong p-5" onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); add(Array.from(event.dataTransfer.files)); }}>
      <label className="block space-y-2 text-sm"><span>Choose files</span><input type="file" multiple disabled={busy} className="block w-full min-w-0 text-sm" onChange={event => { add(Array.from(event.target.files ?? [])); event.target.value = ""; }} /></label>
      <p className="mt-2 text-sm text-muted">Or drop files here. PDF, DOCX, PPTX, CSV, XLSX, Markdown and text.</p>
    </div>
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={autoProcess} disabled={busy} onChange={event => setAutoProcess(event.target.checked)} />Process after upload</label>
    <button className="rounded-lg bg-accent px-4 py-2 text-on-accent disabled:opacity-50" disabled={busy || !projectId || !items.some(item => item.phase === "queued")} onClick={() => void run(items.filter(item => item.phase === "queued"))}>{busy ? "Working…" : "Upload files"}</button>
    {refreshError && <p role="alert">Files were handled, but the project could not refresh. Refresh the page to check its current totals.</p>}
    <ul className="divide-y divide-line" aria-label="Upload results">{items.map(item => <li key={item.id} className="space-y-2 py-4">
      <div className="flex flex-wrap items-start justify-between gap-2"><p className="min-w-0 break-all font-medium">{item.file.name}</p><span className="text-sm text-secondary">{labels[item.phase]}</span></div>
      {item.phase === "uploading" && <div role="progressbar" aria-label={`${item.file.name} upload`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={item.percent ?? undefined} className="h-2 overflow-hidden rounded bg-surface-alt">{item.percent !== null && <div className="h-full bg-accent" style={{ width: `${item.percent}%` }} />}</div>}
      {item.phase === "uploading" && <p className="text-xs text-muted">{item.percent === null ? "Transfer progress not reported." : `${item.percent}% transferred`}</p>}
      {item.error && <p role="alert" className="break-words text-sm text-danger">{item.error}</p>}
      <div className="flex flex-wrap gap-4 text-sm">{item.documentId && <Link className="text-accent-text underline" href={`/documents/${item.documentId}`}>Open {item.file.name}</Link>}{item.phase === "failed" && <button disabled={busy} className="text-accent-text underline" onClick={() => void run([item])}>Retry {item.file.name}</button>}{item.phase === "queued" && <button disabled={busy} className="text-secondary underline" onClick={() => setItems(previous => previous.filter(row => row.id !== item.id))}>Remove {item.file.name}</button>}</div>
    </li>)}</ul>
  </section>;
}
