"""Wache: Aktivitätserkennung auf Kurz-/Mittelwellen-Kanälen.

Prüft einmal pro Minute (einstellbar, nicht unter 30 s – Fairness) kurz
Kanäle wie das Hurricane Watch Net und meldet der Engine, wenn dort Betrieb
ist. Die Erkennung läuft über das S-Meter des KiwiSDR:

  spread      Spreizung der S-Meter-Werte (Sprache in SSB schwankt stark)
  noisefloor  Abstand zum gelernten Rauschboden
  fixed       fester Pegel (Standard -90 dBm)

Nach ``hits_to_switch`` Treffern in Folge → umschalten, nach
``quiet_to_return`` ruhigen Abfragen → zurück. „Zurück zum Programm"
schaltet den Kanal ``mute_minutes`` lang stumm. Hört man den Kanal ohnehin
gerade (gleicher Host/Frequenz wie das aktive Deck), wird kein zweiter
Kiwi-Slot belegt.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

import numpy as np

from .sources.kiwi import probe_smeter


@dataclass
class WatchChannel:
    name: str
    host: str
    freq_khz: float
    mode: str = "usb"
    # Laufzeitzustand
    hits: int = 0
    quiet: int = 0
    noise_floor: float = field(default=-110.0)
    muted_until: float = 0.0
    last_dbm: float | None = None
    active: bool = False

    def key(self) -> tuple:
        return (self.host.split("://")[-1], round(self.freq_khz, 1))


def detect(values: list[float], mode: str, channel: WatchChannel,
           fixed_dbm: float) -> bool:
    """Ein Satz S-Meter-Werte -> Betrieb ja/nein."""
    if not values:
        return False
    arr = np.asarray(values)
    peak = float(arr.max())
    channel.last_dbm = peak
    if mode == "fixed":
        return peak > fixed_dbm
    if mode == "spread":
        spread = float(arr.max() - arr.min())
        return spread > 6.0 and peak > channel.noise_floor + 8.0
    # noisefloor: gleitend lernen, Ausschlag darüber = Betrieb
    med = float(np.median(arr))
    channel.noise_floor = 0.9 * channel.noise_floor + 0.1 * med
    return peak > channel.noise_floor + 10.0


class Watcher(threading.Thread):
    """Eigener Thread; ruft ``on_activity(channel)`` / ``on_clear(channel)``."""

    def __init__(self, config: dict, on_activity=None, on_clear=None,
                 is_listening=None):
        super().__init__(name="watcher", daemon=True)
        self.on_activity = on_activity
        self.on_clear = on_clear
        self.is_listening = is_listening or (lambda ch: False)
        self._stop = threading.Event()
        self.apply(config)

    def apply(self, config: dict) -> None:
        self.enabled = config.get("enabled", True)
        self.poll = max(30.0, float(config.get("poll_seconds", 60.0)))  # Fairness
        self.hits_to_switch = int(config.get("hits_to_switch", 2))
        self.quiet_to_return = int(config.get("quiet_to_return", 10))
        self.mute_minutes = float(config.get("mute_minutes", 30))
        self.detector = config.get("detector", "spread")
        self.fixed_dbm = float(config.get("fixed_dbm", -90.0))
        self.channels = [WatchChannel(**{k: c[k] for k in
                         ("name", "host", "freq_khz", "mode") if k in c})
                         for c in config.get("channels", [])]

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        if not self.enabled or not self.channels:
            return
        idx = 0
        while not self._stop.is_set():
            # Abfragen reihum auf die Kanäle verteilen (fair gegenüber Kiwis)
            ch = self.channels[idx % len(self.channels)]
            idx += 1
            self._check(ch)
            # Wartezeit so, dass jeder Kanal ~alle poll Sekunden drankommt
            self._stop.wait(self.poll / max(1, len(self.channels)))

    def _check(self, ch: WatchChannel) -> None:
        now = time.time()
        if now < ch.muted_until:
            return
        if self.is_listening(ch):
            return   # kein zweiter Slot, wenn wir den Kanal eh hören
        try:
            values = probe_smeter(ch.host, ch.freq_khz, ch.mode, seconds=3.0)
        except Exception:
            return
        busy = detect(values, self.detector, ch, self.fixed_dbm)
        if busy:
            ch.hits += 1
            ch.quiet = 0
            if ch.hits >= self.hits_to_switch and not ch.active:
                ch.active = True
                if self.on_activity:
                    self.on_activity(ch)
        else:
            ch.quiet += 1
            ch.hits = 0
            if ch.active and ch.quiet >= self.quiet_to_return:
                ch.active = False
                if self.on_clear:
                    self.on_clear(ch)

    def dismiss(self, ch: WatchChannel) -> None:
        """„Zurück zum Programm": Kanal eine Weile stummschalten."""
        ch.active = False
        ch.hits = 0
        ch.muted_until = time.time() + self.mute_minutes * 60

    def state(self) -> dict:
        return {
            "enabled": self.enabled, "poll_seconds": self.poll,
            "detector": self.detector,
            "channels": [{"name": c.name, "freq_khz": c.freq_khz, "mode": c.mode,
                          "active": c.active, "last_dbm": c.last_dbm,
                          "muted": time.time() < c.muted_until} for c in self.channels],
        }
