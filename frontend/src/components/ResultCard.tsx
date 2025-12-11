import clsx from "clsx";
import Link from "next/link";
import { forwardRef } from "react";

import { AddToCollection } from "@/components/AddToCollection";
import type { Document, Project } from "@/types/document";
import type { SearchResultChunk } from "@/types/search";

type ResultCardProps = {
  result: SearchResultChunk;
  document?: Document;
  project?: Project;
  isHighlighted?: boolean;
};

export const ResultCard = forwardRef<HTMLDivElement, ResultCardProps>(function ResultCard(
  { result, document, project, isHighlighted = false },
  ref,
) {

  const documentLabel = document?.name ?? document?.file_path ?? result.document_id ?? "Unlinked document";
  const projectLabel = project?.name ?? result.project_id;
  const chunkPreview = result.content.length > 360 ? `${result.content.slice(0, 357)}…` : result.content;
  const scoreLabel = typeof result.score === "number" ? result.score.toFixed(3) : "–";

  return (
    <div
      ref={ref}
      className={clsx(
        "rounded-2xl border p-5 transition bg-white/5 backdrop-blur text-white/90",
        isHighlighted
          ? "border-amber-300 shadow-lg shadow-amber-500/30"
          : "border-white/10 hover:border-sky-300/60",
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Chunk score</p>
          <p className="text-2xl font-semibold text-sky-200">{scoreLabel}</p>
        </div>
        {result.chunk_id && (
          <code className="rounded-full border border-white/15 bg-black/30 px-3 py-1 text-xs text-slate-200">
            {result.chunk_id}
          </code>
        )}
      </div>

      <div className="mt-4 space-y-2">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {result.project_id && (
            <Link
              href={`/projects/${result.project_id}`}
              className="text-sky-300 hover:text-sky-200 hover:underline"
            >
              {projectLabel}
            </Link>
          )}
          {result.project_id && result.document_id && (
            <span className="text-slate-500">/</span>
          )}
          {result.document_id ? (
            <Link
              href={`/documents/${result.document_id}`}
              className="text-slate-300 hover:text-white hover:underline"
            >
              {documentLabel}
            </Link>
          ) : (
            <span className="text-slate-300">{documentLabel}</span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm text-slate-400">
          <span>{result.source_type ? result.source_type : "Unknown type"}</span>
          {document?.uploaded_at && (
            <span className="text-xs text-slate-500">
              Uploaded {new Date(document.uploaded_at).toLocaleDateString()}
            </span>
          )}
          {/* PEDR metadata badges */}
          {result.element_type && (
            <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-300">
              {result.element_type}
            </span>
          )}
          {result.quality_score !== undefined && result.quality_score < 1 && (
            <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-300">
              Quality: {(result.quality_score * 100).toFixed(0)}%
            </span>
          )}
        </div>
      </div>

      <p className="mt-4 text-slate-100 leading-relaxed whitespace-pre-line">{chunkPreview}</p>

      <div className="mt-4 flex flex-wrap items-center justify-end gap-4">
        {result.chunk_id && (
          <AddToCollection chunkId={result.chunk_id} />
        )}
      </div>
    </div>
  );
});
