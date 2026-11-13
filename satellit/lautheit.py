"""Lautheitsangleich nach EBU R128 / ITU-R BS.1770.

Jeder Sender wird anders abgemischt: Privatsender drücken alles nach vorn,
Kultursender lassen Dynamik, AM-Empfänger kommen leise. Statt fester
``gain``-Werte pro Sender misst Satellit die Lautheit (LUFS) laufend und
regelt **langsam** auf einen gemeinsamen Zielwert. Langsam heißt: Ein leises
Stück bleibt leise, nur der Sender als Ganzes wird angeglichen – kein
Pumpen wie bei einem Kompressor.

Messung wie in BS.1770: K-Gewichtung (Höhenanhebung + Tiefensperre),
Leistung aller Kanäle summiert, Abschnitte von 0,4 s, Stille (< −70 LUFS)
und deutlich leisere Stellen (Pausen, Moderation zwischen Titeln) zählen
nicht mit. Die K-Gewichtung wird spektral angewendet (FFT je Block); das
spart einen Filter in Python und ist für die Regelung genau genug.

Gemessene Werte merkt sich Satellit pro Sender (``lautheit.json`` neben der
Konfiguration): Beim nächsten Einschalten stimmt der Pegel sofort.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import threading
from pathlib import Path

import numpy as np

from .audio import BLOCK, SAMPLE_RATE

#: Zielwert; −16 LUFS ist die übliche Empfehlung für Streaming/Wiedergabe
ZIEL_LUFS = -16.0
MAX_ANHEBUNG_DB = 10.0
MAX_ABSENKUNG_DB = 15.0
ABSCHNITT_S = 0.4
ABSOLUT_GATE = -70.0
RELATIV_GATE = 20.0          # so viel leiser als der Sender -> Pause, zählt nicht
ZEITKONSTANTE_S = 20.0       # Gedächtnis der Messung
#: Regelgeschwindigkeit (dB/s): am Anfang zügig, eingeschwungen behutsam
TEMPO_ANFANG = 6.0
TEMPO_RUHIG = 1.5

# K-Gewichtung bei 48 kHz (BS.1770-4, Tabelle 1 und 2)
_B1 = (1.53512485958697, -2.69169618940638, 1.19839281085285)
_A1 = (1.0, -1.69065929318241, 0.73248077421585)
_B2 = (1.0, -2.0, 1.0)
_A2 = (1.0, -1.99004745483398, 0.99007225036621)


def _k_gewichte(n: int, rate: int = SAMPLE_RATE) -> np.ndarray:
    """|H_K(f)|² für die rfft-Bins eines Blocks der Länge ``n``."""
    z = np.exp(-2j * np.pi * np.fft.rfftfreq(n, 1.0 / rate) / rate)

    def h(b, a):
        return (b[0] + b[1] * z + b[2] * z * z) / (a[0] + a[1] * z + a[2] * z * z)

    return (np.abs(h(_B1, _A1) * h(_B2, _A2)) ** 2).astype(np.float64)


_CACHE: dict[int, tuple[np.ndarray, np.ndarray, float]] = {}


def _fenster(n: int):
    if n not in _CACHE:
        w = np.hanning(n)
        g = _k_gewichte(n)
        g[1:-1] *= 2.0                       # einseitiges Spektrum
        if n % 2:
            g[-1] *= 2.0
        _CACHE[n] = (w, g, 1.0 / (n * float(np.sum(w * w))))
    return _CACHE[n]


def k_leistung(block: np.ndarray) -> float:
    """K-gewichtete mittlere Leistung, über die Kanäle summiert (BS.1770 „z“)."""
    n = len(block)
    if n < 16:
        return 0.0
    x = block.reshape(n, -1).astype(np.float64)
    w, g, norm = _fenster(n)
    spec = np.fft.rfft(x * w[:, None], axis=0)
    return float(np.sum(g[:, None] * (spec.real ** 2 + spec.imag ** 2)) * norm)


def lufs(leistung: float) -> float:
    return -0.691 + 10.0 * math.log10(leistung) if leistung > 0 else -math.inf


def leistung_aus_lufs(l: float) -> float:
    return 10.0 ** ((l + 0.691) / 10.0)


class Lautheit:
    """Misst die Lautheit eines Decks und liefert die Ausgleichsverstärkung."""

    def __init__(self, ziel: float = ZIEL_LUFS):
        self.ziel = ziel
        self._blocks_je_abschnitt = max(1, round(ABSCHNITT_S * SAMPLE_RATE / BLOCK))
        self._max_n = max(1, round(ZEITKONSTANTE_S / ABSCHNITT_S))
        self.reset()

    def reset(self, gemerkt: float | None = None) -> None:
        """Neuer Sender. ``gemerkt`` = früher gemessene Lautheit (LUFS)."""
        self._summe = 0.0
        self._anzahl = 0
        self._gesperrt = 0
        if gemerkt is not None and math.isfinite(gemerkt):
            self._e = leistung_aus_lufs(gemerkt)
            self._n = self._max_n // 2           # vertrauen, aber nachführen
            self.gain_db = self._soll_db()
        else:
            self._e = 0.0
            self._n = 0
            self.gain_db = 0.0

    @property
    def messwert(self) -> float | None:
        """Lautheit des Senders (LUFS), sobald genug gemessen ist."""
        return lufs(self._e) if self._n >= 3 else None

    def _soll_db(self) -> float:
        l = lufs(self._e)
        return min(MAX_ANHEBUNG_DB, max(-MAX_ABSENKUNG_DB, self.ziel - l))

    def messen(self, block: np.ndarray) -> None:
        self._summe += k_leistung(block)
        self._anzahl += 1
        if self._anzahl < self._blocks_je_abschnitt:
            return
        z = self._summe / self._anzahl
        self._summe, self._anzahl = 0.0, 0
        l = lufs(z)
        if l < ABSOLUT_GATE:
            return
        if self._n >= 3 and l < lufs(self._e) - RELATIV_GATE:
            # Pause oder leise Stelle – außer der Sender ist wirklich leiser
            # geworden (eine halbe Minute lang nichts anderes)
            self._gesperrt += 1
            if self._gesperrt * ABSCHNITT_S < 30.0:
                return
        self._gesperrt = 0
        self._n = min(self._max_n, self._n + 1)
        self._e += (z - self._e) / self._n

    def schritt(self, frames: int) -> tuple[float, float]:
        """Verstärkung (linear) am Blockanfang und -ende; nachgeführt mit
        begrenzter Geschwindigkeit, damit nichts springt."""
        g0 = self.gain_db
        if self._n >= 3:
            tempo = TEMPO_ANFANG if self._n < self._max_n // 2 else TEMPO_RUHIG
            d = tempo * frames / SAMPLE_RATE
            soll = self._soll_db()
            self.gain_db = min(soll, g0 + d) if soll > g0 else max(soll, g0 - d)
        return 10.0 ** (g0 / 20.0), 10.0 ** (self.gain_db / 20.0)


class Merker:
    """Gemessene Lautheit je Sender, als kleine JSON-Datei gespeichert."""

    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path) if path else None
        self.werte: dict[str, float] = {}
        self._geaendert = False
        self._lock = threading.Lock()
        if self.path and self.path.exists():
            try:
                daten = json.loads(self.path.read_text(encoding="utf-8"))
                self.werte = {str(k): float(v) for k, v in daten.items()
                              if isinstance(v, (int, float)) and math.isfinite(v)}
            except (OSError, ValueError, AttributeError):
                self.werte = {}

    def get(self, key: str | None) -> float | None:
        return self.werte.get(key) if key else None

    def set(self, key: str | None, wert: float | None) -> None:
        if not key or wert is None:
            return
        wert = round(wert, 1)
        with self._lock:
            if self.werte.get(key) != wert:
                self.werte[key] = wert
                self._geaendert = True

    def speichern(self) -> None:
        if not self.path:
            return
        with self._lock:
            if not self._geaendert:
                return
            daten = dict(self.werte)
            self._geaendert = False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(daten, f, indent=1, sort_keys=True)
            os.replace(tmp, self.path)
        except OSError:
            self._geaendert = True
