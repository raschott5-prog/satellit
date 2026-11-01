"""Senderchronik: Wissen und Geschichten zu einem Sender, Eintrag für Eintrag.

Jeder Eintrag hat Text, Autor, Zeitpunkt (UTC) und optional eine Quelle.
Einträge werden nur hinzugefügt, nie geändert: Eine Berichtigung ist ein
neuer Eintrag mit ``replaces`` = ID des berichtigten Eintrags. So gibt es
keine Bearbeitungskonflikte, und Chroniken lassen sich gefahrlos zusammenführen
(Export/Import, später auch von Satellit zu Satellit).

Die ID ist ein Prüfwert über den Inhalt. Dieselbe Geschichte, zweimal
importiert, landet nur einmal in der Chronik, und ein nachträglich
veränderter Eintrag fällt beim Import auf.

Datei: ``chronik.json`` neben der ``config.json``.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

FORMAT = "satellit-chronik"
VERSION = 1
MAX_TEXT = 5000
MAX_AUTHOR = 80
MAX_SOURCE = 500
MAX_STATION = 80
ID_LEN = 16
FIELDS = ("station", "station_name", "text", "author", "created", "source", "replaces")


def _clean(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()[:limit]


def entry_id(entry: dict) -> str:
    """Prüfwert über alle Inhaltsfelder (stabil, unabhängig von der Reihenfolge)."""
    core = {k: entry.get(k) or "" for k in FIELDS}
    raw = json.dumps(core, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:ID_LEN]


def make_entry(station: str, text: str, author: str = "", source: str = "",
               replaces: str = "", station_name: str = "",
               created: Optional[str] = None) -> dict:
    """Neuen Eintrag bauen und prüfen. Wirft ValueError bei unbrauchbarem Inhalt."""
    e = {
        "station": _clean(station, MAX_STATION),
        "station_name": _clean(station_name, MAX_STATION),
        "text": _clean(text, MAX_TEXT),
        "author": _clean(author, MAX_AUTHOR) or "anonym",
        "created": created or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": _clean(source, MAX_SOURCE),
        "replaces": _clean(replaces, ID_LEN),
    }
    if not e["station"]:
        raise ValueError("Sender fehlt")
    if not e["text"]:
        raise ValueError("Text fehlt")
    e["id"] = entry_id(e)
    return e


def _valid(e: Any) -> bool:
    """Eintrag aus fremder Quelle: Pflichtfelder da, Längen ok, Prüfwert passt."""
    if not isinstance(e, dict):
        return False
    if not all(isinstance(e.get(k, ""), str) for k in FIELDS + ("id",)):
        return False
    if not e.get("station") or not e.get("text") or not e.get("created"):
        return False
    if (len(e["text"]) > MAX_TEXT or len(e.get("author", "")) > MAX_AUTHOR
            or len(e.get("source", "")) > MAX_SOURCE or len(e["station"]) > MAX_STATION):
        return False
    try:
        datetime.fromisoformat(e["created"])
    except ValueError:
        return False
    return e.get("id") == entry_id(e)


class Chronik:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._entries: list[dict] = []
        self._loaded = False

    # --- Laden / Speichern ------------------------------------------------
    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for e in data.get("entries", []) if isinstance(data, dict) else []:
            if _valid(e):
                self._entries.append({k: e.get(k, "") for k in FIELDS + ("id",)})

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps({"format": FORMAT, "version": VERSION, "entries": self._entries},
                          ensure_ascii=False, indent=1)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(body)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    # --- Lesen ------------------------------------------------------------
    def entries(self, station: Optional[str] = None) -> list[dict]:
        """Einträge (ältester zuerst); berichtigte Einträge tragen ``replaced_by``."""
        with self._lock:
            self._load()
            sel = [dict(e) for e in self._entries if station is None or e["station"] == station]
        by_id = {e["id"]: e for e in sel}
        for e in sel:
            if e["replaces"] and e["replaces"] in by_id:
                by_id[e["replaces"]]["replaced_by"] = e["id"]
        return sorted(sel, key=lambda e: (e["created"], e["id"]))

    def counts(self) -> dict[str, int]:
        """Anzahl gültiger (nicht berichtigter) Einträge je Sender."""
        out: dict[str, int] = {}
        for e in self.entries():
            if "replaced_by" not in e:
                out[e["station"]] = out.get(e["station"], 0) + 1
        return out

    # --- Schreiben --------------------------------------------------------
    def add(self, **kw) -> dict:
        e = make_entry(**kw)
        with self._lock:
            self._load()
            if e["replaces"] and not any(x["id"] == e["replaces"] for x in self._entries):
                raise ValueError("berichtigter Eintrag nicht gefunden")
            if not any(x["id"] == e["id"] for x in self._entries):
                self._entries.append(e)
                self._save()
        return e

    # --- Austausch --------------------------------------------------------
    def export(self, station: Optional[str] = None) -> dict:
        return {"format": FORMAT, "version": VERSION,
                "entries": [{k: e[k] for k in FIELDS + ("id",)} for e in self.entries(station)]}

    def import_(self, data: Any) -> dict:
        """Fremde Chronik übernehmen. Ergebnis: neu / schon da / ungültig."""
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            raise ValueError("keine Satellit-Chronik")
        raw = data.get("entries")
        if not isinstance(raw, list):
            raise ValueError("keine Einträge")
        added = known = invalid = 0
        with self._lock:
            self._load()
            ids = {e["id"] for e in self._entries}
            for e in raw:
                if not _valid(e):
                    invalid += 1
                    continue
                if e["id"] in ids:
                    known += 1
                    continue
                self._entries.append({k: e.get(k, "") for k in FIELDS + ("id",)})
                ids.add(e["id"])
                added += 1
            if added:
                self._save()
        return {"added": added, "known": known, "invalid": invalid}
