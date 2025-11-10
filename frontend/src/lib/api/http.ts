import { clearStoredAuth, getStoredAuth } from "@/lib/auth/storage";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type ApiRequestOptions = RequestInit & {
  skipAuth?: boolean;
};

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { skipAuth = false, headers, ...rest } = options;
  const resolvedHeaders: HeadersInit = {
    "Content-Type": "application/json",
    ...(headers ?? {}),
  };

  if (!skipAuth) {
    const auth = getStoredAuth();
    if (auth?.token) {
      resolvedHeaders.Authorization = `Bearer ${auth.token}`;
    }
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers: resolvedHeaders,
  });

  if (response.status === 401 && !skipAuth) {
    clearStoredAuth();
    const detail = await response.text();
    throw new Error(detail || "Unauthorized – please sign in again.");
  }

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request to ${path} failed with status ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
