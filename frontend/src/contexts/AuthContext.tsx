import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { login as loginRequest, refresh as refreshRequest } from "@/lib/api/auth";
import { clearStoredAuth, getStoredAuth, setStoredAuth } from "@/lib/auth/storage";
import type { TokenResponse, TokenUser } from "@/types/auth";

type AuthContextValue = {
  user: TokenUser | null;
  token: string | null;
  isAuthenticated: boolean;
  isReady: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<TokenResponse>;
};

type AuthState = {
  user: TokenUser | null;
  token: string | null;
  isReady: boolean;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const initialState: AuthState = {
  user: null,
  token: null,
  isReady: false,
};

const TEST_AUTH_TOKEN = process.env.NEXT_PUBLIC_E2E_AUTH_TOKEN;
const TEST_AUTH_USER = process.env.NEXT_PUBLIC_E2E_AUTH_USER ?? "mission-tester";

function persistSession(response: TokenResponse) {
  setStoredAuth({ token: response.access_token, username: response.user.username });
  return {
    token: response.access_token,
    user: response.user,
    isReady: true,
  } satisfies AuthState;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => {
    const stored = getStoredAuth();
    if (stored) {
      return { token: stored.token, user: { username: stored.username }, isReady: true } satisfies AuthState;
    }
    if (TEST_AUTH_TOKEN) {
      return { token: TEST_AUTH_TOKEN, user: { username: TEST_AUTH_USER }, isReady: true } satisfies AuthState;
    }
    return { ...initialState, isReady: true } satisfies AuthState;
  });

  const login = useCallback(async (username: string, password: string) => {
    const response = await loginRequest({ username, password });
    setState(persistSession(response));
  }, []);

  const logout = useCallback(() => {
    clearStoredAuth();
    setState({ token: null, user: null, isReady: true });
  }, []);

  const refresh = useCallback(async () => {
    const response = await refreshRequest();
    setState(persistSession(response));
    return response;
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user: state.user,
      token: state.token,
      isAuthenticated: Boolean(state.token),
      isReady: state.isReady,
      login,
      logout,
      refresh,
    }),
    [login, logout, refresh, state.token, state.user, state.isReady],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
