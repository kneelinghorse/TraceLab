/**
 * Admin → Spaces management (T48.3).
 *
 * Drives the S44 admin_spaces API + the project-assignment route: create/list
 * Spaces, manage membership (add/remove, with an active-users picker), and
 * assign projects to a Space. Membership and assignment cache-busting are
 * server-side (S47 + T48.3); the client just re-fetches local page state.
 * Lives behind RequireAdmin (UX only; the API enforces require_admin).
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { AuthGate } from "@/components/AuthGate";
import { RequireAdmin } from "@/components/RequireAdmin";
import { adminSpacesApi, adminUsersApi } from "@/lib/api/admin";
import type { AdminSpace, AdminUser, SpaceMember } from "@/lib/api/admin";
import { apiErrorMessage } from "@/lib/api/errors";
import { projectsApi } from "@/lib/api/projects";
import type { Project } from "@/types/document";

const errorBox =
  "rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-300";
const successBox =
  "rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 px-4 py-3 text-sm text-green-700 dark:text-green-300";
const cardClass = "rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-6";

export function SpacesAdmin() {
  const [spaces, setSpaces] = useState<AdminSpace[] | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectTotal, setProjectTotal] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [newSpaceName, setNewSpaceName] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const [selectedSpaceId, setSelectedSpaceId] = useState<string | null>(null);
  const [members, setMembers] = useState<SpaceMember[] | null>(null);
  const [pickedUserId, setPickedUserId] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [memberBusy, setMemberBusy] = useState(false);
  // Monotonic id so a slow listMembers response for a previously-selected Space
  // can't overwrite the roster of the one now selected (fast space switching).
  const memberReqRef = useRef(0);

  const loadSpaces = useCallback(async () => {
    try {
      setSpaces(await adminSpacesApi.list());
    } catch (err) {
      setSpaces([]);
      setLoadError(apiErrorMessage(err, "Failed to load spaces."));
    }
  }, []);

  useEffect(() => {
    void loadSpaces();
    adminUsersApi
      .list()
      .then(setUsers)
      .catch((err) => setLoadError(apiErrorMessage(err, "Failed to load users.")));
    projectsApi
      .listProjects({ pageSize: 100 })
      .then((res) => {
        setProjects(res.data);
        setProjectTotal(res.pagination.total);
      })
      .catch((err) => setLoadError(apiErrorMessage(err, "Failed to load projects.")));
  }, [loadSpaces]);

  const loadMembers = useCallback(async (spaceId: string) => {
    const reqId = (memberReqRef.current += 1);
    setActionError(null);
    setMembers(null);
    try {
      const roster = await adminSpacesApi.listMembers(spaceId);
      if (memberReqRef.current === reqId) {
        setMembers(roster);
      }
    } catch (err) {
      if (memberReqRef.current === reqId) {
        setMembers([]);
        setActionError(apiErrorMessage(err, "Failed to load members."));
      }
    }
  }, []);

  useEffect(() => {
    if (selectedSpaceId) {
      setPickedUserId(""); // a user picked for the prior Space must not carry over
      void loadMembers(selectedSpaceId);
    }
  }, [selectedSpaceId, loadMembers]);

  const createSpace = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateError(null);
    setCreateSuccess(null);
    if (!newSpaceName.trim()) {
      setCreateError("Space name cannot be blank.");
      return;
    }
    setCreating(true);
    try {
      const created = await adminSpacesApi.create(newSpaceName.trim());
      setCreateSuccess(`Created Space “${created.name}”.`);
      setNewSpaceName("");
      await loadSpaces();
    } catch (err) {
      setCreateError(apiErrorMessage(err, "Failed to create space."));
    } finally {
      setCreating(false);
    }
  };

  const addMember = async () => {
    if (!selectedSpaceId || !pickedUserId) {
      return;
    }
    setActionError(null);
    setMemberBusy(true);
    try {
      await adminSpacesApi.addMember(selectedSpaceId, pickedUserId);
      setPickedUserId("");
      await loadMembers(selectedSpaceId);
    } catch (err) {
      setActionError(apiErrorMessage(err, "Failed to add member."));
    } finally {
      setMemberBusy(false);
    }
  };

  const removeMember = async (userId: string) => {
    if (!selectedSpaceId) {
      return;
    }
    setActionError(null);
    setMemberBusy(true);
    try {
      await adminSpacesApi.removeMember(selectedSpaceId, userId);
      await loadMembers(selectedSpaceId);
    } catch (err) {
      setActionError(apiErrorMessage(err, "Failed to remove member."));
    } finally {
      setMemberBusy(false);
    }
  };

  const assignProject = async (project: Project, spaceId: string) => {
    const next = spaceId || null;
    if ((project.workspace_id ?? null) === next) {
      return;
    }
    setActionError(null);
    try {
      await adminSpacesApi.assignProjectSpace(project.id, next);
      setProjects((prev) =>
        prev.map((p) => (p.id === project.id ? { ...p, workspace_id: next } : p)),
      );
    } catch (err) {
      setActionError(apiErrorMessage(err, "Failed to assign project."));
    }
  };

  // The member picker only offers ACTIVE users who are not already members.
  const memberIds = new Set((members ?? []).map((m) => m.user_id));
  const eligibleUsers = users.filter((u) => u.is_active && !memberIds.has(u.id));
  const selectedSpace = spaces?.find((s) => s.id === selectedSpaceId) ?? null;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Spaces</h1>

        {loadError && <p className={errorBox}>{loadError}</p>}
        {/* Action errors (member add/remove/load, project assignment) — page-level
            so an assignment failure is visible even with no Space selected. */}
        {actionError && <p className={errorBox}>{actionError}</p>}

        <section className={cardClass}>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Create space</h2>
          {createError && <p className={`mb-4 ${errorBox}`}>{createError}</p>}
          {createSuccess && <p className={`mb-4 ${successBox}`}>{createSuccess}</p>}
          <form onSubmit={createSpace} className="flex flex-col sm:flex-row gap-3" noValidate>
            <input
              type="text"
              aria-label="Space name"
              placeholder="Space name"
              value={newSpaceName}
              onChange={(e) => setNewSpaceName(e.target.value)}
              className="form-input flex-1"
            />
            <button
              type="submit"
              disabled={creating}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
            >
              {creating ? "Creating…" : "Create space"}
            </button>
          </form>
        </section>

        <section className={cardClass}>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Spaces</h2>
          {spaces === null ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">Loading spaces…</p>
          ) : spaces.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">No spaces yet.</p>
          ) : (
            <ul className="divide-y divide-gray-100 dark:divide-gray-700/50">
              {spaces.map((s) => (
                <li key={s.id} className="flex items-center justify-between py-3">
                  <span className="text-gray-900 dark:text-white">{s.name}</span>
                  <button
                    type="button"
                    onClick={() => setSelectedSpaceId(s.id)}
                    className={`text-sm font-medium ${
                      s.id === selectedSpaceId
                        ? "text-blue-700 dark:text-blue-300"
                        : "text-blue-600 hover:text-blue-700"
                    }`}
                  >
                    Manage members
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {selectedSpace && (
          <section className={cardClass}>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Members of “{selectedSpace.name}”
            </h2>

            <div className="flex flex-col sm:flex-row gap-3 mb-4">
              <select
                aria-label="Add member to space"
                value={pickedUserId}
                onChange={(e) => setPickedUserId(e.target.value)}
                className="form-input flex-1"
              >
                <option value="">Select an active user…</option>
                {eligibleUsers.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.display_name} ({u.email})
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={addMember}
                disabled={!pickedUserId || memberBusy}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
              >
                Add member
              </button>
            </div>

            {members === null ? (
              <p className="text-sm text-gray-500 dark:text-gray-400">Loading members…</p>
            ) : members.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400">No members in this Space.</p>
            ) : (
              <ul className="divide-y divide-gray-100 dark:divide-gray-700/50">
                {members.map((m) => (
                  <li key={m.user_id} className="flex items-center justify-between py-3 text-sm">
                    <span className="text-gray-900 dark:text-white">
                      {m.display_name} <span className="text-gray-400">({m.email})</span>
                      {!m.is_active && <span className="ml-2 text-xs text-amber-600">disabled</span>}
                    </span>
                    <button
                      type="button"
                      onClick={() => removeMember(m.user_id)}
                      disabled={memberBusy}
                      className="text-red-600 hover:text-red-700 disabled:opacity-40"
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        <section className={cardClass}>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Project assignment
          </h2>
          {projectTotal > projects.length && (
            <p className="mb-4 text-sm text-amber-600 dark:text-amber-400">
              Showing the first {projects.length} of {projectTotal} projects. Use search on the
              Projects page to assign the rest.
            </p>
          )}
          {projects.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">No projects.</p>
          ) : (
            <ul className="divide-y divide-gray-100 dark:divide-gray-700/50">
              {projects.map((p) => (
                <li key={p.id} className="flex items-center justify-between py-3 text-sm">
                  <span className="text-gray-900 dark:text-white">{p.name}</span>
                  <select
                    aria-label={`Space for ${p.name}`}
                    value={p.workspace_id ?? ""}
                    onChange={(e) => assignProject(p, e.target.value)}
                    className="rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-2 py-1 text-sm text-gray-900 dark:text-white"
                  >
                    <option value="">— No Space —</option>
                    {(spaces ?? []).map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

export default function AdminSpacesPage() {
  return (
    <AuthGate>
      <RequireAdmin>
        <SpacesAdmin />
      </RequireAdmin>
    </AuthGate>
  );
}
