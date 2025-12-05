/**
 * RelationshipTree - Hierarchical display of mission relationships.
 * Shows documents, evidence chunks, and insights as a collapsible tree.
 */

import { useState } from "react";
import type { RelationshipContextResponse, RelatedDocument, RelatedChunk, RelatedInsight } from "@/types/console";

interface RelationshipTreeProps {
  relationships: RelationshipContextResponse;
  onChunkClick?: (chunkId: string) => void;
  onDocumentClick?: (documentId: string) => void;
}

interface TreeNodeProps {
  label: string;
  sublabel?: string;
  badge?: { text: string; color: string };
  children?: React.ReactNode;
  defaultOpen?: boolean;
  onClick?: () => void;
}

function TreeNode({ label, sublabel, badge, children, defaultOpen = false, onClick }: TreeNodeProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const hasChildren = Boolean(children);

  return (
    <div className="ml-4 border-l border-gray-200 dark:border-gray-700 pl-4">
      <div
        className={`flex items-center gap-2 py-2 ${onClick ? "cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 -ml-4 pl-4 pr-2 rounded" : ""}`}
        onClick={() => {
          if (hasChildren) setIsOpen(!isOpen);
          onClick?.();
        }}
      >
        {hasChildren && (
          <span className="text-gray-400 w-4 text-center">
            {isOpen ? "−" : "+"}
          </span>
        )}
        <span className="font-medium text-gray-900 dark:text-white">{label}</span>
        {sublabel && (
          <span className="text-sm text-gray-500 dark:text-gray-400">{sublabel}</span>
        )}
        {badge && (
          <span className={`text-xs px-2 py-0.5 rounded-full ${badge.color}`}>
            {badge.text}
          </span>
        )}
      </div>
      {hasChildren && isOpen && <div className="mt-1">{children}</div>}
    </div>
  );
}

function DocumentNode({ doc, chunks, onChunkClick }: { doc: RelatedDocument; chunks: RelatedChunk[]; onChunkClick?: (id: string) => void }) {
  const docChunks = chunks.filter(c => c.document_id === doc.id);

  return (
    <TreeNode
      label={doc.name}
      sublabel={doc.file_type ?? undefined}
      badge={{
        text: `${doc.evidence_chunks} chunks`,
        color: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
      }}
    >
      {docChunks.map((chunk) => (
        <TreeNode
          key={chunk.id}
          label={`Chunk ${chunk.chunk_index}`}
          sublabel={chunk.preview ? `"${chunk.preview.slice(0, 50)}..."` : undefined}
          badge={
            chunk.relationship.relevance_score
              ? {
                  text: `${Math.round(chunk.relationship.relevance_score * 100)}%`,
                  color:
                    chunk.relationship.relevance_score >= 0.8
                      ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                      : chunk.relationship.relevance_score >= 0.6
                      ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
                      : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
                }
              : undefined
          }
          onClick={() => onChunkClick?.(chunk.id)}
        />
      ))}
    </TreeNode>
  );
}

function InsightNode({ insight }: { insight: RelatedInsight }) {
  return (
    <TreeNode
      label={insight.title}
      sublabel={insight.insight_type ?? undefined}
      badge={{
        text: insight.validated ? "Validated" : "Pending",
        color: insight.validated
          ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
          : "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200",
      }}
    />
  );
}

export function RelationshipTree({ relationships, onChunkClick, onDocumentClick }: RelationshipTreeProps) {
  const { documents, chunks, insights, totals, cached } = relationships;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
          Relationship Tree
        </h3>
        <div className="flex items-center gap-3 text-sm">
          <span className="text-gray-500 dark:text-gray-400">
            {totals.documents} docs, {totals.chunks} chunks, {totals.insights} insights
          </span>
          {cached && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200">
              Cached
            </span>
          )}
        </div>
      </div>

      <div className="space-y-1">
        {/* Documents Section */}
        {documents.length > 0 && (
          <TreeNode
            label="Documents"
            badge={{
              text: `${documents.length}`,
              color: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
            }}
            defaultOpen
          >
            {documents.map((doc) => (
              <DocumentNode
                key={doc.id}
                doc={doc}
                chunks={chunks}
                onChunkClick={onChunkClick}
              />
            ))}
          </TreeNode>
        )}

        {/* Insights Section */}
        {insights.length > 0 && (
          <TreeNode
            label="Insights"
            badge={{
              text: `${insights.length}`,
              color: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200",
            }}
            defaultOpen
          >
            {insights.map((insight) => (
              <InsightNode key={insight.id} insight={insight} />
            ))}
          </TreeNode>
        )}

        {/* Related Missions Section */}
        {relationships.related_missions.length > 0 && (
          <TreeNode
            label="Related Missions"
            badge={{
              text: `${relationships.related_missions.length}`,
              color: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
            }}
          >
            {relationships.related_missions.map((mission) => (
              <TreeNode
                key={mission.id}
                label={mission.title ?? mission.mission_identifier ?? "Untitled"}
                sublabel={`${mission.completion_percentage}% complete`}
                badge={{
                  text: mission.status,
                  color:
                    mission.status === "complete"
                      ? "bg-green-100 text-green-800"
                      : "bg-gray-100 text-gray-800",
                }}
              />
            ))}
          </TreeNode>
        )}

        {/* Empty State */}
        {documents.length === 0 && insights.length === 0 && (
          <p className="text-gray-500 dark:text-gray-400 text-center py-4">
            No relationships found for this mission.
          </p>
        )}
      </div>
    </div>
  );
}
