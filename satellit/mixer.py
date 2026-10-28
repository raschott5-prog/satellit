"""Mixer: zwei Decks, Equal-Power-Überblendung, Weckrampe, Begrenzer.

Das Herz der weichen Übergänge. Zwei Decks (A und B) laufen gleichzeitig;
``crossfade`` schiebt zwischen ihnen hin und her, immer mit konstanter
Leistung, damit in der Mitte kein Loch entsteht. Darüber liegt eine
Master-Rampe (Wecken/Einschlafen) und ganz am Schluss ein weicher Begrenzer,
der Übersteuern verhindert, ohne hörbar zu zerren.

Reiner Zahlen-Code, keine Threads, kein I/O – dadurch gut testbar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .audio import BLOCK, CHANNELS, DTYPE, SAMPLE_RATE, as_stereo, rms, silence


def equal_power(x: float) -> tuple[float, float]:
    """Equal-Power-Gains für Überblendposition ``x`` in [0, 1].

    x = 0  -> komplett Deck A, x = 1 -> komplett Deck B.
    Die Summe der Leistungen (gA^2 + gB^2) bleibt konstant 1.
    """
    x = min(1.0, max(0.0, x))
    gA = np.cos(x * np.pi / 2.0)
    gB = np.sin(x * np.pi / 2.0)
    return float(gA), float(gB)


def _ramp(start: float, end: float, n: int) -> np.ndarray:
    return np.linspace(start, end, n, endpoint=False, dtype=np.float64)


@dataclass
class Deck:
    """Ein Deck hält eine Quelle und einen eigenen Pegel (Pegelausgleich).

    Die Quelle ist alles, was eine ``read(frames) -> ndarray`` Methode und
    ein ``ready``-Flag besitzt (siehe sources.base.Source). Ein frisch
    zugewiesener Sender wird erst „scharf“ geschaltet, wenn er wirklich Ton
    liefert; bis dahin bleibt ``ready`` False und der Mixer blendet nicht um.
    """

    name: str = ""
    source: object | None = None
    gain: float = 1.0           # fester Pegelausgleich (AM leiser als UKW-Stream)
    label: str = ""             # Anzeigename des aktuellen Senders

    # Laufende RMS-Schätzung für optionale Auto-Normalisierung
    _rms: float = field(default=0.0, repr=False)

    def read(self, frames: int) -> np.ndarray:
        src = self.source
        if src is None:
            return silence(frames)
        try:
            block = as_stereo(src.read(frames))
        except Exception:
            return silence(frames)
        if len(block) < frames:
            pad = silence(frames)
            pad[: len(block)] = block[:frames]
            block = pad
        # gleitender RMS (langsam), für Auto-Pegel
        cur = rms(block)
        self._rms = 0.98 * self._rms + 0.02 * cur
        return block * self.gain

    @property
    def ready(self) -> bool:
        src = self.source
        return bool(src is not None and getattr(src, "ready", True))

    @property
    def level(self) -> float:
        return self._rms


class Mixer:
    """Mischt Deck A und Deck B und wendet Master-Rampe + Begrenzer an.

    Zustände:
      crossfade      aktuelle Position 0..1 (0 = A, 1 = B)
      crossfade_to   Ziel; der Mixer läuft pro Block mit begrenzter
                     Geschwindigkeit darauf zu (Equal-Power).
      master         aktueller Masterpegel 0..1 (Wecken/Einschlafen)
      master_to      Ziel des Masterpegels.
    """

    def __init__(self, auto_level: bool = True):
        self.deck_a = Deck(name="A")
        self.deck_b = Deck(name="B")
        # Einspielungen (Ansagen, Gong): eigenes Deck über dem Programm.
        self.deck_o = Deck(name="O")
        self.overlay_on = False
        self.overlay_gain = 1.0
        # Absenken des Programms unter eine Einspielung (Ducking)
        self.duck = 1.0
        self.duck_to = 1.0
        self._duck_per_block = 1.0
        # Bedienlautstärke + Stumm (unabhängig von Weck-/Schlummer-Rampe)
        self.volume = 1.0
        self.volume_to = 1.0
        self.muted = False
        self._vol_per_block = self._per_block_static(0.3)
        self.crossfade = 0.0
        self.crossfade_to = 0.0
        self.master = 1.0
        self.master_to = 1.0
        self.auto_level = auto_level
        self.noise_level = 0.0        # Senderrauschen während Überblendungen
        self._fade_per_block = 1.0    # wird aus Dauer berechnet
        self._master_per_block = 1.0
        self._rng = np.random.default_rng(0xBEEF)
        self.limiter_ceiling = 0.98
        # Mithörer (Übersetzer): bekommt jeden Block vor Lautstärke/Stumm
        self.tap = None

    # --- Steuerung ---------------------------------------------------------
    def set_crossfade(self, target: float, seconds: float = 4.0) -> None:
        """Weich zu Ziel ``target`` (0..1) über ``seconds`` überblenden."""
        self.crossfade_to = min(1.0, max(0.0, target))
        self._fade_per_block = self._per_block(seconds)

    def set_master(self, target: float, seconds: float = 2.0) -> None:
        """Masterpegel weich auf ``target`` (0..1) fahren (Wecken/Ausblenden)."""
        self.master_to = min(1.0, max(0.0, target))
        self._master_per_block = self._per_block(seconds)

    def set_duck(self, target: float, seconds: float = 0.8) -> None:
        """Programm unter eine Einspielung absenken (0 = ganz weg) bzw. zurück."""
        self.duck_to = min(1.0, max(0.0, target))
        self._duck_per_block = self._per_block(seconds)

    def set_volume(self, value: float) -> None:
        self.volume_to = min(1.0, max(0.0, value))

    def set_muted(self, muted: bool) -> None:
        self.muted = bool(muted)

    @property
    def duck_settled(self) -> bool:
        return abs(self.duck - self.duck_to) < 1e-6

    @staticmethod
    def _per_block_static(seconds: float) -> float:
        if seconds <= 0:
            return 1.0
        return 1.0 / max(1.0, seconds * SAMPLE_RATE / BLOCK)

    def _per_block(self, seconds: float) -> float:
        return self._per_block_static(seconds)

    @staticmethod
    def _step(cur: float, to: float, step: float) -> float:
        if cur < to:
            return min(to, cur + step)
        if cur > to:
            return max(to, cur - step)
        return cur

    def active_deck(self) -> Deck:
        """Das Deck, das gerade „vorne“ ist (für Pegel-/Statusanzeige)."""
        return self.deck_b if self.crossfade_to >= 0.5 else self.deck_a

    def standby_deck(self) -> Deck:
        return self.deck_a if self.crossfade_to >= 0.5 else self.deck_b

    # --- Audio -------------------------------------------------------------
    def process(self, frames: int = BLOCK) -> np.ndarray:
        # Crossfade in Richtung Ziel bewegen
        if self.crossfade < self.crossfade_to:
            self.crossfade = min(self.crossfade_to, self.crossfade + self._fade_per_block)
        elif self.crossfade > self.crossfade_to:
            self.crossfade = max(self.crossfade_to, self.crossfade - self._fade_per_block)

        gA, gB = equal_power(self.crossfade)

        a = self.deck_a.read(frames) if gA > 1e-4 else silence(frames)
        b = self.deck_b.read(frames) if gB > 1e-4 else silence(frames)

        if self.auto_level:
            gA *= self._auto(self.deck_a)
            gB *= self._auto(self.deck_b)

        mix = a * gA + b * gB

        # Etwas Senderrauschen, solange wir mitten im Überblenden sind –
        # das verdeckt harte Kanten und klingt nach „zwischen den Sendern“.
        mid = 1.0 - abs(2.0 * self.crossfade - 1.0)   # 0 an den Enden, 1 in der Mitte
        if self.noise_level > 0 and mid > 0.01:
            noise = self._rng.standard_normal((frames, CHANNELS)).astype(DTYPE)
            mix += noise * (self.noise_level * mid)

        # Programm absenken, Einspielung obendrauf
        d0 = self.duck
        self.duck = self._step(self.duck, self.duck_to, self._duck_per_block)
        if d0 != 1.0 or self.duck != 1.0:
            mix = mix * _ramp(d0, self.duck, frames)[:, None]
        if self.overlay_on:
            mix = mix + self.deck_o.read(frames) * self.overlay_gain
        if self.tap is not None:
            try:
                self.tap(mix)
            except Exception:
                pass            # der Mithörer darf den Ton nie stören

        # Master-Rampe (Wecken/Schlummern) × Bedienlautstärke (inkl. Stumm)
        m0 = self.master
        self.master = self._step(self.master, self.master_to, self._master_per_block)
        v0 = self.volume
        self.volume = self._step(self.volume, 0.0 if self.muted else self.volume_to,
                                 self._vol_per_block)
        env = (_ramp(m0, self.master, frames) * _ramp(v0, self.volume, frames))[:, None]
        mix = mix * env

        return self._limit(mix).astype(DTYPE)

    def _auto(self, deck: Deck) -> float:
        """Sanfte Auto-Normalisierung auf einen Zielpegel, stark gedämpft."""
        target = 0.12
        lvl = deck.level
        if lvl < 1e-4:
            return 1.0
        g = target / lvl
        return float(min(3.0, max(0.3, g)))

    def _limit(self, x: np.ndarray) -> np.ndarray:
        """Weicher Begrenzer: unterhalb der Schwelle linear, darüber tanh."""
        c = self.limiter_ceiling
        peak = float(np.max(np.abs(x))) if x.size else 0.0
        if peak <= c:
            return x
        # tanh-Soft-Clip, auf Decke skaliert
        return (np.tanh(x / c) * c).astype(DTYPE)
