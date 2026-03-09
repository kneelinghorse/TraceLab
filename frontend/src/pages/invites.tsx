import { useState, useEffect, useCallback } from "react";

import { useAuth } from "@/contexts/AuthContext";
import { apiRequest } from "@/lib/api/http";

type InviteCode = {
  id: string;
  code: string;
  status: "unused" | "used" | "expired";
  created_at: string;
  used_at: string | null;
  expires_at: string | null;
};

type InviteListResponse = {
  codes: InviteCode[];
  total: number;
};

type CreateInviteResponse = {
  id: string;
  code: string;
  created_at: string;
  expires_at: string | null;
};

export default function InvitesPage() {
  return <InviteManagement />;
}

function InviteManagement() {
  const { user } = useAuth();
  const [codes, setCodes] = useState<InviteCode[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [newCode, setNewCode] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchCodes = useCallback(async () => {
    try {
      const data = await apiRequest<InviteListResponse>("/auth/invite-codes");
      setCodes(data.codes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load invite codes");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCodes();
  }, [fetchCodes]);

  const handleGenerate = async () => {
    setIsCreating(true);
    setError(null);
    setNewCode(null);
    try {
      const data = await apiRequest<CreateInviteResponse>("/auth/invite-codes", {
        method: "POST",
      });
      setNewCode(data.code);
      setCopied(false);
      await fetchCodes();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate invite code");
    } finally {
      setIsCreating(false);
    }
  };

  const handleCopy = async (code: string) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for non-secure contexts
      const textArea = document.createElement("textarea");
      textArea.value = code;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand("copy");
      document.body.removeChild(textArea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDelete = async (codeId: string) => {
    try {
      await apiRequest(`/auth/invite-codes/${codeId}`, { method: "DELETE" });
      await fetchCodes();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete invite code");
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
    <main className="max-w-3xl mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Invite Codes</h1>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
          Generate invite codes to share with others. Each code can only be used once.
        </p>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      {/* Generate new code */}
      <div className="mb-8 p-6 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">Generate New Code</h2>
        <button
          onClick={handleGenerate}
          disabled={isCreating}
          className="px-4 py-2 bg-sky-500 text-white rounded-lg font-medium hover:bg-sky-600 disabled:opacity-50 transition-colors"
        >
          {isCreating ? "Generating..." : "Generate Invite Code"}
        </button>

        {newCode && (
          <div className="mt-4 p-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
            <p className="text-sm text-green-700 dark:text-green-300 mb-2">New invite code generated:</p>
            <div className="flex items-center gap-3">
              <code className="text-2xl font-mono font-bold tracking-[0.3em] text-green-900 dark:text-green-100">
                {newCode}
              </code>
              <button
                onClick={() => handleCopy(newCode)}
                className="px-3 py-1 text-sm bg-green-100 dark:bg-green-800 text-green-700 dark:text-green-200 rounded hover:bg-green-200 dark:hover:bg-green-700 transition-colors"
              >
                {copied ? "Copied!" : "Copy"}
              </button>
            </div>
            <p className="text-xs text-green-600 dark:text-green-400 mt-2">
              Share this code with someone to let them register. It can only be used once.
            </p>
          </div>
        )}
      </div>

      {/* List existing codes */}
      <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Your Invite Codes</h2>
        </div>

        {isLoading ? (
          <div className="p-6 text-center text-gray-500 dark:text-gray-400">Loading...</div>
        ) : codes.length === 0 ? (
          <div className="p-6 text-center text-gray-500 dark:text-gray-400">
            No invite codes yet. Generate one above.
          </div>
        ) : (
          <ul className="divide-y divide-gray-200 dark:divide-gray-700">
            {codes.map((code) => (
              <li key={code.id} className="px-6 py-4 flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <code className="font-mono text-lg tracking-widest text-gray-900 dark:text-white">
                    {code.code}
                  </code>
                  <span
                    className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      code.status === "unused"
                        ? "bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300"
                        : code.status === "used"
                        ? "bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400"
                        : "bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300"
                    }`}
                  >
                    {code.status}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    {new Date(code.created_at).toLocaleDateString()}
                  </span>
                  {code.status === "unused" && (
                    <>
                      <button
                        onClick={() => handleCopy(code.code)}
                        className="text-xs text-sky-600 dark:text-sky-400 hover:text-sky-700 dark:hover:text-sky-300"
                      >
                        Copy
                      </button>
                      <button
                        onClick={() => handleDelete(code.id)}
                        className="text-xs text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300"
                      >
                        Delete
                      </button>
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
    </div>
  );
}
