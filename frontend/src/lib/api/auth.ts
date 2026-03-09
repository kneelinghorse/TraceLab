import { apiRequest } from "@/lib/api/http";
import type { LoginPayload, RegisterPayload, TokenResponse } from "@/types/auth";

const AUTH_PATH = "/auth";

export async function login(payload: LoginPayload): Promise<TokenResponse> {
  return apiRequest<TokenResponse>(`${AUTH_PATH}/login`, {
    method: "POST",
    body: JSON.stringify(payload),
    skipAuth: true,
  });
}

export async function register(payload: RegisterPayload): Promise<TokenResponse> {
  return apiRequest<TokenResponse>(`${AUTH_PATH}/register`, {
    method: "POST",
    body: JSON.stringify(payload),
    skipAuth: true,
  });
}

export async function refresh(): Promise<TokenResponse> {
  return apiRequest<TokenResponse>(`${AUTH_PATH}/refresh`, {
    method: "POST",
  });
}
