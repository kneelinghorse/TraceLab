import { useState } from "react";
import type { ReactNode } from "react";

import { useAuth } from "@/contexts/AuthContext";
import { LoginPanel } from "@/components/LoginPanel";
import { RegisterPanel } from "@/components/RegisterPanel";

type AuthGateProps = {
  children: ReactNode;
};

export function AuthGate({ children }: AuthGateProps) {
  const { isReady, isAuthenticated, user, logout } = useAuth();
  const [view, setView] = useState<"login" | "register">("login");

  if (!isReady) {
    return (
      <main className="min-h-screen grid place-items-center bg-[hsl(var(--background))] text-slate-300">
        Verifying session…
      </main>
    );
  }

  if (!isAuthenticated) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))] px-4">
        {view === "login" ? (
          <LoginPanel onSwitchToRegister={() => setView("register")} />
        ) : (
          <RegisterPanel onSwitchToLogin={() => setView("login")} />
        )}
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-[hsl(var(--background))]">
      <header className="sticky top-0 z-20 flex items-center justify-between px-6 py-3 text-sm text-slate-200 bg-slate-950/70 border-b border-white/10">
        <div>
          <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Authenticated</p>
          <p className="text-white/90">
            Signed in as <span className="font-semibold text-white">{user?.display_name || user?.email}</span>
          </p>
        </div>
        <button
          onClick={logout}
          className="px-4 py-2 text-sm font-semibold rounded-full border border-white/20 text-white hover:border-sky-400"
        >
          Sign out
        </button>
      </header>
      {children}
    </div>
  );
}
