import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { parseApiTimestamp } from "@/lib/api/timestamps";
import { documentState } from "@/lib/document-state";
import type { Document } from "@/types/document";

export function DocumentRows({ documents, onDelete, projects }: { documents: Document[]; onDelete: (id: string) => void; projects?: Map<string, string> }) {
  return <ul className="divide-y divide-line">{documents.map(document => <li key={document.id} className="flex flex-wrap items-start justify-between gap-3 py-5">
    <div className="min-w-0 flex-1 space-y-2"><Link className="block break-words font-semibold hover:text-accent-text" href={`/documents/${document.id}`}>{document.name}</Link>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-secondary">{projects && <Link className="text-accent-text underline" href={`/projects/${document.project_id}`}>{projects.get(document.project_id) ?? "Project"}</Link>}<span>{document.file_type || document.mime_type || "Type unknown"}</span>{document.file_size != null && <span>{(document.file_size / 1024).toFixed(1)} KB</span>}{document.uploaded_at && <span>Uploaded {formatDistanceToNow(parseApiTimestamp(document.uploaded_at), { addSuffix: true })}</span>}</div>
    </div>
    <StatusBadge {...documentState(document)} />
    <button className="rounded px-2 py-1 text-sm text-danger hover:bg-danger-surface" onClick={() => onDelete(document.id)} aria-label={`Delete ${document.name}`}>Delete</button>
  </li>)}</ul>;
}
