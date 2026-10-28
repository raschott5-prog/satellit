"""Konfiguration: plattformübergreifend laden und speichern.

Windows:  %APPDATA%\\Satellit\\config.json
Linux:    ~/.config/satellit/config.json
macOS:    ~/Library/Application Support/Satellit/config.json

Die Datei wird über die Oberfläche bearbeitet; hier liegen nur Laden,
Speichern (atomar) und die mitgelieferten Beispielwerte.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any


def default_config_path() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "Satellit" / "config.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Satellit" / "config.json"
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "satellit" / "config.json"


def default_config() -> dict[str, Any]:
    """Ein spielbarer Beispielstand – echte Stream-URLs trägt der Nutzer ein."""
    return {
        "version": 2,
        # radio = Skala, Frequenzen, SDR, Wache
        # program = Wochenplan, Musik, Ansagen – keine Funkbegriffe
        "mode": "radio",
        "media_dir": None,           # None = Unterordner "media" neben config.json
        "fallback": "musik",         # Ersatz, wenn das Programm ausfällt (offline);
                                     # ein Sender kann mit "fallback" einen eigenen haben
        "audio": {
            "device": None,          # None = Standardgerät
            "auto_level": True,
            "volume": 0.5,           # bewusst zurückhaltend
            "crossfade_seconds": 4.0,
            "wake_seconds": 90.0,    # Weck-Einblendung über Minuten
            "noise_level": 0.006,    # Senderrauschen bei Überblendungen
        },
        "announce": {
            "duck_level": 0.15,      # Musik unter einer Ansage auf 15 %
            "duck_seconds": 0.8,     # so schnell absenken
            "release_seconds": 1.5,  # so weich wieder hochfahren
            "gain": 1.0,             # Pegel der Einspielungen
            "max_delay_minutes": 10, # länger verspätet (Stau, Standby) -> verwerfen
        },
        "stations": [
            # Lokale Musik – läuft ohne Internet, Standard-Ersatzquelle
            {"id": "musik", "name": "Musik (lokal)", "kind": "folder",
             "path": "musik", "freq": 90.0},
            # UKW = Internet-Stream; freq = Position auf der Skala (MHz)
            {"id": "fm1", "name": "Beispiel UKW", "kind": "stream",
             "url": "https://example.org/stream.mp3", "freq": 98.4, "gain": 0.8},
            # Mittelwelle live von einem KiwiSDR
            {"id": "mw1", "name": "AM Nachtprogramm", "kind": "kiwi",
             "host": "kiwisdr.example.org:8073", "freq_khz": 783, "mode": "am",
             "freq": 0.783, "gain": 1.2},
            # Kurzwelle von einer UberSDR-Instanz
            {"id": "sw1", "name": "UberSDR 49m", "kind": "ubersdr",
             "host": "ubersdr.example.org:8080", "freq_khz": 6155, "mode": "am",
             "freq": 6.155, "gain": 1.1},
        ],
        "schedule": {
            "enabled": True,
            "entries": [
                {"time": "06:30", "station": "mw1", "fade": 90.0, "wake": True},
                {"time": "08:30", "station": "fm1", "fade": 8.0},
                {"time": "23:00", "action": "sleep", "fade": 120.0},
                # Beispiel-Einspielung (aus): Gong + Ansage werktags um 10:00
                {"time": "10:00", "play": ["gong.wav"], "label": "Gong (Beispiel)",
                 "days": ["mo", "di", "mi", "do", "fr"], "enabled": False},
            ],
        },
        "watcher": {
            "enabled": True,
            "poll_seconds": 60.0,       # Fairness: nicht unter 30 stellen
            "hits_to_switch": 2,
            "quiet_to_return": 10,
            "mute_minutes": 30,
            "detector": "spread",       # spread | noisefloor | fixed
            "fixed_dbm": -90.0,
            "channels": [
                {"name": "Hurricane Watch Net 20m", "host": "kiwisdr.example.org:8073",
                 "freq_khz": 14325.0, "mode": "usb"},
                {"name": "Hurricane Watch Net 40m", "host": "kiwisdr.example.org:8073",
                 "freq_khz": 7268.0, "mode": "lsb"},
            ],
        },
        "same": {
            "enabled": True,
            # NWR-Internet-Streams bevorzugt (162 MHz liegt außerhalb von Kiwi/UberSDR)
            "sources": [
                {"name": "NWR Beispiel", "kind": "stream",
                 "url": "https://example.org/nwr.mp3"},
            ],
            "fips": ["024031", "051059"],   # eigene County-Codes (PSSCCC)
            "events": {
                "warnings": ["TOR", "SVR", "FFW", "EWW", "SVW"],
                "watches": ["TOA", "SVA", "FFA"],
                "tests": ["RWT", "RMT", "NPT"],
            },
            "on_test": "log",       # log | chime
            "fade_seconds": 3.0,    # kürzer als die Weckrampe – Ton ist das Signal
        },
        "translate": {
            "enabled": False,        # braucht faster-whisper (optional)
            "model": "small",        # tiny/base schneller, medium genauer
            "language": None,        # None = Sprache erkennen, sonst z. B. "fr"
            "beam": 1,               # größer = genauer, aber langsamer
            "fallback": False,       # Whisper-Neuversuche: genauer, auf Kurzwelle 3–4× langsamer
            "threads": 0,            # 0 = automatisch (Kerne − 2)
            "min_seconds": 5.0,      # Abschnitte 5–12 s, Schnitt in Sprechpausen
            "max_seconds": 12.0,
            "min_lang_prob": 0.5,    # darunter wird die Zeile als unsicher markiert
            "keep_lines": 50,
        },
        # Sendeplan der HFCC: zeigt, was auf einer Kurzwellenfrequenz läuft,
        # und gibt dem Übersetzer die Sprache vor (~160 KB pro Woche)
        "hfcc": {"enabled": True, "base_url": "http://www.hfcc.org/data", "refresh_days": 7},
        "web": {"listen": "127.0.0.1", "port": 8080},
    }


class Config:
    """Dünne Hülle um die JSON-Datei mit atomarem Speichern."""

    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path) if path else default_config_path()
        self._lock = threading.Lock()
        self.data: dict[str, Any] = default_config()

    def load(self) -> "Config":
        with self._lock:
            if self.path.exists():
                try:
                    loaded = json.loads(self.path.read_text(encoding="utf-8"))
                    self.data = _merge(default_config(), loaded)
                except (json.JSONDecodeError, OSError) as exc:
                    # kaputte Datei nicht wegwerfen: beiseitelegen, Default nehmen
                    try:
                        self.path.rename(self.path.with_suffix(".json.bad"))
                    except OSError:
                        pass
                    print(f"[config] {self.path} unlesbar ({exc}); Standardwerte.",
                          file=sys.stderr)
            else:
                self._write_unlocked()   # Lock schon gehalten
            if self._normalize():
                self._write_unlocked()
        return self

    def _normalize(self) -> bool:
        """Fahrplan-Einträge bekommen stabile IDs (für an/aus in der Oberfläche)."""
        changed = False
        entries = self.data.get("schedule", {}).get("entries", [])
        used = {e.get("id") for e in entries if e.get("id")}
        n = 1
        for e in entries:
            if not e.get("id"):
                while f"e{n}" in used:
                    n += 1
                e["id"] = f"e{n}"
                used.add(e["id"])
                changed = True
        return changed

    @property
    def media_dir(self) -> Path:
        md = self.data.get("media_dir")
        return Path(md) if md else self.path.parent / "media"

    def set_entry(self, entry_id: str, **fields) -> bool:
        """Einzelnen Fahrplan-Eintrag ändern (z. B. enabled, skip_date)."""
        with self._lock:
            for e in self.data.get("schedule", {}).get("entries", []):
                if e.get("id") == entry_id:
                    e.update(fields)
                    self._write_unlocked()
                    return True
        return False

    def save(self) -> None:
        with self._lock:
            self._write_unlocked()

    def _write_unlocked(self) -> None:
        """Atomar schreiben; Aufrufer hält bereits die Lock."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    # bequemer Zugriff -----------------------------------------------------
    def get(self, *keys: str, default: Any = None) -> Any:
        node: Any = self.data
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node

    def update(self, new: dict[str, Any]) -> None:
        with self._lock:
            self.data = _merge(self.data, new)
            self._normalize()
            self._write_unlocked()

    def station(self, station_id: str) -> dict[str, Any] | None:
        for s in self.data.get("stations", []):
            if s.get("id") == station_id:
                return s
        return None


def _merge(base: dict, over: dict) -> dict:
    """Rekursives Mischen: ``over`` gewinnt, Listen werden ersetzt."""
    out = dict(base)
    for k, v in over.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out
