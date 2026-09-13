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
  const router = useRouter();
  const incoming = router.query.code;
  const value = Array.isArray(incoming) ? incoming[0] : incoming;
  const initialCode = router.isReady && typeof value === "string" && value.length >= 4 ? formatUserCode(value) : "";
  return (
    <AuthGate>
      <DeviceApproval key={initialCode} initialCode={initialCode} />
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

function DeviceApproval({ initialCode }: { initialCode: string }) {
  const [code, setCode] = useState(initialCode);
  const [labelOverride, setLabelOverride] = useState<string>("");
  const [outcome, setOutcome] = useState<Outcome>({ kind: initialCode ? "loading" : "idle" });

  // Only the read preview runs automatically; approval always requires a click.
  useEffect(() => {
    if (!initialCode) return;
    let active = true;
    previewDeviceGrant(initialCode).then(grant => {
      if (active) setOutcome({ kind: "preview", grant });
    }).catch(err => {
      if (active) setOutcome({ kind: "error", message: err instanceof Error ? err.message : "Could not look up that code." });
    });
    return () => { active = false; };
  }, [initialCode]);

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
    <div className="min-h-[calc(100vh-64px)] flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-lg rounded-2xl border border-line bg-background p-8 shadow-xl text-secondary">
        <p className="text-xs uppercase tracking-[0.4em] text-muted">Device login</p>
        <h1 className="mt-1 text-2xl font-semibold text-foreground">Approve TraceLab MCP</h1>
        <p className="mt-2 text-sm text-muted">
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
                Issued API key <span className="font-mono text-success">{outcome.label}</span>.
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
    </div>
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
      <label className="block text-sm font-medium text-secondary" htmlFor="device-code">
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
        className="w-full rounded-lg border border-line bg-background px-4 py-3 font-mono text-lg tracking-widest text-foreground placeholder:text-secondary focus:border-info-line focus:outline-none"
        disabled={disabled}
      />
      <button
        type="submit"
        disabled={disabled}
        className="w-full rounded-lg bg-accent px-4 py-3 text-sm font-semibold text-on-accent shadow hover:bg-accent disabled:opacity-60"
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
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 15000); return () => clearInterval(timer); }, []);
  const expiresAt = new Date(grant.expires_at);
  const minutesLeft = Math.max(0, Math.round((expiresAt.getTime() - now) / 60_000));

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
      <dl className="rounded-lg border border-line bg-background p-4 text-sm">
        <Row label="Code">
          <span className="font-mono tracking-widest text-foreground">{grant.user_code}</span>
        </Row>
        <Row label="Client">
          <span className="font-mono text-secondary">{grant.client_label}</span>
        </Row>
        <Row label="Expires in">
          <span className="text-secondary">~{minutesLeft} min</span>
        </Row>
      </dl>

      <div>
        <label className="block text-sm font-medium text-secondary" htmlFor="device-label">
          Key label <span className="text-muted font-normal">(optional)</span>
        </label>
        <input
          id="device-label"
          type="text"
          value={labelOverride}
          onChange={(e) => setLabelOverride(e.target.value)}
          placeholder={grant.client_label}
          className="mt-1 w-full rounded-lg border border-line bg-background px-3 py-2 text-sm text-foreground placeholder:text-secondary focus:border-info-line focus:outline-none"
        />
        <p className="mt-1 text-xs text-muted">
          Defaults to the client name. Override if you want to label this key
          (e.g. &quot;Work laptop&quot;, &quot;CI runner&quot;).
        </p>
      </div>

      <div className="flex gap-3">
        <button
          type="button"
          onClick={onApprove}
          className="flex-1 rounded-lg bg-success px-4 py-2.5 text-sm font-semibold text-on-accent shadow hover:bg-success-surface"
        >
          Approve
        </button>
        <button
          type="button"
          onClick={onDeny}
          className="flex-1 rounded-lg border border-line px-4 py-2.5 text-sm font-semibold text-foreground hover:border-danger-line hover:text-danger"
        >
          Deny
        </button>
      </div>

      <button
        type="button"
        onClick={onChangeCode}
        className="text-xs text-muted hover:text-secondary"
      >
        ← Use a different code
      </button>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between py-1.5 first:pt-0 last:pb-0 border-b border-line last:border-b-0">
      <dt className="text-xs uppercase tracking-wider text-muted">{label}</dt>
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
    success: "border-success-line bg-success-surface text-success",
    warning: "border-warning-line bg-warning-surface text-warning",
    error: "border-danger-line bg-danger-surface text-danger",
  }[tone];

  return (
    <div className={`mt-6 rounded-lg border p-4 ${accent}`}>
      <p className="text-sm font-semibold">{heading}</p>
      <p className="mt-1 text-sm opacity-90">{body}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded border border-line px-3 py-1 text-xs hover:bg-surface"
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
