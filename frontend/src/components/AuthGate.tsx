import { PageState } from "@/components/ui/PageState";
import { useState } from "react";
import type { ReactNode } from "react";

import { useAuth } from "@/contexts/AuthContext";
import { LoginPanel } from "@/components/LoginPanel";
import { RegisterPanel } from "@/components/RegisterPanel";

type AuthGateProps = {
  children: ReactNode;
};

export function AuthGate({ children }: AuthGateProps) {
  const { isReady, isAuthenticated } = useAuth();
  const [view, setView] = useState<"login" | "register">("login");

  if (!isReady) {
    return (
      <PageState state="loading" title="Verifying session…" />
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="flex w-full items-center justify-center">
        {view === "login" ? (
          <LoginPanel onSwitchToRegister={() => setView("register")} />
        ) : (
          <RegisterPanel onSwitchToLogin={() => setView("login")} />
        )}
      </div>
    );
  }

  return <>{children}</>;
}
