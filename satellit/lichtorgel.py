"""Anbindung an die Lichtorgel (optionales Zusatzprogramm, eigenes Projekt).

Die Lichtorgel läuft als eigener Dienst und tauscht sich über zwei kleine
JSON-Dateien in ihrem Ordner aus (Standard ``~/.config/lichtorgel``):

* ``status.json`` schreibt die Lichtorgel jede Sekunde:
  ``{"t": <unix-zeit>, "hell": 0..100, "stumm": bool, "stille_db": .., "pegel_db": ..}``
* ``regler.json`` liest sie, sobald sich die Datei ändert:
  ``{"hell": 0..100, "stille_db": -70..-20}``

Ist kein frischer Status da (Lichtorgel nicht installiert oder gestoppt), meldet
Satellit ``aktiv: false`` und die Oberfläche graut die Regler aus.

Konfiguration (optional): ``"lichtorgel": {"enabled": true, "dir": "~/.config/lichtorgel"}``
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

FRISCH_S = 5.0                 # Status älter als das = Lichtorgel läuft nicht
HELL_BEREICH = (0, 100)
STILLE_BEREICH = (-70.0, -20.0)


def _ordner(config_data: dict) -> Path | None:
    lo = config_data.get("lichtorgel") or {}
    if lo.get("enabled") is False:
        return None
    return Path(os.path.expanduser(lo.get("dir") or "~/.config/lichtorgel"))


def zustand(config_data: dict, jetzt: float | None = None) -> dict:
    """Zustand für /api/state: aktiv + aktuelle Werte (nur wenn aktiv)."""
    ordner = _ordner(config_data)
    if ordner is None:
        return {"aktiv": False, "grund": "abgeschaltet"}
    try:
        with open(ordner / "status.json") as f:
            st = json.load(f)
    except (OSError, ValueError):
        return {"aktiv": False, "grund": "nicht gefunden"}
    jetzt = time.time() if jetzt is None else jetzt
    alter = jetzt - float(st.get("t", 0))
    if alter > FRISCH_S:
        return {"aktiv": False, "grund": "läuft nicht"}
    return {"aktiv": True,
            "hell": st.get("hell"), "stumm": bool(st.get("stumm")),
            "stille_db": st.get("stille_db"), "pegel_db": st.get("pegel_db")}


def setzen(config_data: dict, werte: dict) -> dict:
    """Vorgaben in regler.json schreiben (vorhandene Felder bleiben). Gibt die Datei zurück."""
    ordner = _ordner(config_data)
    if ordner is None:
        raise ValueError("Lichtorgel ist in der Konfiguration abgeschaltet")
    neu = {}
    if "hell" in werte:
        h = werte["hell"]
        if not isinstance(h, (int, float)) or isinstance(h, bool):
            raise ValueError("hell muss eine Zahl sein")
        neu["hell"] = int(round(min(max(h, HELL_BEREICH[0]), HELL_BEREICH[1])))
    if "stille_db" in werte:
        s = werte["stille_db"]
        if not isinstance(s, (int, float)) or isinstance(s, bool):
            raise ValueError("stille_db muss eine Zahl sein")
        neu["stille_db"] = round(float(min(max(s, STILLE_BEREICH[0]), STILLE_BEREICH[1])), 1)
    if not neu:
        raise ValueError("nichts zu setzen (hell oder stille_db)")
    datei = ordner / "regler.json"
    alt = {}
    try:
        with open(datei) as f:
            alt = json.load(f)
    except (OSError, ValueError):
        pass
    alt.update(neu)
    ordner.mkdir(parents=True, exist_ok=True)
    tmp = datei.with_suffix(".neu")
    with open(tmp, "w") as f:
        json.dump(alt, f)
    os.replace(tmp, datei)
    return alt
