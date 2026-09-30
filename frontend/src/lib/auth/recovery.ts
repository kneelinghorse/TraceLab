/** Runs before Next bootstraps, so the fragment never enters router history or telemetry. */
export const recoveryBootstrapScript = `(function(){if(location.pathname==='/reset-password'){var t=new URLSearchParams(location.hash.slice(1)).get('token');if(t&&/^[A-Za-z0-9_-]{43}$/.test(t))window.__traceLabRecoveryToken=t;history.replaceState(history.state,'',location.pathname);}})();`;

declare global {
  interface Window { __traceLabRecoveryToken?: string }
}

export function takeRecoveryToken(): string | null {
  const token = window.__traceLabRecoveryToken ?? null;
  delete window.__traceLabRecoveryToken;
  return token;
}
