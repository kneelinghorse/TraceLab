import { clearStoredAuth, getStoredAuth } from "@/lib/auth/storage";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type ApiRequestOptions = RequestInit & {
  skipAuth?: boolean;
};

type RequestParams = Record<string, string | number | boolean | undefined>;

const buildUrl = (path: string, params?: RequestParams): string => {
  if (!params || Object.keys(params).length === 0) {
    return path;
  }
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null) {
      return;
    }
    searchParams.append(key, String(value));
  });
  const query = searchParams.toString();
  return query ? `${path}?${query}` : path;
};

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { skipAuth = false, headers, ...rest } = options;
  const resolvedHeaders = new Headers(headers ?? undefined);
  resolvedHeaders.set("Content-Type", "application/json");

  if (!skipAuth) {
    const auth = getStoredAuth();
    if (auth?.token) {
      resolvedHeaders.set("Authorization", `Bearer ${auth.token}`);
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

type HttpClientRequestConfig = {
  params?: RequestParams;
  skipAuth?: boolean;
  headers?: HeadersInit;
};

export const httpClient = {
  get<T>(path: string, config: HttpClientRequestConfig = {}): Promise<T> {
    const url = buildUrl(path, config.params);
    return apiRequest<T>(url, { method: "GET", skipAuth: config.skipAuth, headers: config.headers });
  },

  post<T>(path: string, body?: unknown, config: HttpClientRequestConfig = {}): Promise<T> {
    const url = buildUrl(path, config.params);
    return apiRequest<T>(url, {
      method: "POST",
      body: body !== undefined ? JSON.stringify(body) : undefined,
      skipAuth: config.skipAuth,
      headers: config.headers,
    });
  },

  put<T>(path: string, body?: unknown, config: HttpClientRequestConfig = {}): Promise<T> {
    const url = buildUrl(path, config.params);
    return apiRequest<T>(url, {
      method: "PUT",
      body: body !== undefined ? JSON.stringify(body) : undefined,
      skipAuth: config.skipAuth,
      headers: config.headers,
    });
  },

  delete<T>(path: string, config: HttpClientRequestConfig = {}): Promise<T> {
    const url = buildUrl(path, config.params);
    return apiRequest<T>(url, { method: "DELETE", skipAuth: config.skipAuth, headers: config.headers });
  },
};
