import Head from "next/head";
import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { useAuth } from "@/contexts/AuthContext";
import { confirmPasswordReset, requestPasswordReset } from "@/lib/api/auth";
import { HttpError } from "@/lib/api/http";
import { takeRecoveryToken } from "@/lib/auth/recovery";

const inputStyle = "w-full rounded-xl bg-background border border-line px-4 py-3 focus:outline-none focus:ring-2 focus:ring-focus";

function errorMessage(error: unknown, resetting: boolean): string {
  if (error instanceof HttpError) {
    if (error.status === 429) return "Too many attempts. Wait a minute, then try again.";
    if (error.status === 503) return "Password recovery is temporarily unavailable. Please try again later.";
    if (error.status === 400 && resetting) return "This link is invalid, expired, or already used. Request a new link below.";
    if (error.status === 422) return "Check that your passwords match and contain at least 8 characters (at most 72 bytes).";
  }
  return "We couldn't connect. Check your connection and try again.";
}

export function PasswordRecovery({ resetting = false }: { resetting?: boolean }) {
  const { logout } = useAuth();
  const [token, setToken] = useState<string | null>(() => typeof window === "undefined" ? null : window.__traceLabRecoveryToken ?? null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    // Read in the initializer without consuming it: React Strict Mode may call
    // initializers twice. The effect removes the bootstrap slot after mount.
    if (resetting) takeRecoveryToken();
  }, [resetting]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    setError(null);
    if (resetting && (password.length < 8 || new TextEncoder().encode(password).length > 72 || password !== confirmation)) {
      setError("Use at least 8 characters (at most 72 bytes) and enter the same password twice.");
      return;
    }
    setPending(true);
    try {
      const result = resetting
        ? await confirmPasswordReset(token!, password, confirmation)
        : await requestPasswordReset(email.trim());
      setMessage(result.message);
      if (resetting) {
        setPassword(""); setConfirmation(""); setToken(null);
        logout();
      }
    } catch (failure) {
      setError(errorMessage(failure, resetting));
    } finally {
      setPending(false);
    }
  }

  return <section aria-labelledby="recovery-title" className="w-full max-w-md panel border border-line rounded-3xl p-6 sm:p-8 space-y-6">
    <Head><title>{resetting ? "Reset password" : "Forgot password"} · TraceLab</title><meta name="referrer" content="no-referrer" /><meta name="robots" content="noindex, nofollow" /></Head>
    <div><p className="text-xs uppercase tracking-[0.4em] text-muted">TraceLab</p><h1 id="recovery-title" className="text-3xl text-foreground font-semibold mt-2">{resetting ? "Choose a new password" : "Forgot password?"}</h1></div>
    {message ? <div role="status" className="space-y-4 text-secondary"><p>{message}</p>{!resetting && <><p>Only the newest link works. Links expire after 30 minutes. If no email arrives, wait a minute before trying again.</p><button type="button" className="text-accent-text underline" onClick={() => setMessage(null)}>Try another request</button></>}</div>
      : resetting && !token ? <p role="alert" className="text-secondary">This link is missing or no longer available in this tab. Reopen your email link or request a new one.</p>
      : <form onSubmit={submit} className="space-y-5">
        {resetting ? <>
          <p className="text-secondary text-sm">This changes the account that received the email. You’ll be signed out of its existing sessions, and its API and MCP keys will stop working. Reconnect your integrations after signing in.</p>
          <label className="block space-y-2 text-sm text-secondary"><span>New password</span><input className={inputStyle} type="password" autoComplete="new-password" required minLength={8} maxLength={72} value={password} onChange={event => setPassword(event.target.value)} /></label>
          <label className="block space-y-2 text-sm text-secondary"><span>Confirm new password</span><input className={inputStyle} type="password" autoComplete="new-password" required minLength={8} maxLength={72} value={confirmation} onChange={event => setConfirmation(event.target.value)} /></label>
        </> : <>
          <p className="text-secondary text-sm">Enter your account’s email address. If it can receive recovery email, we’ll send a link to choose a new password.</p>
          <label className="block space-y-2 text-sm text-secondary"><span>Email</span><input className={inputStyle} type="email" autoComplete="email" required maxLength={255} value={email} onChange={event => setEmail(event.target.value)} /></label>
        </>}
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
        <button type="submit" disabled={pending} className="w-full py-3 rounded-xl bg-accent text-on-accent font-semibold disabled:opacity-50">{pending ? "Please wait…" : resetting ? "Save new password" : "Send reset link"}</button>
      </form>}
    <div className="flex flex-wrap gap-4 text-sm text-accent-text">{resetting && !message && <Link className="underline" href="/forgot-password">Request a new link</Link>}<Link className="underline" href="/">Back to sign in</Link></div>
  </section>;
}
