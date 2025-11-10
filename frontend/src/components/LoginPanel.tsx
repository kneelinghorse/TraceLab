import { useState, type FormEvent } from "react";

import { useAuth } from "@/contexts/AuthContext";

export function LoginPanel() {
  const { login } = useAuth();
  const [username, setUsername] = useState("tracelab-admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await login(username.trim(), password);
      setPassword("");
    } catch (submissionError) {
      const message = submissionError instanceof Error ? submissionError.message : "Unable to authenticate";
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))] px-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md glass-card border border-white/5 rounded-3xl p-8 space-y-6"
      >
        <div>
          <p className="text-xs uppercase tracking-[0.4em] text-slate-400">TraceLab Access</p>
          <h1 className="text-3xl text-white font-semibold mt-2">Sign in to Mission Protocol</h1>
          <p className="text-sm text-slate-300 mt-3">
            Use the credentials configured via <code>AUTH_USERNAME</code> / <code>AUTH_PASSWORD</code> to obtain a JWT. Requests will
            include the bearer token automatically once authentication succeeds.
          </p>
        </div>

        <label className="block space-y-2 text-sm text-slate-200">
          <span>Username</span>
          <input
            type="text"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            className="w-full rounded-xl bg-slate-900/40 border border-white/10 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-sky-400"
            autoComplete="username"
          />
        </label>

        <label className="block space-y-2 text-sm text-slate-200">
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="w-full rounded-xl bg-slate-900/40 border border-white/10 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-sky-400"
            autoComplete="current-password"
          />
        </label>

        {error && <p className="text-sm text-rose-300">{error}</p>}

        <button
          type="submit"
          className="w-full py-3 rounded-xl bg-sky-400 text-slate-900 font-semibold disabled:opacity-50"
          disabled={isSubmitting}
        >
          {isSubmitting ? "Signing in…" : "Sign in"}
        </button>

        <p className="text-xs text-slate-400">
          Need help? Review <code>docs/auth_and_cors_guidance.md</code> for credential storage and allowed origin details. Tokens expire
          automatically and can be refreshed without re-entering passwords.
        </p>
      </form>
    </main>
  );
}
