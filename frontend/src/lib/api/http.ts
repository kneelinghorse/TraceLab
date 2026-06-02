import { clearStoredAuth, getStoredAuth } from "@/lib/auth/storage";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/**
 * Fired on the window when an authenticated request gets a 401. AuthContext
 * listens and drives a full logout — clearing localStorage alone (below) leaves
 * a "signed in" shell whose in-memory token keeps isAuthenticated=true while
 * every call 401s (decision #315a). A window event decouples this module from
 * AuthContext (no circular import).
 */
export const AUTH_EXPIRED_EVENT = "tracelab:auth-expired";

const normalizePrefix = (value: string | undefined | null): string => {
  if (!value) {
    return "";
  }
  let prefix = value.trim();
  if (!prefix || prefix === "/") {
    return "";
  }
  if (!prefix.startsWith("/")) {
    prefix = `/${prefix}`;
  }
  return prefix.replace(/\/+$/, "");
};

export const API_PATH_PREFIX = normalizePrefix(process.env.NEXT_PUBLIC_API_PATH_PREFIX ?? "/api/v1");

type ApiRequestOptions = RequestInit & {
  skipAuth?: boolean;
  params?: RequestParams;
};

type RequestParams = Record<string, string | number | boolean | undefined>;

const normalizePath = (path: string): string => {
  if (!path) {
    return "/";
  }
  return path.startsWith("/") ? path : `/${path}`;
};

const buildSearch = (params?: RequestParams): string => {
  if (!params || Object.keys(params).length === 0) {
    return "";
  }
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null) {
      return;
    }
    searchParams.append(key, String(value));
  });
  const query = searchParams.toString();
  return query ? `?${query}` : "";
};

const applyPrefix = (pathWithQuery: string): string => {
  if (!API_PATH_PREFIX) {
    return pathWithQuery;
  }
  const [pathname, query] = pathWithQuery.split("?");
  if (pathname === API_PATH_PREFIX || pathname.startsWith(`${API_PATH_PREFIX}/`)) {
    return pathWithQuery;
  }
  const prefixed = `${API_PATH_PREFIX}${pathname}`;
  return query ? `${prefixed}?${query}` : prefixed;
};

const buildRelativePath = (path: string, params?: RequestParams): string => {
  const normalized = normalizePath(path);
  const search = buildSearch(params);
  return applyPrefix(`${normalized}${search}`);
};

export const buildApiUrl = (path: string, params?: RequestParams): string => {
  return `${API_BASE_URL}${buildRelativePath(path, params)}`;
};

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { skipAuth = false, headers, params, ...rest } = options;
  const resolvedHeaders = new Headers(headers ?? undefined);
  resolvedHeaders.set("Content-Type", "application/json");

  if (!skipAuth) {
    const auth = getStoredAuth();
    if (auth?.token) {
      resolvedHeaders.set("Authorization", `Bearer ${auth.token}`);
    }
  }

  const targetUrl = buildApiUrl(path, params);
  const response = await fetch(targetUrl, {
    ...rest,
    headers: resolvedHeaders,
  });

  if (response.status === 401 && !skipAuth) {
    clearStoredAuth();
    // Drop AuthContext's in-memory session too, else the user is left in a
    // logged-in-looking but fully broken shell (decision #315a).
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    }
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
    return apiRequest<T>(path, { method: "GET", skipAuth: config.skipAuth, headers: config.headers, params: config.params });
  },

  post<T>(path: string, body?: unknown, config: HttpClientRequestConfig = {}): Promise<T> {
    return apiRequest<T>(path, {
      method: "POST",
      body: body !== undefined ? JSON.stringify(body) : undefined,
      skipAuth: config.skipAuth,
      headers: config.headers,
      params: config.params,
    });
  },

  put<T>(path: string, body?: unknown, config: HttpClientRequestConfig = {}): Promise<T> {
    return apiRequest<T>(path, {
      method: "PUT",
      body: body !== undefined ? JSON.stringify(body) : undefined,
      skipAuth: config.skipAuth,
      headers: config.headers,
      params: config.params,
    });
  },

  patch<T>(path: string, body?: unknown, config: HttpClientRequestConfig = {}): Promise<T> {
    return apiRequest<T>(path, {
      method: "PATCH",
      body: body !== undefined ? JSON.stringify(body) : undefined,
      skipAuth: config.skipAuth,
      headers: config.headers,
      params: config.params,
    });
  },

  delete<T>(path: string, config: HttpClientRequestConfig = {}): Promise<T> {
    return apiRequest<T>(path, { method: "DELETE", skipAuth: config.skipAuth, headers: config.headers, params: config.params });
  },
};
