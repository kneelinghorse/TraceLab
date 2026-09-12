/**
 * Admin → Users management (T48.2).
 *
 * Drives the already-complete /api/v1/admin/users API: list, create-at-role,
 * change-role, enable/disable, and hard-delete. Owner-gating is UX only — only
 * an owner sees the "owner" option (the server also 403s an admin granting
 * owner, and 409s removing the last owner). Lives behind RequireAdmin (which is
 * itself UX; the API enforces require_admin server-side).
 */

import { useForm } from "react-hook-form";
import { useCallback, useEffect, useRef, useState } from "react";

import { AuthGate } from "@/components/AuthGate";
import { RequireAdmin } from "@/components/RequireAdmin";
import { useAuth } from "@/contexts/AuthContext";
import { useRole } from "@/contexts/RoleContext";
import { adminUsersApi } from "@/lib/api/admin";
import type { AdminUser, CreateUserPayload } from "@/lib/api/admin";
import { apiErrorMessage } from "@/lib/api/errors";
import type { Role } from "@/types/auth";

const ROLE_ORDER: Role[] = ["viewer", "member", "admin", "owner", "service"];

/**
 * Roles the caller may pick. "owner" is owner-gated (only an owner can grant it),
 * but it is still shown when it is the row's CURRENT role so the select reflects
 * reality for an admin viewing an owner.
 */
function roleOptions(currentRole: Role | null, isOwnerCaller: boolean): Role[] {
  return ROLE_ORDER.filter((r) => r !== "owner" || isOwnerCaller || currentRole === "owner");
}

function StatusBadge({ active }: { active: boolean }) {
  const classes = active
    ? "bg-success-surface text-success dark:bg-success-surface dark:text-success"
    : "bg-surface-alt text-secondary dark:bg-surface-alt dark:text-secondary";
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${classes}`}>
      {active ? "Active" : "Disabled"}
    </span>
  );
}

export function UsersAdmin() {
  const { role: callerRole } = useRole();
  const { user: self } = useAuth();
  const isOwnerCaller = callerRole === "owner";
  const selfId = self?.user_id ?? null;

  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<AdminUser | null>(null);
  const cancelDeleteRef = useRef<HTMLButtonElement>(null);

  // Move focus into the destructive-action dialog when it opens (a11y).
  useEffect(() => {
    if (pendingDelete) {
      cancelDeleteRef.current?.focus();
    }
  }, [pendingDelete]);

  const reload = useCallback(async () => {
    setLoadError(null);
    try {
      setUsers(await adminUsersApi.list());
    } catch (err) {
      setUsers([]);
      setLoadError(apiErrorMessage(err, "Failed to load users."));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const changeRole = async (target: AdminUser, role: Role) => {
    if (role === target.role) {
      return;
    }
    setActionError(null);
    setBusyId(target.id);
    try {
      await adminUsersApi.setRole(target.id, role);
      await reload();
    } catch (err) {
      setActionError(apiErrorMessage(err, "Failed to change role."));
    } finally {
      setBusyId(null);
    }
  };

  const toggleActive = async (target: AdminUser) => {
    setActionError(null);
    setBusyId(target.id);
    try {
      await adminUsersApi.setActive(target.id, !target.is_active);
      await reload();
    } catch (err) {
      setActionError(apiErrorMessage(err, "Failed to update status."));
    } finally {
      setBusyId(null);
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) {
      return;
    }
    const target = pendingDelete;
    setActionError(null);
    setBusyId(target.id);
    try {
      await adminUsersApi.remove(target.id);
      setPendingDelete(null);
      await reload();
    } catch (err) {
      setPendingDelete(null);
      setActionError(apiErrorMessage(err, "Failed to delete user."));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="min-h-screen bg-background dark:bg-background">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        <h1 className="text-2xl font-bold text-foreground dark:text-foreground">User management</h1>

        <CreateUserForm isOwnerCaller={isOwnerCaller} onCreated={reload} />

        <section className="rounded-lg bg-surface dark:bg-surface border border-line dark:border-line p-6">
          <h2 className="text-lg font-semibold text-foreground dark:text-foreground mb-4">Users</h2>

          {actionError && (
            <p className="mb-4 rounded-lg bg-danger-surface dark:bg-danger-surface border border-danger-line dark:border-danger-line px-4 py-3 text-sm text-danger dark:text-danger">
              {actionError}
            </p>
          )}
          {loadError && (
            <p className="rounded-lg bg-danger-surface dark:bg-danger-surface border border-danger-line dark:border-danger-line px-4 py-3 text-sm text-danger dark:text-danger">
              {loadError}
            </p>
          )}

          {loadError ? null : users === null ? (
            <p className="text-sm text-muted dark:text-muted">Loading users…</p>
          ) : users.length === 0 ? (
            <p className="text-sm text-muted dark:text-muted">No users.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-muted dark:text-muted border-b border-line dark:border-line">
                    <th className="py-2 pr-4 font-medium">Email</th>
                    <th className="py-2 pr-4 font-medium">Name</th>
                    <th className="py-2 pr-4 font-medium">Role</th>
                    <th className="py-2 pr-4 font-medium">Status</th>
                    <th className="py-2 pr-4 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => {
                    const isSelf = u.id === selfId;
                    const rowBusy = busyId === u.id;
                    return (
                      <tr key={u.id} className="border-b border-line dark:border-line">
                        <td className="py-3 pr-4 text-foreground dark:text-foreground">
                          {u.email}
                          {isSelf && <span className="ml-2 text-xs text-muted">(you)</span>}
                        </td>
                        <td className="py-3 pr-4 text-secondary dark:text-secondary">{u.display_name}</td>
                        <td className="py-3 pr-4">
                          <select
                            aria-label={`Role for ${u.email}`}
                            value={u.role}
                            disabled={rowBusy}
                            onChange={(e) => changeRole(u, e.target.value as Role)}
                            className="rounded-md border border-line-strong dark:border-line-strong bg-surface dark:bg-surface-alt px-2 py-1 text-sm text-foreground dark:text-foreground disabled:opacity-50"
                          >
                            {roleOptions(u.role, isOwnerCaller).map((r) => (
                              <option key={r} value={r}>
                                {r}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="py-3 pr-4">
                          <StatusBadge active={u.is_active} />
                        </td>
                        <td className="py-3 pr-4">
                          <div className="flex items-center gap-3">
                            <button
                              type="button"
                              onClick={() => toggleActive(u)}
                              disabled={rowBusy}
                              className="text-secondary dark:text-secondary hover:text-foreground dark:hover:text-foreground disabled:opacity-40"
                            >
                              {u.is_active ? "Disable" : "Enable"}
                            </button>
                            <button
                              type="button"
                              onClick={() => setPendingDelete(u)}
                              disabled={rowBusy || isSelf}
                              title={isSelf ? "You cannot delete your own account" : undefined}
                              className="text-danger hover:text-danger disabled:opacity-40"
                            >
                              Delete
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      {pendingDelete && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-dialog-title"
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setPendingDelete(null);
            }
          }}
          className="fixed inset-0 z-30 grid place-items-center bg-backdrop/50 px-4"
        >
          <div className="max-w-md w-full rounded-lg bg-surface dark:bg-surface border border-line dark:border-line p-6">
            <h2 id="delete-dialog-title" className="text-lg font-semibold text-foreground dark:text-foreground">
              Delete {pendingDelete.email}?
            </h2>
            <p className="mt-2 text-sm text-secondary dark:text-secondary">
              This permanently deletes the account along with its API keys and invite codes. Any
              projects, collections, documents, missions, and reports they own are kept, but their
              owner is cleared (set to no owner). This cannot be undone.
            </p>
            <div className="mt-5 flex justify-end gap-3">
              <button
                ref={cancelDeleteRef}
                type="button"
                onClick={() => setPendingDelete(null)}
                className="px-4 py-2 text-sm font-medium text-secondary dark:text-secondary hover:text-foreground dark:hover:text-foreground"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDelete}
                disabled={busyId === pendingDelete.id}
                className="px-4 py-2 text-sm font-medium bg-danger-surface text-danger rounded-lg hover:bg-danger-surface disabled:opacity-50"
              >
                Delete user
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CreateUserForm({
  isOwnerCaller,
  onCreated,
}: {
  isOwnerCaller: boolean;
  onCreated: () => Promise<void>;
}) {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<CreateUserPayload>({
    defaultValues: { email: "", password: "", display_name: "", role: "member" },
  });
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);

  const onSubmit = handleSubmit(async (values) => {
    setCreateError(null);
    setCreateSuccess(null);
    try {
      const created = await adminUsersApi.create(values);
      setCreateSuccess(`Created ${created.email} as ${created.role}.`);
      reset({ email: "", password: "", display_name: "", role: "member" });
      await onCreated();
    } catch (err) {
      setCreateError(apiErrorMessage(err, "Failed to create user."));
    }
  });

  return (
    <section className="rounded-lg bg-surface dark:bg-surface border border-line dark:border-line p-6">
      <h2 className="text-lg font-semibold text-foreground dark:text-foreground mb-4">Create user</h2>

      {createError && (
        <p className="mb-4 rounded-lg bg-danger-surface dark:bg-danger-surface border border-danger-line dark:border-danger-line px-4 py-3 text-sm text-danger dark:text-danger">
          {createError}
        </p>
      )}
      {createSuccess && (
        <p className="mb-4 rounded-lg bg-success-surface dark:bg-success-surface border border-success-line dark:border-success-line px-4 py-3 text-sm text-success dark:text-success">
          {createSuccess}
        </p>
      )}

      <form onSubmit={onSubmit} className="grid grid-cols-1 sm:grid-cols-2 gap-4" noValidate>
        <div>
          <label className="form-label" htmlFor="new-user-email">
            Email
          </label>
          <input
            id="new-user-email"
            type="email"
            className="form-input"
            {...register("email", {
              required: "Email is required",
              validate: (v) =>
                (v.includes("@") && (v.split("@").pop() ?? "").includes(".")) ||
                "Enter a valid email address",
            })}
          />
          {errors.email && <p className="form-error">{errors.email.message}</p>}
        </div>

        <div>
          <label className="form-label" htmlFor="new-user-name">
            Display name
          </label>
          <input
            id="new-user-name"
            type="text"
            className="form-input"
            {...register("display_name", {
              required: "Display name is required",
              validate: (v) => v.trim().length > 0 || "Display name cannot be blank",
              maxLength: { value: 100, message: "Display name must be 100 characters or fewer" },
            })}
          />
          {errors.display_name && <p className="form-error">{errors.display_name.message}</p>}
        </div>

        <div>
          <label className="form-label" htmlFor="new-user-password">
            Temporary password
          </label>
          <input
            id="new-user-password"
            type="password"
            className="form-input"
            {...register("password", {
              required: "Password is required",
              minLength: { value: 8, message: "Password must be at least 8 characters" },
            })}
          />
          {errors.password && <p className="form-error">{errors.password.message}</p>}
        </div>

        <div>
          <label className="form-label" htmlFor="new-user-role">
            Role
          </label>
          <select id="new-user-role" className="form-input" aria-label="New user role" {...register("role")}>
            {roleOptions(null, isOwnerCaller).map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>

        <div className="sm:col-span-2">
          <button
            type="submit"
            disabled={isSubmitting}
            className="px-4 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent disabled:opacity-50 text-sm font-medium"
          >
            {isSubmitting ? "Creating…" : "Create user"}
          </button>
        </div>
      </form>
    </section>
  );
}

export default function AdminUsersPage() {
  return (
    <AuthGate>
      <RequireAdmin>
        <UsersAdmin />
      </RequireAdmin>
    </AuthGate>
  );
}
