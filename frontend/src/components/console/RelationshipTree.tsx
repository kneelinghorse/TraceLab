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
    <div className="ml-4 border-l border-line dark:border-line pl-4">
      <div
        className={`flex items-center gap-2 py-2 ${onClick ? "cursor-pointer hover:bg-background dark:hover:bg-surface -ml-4 pl-4 pr-2 rounded" : ""}`}
        onClick={() => {
          if (hasChildren) setIsOpen(!isOpen);
          onClick?.();
        }}
      >
        {hasChildren && (
          <span className="text-muted w-4 text-center">
            {isOpen ? "−" : "+"}
          </span>
        )}
        <span className="font-medium text-foreground dark:text-foreground">{label}</span>
        {sublabel && (
          <span className="text-sm text-muted dark:text-muted">{sublabel}</span>
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
        color: "bg-info-surface text-info dark:bg-info-surface dark:text-info",
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
                      ? "bg-success-surface text-success dark:bg-success-surface dark:text-success"
                      : chunk.relationship.relevance_score >= 0.6
                      ? "bg-warning-surface text-warning dark:bg-warning-surface dark:text-warning"
                      : "bg-danger-surface text-danger dark:bg-danger-surface dark:text-danger",
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
          ? "bg-success-surface text-success dark:bg-success-surface dark:text-success"
          : "bg-surface text-foreground dark:bg-surface-alt dark:text-secondary",
      }}
    />
  );
}

export function RelationshipTree({ relationships, onChunkClick, onDocumentClick }: RelationshipTreeProps) {
  const { documents, chunks, insights, totals, cached } = relationships;

  return (
    <div className="bg-surface dark:bg-surface rounded-lg border border-line dark:border-line p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-foreground dark:text-foreground">
          Relationship Tree
        </h3>
        <div className="flex items-center gap-3 text-sm">
          <span className="text-muted dark:text-muted">
            {totals.documents} docs, {totals.chunks} chunks, {totals.insights} insights
          </span>
          {cached && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-info-surface text-info dark:bg-info-surface dark:text-info">
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
              color: "bg-info-surface text-info dark:bg-info-surface dark:text-info",
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
              color: "bg-success-surface text-success dark:bg-success-surface dark:text-success",
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
              color: "bg-warning-surface text-warning dark:bg-warning-surface dark:text-warning",
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
                      ? "bg-success-surface text-success"
                      : "bg-surface text-foreground",
                }}
              />
            ))}
          </TreeNode>
        )}

        {/* Empty State */}
        {documents.length === 0 && insights.length === 0 && (
          <p className="text-muted dark:text-muted text-center py-4">
            No relationships found for this mission.
          </p>
        )}
      </div>
    </div>
  );
}
