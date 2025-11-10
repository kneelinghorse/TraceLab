export type StoredAuth = {
  token: string;
  username: string;
};

const STORAGE_KEY = "tracelab.auth.v1";

const canUseStorage = () => typeof window !== "undefined" && typeof window.localStorage !== "undefined";

export function getStoredAuth(): StoredAuth | null {
  if (!canUseStorage()) {
    return null;
  }
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as StoredAuth;
  } catch {
    window.localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function setStoredAuth(payload: StoredAuth): void {
  if (!canUseStorage()) {
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
}

export function clearStoredAuth(): void {
  if (!canUseStorage()) {
    return;
  }
  window.localStorage.removeItem(STORAGE_KEY);
}
