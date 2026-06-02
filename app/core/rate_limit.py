"""In-memory sliding-window rate limiter for auth endpoints.

Tracks request counts per IP with a configurable window and limit.
No external dependency required — uses a simple dict + TTL pruning.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from threading import Lock

from fastapi import HTTPException, Request, status

from app.core.config import settings

logger = logging.getLogger(__name__)

# Observed X-Forwarded-For hop counts already logged, so the self-observation
# below emits once per distinct count instead of on every request. This lets prod
# logs confirm the real trusted-hop count N without any manual measurement.
_seen_xff_hop_counts: set[int] = set()


@dataclass
class RateLimitConfig:
    """Configuration for a rate limit rule."""

    max_requests: int = 5
    window_seconds: int = 60


def client_ip(request: Request) -> str:
    """Extract the client IP for rate-limit keying + the auth audit log (T47.5),
    honoring a TRUSTED proxy's X-Forwarded-For.

    RL-1 fix (T48.5): key on the Nth-from-the-RIGHT XFF entry, where
    N = ``settings.rate_limit_trusted_proxy_hops`` is the number of trusted proxies
    that prepend to XFF. The right-most entries are the ones our trusted edge
    appended and cannot be forged by the caller; the LEFT-most entries ARE
    client-controllable (the old, spoofable behavior that let a caller rotate the
    header to evade the /login limiter). The prod backend is Railway-edge-direct
    (`server: railway-edge`, no Cloudflare proxy / `cf-ray`), a single hop ⇒ N=1.

    FAIL-SAFE: if the header is absent or has fewer than N entries, fall back to the
    socket peer (``request.client.host``) — never an IndexError, never a wrong-slot
    read. A too-high N therefore degrades to per-edge-IP keying in the pathological
    case rather than locking everyone out of login; bump the setting if prod logs
    (below) ever show a hop count > 1.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        entries = [part.strip() for part in forwarded.split(",") if part.strip()]
        hops = len(entries)
        if hops and hops not in _seen_xff_hop_counts:
            _seen_xff_hop_counts.add(hops)
            logger.info(
                "Observed X-Forwarded-For hop count=%d (rate_limit_trusted_proxy_hops=%d)",
                hops,
                settings.rate_limit_trusted_proxy_hops,
            )
        n = settings.rate_limit_trusted_proxy_hops
        if n >= 1 and hops >= n:
            return entries[-n]
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
