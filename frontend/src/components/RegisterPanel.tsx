import { useState, type FormEvent } from "react";

import { useAuth } from "@/contexts/AuthContext";

interface RegisterPanelProps {
  onSwitchToLogin?: () => void;
}

export function RegisterPanel({ onSwitchToLogin }: RegisterPanelProps) {
  const { register } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);

    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }

    if (!displayName.trim()) {
      setError("Display name is required");
      return;
    }

    if (inviteCode.trim().length !== 8) {
      setError("Invite code must be 8 characters");
      return;
    }

    setIsSubmitting(true);
    try {
      await register(email.trim(), password, displayName.trim(), inviteCode.trim().toUpperCase());
      setPassword("");
    } catch (submissionError) {
      const message = submissionError instanceof Error ? submissionError.message : "Registration failed";
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
        <h1 className="text-3xl text-white font-semibold mt-2">Create account</h1>
        <p className="text-sm text-slate-300 mt-3">
          Register for access to Mission Protocol.
        </p>
      </div>

      <label className="block space-y-2 text-sm text-slate-200">
        <span>Invite code</span>
        <input
          type="text"
          value={inviteCode}
          onChange={(event) => setInviteCode(event.target.value.toUpperCase())}
          placeholder="Enter your 8-character invite code"
          required
          maxLength={8}
          className="w-full rounded-xl bg-slate-900/40 border border-white/10 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-sky-400 uppercase tracking-widest font-mono"
          autoComplete="off"
        />
      </label>

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
        <span>Display name</span>
        <input
          type="text"
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          placeholder="How you want to be identified"
          required
          className="w-full rounded-xl bg-slate-900/40 border border-white/10 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-sky-400"
          autoComplete="name"
        />
      </label>

      <label className="block space-y-2 text-sm text-slate-200">
        <span>Password</span>
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="Minimum 8 characters"
          required
          minLength={8}
          className="w-full rounded-xl bg-slate-900/40 border border-white/10 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-sky-400"
          autoComplete="new-password"
        />
      </label>

      {error && <p className="text-sm text-rose-300">{error}</p>}

      <button
        type="submit"
        className="w-full py-3 rounded-xl bg-sky-400 text-slate-900 font-semibold disabled:opacity-50"
        disabled={isSubmitting}
      >
        {isSubmitting ? "Creating account\u2026" : "Create account"}
      </button>

      {onSwitchToLogin && (
        <p className="text-center text-sm text-slate-400">
          Already have an account?{" "}
          <button
            type="button"
            onClick={onSwitchToLogin}
            className="text-sky-400 hover:text-sky-300 font-medium"
          >
            Sign in
          </button>
        </p>
      )}
    </form>
  );
}
