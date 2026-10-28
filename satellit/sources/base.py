"""Gemeinsame Basis aller Audioquellen.

Eine Quelle liefert PCM im internen Format (48 kHz, Stereo, float32) über
einen Ringpuffer. Sie läuft in einem eigenen Thread, der Mixer liest nur
synchron per ``read``. Zwei Regeln halten die weichen Übergänge zusammen:

* ``ready`` wird erst True, wenn wirklich Ton im Puffer liegt – ein neuer
  Sender wird nie eingeblendet, solange er stumm ist.
* Fällt eine Quelle aus, liefert ``read`` einfach Stille; nichts stürzt ab.
* Läuft der Puffer einer Netzquelle leer, wird erst wieder ``prebuffer``
  gesammelt (einmal kurz still statt ständigem Hoppeln), dann über
  ``RESUME_FADE`` sanft wieder eingeblendet. Wie viel Vorlauf
  ein Sender bekommt, steht in seinem Eintrag (``"buffer"`` in Sekunden).
"""

from __future__ import annotations

import threading
import time

import numpy as np

from ..audio import BLOCK, RingBuffer, SAMPLE_RATE, silence

BUFFER_MIN, BUFFER_MAX = 0.2, 30.0   # erlaubter Vorlauf pro Sender (s)
RESUME_FADE = 2.0                    # s Einblenden nach einem Abriss


class Source:
    """Abstrakte Quelle. Unterklassen füllen ``self.buffer`` im Thread."""

    kind = "base"
    rebuffer = False      # Netzquellen: nach Leerlauf erst wieder vorpuffern

    def __init__(self, name: str = "", prebuffer_seconds: float = 0.6,
                 fail_fast_seconds: float = 3.0, timeout_seconds: float = 15.0,
                 stall_seconds: float = 6.0):
        self.name = name
        prebuffer_seconds = min(max(float(prebuffer_seconds), BUFFER_MIN), BUFFER_MAX)
        # Platz für den Vorlauf plus Nachschub-Schübe, mindestens wie bisher 8 s
        self.buffer = RingBuffer(capacity_frames=int(
            SAMPLE_RATE * max(8.0, 2 * prebuffer_seconds + 4)))
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._prebuffer = int(prebuffer_seconds * SAMPLE_RATE)
        self._fail_fast = fail_fast_seconds
        self._timeout = timeout_seconds
        self._stall = stall_seconds
        self.was_ready = False         # lief schon einmal (dann zählt nur echter Ausfall)
        self.last_audio = 0.0          # Zeitpunkt des letzten Blocks
        self.status = "stopped"        # stopped|connecting|playing|error|stalled
        self.error: str | None = None
        self.started_at = 0.0
        self.s_meter_dbm: float | None = None   # nur Kiwi/UberSDR
        self.buffering = False         # leergelaufen, sammelt wieder Vorlauf
        self.rebuffers = 0
        self._resume_pos = -1          # >= 0: wird gerade wieder eingeblendet

    # --- Lebenszyklus (von der Engine gesteuert) --------------------------
    def start(self) -> "Source":
        if self._thread and self._thread.is_alive():
            return self
        self._stop.clear()
        self.status = "connecting"
        self.error = None
        self.started_at = time.time()
        self._thread = threading.Thread(target=self._guarded_run,
                                        name=f"src-{self.name}", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=2.0)
        self.status = "stopped"
        self.buffering = False
        self.buffer.clear()

    # --- vom Mixer genutzt ------------------------------------------------
    def read(self, frames: int = BLOCK) -> np.ndarray:
        if not self.rebuffer:
            return self.buffer.pull(frames)
        if self.buffering:
            if self.buffer.available < self._prebuffer:
                return silence(frames)
            self.buffering = False
            self._resume_pos = 0
        if self.was_ready and self.buffer.available < frames:
            # Abriss: den letzten Rest ausblenden statt hart abzuschneiden
            take = self.buffer.available
            out = self.buffer.pull(frames)
            if take > 0:
                out[:take] *= np.linspace(1.0, 0.0, take, dtype=out.dtype)[:, None]
            self.buffering = True
            self._resume_pos = -1
            self.rebuffers += 1
            return out
        out = self.buffer.pull(frames)
        if self._resume_pos >= 0:      # nach dem Abriss sanft wieder hoch
            total = int(RESUME_FADE * SAMPLE_RATE)
            pos = self._resume_pos + np.arange(frames)
            out *= np.minimum(pos / total, 1.0).astype(out.dtype)[:, None]
            self._resume_pos += frames
            if self._resume_pos >= total:
                self._resume_pos = -1
        return out

    @property
    def ready(self) -> bool:
        """True, sobald genug vorgepuffert ist – Grundlage fürs Einblenden."""
        return self.buffer.available >= self._prebuffer and self.status == "playing"

    @property
    def failed(self) -> bool:
        return self.status == "error"

    def waited_too_long(self) -> bool:
        """Kam nach Timeout kein Ton? (Engine bleibt dann beim alten Sender.)

        Eine Quelle, die schon lief, gilt erst als ausgefallen, wenn sie
        gestoppt/gestört ist oder ``stall_seconds`` lang nichts mehr kam –
        über LTE pendelt der Puffer sonst ständig um die Startschwelle.
        """
        if self.ready:
            return False
        if self.was_ready:
            if self.status in ("error", "stopped"):
                return True
            return time.time() - self.last_audio > self._stall
        waited = time.time() - self.started_at
        if self.status == "error" and waited > self._fail_fast:
            return True
        return waited > self._timeout

    # --- von Unterklassen implementiert -----------------------------------
    def run(self) -> None:          # pragma: no cover - abstrakt
        raise NotImplementedError

    def _guarded_run(self) -> None:
        try:
            self.run()
        except Exception as exc:        # nie den Thread hart sterben lassen
            self.error = f"{type(exc).__name__}: {exc}"
            self.status = "error"

    def _emit_paced(self, block: np.ndarray, headroom_seconds: float = 2.0) -> bool:
        """Für Dateien: nur so schnell einstellen, wie abgespielt wird.

        Ein Ringpuffer überschreibt sonst die ältesten Samples. Wartet, bis
        Platz ist; liefert False, wenn die Quelle gestoppt wurde.
        """
        cap = self.buffer._cap
        limit = cap - int(headroom_seconds * SAMPLE_RATE)
        step = SAMPLE_RATE // 2
        for i in range(0, len(block), step):
            part = block[i:i + step]
            while self.buffer.available + len(part) > limit:
                if self._stop.wait(0.05):
                    return False
            self._emit(part)
        return True

    # Hilfe für Unterklassen: Block einstellen und Status hochziehen
    def _emit(self, block: np.ndarray) -> None:
        self.buffer.push(block)
        self.last_audio = time.time()
        if self.status in ("connecting", "stalled") and \
                self.buffer.available >= self._prebuffer:
            self.status = "playing"
            self.was_ready = True

    def describe(self) -> dict:
        return {
            "name": self.name, "kind": self.kind, "status": self.status,
            "ready": self.ready, "error": self.error,
            "s_meter_dbm": self.s_meter_dbm, "fill": round(self.buffer.fill, 3),
            "buffer_s": round(self.buffer.available / SAMPLE_RATE, 1),
            "prebuffer_s": round(self._prebuffer / SAMPLE_RATE, 1),
            "rebuffers": self.rebuffers,
        }
