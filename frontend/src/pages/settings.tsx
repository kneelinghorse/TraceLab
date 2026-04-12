/**
 * User settings page — profile, API keys, invite codes
 */

import { AuthGate } from "@/components/AuthGate";
import { useAuth } from "@/contexts/AuthContext";
import { apiKeysApi, inviteCodesApi, profileApi } from "@/lib/api/settings";
import type { APIKeyInfo, APIKeyResponse, InviteCode } from "@/lib/api/settings";
import { formatDistanceToNow } from "date-fns";
import { useCallback, useEffect, useState } from "react";

export default function SettingsPage() {
  return (
    <AuthGate>
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Settings</h1>
          <ProfileSection />
          <APIKeysSection />
          <InviteCodesSection />
        </div>
      </div>
    </AuthGate>
  );
}

// ---------------------------------------------------------------------------
// Profile section
// ---------------------------------------------------------------------------

function ProfileSection() {
  const { user } = useAuth();
  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    setDisplayName(user?.display_name ?? "");
  }, [user?.display_name]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);

    if (newPassword && newPassword !== confirmPassword) {
      setMessage({ type: "error", text: "New passwords do not match" });
      return;
    }

    const payload: Record<string, string> = {};
    if (displayName.trim() && displayName.trim() !== user?.display_name) {
      payload.display_name = displayName.trim();
    }
    if (newPassword) {
      payload.current_password = currentPassword;
      payload.new_password = newPassword;
    }

    if (Object.keys(payload).length === 0) {
      setMessage({ type: "error", text: "No changes to save" });
      return;
    }

    setIsSaving(true);
    try {
      await profileApi.update(payload);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setMessage({ type: "success", text: "Profile updated" });
    } catch (err) {
      setMessage({ type: "error", text: err instanceof Error ? err.message : "Failed to update profile" });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <section className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Profile</h2>
      <form onSubmit={handleSave} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Email
          </label>
          <p className="text-sm text-gray-500 dark:text-gray-400">{user?.email}</p>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Display name
          </label>
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
          />
        </div>

        <div className="pt-2 border-t border-gray-100 dark:border-gray-700">
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">Change password</p>
          <div className="space-y-3">
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">Current password</label>
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                autoComplete="current-password"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">New password</label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">Confirm new password</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              />
            </div>
          </div>
        </div>

        {message && (
          <p className={`text-sm ${message.type === "success" ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
            {message.text}
          </p>
        )}

        <button
          type="submit"
          disabled={isSaving}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors text-sm font-medium"
        >
          {isSaving ? "Saving..." : "Save changes"}
        </button>
      </form>
    </section>
  );
}

// ---------------------------------------------------------------------------
// API Keys section
// ---------------------------------------------------------------------------

function APIKeysSection() {
  const [keys, setKeys] = useState<APIKeyInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [newKeyName, setNewKeyName] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [createdKey, setCreatedKey] = useState<APIKeyResponse | null>(null);
  const [copiedKeyId, setCopiedKeyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchKeys = useCallback(async () => {
    try {
      const data = await apiKeysApi.list();
      setKeys(data.keys);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load API keys");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchKeys();
  }, [fetchKeys]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newKeyName.trim()) return;
    setIsCreating(true);
    setError(null);
    setCreatedKey(null);
    try {
      const key = await apiKeysApi.create({ name: newKeyName.trim() });
      setCreatedKey(key);
      setNewKeyName("");
      await fetchKeys();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create API key");
    } finally {
      setIsCreating(false);
    }
  };

  const handleDelete = async (keyId: string, name: string) => {
    if (!confirm(`Revoke API key "${name}"? Any integrations using it will stop working.`)) return;
    try {
      await apiKeysApi.delete(keyId);
      await fetchKeys();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to revoke API key");
    }
  };

  const handleCopy = async (text: string, id: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKeyId(id);
      setTimeout(() => setCopiedKeyId(null), 2000);
    } catch {
      // ignore
    }
  };

  return (
    <section className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">API Keys</h2>
        <span className="text-xs text-gray-500 dark:text-gray-400">Used by MCP and external integrations</span>
      </div>

      {error && (
        <p className="mb-4 text-sm text-red-600 dark:text-red-400">{error}</p>
      )}

      {/* New key created — show full key once */}
      {createdKey && (
        <div className="mb-4 p-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
          <p className="text-sm font-medium text-green-800 dark:text-green-300 mb-2">
            API key created — copy it now, it won&apos;t be shown again.
          </p>
          <div className="flex items-center gap-3">
            <code className="text-sm font-mono bg-green-100 dark:bg-green-900/40 px-3 py-1.5 rounded text-green-900 dark:text-green-100 break-all">
              {createdKey.key}
            </code>
            <button
              onClick={() => handleCopy(createdKey.key, "new")}
              className="shrink-0 px-3 py-1.5 text-xs bg-green-700 text-white rounded hover:bg-green-800 transition-colors"
            >
              {copiedKeyId === "new" ? "Copied!" : "Copy"}
            </button>
          </div>
        </div>
      )}

      {/* Create form */}
      <form onSubmit={handleCreate} className="flex gap-3 mb-6">
        <input
          type="text"
          value={newKeyName}
          onChange={(e) => setNewKeyName(e.target.value)}
          placeholder="Key name (e.g. MCP local)"
          className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
        />
        <button
          type="submit"
          disabled={isCreating || !newKeyName.trim()}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors text-sm font-medium"
        >
          {isCreating ? "Creating..." : "Create key"}
        </button>
      </form>

      {/* Key list */}
      {isLoading ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">Loading...</p>
      ) : keys.length === 0 ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">No API keys yet.</p>
      ) : (
        <ul className="space-y-2">
          {keys.map((key) => (
            <li
              key={key.id}
              className="flex items-center justify-between py-3 px-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-900 dark:text-white">{key.name}</p>
                <div className="flex items-center gap-3 mt-0.5">
                  <code className="text-xs text-gray-500 dark:text-gray-400 font-mono">{key.key_prefix}…</code>
                  <span className="text-xs text-gray-400 dark:text-gray-500">
                    Created {formatDistanceToNow(new Date(key.created_at), { addSuffix: true })}
                  </span>
                  {key.last_used_at && (
                    <span className="text-xs text-gray-400 dark:text-gray-500">
                      Last used {formatDistanceToNow(new Date(key.last_used_at), { addSuffix: true })}
                    </span>
                  )}
                </div>
              </div>
              <button
                onClick={() => handleDelete(key.id, key.name)}
                className="ml-4 px-3 py-1 text-xs text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors"
              >
                Revoke
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Invite codes section
// ---------------------------------------------------------------------------

function InviteCodesSection() {
  const [codes, setCodes] = useState<InviteCode[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [newCode, setNewCode] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchCodes = useCallback(async () => {
    try {
      const data = await inviteCodesApi.list();
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
      const data = await inviteCodesApi.create();
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
      // ignore
    }
  };

  const handleDelete = async (codeId: string) => {
    try {
      await inviteCodesApi.delete(codeId);
      await fetchCodes();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete invite code");
    }
  };

  return (
    <section className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Invite Codes</h2>
        <button
          onClick={handleGenerate}
          disabled={isCreating}
          className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors font-medium"
        >
          {isCreating ? "Generating..." : "Generate code"}
        </button>
      </div>

      {error && (
        <p className="mb-4 text-sm text-red-600 dark:text-red-400">{error}</p>
      )}

      {newCode && (
        <div className="mb-4 p-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
          <p className="text-sm text-green-700 dark:text-green-300 mb-2">New invite code:</p>
          <div className="flex items-center gap-3">
            <code className="text-xl font-mono font-bold tracking-[0.25em] text-green-900 dark:text-green-100">
              {newCode}
            </code>
            <button
              onClick={() => handleCopy(newCode)}
              className="px-3 py-1 text-sm bg-green-100 dark:bg-green-800 text-green-700 dark:text-green-200 rounded hover:bg-green-200 dark:hover:bg-green-700 transition-colors"
            >
              {copied ? "Copied!" : "Copy"}
            </button>
          </div>
        </div>
      )}

      {isLoading ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">Loading...</p>
      ) : codes.length === 0 ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">No invite codes yet.</p>
      ) : (
        <ul className="space-y-2">
          {codes.map((code) => (
            <li
              key={code.id}
              className="flex items-center justify-between py-2.5 px-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg"
            >
              <div className="flex items-center gap-4">
                <code className="font-mono text-base tracking-widest text-gray-900 dark:text-white">
                  {code.code}
                </code>
                <span
                  className={`px-2 py-0.5 rounded-full text-xs font-medium ${
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
                <span className="text-xs text-gray-400 dark:text-gray-500">
                  {new Date(code.created_at).toLocaleDateString()}
                </span>
                {code.status === "unused" && (
                  <>
                    <button
                      onClick={() => handleCopy(code.code)}
                      className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                    >
                      Copy
                    </button>
                    <button
                      onClick={() => handleDelete(code.id)}
                      className="text-xs text-red-600 dark:text-red-400 hover:underline"
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
    </section>
  );
}
