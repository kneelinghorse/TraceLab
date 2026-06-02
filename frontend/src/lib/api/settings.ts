/**
 * Settings API client — profile, API keys, invite codes
 */

import type { Role } from "@/types/auth";

import { httpClient } from "./http";

// --- Profile ---

export type ProfileResponse = {
  user_id: string;
  email: string;
  display_name: string;
  role: Role;
};

export type ProfileUpdatePayload = {
  display_name?: string;
  current_password?: string;
  new_password?: string;
};

export const profileApi = {
  get(): Promise<ProfileResponse> {
    return httpClient.get("/auth/me");
  },
  update(payload: ProfileUpdatePayload): Promise<ProfileResponse> {
    return httpClient.patch("/auth/me", payload);
  },
};

// --- API Keys ---

export type APIKeyInfo = {
  id: string;
  name: string;
  key_prefix: string;
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
};

export type APIKeyResponse = APIKeyInfo & {
  key: string; // full key, only present at creation
};

export type APIKeyList = {
  keys: APIKeyInfo[];
  total: number;
};

export const apiKeysApi = {
  list(): Promise<APIKeyList> {
    return httpClient.get("/auth/api-keys");
  },
  create(payload: { name: string; expires_in_days?: number }): Promise<APIKeyResponse> {
    return httpClient.post("/auth/api-keys", payload);
  },
  delete(keyId: string): Promise<void> {
    return httpClient.delete(`/auth/api-keys/${keyId}`);
  },
};

// --- Invite Codes ---

export type InviteCode = {
  id: string;
  code: string;
  status: "unused" | "used" | "expired";
  created_at: string;
  used_at: string | null;
  expires_at: string | null;
};

export type InviteCodeList = {
  codes: InviteCode[];
  total: number;
};

export const inviteCodesApi = {
  list(): Promise<InviteCodeList> {
    return httpClient.get("/auth/invite-codes");
  },
  create(): Promise<InviteCode> {
    return httpClient.post("/auth/invite-codes");
  },
  delete(codeId: string): Promise<void> {
    return httpClient.delete(`/auth/invite-codes/${codeId}`);
  },
};
