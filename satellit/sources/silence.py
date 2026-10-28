"""Stille- bzw. Rauschquelle.

Dient als Platzhalter (z. B. „Schlummern“/„zwischen den Sendern“) und als
sicherer Fallback, wenn eine echte Quelle nicht startet. Immer sofort bereit.
"""

from __future__ import annotations

import time

import numpy as np

from ..audio import BLOCK, CHANNELS, DTYPE, SAMPLE_RATE
from .base import Source


class SilenceSource(Source):
    kind = "silence"

    def __init__(self, name: str = "—", noise: float = 0.0):
        super().__init__(name=name, prebuffer_seconds=0.1)
        self.noise = noise
        self._rng = np.random.default_rng()

    def run(self) -> None:
        self.status = "playing"
        self.was_ready = True
        period = BLOCK / SAMPLE_RATE
        while not self._stop.is_set():
            if self.noise > 0:
                block = (self._rng.standard_normal((BLOCK, CHANNELS)) * self.noise
                         ).astype(DTYPE)
            else:
                block = np.zeros((BLOCK, CHANNELS), dtype=DTYPE)
            self._emit(block)
            time.sleep(period * 0.5)   # etwas schneller als Echtzeit, Puffer füllt

    @property
    def ready(self) -> bool:
        return True
