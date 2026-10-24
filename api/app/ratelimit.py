"""Server-side caps for /api/detect and for describe calls, protecting the Gemini free-tier quota."""

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

    def _wait_ms(self) -> int:
        """Record this call and return 0, or return the ms until the next one is allowed."""
        if self.min_interval <= 0:
            return 0
        with self._lock:
            now = self._clock()
            if self._last is not None:
                elapsed = now - self._last
                if elapsed < self.min_interval:
                    # round() first so float noise (200.0000001 ms) doesn't ceil up a whole ms.
                    return math.ceil(round((self.min_interval - elapsed) * 1000, 3))
            self._last = now
            return 0

    def check(self) -> None:
        """Record this call, or raise RateLimited if it comes too soon after the last allowed one."""
        retry_after_ms = self._wait_ms()
        if retry_after_ms:
            raise RateLimited("Too many detect requests.", retry_after_ms=retry_after_ms)

    def allow(self) -> bool:
        """Record this call and return True, or return False if it comes too soon. Never raises."""
        return self._wait_ms() == 0

    def reset(self) -> None:
        with self._lock:
            self._last = None


detect_limiter = RateLimiter(settings.max_detect_per_sec)
describe_limiter = RateLimiter(settings.max_describe_per_sec)
