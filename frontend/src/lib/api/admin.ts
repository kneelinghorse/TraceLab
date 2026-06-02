/**
 * Admin API client — user management (T48.2) and, later, Spaces (T48.3).
 *
 * Mirrors app/api/v1/admin_users.py (mounted at /api/v1/admin/users, gated by
 * require_admin at the router level). httpClient prepends /api/v1, so paths
 * here are relative to that. The server is the real authorization boundary;
 * these calls 403 server-side if the caller is not actually admin/owner.
 */

import type { Role } from "@/types/auth";

import { httpClient } from "./http";

export type AdminUser = {
  id: string;
  email: string;
  display_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
};

export type CreateUserPayload = {
  email: string;
  password: string;
  display_name: string;
  role: Role;
};

export type DeleteUserResult = {
  success: boolean;
  id: string;
  message: string;
};

const USERS_PATH = "/admin/users";

export const adminUsersApi = {
  list(): Promise<AdminUser[]> {
    return httpClient.get(USERS_PATH);
  },
  create(payload: CreateUserPayload): Promise<AdminUser> {
    return httpClient.post(USERS_PATH, payload);
  },
  setRole(userId: string, role: Role): Promise<AdminUser> {
    return httpClient.patch(`${USERS_PATH}/${userId}/role`, { role });
  },
  setActive(userId: string, isActive: boolean): Promise<AdminUser> {
    return httpClient.patch(`${USERS_PATH}/${userId}/active`, { is_active: isActive });
  },
  remove(userId: string): Promise<DeleteUserResult> {
    return httpClient.delete(`${USERS_PATH}/${userId}`);
  },
};

// --- Spaces (T48.3) — mirrors app/api/v1/spaces.py + the project-assign route ---

export type AdminSpace = {
  id: string;
  name: string;
  created_at: string;
};

export type SpaceMember = {
  user_id: string;
  email: string;
  display_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
};

const SPACES_PATH = "/admin/spaces";

export const adminSpacesApi = {
  list(): Promise<AdminSpace[]> {
    return httpClient.get(SPACES_PATH);
  },
  create(name: string): Promise<AdminSpace> {
    return httpClient.post(SPACES_PATH, { name });
  },
  listMembers(spaceId: string): Promise<SpaceMember[]> {
    return httpClient.get(`${SPACES_PATH}/${spaceId}/members`);
  },
  // Grant role defaults to 'member' server-side; the Sprint B/C membership check
  // only cares about row presence (decision #227), so no role picker is exposed.
  addMember(spaceId: string, userId: string): Promise<unknown> {
    return httpClient.post(`${SPACES_PATH}/${spaceId}/members`, { user_id: userId });
  },
  removeMember(spaceId: string, userId: string): Promise<unknown> {
    return httpClient.delete(`${SPACES_PATH}/${spaceId}/members/${userId}`);
  },
  // The project-assignment route lives under /admin/projects, not /admin/spaces.
  // space_id null un-assigns (space-less). Server busts the project list caches.
  assignProjectSpace(projectId: string, spaceId: string | null): Promise<unknown> {
    return httpClient.patch(`/admin/projects/${projectId}/space`, { space_id: spaceId });
  },
};
