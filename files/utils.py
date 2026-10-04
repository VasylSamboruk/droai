from __future__ import annotations

import time


class FPSCounter:
    def __init__(self, smoothing: float = 0.2) -> None:
        self.smoothing = smoothing
        self._last_time: float | None = None
        self.value = 0.0

    def tick(self) -> float:
        now = time.perf_counter()
        if self._last_time is not None:
            instant = 1.0 / max(now - self._last_time, 1e-6)
            self.value = instant if self.value == 0 else self.value * (1 - self.smoothing) + instant * self.smoothing
        self._last_time = now
        return self.value