"""Server-side request cap for /api/detect, protecting the Gemini free-tier quota."""

import math
import threading
import time
from collections.abc import Callable

from app.config import settings
from app.errors import RateLimited


class RateLimiter:
    """At most one call per 1 / max_per_sec seconds, across all clients. max_per_sec <= 0 disables it."""

    def __init__(self, max_per_sec: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.min_interval = 1.0 / max_per_sec if max_per_sec > 0 else 0.0
        self._clock = clock
        self._lock = threading.Lock()
        self._last: float | None = None

    def check(self) -> None:
        """Record this call, or raise RateLimited if it comes too soon after the last allowed one."""
        if self.min_interval <= 0:
            return
        with self._lock:
            now = self._clock()
            if self._last is not None:
                elapsed = now - self._last
                if elapsed < self.min_interval:
                    # round() first so float noise (200.0000001 ms) doesn't ceil up a whole ms.
                    retry_after_ms = math.ceil(round((self.min_interval - elapsed) * 1000, 3))
                    raise RateLimited("Too many detect requests.", retry_after_ms=retry_after_ms)
            self._last = now

    def reset(self) -> None:
        with self._lock:
            self._last = None


detect_limiter = RateLimiter(settings.max_detect_per_sec)
