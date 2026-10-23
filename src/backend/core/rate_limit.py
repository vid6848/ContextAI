"""In-memory sliding-window rate limiting for API endpoints.

Suitable for a single-process deployment; swap for Redis-backed limiting if the app is scaled out.
"""

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request


class SlidingWindowLimiter:
    """Allows at most `limit` hits per `window` seconds for each key."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window: float) -> float | None:
        """Record a hit. Returns None if allowed, else seconds until the next hit is allowed."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= window:
                hits.popleft()
            if len(hits) >= limit:
                return window - (now - hits[0])
            hits.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def client_ip(request: Request) -> str:
    """Client address; uvicorn's --proxy-headers already resolves X-Forwarded-For behind a proxy."""
    return request.client.host if request.client else "unknown"


def rate_limit(scope: str, limit: Callable[[], int], window: float = 60.0):
    """FastAPI dependency limiting each client IP to `limit()` requests per window for this scope.

    `limit` is a callable so settings can be changed at runtime (and in tests).
    """

    def dependency(request: Request) -> None:
        retry_after = limiter.hit(f"{scope}:{client_ip(request)}", limit(), window)
        if retry_after is not None:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please slow down and try again shortly.",
                headers={"Retry-After": str(max(1, int(retry_after) + 1))},
            )

    return dependency
