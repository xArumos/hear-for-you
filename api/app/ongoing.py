"""Groups repeated detections of one ongoing sound into a single history event.

While the same sound keeps being detected with gaps under ONGOING_GAP_S, /detect returns the open event's
event_id and saves nothing new. The frontend already ignores an event_id it has seen, so it alerts once.
This is a notification-grouping choice, not an ML threshold.
"""

import threading
import time
from collections.abc import Callable

ONGOING_GAP_S = 10.0


class OngoingEvents:
    def __init__(self, gap_s: float = ONGOING_GAP_S, clock: Callable[[], float] = time.monotonic) -> None:
        self.gap_s = gap_s
        self._clock = clock
        self._lock = threading.Lock()
        self._open: dict[str, tuple[dict[str, object], float]] = {}

    def admit(
        self, key: str, confidence: float | None, save: Callable[[], dict[str, object]]
    ) -> dict[str, object]:
        """The open event for key (with this clip's confidence) if it was seen recently, else save() a new one."""
        with self._lock:
            now = self._clock()
            current = self._open.get(key)
            if current is not None and now - current[1] < self.gap_s:
                event = current[0]
                self._open[key] = (event, now)
                return {**event, "confidence": confidence}
            event = save()
            self._open[key] = (event, now)
            return event

    def reset(self) -> None:
        with self._lock:
            self._open.clear()


events = OngoingEvents()
