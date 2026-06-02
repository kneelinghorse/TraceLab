"""In-memory sliding-window rate limiter for auth endpoints.

Tracks request counts per IP with a configurable window and limit.
No external dependency required — uses a simple dict + TTL pruning.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from threading import Lock

from fastapi import HTTPException, Request, status


@dataclass
class RateLimitConfig:
    """Configuration for a rate limit rule."""

    max_requests: int = 5
    window_seconds: int = 60


def client_ip(request: Request) -> str:
    """Extract the client IP, honoring X-Forwarded-For from a trusted proxy.

    Shared by the rate limiter (keying) and the auth audit log (T47.5), so both
    attribute a request to the same IP and cannot diverge.

    KNOWN GAP (RL-1, T47.5 review — OPEN): this takes the LEFT-most XFF hop, which is
    client-controllable, so the per-IP login limiter can be evaded by rotating the
    header. The prod backend (api.tracelab.aquex.ai) is fronted by Railway's edge ONLY
    (Cloudflare is DNS-only — verified: `server: railway-edge`, no `cf-ray`), so the
    secure fix is to key on the hop Railway appends (the right-most for a single edge).
    NOT applied yet: keying on the wrong hop count would collapse all clients to one
    Railway-internal IP and lock out ALL logins. Confirm Railway's real XFF hop count
    first (e.g. log the raw XFF on one prod login), then switch to the right-most-of-N
    hop behind a `rate_limit_trusted_proxy_hops` setting.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """Sliding-window rate limiter keyed by client IP."""

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self.config = config or RateLimitConfig()
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP, respecting X-Forwarded-For from trusted proxies."""
        return client_ip(request)

    def _prune(self, key: str, now: float) -> None:
        """Remove timestamps outside the current window, and drop the key entirely
        when it empties so idle IPs don't accumulate forever (bounded memory now that
        this is wired to a public, unauthenticated endpoint — T47.5 review)."""
        cutoff = now - self.config.window_seconds
        fresh = [ts for ts in self._requests.get(key, []) if ts > cutoff]
        if fresh:
            self._requests[key] = fresh
        else:
            self._requests.pop(key, None)

    def check(self, request: Request) -> None:
        """Check rate limit for the request. Raises HTTP 429 if exceeded."""
        ip = self._get_client_ip(request)
        now = time.monotonic()

        with self._lock:
            self._prune(ip, now)
            if len(self._requests[ip]) >= self.config.max_requests:
                retry_after = int(self.config.window_seconds)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )
            self._requests[ip].append(now)

    def reset(self) -> None:
        """Clear all tracked requests (useful for testing)."""
        with self._lock:
            self._requests.clear()


# Shared instance for auth endpoints (5 requests per 60 seconds per IP)
auth_rate_limiter = RateLimiter(RateLimitConfig(max_requests=5, window_seconds=60))


__all__ = [
    "RateLimitConfig",
    "RateLimiter",
    "auth_rate_limiter",
    "client_ip",
]
