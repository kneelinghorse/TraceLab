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
    ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300"
    : "bg-gray-200 text-gray-600 dark:bg-gray-700 dark:text-gray-300";
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
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">User management</h1>

        <CreateUserForm isOwnerCaller={isOwnerCaller} onCreated={reload} />

        <section className="rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Users</h2>

          {actionError && (
            <p className="mb-4 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-300">
              {actionError}
            </p>
          )}
          {loadError && (
            <p className="rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-300">
              {loadError}
            </p>
          )}

          {loadError ? null : users === null ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">Loading users…</p>
          ) : users.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">No users.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
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
                      <tr key={u.id} className="border-b border-gray-100 dark:border-gray-700/50">
                        <td className="py-3 pr-4 text-gray-900 dark:text-white">
                          {u.email}
                          {isSelf && <span className="ml-2 text-xs text-gray-400">(you)</span>}
                        </td>
                        <td className="py-3 pr-4 text-gray-700 dark:text-gray-300">{u.display_name}</td>
                        <td className="py-3 pr-4">
                          <select
                            aria-label={`Role for ${u.email}`}
                            value={u.role}
                            disabled={rowBusy}
                            onChange={(e) => changeRole(u, e.target.value as Role)}
                            className="rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-2 py-1 text-sm text-gray-900 dark:text-white disabled:opacity-50"
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
                              className="text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white disabled:opacity-40"
                            >
                              {u.is_active ? "Disable" : "Enable"}
                            </button>
                            <button
                              type="button"
                              onClick={() => setPendingDelete(u)}
                              disabled={rowBusy || isSelf}
                              title={isSelf ? "You cannot delete your own account" : undefined}
                              className="text-red-600 hover:text-red-700 disabled:opacity-40"
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
          className="fixed inset-0 z-30 grid place-items-center bg-black/50 px-4"
        >
          <div className="max-w-md w-full rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-6">
            <h2 id="delete-dialog-title" className="text-lg font-semibold text-gray-900 dark:text-white">
              Delete {pendingDelete.email}?
            </h2>
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
              This permanently deletes the account along with its API keys and invite codes. Any
              projects, collections, documents, missions, and reports they own are kept, but their
              owner is cleared (set to no owner). This cannot be undone.
            </p>
            <div className="mt-5 flex justify-end gap-3">
              <button
                ref={cancelDeleteRef}
                type="button"
                onClick={() => setPendingDelete(null)}
                className="px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDelete}
                disabled={busyId === pendingDelete.id}
                className="px-4 py-2 text-sm font-medium bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
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
    <section className="rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Create user</h2>

      {createError && (
        <p className="mb-4 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          {createError}
        </p>
      )}
      {createSuccess && (
        <p className="mb-4 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 px-4 py-3 text-sm text-green-700 dark:text-green-300">
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
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
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
