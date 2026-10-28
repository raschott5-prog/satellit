"""Audio-Grundlagen: Format-Konstanten und ein kleiner Ringpuffer.

Alles im Programm rechnet in einem einzigen Format: 48 kHz, Stereo,
float32 im Bereich [-1, 1]. Jede Quelle liefert in dieses Format,
der Mixer mischt darin, die Ausgabe wandelt erst ganz am Ende.
"""

from __future__ import annotations

import threading

import numpy as np

# --- Festes internes Format -------------------------------------------------
SAMPLE_RATE = 48_000
CHANNELS = 2
DTYPE = np.float32

#: Blockgröße, in der Engine und Ausgabe arbeiten (~21 ms bei 48 kHz).
BLOCK = 1024


def silence(frames: int = BLOCK) -> np.ndarray:
    """Ein Block Stille im internen Format."""
    return np.zeros((frames, CHANNELS), dtype=DTYPE)


def as_stereo(block: np.ndarray) -> np.ndarray:
    """Beliebiges PCM auf (frames, 2) float32 bringen."""
    arr = np.asarray(block, dtype=DTYPE)
    if arr.ndim == 1:
        arr = np.repeat(arr[:, None], CHANNELS, axis=1)
    elif arr.shape[1] == 1:
        arr = np.repeat(arr, CHANNELS, axis=1)
    elif arr.shape[1] > CHANNELS:
        arr = arr[:, :CHANNELS]
    return arr


def rms(block: np.ndarray) -> float:
    """Effektivwert eines Blocks (0.0 bei leerem Block)."""
    if block.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(block, dtype=np.float64))))


class RingBuffer:
    """Thread-sicherer Ringpuffer für Stereo-float32-Samples.

    Quellen schreiben asynchron hinein (``push``), der Mixer liest im
    Audiotakt synchron heraus (``pull``). Fehlt Material, liefert ``pull``
    Stille zurück und meldet einen Unterlauf – das Programm bricht nie ab,
    es wird höchstens kurz still.
    """

    def __init__(self, capacity_frames: int = SAMPLE_RATE * 8):
        self._cap = int(capacity_frames)
        self._buf = np.zeros((self._cap, CHANNELS), dtype=DTYPE)
        self._write = 0
        self._avail = 0
        self._lock = threading.Lock()
        self.underruns = 0
        self.total_pushed = 0

    def push(self, block: np.ndarray) -> None:
        block = as_stereo(block)
        n = len(block)
        if n == 0:
            return
        with self._lock:
            if n >= self._cap:
                block = block[-self._cap:]
                n = len(block)
            end = self._write + n
            if end <= self._cap:
                self._buf[self._write:end] = block
            else:
                first = self._cap - self._write
                self._buf[self._write:] = block[:first]
                self._buf[: n - first] = block[first:]
            self._write = (self._write + n) % self._cap
            self._avail = min(self._cap, self._avail + n)
            self.total_pushed += n

    def pull(self, frames: int = BLOCK) -> np.ndarray:
        with self._lock:
            out = np.zeros((frames, CHANNELS), dtype=DTYPE)
            take = min(frames, self._avail)
            if take > 0:
                start = (self._write - self._avail) % self._cap
                end = start + take
                if end <= self._cap:
                    out[:take] = self._buf[start:end]
                else:
                    first = self._cap - start
                    out[:first] = self._buf[start:]
                    out[first:take] = self._buf[: take - first]
                self._avail -= take
            if take < frames:
                self.underruns += 1
            return out

    @property
    def available(self) -> int:
        with self._lock:
            return self._avail

    @property
    def fill(self) -> float:
        """Füllgrad 0..1 – nützlich, um ein Deck erst „bereit“ zu melden."""
        with self._lock:
            return self._avail / self._cap

    def clear(self) -> None:
        with self._lock:
            self._avail = 0
            self._write = 0
