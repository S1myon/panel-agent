"""Экспоненциальный backoff с джиттером."""
from __future__ import annotations

import asyncio
import random


class Backoff:
    def __init__(self, base: float = 1.0, cap: float = 30.0, jitter: float = 0.3):
        self.base = base
        self.cap = cap
        self.jitter = jitter
        self._attempt = 0

    def reset(self) -> None:
        self._attempt = 0

    def next_delay(self) -> float:
        delay = min(self.cap, self.base * (2 ** self._attempt))
        self._attempt += 1
        j = delay * self.jitter
        return delay + random.uniform(-j, j)

    async def sleep(self) -> None:
        await asyncio.sleep(self.next_delay())