import { useState, type FormEvent } from "react";

import { useAuth } from "@/contexts/AuthContext";

interface LoginPanelProps {
  onSwitchToRegister?: () => void;
}

export function LoginPanel({ onSwitchToRegister }: LoginPanelProps) {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await login(email.trim(), password);
      setPassword("");
    } catch (submissionError) {
      const message = submissionError instanceof Error ? submissionError.message : "Unable to authenticate";
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="w-full max-w-md glass-card border border-white/5 rounded-3xl p-8 space-y-6"
    >
      <div>
        <p className="text-xs uppercase tracking-[0.4em] text-slate-400">TraceLab</p>
        <h1 className="text-3xl text-white font-semibold mt-2">Sign in</h1>
        <p className="text-sm text-slate-300 mt-3">
          Enter your credentials to access Mission Protocol.
        </p>
      </div>

      <label className="block space-y-2 text-sm text-slate-200">
        <span>Email</span>
        <input
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@example.com"
          required
          className="w-full rounded-xl bg-slate-900/40 border border-white/10 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-sky-400"
          autoComplete="email"
        />
      </label>

      <label className="block space-y-2 text-sm text-slate-200">
        <span>Password</span>
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="Enter your password"
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
        {isSubmitting ? "Signing in\u2026" : "Sign in"}
      </button>

      {onSwitchToRegister && (
        <p className="text-center text-sm text-slate-400">
          Don&apos;t have an account?{" "}
          <button
            type="button"
            onClick={onSwitchToRegister}
            className="text-sky-400 hover:text-sky-300 font-medium"
          >
            Create one
          </button>
        </p>
      )}
    </form>
  );
}
