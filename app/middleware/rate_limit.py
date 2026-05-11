"""
In-memory rate limiter middleware.

Uses a simple sliding-window counter per IP address.
No external dependencies (Redis-free).
"""

import time
import threading
from functools import wraps
from flask import request, jsonify, current_app


class _RateLimiter:
    """Thread-safe in-memory rate limiter with automatic cleanup."""

    def __init__(self):
        self._buckets: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _cleanup_key(self, key: str, window: float):
        now = time.monotonic()
        self._buckets[key] = [
            t for t in self._buckets.get(key, []) if now - t < window
        ]

    def is_allowed(self, key: str, max_calls: int, window: float) -> bool:
        with self._lock:
            self._cleanup_key(key, window)
            hits = self._buckets.get(key, [])
            if len(hits) >= max_calls:
                return False
            self._buckets.setdefault(key, []).append(time.monotonic())
            return True

    def remaining(self, key: str, max_calls: int, window: float) -> int:
        with self._lock:
            self._cleanup_key(key, window)
            return max(0, max_calls - len(self._buckets.get(key, [])))


_limiter = _RateLimiter()


def rate_limit(max_calls: int = 5, period_seconds: int = 60):
    """Decorator that rate-limits an endpoint by client IP.

    Usage::

        @app.route("/login", methods=["POST"])
        @rate_limit(max_calls=5, period_seconds=60)
        def login():
            ...
    """

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # Skip rate limiting when disabled (e.g. during tests)
            if not current_app.config.get("RATELIMIT_ENABLED", True):
                return f(*args, **kwargs)
            ip = request.remote_addr or "unknown"
            key = f"{f.__name__}:{ip}"
            if not _limiter.is_allowed(key, max_calls, period_seconds):
                return jsonify({
                    "error": "Demasiados intentos. Intenta de nuevo más tarde.",
                }), 429
            return f(*args, **kwargs)
        return decorated
    return decorator
