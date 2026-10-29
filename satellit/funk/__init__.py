"""Funk-Teil: alles für Funkamateure und Kurzwellen-Nerds.

Das Grundgerät (Streams, Musik, Fahrplan, Wecken, Ansagen) kommt ohne dieses
Paket aus. Erst der Schalter ``"funk": {"enabled": true}`` lädt es:

* Quellen ``kiwi``, ``ubersdr``, ``websdr`` (Web-SDR-Empfänger),
* Wache (S-Meter-Abfrage beobachteter Kanäle),
* SAME (US-Notfalldurchsagen),
* HFCC-Sendeplan und Übersetzer (Whisper).

Zusatzpakete stehen in ``requirements-funk.txt``; fehlt eines, läuft der
Funk-Teil trotzdem, nur die betroffene Funktion meldet es.
"""

from __future__ import annotations

import importlib.util
from typing import Any

#: Quellenarten, die zum Funk-Teil gehören
FUNK_KINDS = ("kiwi", "ubersdr", "websdr")

#: Zusatzpaket -> wofür es gebraucht wird
PACKAGES = {
    "websocket": "KiwiSDR, UberSDR, WebSDR (websocket-client)",
    "opuslib": "UberSDR (opuslib)",
    "faster_whisper": "Übersetzer (faster-whisper)",
}


def missing_packages() -> list[str]:
    """Fehlende Zusatzpakete als lesbare Liste (leer = alles da)."""
    out = []
    for mod, what in PACKAGES.items():
        try:
            found = importlib.util.find_spec(mod) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            out.append(what)
    return out


def make_source(spec: dict[str, Any], *, uuid: str = "", **kw):
    """Funkquelle aus einem Sendereintrag (``kind`` in ``FUNK_KINDS``)."""
    kind = spec.get("kind")
    name = spec.get("name", "")
    gain = float(spec.get("gain", 1.0))
    if kind == "kiwi":
        from .kiwi import KiwiSource
        return KiwiSource(host=spec["host"], freq_khz=spec["freq_khz"],
                          mode=spec.get("mode", "am"), name=name, gain=gain,
                          password=spec.get("password", ""), **kw)
    if kind == "ubersdr":
        from .ubersdr import UberSDRSource
        return UberSDRSource(host=spec["host"], freq_khz=spec["freq_khz"],
                             mode=spec.get("mode", "am"), name=name, gain=gain,
                             user_session_id=uuid, **kw)
    if kind == "websdr":
        from .websdr import WebSDRSource
        return WebSDRSource(url=spec["url"], freq_khz=spec["freq_khz"],
                            mode=spec.get("mode", "usb"), name=name, gain=gain,
                            browser=spec.get("browser", ""), **kw)
    raise ValueError(f"keine Funkquelle: {kind}")
