export type StoredAuth = {
  token: string;
  user_id: string;
  email: string;
  display_name: string;
};

const STORAGE_KEY = "tracelab.auth.v2";
const LEGACY_KEY = "tracelab.auth.v1";

const canUseStorage = () => typeof window !== "undefined" && typeof window.localStorage !== "undefined";

export function getStoredAuth(): StoredAuth | null {
  if (!canUseStorage()) {
    return null;
  }
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (raw) {
    try {
      return JSON.parse(raw) as StoredAuth;
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  }
  // Migrate legacy v1 storage
  const legacy = window.localStorage.getItem(LEGACY_KEY);
  if (legacy) {
    try {
      const parsed = JSON.parse(legacy);
      window.localStorage.removeItem(LEGACY_KEY);
      if (parsed.token) {
        const migrated: StoredAuth = {
          token: parsed.token,
          user_id: "",
          email: "",
          display_name: parsed.username || "",
        };
        setStoredAuth(migrated);
        return migrated;
      }
    } catch {
      window.localStorage.removeItem(LEGACY_KEY);
    }
  }
  return null;
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
  window.localStorage.removeItem(LEGACY_KEY);
}
