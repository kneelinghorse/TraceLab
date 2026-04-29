/**
 * /device — RFC 8628 device-code approval page (T42.4).
 *
 * The TraceLab MCP client prints a verification URL + short user_code to the
 * installer's terminal. The user opens this page, types or pastes the code,
 * and approves (or denies) the in-flight grant. On approval the server mints
 * an API key on the user's behalf and the polling MCP client picks it up
 * within seconds.
 *
 * The page accepts a ?code=ABCD-EFGH query-param prefill so the MCP client's
 * terminal output can deep-link directly to a populated form.
 */
import { useEffect, useState } from "react";
import { useRouter } from "next/router";

import { AuthGate } from "@/components/AuthGate";
import {
  approveDeviceGrant,
  denyDeviceGrant,
  previewDeviceGrant,
  type DeviceGrantPreview,
} from "@/lib/api/deviceAuth";

export default function DeviceApprovalPage() {
  return (
    <AuthGate>
      <DeviceApproval />
    </AuthGate>
  );
}

type Outcome =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "preview"; grant: DeviceGrantPreview }
  | { kind: "approved"; label: string }
  | { kind: "denied" }
  | { kind: "error"; message: string };

function DeviceApproval() {
  const router = useRouter();
  const [code, setCode] = useState<string>("");
  const [labelOverride, setLabelOverride] = useState<string>("");
  const [outcome, setOutcome] = useState<Outcome>({ kind: "idle" });

  // Pre-fill from ?code=ABCD-EFGH and auto-fetch the preview.
  useEffect(() => {
    if (!router.isReady) return;
    const incoming = router.query.code;
    const value = Array.isArray(incoming) ? incoming[0] : incoming;
    if (typeof value === "string" && value.length >= 4) {
      const normalized = formatUserCode(value);
      setCode(normalized);
      void loadPreview(normalized);
    }
  }, [router.isReady, router.query.code]);

  async function loadPreview(userCode: string): Promise<void> {
    setOutcome({ kind: "loading" });
    try {
      const grant = await previewDeviceGrant(userCode);
      setOutcome({ kind: "preview", grant });
    } catch (err) {
      setOutcome({
        kind: "error",
        message: err instanceof Error ? err.message : "Could not look up that code.",
      });
    }
  }

  async function handleLookup(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    const trimmed = code.trim();
    if (trimmed.length < 4) {
      setOutcome({ kind: "error", message: "Enter the code shown by your MCP client." });
      return;
    }
    await loadPreview(trimmed);
  }

  async function handleApprove(): Promise<void> {
    if (outcome.kind !== "preview") return;
    setOutcome({ kind: "loading" });
    try {
      const response = await approveDeviceGrant(
        outcome.grant.user_code,
        labelOverride.trim() || undefined
      );
      setOutcome({ kind: "approved", label: response.label });
    } catch (err) {
      setOutcome({
        kind: "error",
        message: err instanceof Error ? err.message : "Approval failed.",
      });
    }
  }

  async function handleDeny(): Promise<void> {
    if (outcome.kind !== "preview") return;
    setOutcome({ kind: "loading" });
    try {
      await denyDeviceGrant(outcome.grant.user_code);
      setOutcome({ kind: "denied" });
    } catch (err) {
      setOutcome({
        kind: "error",
        message: err instanceof Error ? err.message : "Deny failed.",
      });
    }
  }

  return (
    <main className="min-h-[calc(100vh-64px)] flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-lg rounded-2xl border border-white/10 bg-slate-900/60 p-8 shadow-xl text-slate-200">
        <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Device login</p>
        <h1 className="mt-1 text-2xl font-semibold text-white">Approve TraceLab MCP</h1>
        <p className="mt-2 text-sm text-slate-400">
          Enter the code shown by the TraceLab MCP client to issue it an API key on
          your account.
        </p>

        {outcome.kind === "idle" || outcome.kind === "loading" ? (
          <CodeEntryForm
            code={code}
            setCode={setCode}
            onSubmit={handleLookup}
            disabled={outcome.kind === "loading"}
          />
        ) : null}

        {outcome.kind === "preview" ? (
          <PreviewPanel
            grant={outcome.grant}
            labelOverride={labelOverride}
            setLabelOverride={setLabelOverride}
            onApprove={handleApprove}
            onDeny={handleDeny}
            onChangeCode={() => {
              setOutcome({ kind: "idle" });
              setCode("");
            }}
          />
        ) : null}

        {outcome.kind === "approved" ? (
          <ResultPanel
            tone="success"
            heading="Device approved"
            body={
              <>
                Issued API key <span className="font-mono text-emerald-300">{outcome.label}</span>.
                You can close this tab — the MCP client will pick it up within
                seconds.
              </>
            }
          />
        ) : null}

        {outcome.kind === "denied" ? (
          <ResultPanel
            tone="warning"
            heading="Request denied"
            body="The MCP client polling this code will receive an access_denied response and stop polling."
          />
        ) : null}

        {outcome.kind === "error" ? (
          <ResultPanel
            tone="error"
            heading="Couldn't process that code"
            body={outcome.message}
            onRetry={() => {
              setOutcome({ kind: "idle" });
              setCode("");
            }}
          />
        ) : null}
      </div>
    </main>
  );
}

interface CodeEntryFormProps {
  code: string;
  setCode: (value: string) => void;
  onSubmit: (event: React.FormEvent) => void | Promise<void>;
  disabled: boolean;
}

function CodeEntryForm({ code, setCode, onSubmit, disabled }: CodeEntryFormProps) {
  return (
    <form onSubmit={onSubmit} className="mt-6 space-y-4">
      <label className="block text-sm font-medium text-slate-300" htmlFor="device-code">
        Code
      </label>
      <input
        id="device-code"
        type="text"
        autoComplete="off"
        autoFocus
        value={code}
        onChange={(e) => setCode(formatUserCode(e.target.value))}
        placeholder="ABCD-EFGH"
        className="w-full rounded-lg border border-white/15 bg-slate-950/40 px-4 py-3 font-mono text-lg tracking-widest text-white placeholder:text-slate-600 focus:border-sky-400 focus:outline-none"
        disabled={disabled}
      />
      <button
        type="submit"
        disabled={disabled}
        className="w-full rounded-lg bg-sky-500 px-4 py-3 text-sm font-semibold text-white shadow hover:bg-sky-400 disabled:opacity-60"
      >
        {disabled ? "Looking up…" : "Continue"}
      </button>
    </form>
  );
}

interface PreviewPanelProps {
  grant: DeviceGrantPreview;
  labelOverride: string;
  setLabelOverride: (v: string) => void;
  onApprove: () => void;
  onDeny: () => void;
  onChangeCode: () => void;
}

function PreviewPanel({
  grant,
  labelOverride,
  setLabelOverride,
  onApprove,
  onDeny,
  onChangeCode,
}: PreviewPanelProps) {
  const expiresAt = new Date(grant.expires_at);
  const minutesLeft = Math.max(0, Math.round((expiresAt.getTime() - Date.now()) / 60_000));

  if (grant.status !== "pending") {
    return (
      <ResultPanel
        tone={grant.status === "approved" ? "success" : "warning"}
        heading={`Grant is ${grant.status}`}
        body={
          grant.status === "approved"
            ? "This code has already been approved on another tab. The MCP client should already have its key."
            : "This code can no longer be approved. Re-run device login on the MCP client to start over."
        }
        onRetry={onChangeCode}
      />
    );
  }

  return (
    <div className="mt-6 space-y-5">
      <dl className="rounded-lg border border-white/10 bg-slate-950/40 p-4 text-sm">
        <Row label="Code">
          <span className="font-mono tracking-widest text-white">{grant.user_code}</span>
        </Row>
        <Row label="Client">
          <span className="font-mono text-slate-200">{grant.client_label}</span>
        </Row>
        <Row label="Expires in">
          <span className="text-slate-200">~{minutesLeft} min</span>
        </Row>
      </dl>

      <div>
        <label className="block text-sm font-medium text-slate-300" htmlFor="device-label">
          Key label <span className="text-slate-500 font-normal">(optional)</span>
        </label>
        <input
          id="device-label"
          type="text"
          value={labelOverride}
          onChange={(e) => setLabelOverride(e.target.value)}
          placeholder={grant.client_label}
          className="mt-1 w-full rounded-lg border border-white/15 bg-slate-950/40 px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:border-sky-400 focus:outline-none"
        />
        <p className="mt-1 text-xs text-slate-500">
          Defaults to the client name. Override if you want to label this key
          (e.g. "Work laptop", "CI runner").
        </p>
      </div>

      <div className="flex gap-3">
        <button
          type="button"
          onClick={onApprove}
          className="flex-1 rounded-lg bg-emerald-500 px-4 py-2.5 text-sm font-semibold text-white shadow hover:bg-emerald-400"
        >
          Approve
        </button>
        <button
          type="button"
          onClick={onDeny}
          className="flex-1 rounded-lg border border-white/15 px-4 py-2.5 text-sm font-semibold text-white hover:border-rose-400 hover:text-rose-300"
        >
          Deny
        </button>
      </div>

      <button
        type="button"
        onClick={onChangeCode}
        className="text-xs text-slate-400 hover:text-slate-200"
      >
        ← Use a different code
      </button>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between py-1.5 first:pt-0 last:pb-0 border-b border-white/5 last:border-b-0">
      <dt className="text-xs uppercase tracking-wider text-slate-500">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

interface ResultPanelProps {
  tone: "success" | "warning" | "error";
  heading: string;
  body: React.ReactNode;
  onRetry?: () => void;
}

function ResultPanel({ tone, heading, body, onRetry }: ResultPanelProps) {
  const accent = {
    success: "border-emerald-400/40 bg-emerald-500/10 text-emerald-100",
    warning: "border-amber-400/40 bg-amber-500/10 text-amber-100",
    error: "border-rose-400/40 bg-rose-500/10 text-rose-100",
  }[tone];

  return (
    <div className={`mt-6 rounded-lg border p-4 ${accent}`}>
      <p className="text-sm font-semibold">{heading}</p>
      <p className="mt-1 text-sm opacity-90">{body}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded border border-white/20 px-3 py-1 text-xs hover:bg-white/10"
        >
          Try another code
        </button>
      ) : null}
    </div>
  );
}

/**
 * Normalize user input into the canonical ABCD-EFGH form.
 *
 * Strips non-alphanumeric, uppercases, drops digits + visually-confusable
 * letters that the server's charset excluded so the user can paste sloppy
 * input. Inserts the dash after the first 4 chars when ≥5 are present.
 */
function formatUserCode(raw: string): string {
  // Mirror the server-side charset (BCDFGHJKLMNPQRSTVWXZ — no vowels, no digits,
  // no visually-confusable letters). Non-charset chars from sloppy paste are
  // dropped so the user gets a clean 4-4 grouped display.
  const cleaned = raw
    .toUpperCase()
    .replace(/[^BCDFGHJKLMNPQRSTVWXZ]/g, "")
    .slice(0, 8);
  if (cleaned.length <= 4) return cleaned;
  return `${cleaned.slice(0, 4)}-${cleaned.slice(4)}`;
}
