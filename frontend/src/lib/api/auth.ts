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

export async function requestPasswordReset(email: string): Promise<{ message: string }> {
  return apiRequest(`${AUTH_PATH}/password-reset/request`, {
    method: "POST", body: JSON.stringify({ email }), skipAuth: true,
  });
}

export async function confirmPasswordReset(token: string, new_password: string, confirm_password: string): Promise<{ message: string }> {
  return apiRequest(`${AUTH_PATH}/password-reset/confirm`, {
    method: "POST", body: JSON.stringify({ token, new_password, confirm_password }), skipAuth: true,
  });
}
