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

Ausklingen: bis zu einer Zieluhrzeit wird die Lichtorgel gleichmäßig dunkler
(bis ``AUSKLANG_HELL`` %) und unempfindlicher (Schwelle bis 0 dB) – am Ende
leuchtet nur noch das Grundlicht. Der laufende Ausklang steht in der
Konfiguration unter ``lichtorgel.ausklang`` und übersteht so einen Neustart.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

FRISCH_S = 5.0                 # Status älter als das = Lichtorgel läuft nicht
HELL_BEREICH = (0, 100)
STILLE_BEREICH = (-70.0, 0.0)  # 0 dB = reagiert praktisch nie (nur Grundlicht)
AUSKLANG_HELL = 25             # Helligkeit am Ende des Ausklingens (Grundlicht schwach)
AUSKLANG_STILLE = 0.0
AUSKLANG_MAX_S = 24 * 3600


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
    z = {"aktiv": True,
         "hell": st.get("hell"), "stumm": bool(st.get("stumm")),
         "stille_db": st.get("stille_db"), "pegel_db": st.get("pegel_db")}
    ak = (config_data.get("lichtorgel") or {}).get("ausklang")
    if ak:
        z["ausklang"] = {"bis_t": ak["bis_t"], "rest_s": max(0, round(ak["bis_t"] - jetzt)),
                         "nach_hell": ak["nach_hell"]}
    return z


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


def ausklang_werte(ak: dict, jetzt: float) -> tuple[int, float, bool]:
    """(hell, stille_db, fertig) für einen Ausklang zum Zeitpunkt ``jetzt`` (linear)."""
    dauer = max(1.0, ak["bis_t"] - ak["start_t"])
    f = min(1.0, max(0.0, (jetzt - ak["start_t"]) / dauer))
    hell = round(ak["von_hell"] + (ak["nach_hell"] - ak["von_hell"]) * f)
    stille = round(ak["von_stille"] + (ak["nach_stille"] - ak["von_stille"]) * f, 1)
    return hell, stille, f >= 1.0


def ausklang_starten(config, bis_t: float, nach_hell: int | None = None,
                     jetzt: float | None = None) -> dict:
    """Ausklang bis ``bis_t`` (Unix-Zeit) starten; Startwerte = aktuelle Regler."""
    jetzt = time.time() if jetzt is None else jetzt
    z = zustand(config.data, jetzt)
    if not z["aktiv"]:
        raise ValueError("Lichtorgel läuft nicht")
    if not isinstance(bis_t, (int, float)) or isinstance(bis_t, bool):
        raise ValueError("bis_t muss eine Zahl sein")
    if not 60 <= bis_t - jetzt <= AUSKLANG_MAX_S:
        raise ValueError("Zieluhrzeit muss 1 min bis 24 h in der Zukunft liegen")
    nach = AUSKLANG_HELL if nach_hell is None else nach_hell
    if not isinstance(nach, (int, float)) or isinstance(nach, bool):
        raise ValueError("nach_hell muss eine Zahl sein")
    von_hell = int(z.get("hell") or 0)
    von_stille = float(z.get("stille_db") if z.get("stille_db") is not None else -45.0)
    ak = {"start_t": round(jetzt, 1), "bis_t": round(float(bis_t), 1),
          "von_hell": von_hell, "nach_hell": int(min(max(nach, 0), von_hell)),
          "von_stille": von_stille, "nach_stille": AUSKLANG_STILLE}
    config.update({"lichtorgel": {"ausklang": ak}})
    return ak


def ausklang_stoppen(config) -> None:
    """Ausklang abbrechen; die Regler bleiben, wo sie gerade stehen."""
    if (config.data.get("lichtorgel") or {}).get("ausklang"):
        config.update({"lichtorgel": {"ausklang": None}})


def ausklang_schritt(config, jetzt: float | None = None, _letzt: dict = {}) -> None:
    """Regelmäßig aufrufen (Steuer-Schleife): schreibt die Zwischenwerte nach regler.json."""
    ak = (config.data.get("lichtorgel") or {}).get("ausklang")
    if not ak:
        return
    jetzt = time.time() if jetzt is None else jetzt
    hell, stille, fertig = ausklang_werte(ak, jetzt)
    if _letzt.get("w") != (hell, stille) or fertig:
        try:
            setzen(config.data, {"hell": hell, "stille_db": stille})
            _letzt["w"] = (hell, stille)
        except (OSError, ValueError):
            return
    if fertig:
        ausklang_stoppen(config)
