import type { Document } from "@/types/document";
import { parseApiTimestamp } from "@/lib/api/timestamps";

export function documentState(document: Partial<Document>): { label: string; status: string } {
  const latest = [...(document.processing_events ?? [])]
    .filter(event => ["failed", "succeeded", "success", "completed"].includes(event.status))
    .sort((a, b) => parseApiTimestamp(b.created_at).getTime() - parseApiTimestamp(a.created_at).getTime())[0];
  if (latest?.status === "failed") return { label: "Failed", status: "failed" };
  if (document.embedded === true) return { label: "Embedded", status: "completed" };
  if (document.chunked === true) return { label: "Chunked", status: "completed" };
  if (document.processed === true) return { label: "Processed", status: "completed" };
  if ([document.processed, document.chunked, document.embedded].every(value => value === false)) return { label: "Pending", status: "pending" };
  return { label: "Unknown", status: "unknown" };
}
