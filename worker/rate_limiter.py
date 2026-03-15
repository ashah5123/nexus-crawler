from __future__ import annotations

import asyncio
import time


class DomainRateLimiter:
    def __init__(self, default_delay: float = 1.0):
        self.delays: dict[str, float] = {}
        self.last_request: dict[str, float] = {}
        self.default_delay = default_delay
        self._lock = asyncio.Lock()

    async def wait(self, domain: str) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = self.delays.get(domain, self.default_delay)
            last = self.last_request.get(domain, 0.0)
            sleep_time = max(0.0, delay - (now - last))

        if sleep_time > 0:
            await asyncio.sleep(sleep_time)

        async with self._lock:
            self.last_request[domain] = time.monotonic()

    def set_delay(self, domain: str, delay: float) -> None:
        self.delays[domain] = delay

    def get_stats(self) -> dict:
        return dict(self.last_request)

