import Link from "next/link";

interface ResultLinksProps {
  documentIds: string[];
  reportId: string | null;
}

function DocumentIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
      />
    </svg>
  );
}

function ReportIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
      />
    </svg>
  );
}

export function ResultLinks({ documentIds, reportId }: ResultLinksProps) {
  const hasDocuments = documentIds.length > 0;
  const hasReport = reportId !== null;

  if (!hasDocuments && !hasReport) {
    return (
      <div className="text-gray-500 dark:text-gray-400 text-sm py-2">
        No results available yet. Results will appear after mission execution.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {hasDocuments && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-3">
            Result Documents ({documentIds.length})
          </h3>
          <div className="space-y-2">
            {documentIds.map((docId) => (
              <Link
                key={docId}
                href={`/documents/${docId}`}
                className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-900 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors group"
              >
                <span className="text-gray-400 group-hover:text-blue-500 transition-colors">
                  <DocumentIcon />
                </span>
                <span className="font-mono text-sm text-gray-700 dark:text-gray-300 truncate">
                  {docId}
                </span>
                <span className="ml-auto text-gray-400 group-hover:text-blue-500 transition-colors">
                  &rarr;
                </span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {hasReport && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-3">
            Generated Report
          </h3>
          <Link
            href={`/reports/${reportId}`}
            className="flex items-center gap-3 p-4 bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-lg hover:bg-emerald-100 dark:hover:bg-emerald-900/30 transition-colors group"
          >
            <span className="text-emerald-500">
              <ReportIcon />
            </span>
            <div className="flex-1">
              <p className="font-medium text-emerald-700 dark:text-emerald-300">View Synthesis Report</p>
              <p className="text-sm text-emerald-600 dark:text-emerald-400 font-mono truncate">{reportId}</p>
            </div>
            <span className="text-emerald-400 group-hover:text-emerald-500 transition-colors">
              &rarr;
            </span>
          </Link>
        </div>
      )}
    </div>
  );
}
