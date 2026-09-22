/**
 * Admin → Spaces management (T48.3).
 *
 * Drives the S44 admin_spaces API + the project-assignment route: create/list
 * Spaces, manage membership (add/remove, with an active-users picker), and
 * assign projects to a Space. Membership and assignment cache-busting are
 * server-side (S47 + T48.3); the client just re-fetches local page state.
 * Personal Spaces (PERSONAL-1) are labelled with their owner, read "My Space"
 * to that owner, and take projects but not members.
 * Lives behind RequireAdmin (UX only; the API enforces require_admin).
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { AuthGate } from "@/components/AuthGate";
import { RequireAdmin } from "@/components/RequireAdmin";
import { useAuth } from "@/contexts/AuthContext";
import { adminSpacesApi, adminUsersApi } from "@/lib/api/admin";
import type { AdminSpace, AdminUser, SpaceMember } from "@/lib/api/admin";
import { apiErrorMessage } from "@/lib/api/errors";
import { projectsApi } from "@/lib/api/projects";
import type { Project } from "@/types/document";

const errorBox =
  "rounded-lg bg-danger-surface border border-danger-line px-4 py-3 text-sm text-danger";
const successBox =
  "rounded-lg bg-success-surface border border-success-line px-4 py-3 text-sm text-success";
const cardClass = "rounded-lg bg-surface border border-line p-6";

export function SpacesAdmin() {
  const { user: self } = useAuth();
  const selfId = self?.user_id ?? null;
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
  const personalSelected = Boolean(selectedSpace?.personal_owner_id);

  const spaceName = (s: AdminSpace) =>
    s.personal_owner_id && s.personal_owner_id === selfId ? "My Space" : s.name;
  const personalTag = (s: AdminSpace) => {
    if (!s.personal_owner_id) {
      return null;
    }
    const owner = users.find((u) => u.id === s.personal_owner_id);
    return `Personal · ${owner?.display_name ?? "unknown user"}`;
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        <h1 className="text-2xl font-bold text-foreground">Spaces</h1>

        {loadError && <p className={errorBox}>{loadError}</p>}
        {/* Action errors (member add/remove/load, project assignment) — page-level
            so an assignment failure is visible even with no Space selected. */}
        {actionError && <p className={errorBox}>{actionError}</p>}

        <section className={cardClass}>
          <h2 className="text-lg font-semibold text-foreground mb-4">Create space</h2>
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
              className="px-4 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent disabled:opacity-50 text-sm font-medium"
            >
              {creating ? "Creating…" : "Create space"}
            </button>
          </form>
        </section>

        <section className={cardClass}>
          <h2 className="text-lg font-semibold text-foreground mb-4">Spaces</h2>
          {spaces === null ? (
            <p className="text-sm text-muted">Loading spaces…</p>
          ) : spaces.length === 0 ? (
            <p className="text-sm text-muted">No spaces yet.</p>
          ) : (
            <ul className="divide-y divide-line">
              {spaces.map((s) => (
                <li key={s.id} className="flex items-center justify-between py-3">
                  <div className="flex flex-wrap items-center gap-x-2">
                    <span className="text-foreground">{spaceName(s)}</span>
                    {personalTag(s) && <span className="text-xs text-muted">{personalTag(s)}</span>}
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedSpaceId(s.id)}
                    className={`text-sm font-medium ${
                      s.id === selectedSpaceId
                        ? "text-accent-text"
                        : "text-accent-text hover:text-accent-text"
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
            <h2 className="text-lg font-semibold text-foreground mb-4">
              Members of “{spaceName(selectedSpace)}”
            </h2>

            {personalSelected && (
              <p className="mb-4 text-sm text-muted">
                A personal Space has one member. Assign projects to it below instead.
              </p>
            )}
            <div className="flex flex-col sm:flex-row gap-3 mb-4">
              <select
                aria-label="Add member to space"
                value={pickedUserId}
                onChange={(e) => setPickedUserId(e.target.value)}
                disabled={personalSelected}
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
                disabled={!pickedUserId || memberBusy || personalSelected}
                className="px-4 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent disabled:opacity-50 text-sm font-medium"
              >
                Add member
              </button>
            </div>

            {members === null ? (
              <p className="text-sm text-muted">Loading members…</p>
            ) : members.length === 0 ? (
              <p className="text-sm text-muted">No members in this Space.</p>
            ) : (
              <ul className="divide-y divide-line">
                {members.map((m) => (
                  <li key={m.user_id} className="flex items-center justify-between py-3 text-sm">
                    <span className="text-foreground">
                      {m.display_name} <span className="text-muted">({m.email})</span>
                      {!m.is_active && <span className="ml-2 text-xs text-warning">disabled</span>}
                    </span>
                    <button
                      type="button"
                      onClick={() => removeMember(m.user_id)}
                      disabled={memberBusy}
                      className="text-danger hover:text-danger disabled:opacity-40"
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
          <h2 className="text-lg font-semibold text-foreground mb-4">
            Project assignment
          </h2>
          {projectTotal > projects.length && (
            <p className="mb-4 text-sm text-warning">
              Showing the first {projects.length} of {projectTotal} projects. Use search on the
              Projects page to assign the rest.
            </p>
          )}
          {projects.length === 0 ? (
            <p className="text-sm text-muted">No projects.</p>
          ) : (
            <ul className="divide-y divide-line">
              {projects.map((p) => (
                <li key={p.id} className="flex items-center justify-between py-3 text-sm">
                  <span className="text-foreground">{p.name}</span>
                  <select
                    aria-label={`Space for ${p.name}`}
                    value={p.workspace_id ?? ""}
                    onChange={(e) => assignProject(p, e.target.value)}
                    className="rounded-md border border-line-strong bg-surface px-2 py-1 text-sm text-foreground"
                  >
                    <option value="">— No Space —</option>
                    {(spaces ?? []).map((s) => (
                      <option key={s.id} value={s.id}>
                        {personalTag(s) ? `${spaceName(s)} (${personalTag(s)})` : s.name}
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
