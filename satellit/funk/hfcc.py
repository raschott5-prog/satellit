"""Sendeplan der HFCC – was läuft gerade auf dieser Kurzwellenfrequenz?

Die High Frequency Co-ordination Conference veröffentlicht pro Saison
(A = Sommer ab letztem Märzsonntag, B = Winter ab letztem Oktobersonntag)
die angemeldeten Sendungen aller großen Kurzwellensender als Zip
(~160 KB, ``http://www.hfcc.org/data/b26/b26allx2.zip``):

* ``B26all00.TXT`` – eine Sendung pro Zeile im festen ITU-Spaltenformat
  (Frequenz, Zeit UTC, Standort, kW, Richtung, Tage, Gültigkeit, Sprache …)
* ``broadcas.txt`` / ``site.txt`` / ``language.txt`` – Nachschlagetabellen

Achtung: Wochentage zählen ab Sonntag (1 = So, 2 = Mo … 7 = Sa).

Die Datei wird beim ersten Bedarf geladen, im Konfigordner zwischengespeichert
und wöchentlich erneuert. Ohne Netz bleibt einfach alles leer.
"""

from __future__ import annotations

import io
import os
import threading
import time
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

DEFAULT_BASE = "http://www.hfcc.org/data"      # hfcc.org spricht kein HTTPS
FREQ_TOLERANCE_KHZ = 2

# ISO 639-3 (HFCC) -> Whisper-Sprachcode; was hier fehlt, kennt Whisper nicht
ISO3_TO_WHISPER = {
    "eng": "en", "zho": "zh", "chn": "zh", "cmn": "zh", "yue": "zh", "nan": "zh",
    "hak": "zh", "jpn": "ja", "fra": "fr", "rus": "ru", "kor": "ko", "ara": "ar",
    "arb": "ar", "apd": "ar", "spa": "es", "prs": "fa", "fas": "fa", "deu": "de",
    "pus": "ps", "pst": "ps", "pbt": "ps", "nld": "nl", "vie": "vi", "mon": "mn",
    "mvf": "mn", "por": "pt", "ron": "ro", "rup": "ro", "som": "so", "amh": "am",
    "urd": "ur", "ind": "id", "hin": "hi", "swa": "sw", "mya": "my", "ben": "bn",
    "tur": "tr", "fil": "tl", "kaz": "kk", "tam": "ta", "nep": "ne", "ita": "it",
    "khm": "km", "bod": "bo", "khg": "bo", "hau": "ha", "ukr": "uk", "srp": "sr",
    "hun": "hu", "bul": "bg", "sin": "si", "ces": "cs", "tha": "th", "mly": "ms",
    "msa": "ms", "sqi": "sq", "aae": "sq", "hrv": "hr", "lao": "lo", "hye": "hy",
    "axm": "hy", "lat": "la", "jav": "jw", "tgk": "tg", "pol": "pl", "mlg": "mg",
    "heb": "he", "kan": "kn", "mal": "ml", "nor": "no", "bel": "be", "kat": "ka",
    "aze": "az", "yor": "yo", "uzb": "uz", "tat": "tt", "snd": "sd", "sun": "su",
    "tel": "te", "asm": "as", "tuk": "tk", "slk": "sk", "slv": "sl", "lit": "lt",
    "lav": "lv", "est": "et", "fin": "fi", "swe": "sv", "dan": "da", "ell": "el",
    "mkd": "mk", "bos": "bs", "cat": "ca", "glg": "gl", "eus": "eu", "isl": "is",
    "mlt": "mt", "cym": "cy", "afr": "af", "sna": "sn", "lin": "ln", "yid": "yi",
    "pan": "pa", "guj": "gu", "mar": "mr", "ori": "or", "haw": "haw", "mri": "mi",
}


# ---------------------------------------------------------------------------
# Saison
# ---------------------------------------------------------------------------
def _last_sunday(year: int, month: int) -> date:
    d = date(year, month + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - 6) % 7)


def season_for(day: date) -> str:
    """Datum -> HFCC-Saison, z. B. 2026-11-03 -> "b26", 2027-01-10 -> "b26"."""
    y = day.year
    if day >= _last_sunday(y, 10):
        return f"b{y % 100:02d}"
    if day >= _last_sunday(y, 3):
        return f"a{y % 100:02d}"
    return f"b{(y - 1) % 100:02d}"


def previous_season(season: str) -> str:
    yy = int(season[1:])
    return f"a{yy:02d}" if season[0] == "b" else f"b{(yy - 1) % 100:02d}"


def whisper_langs(code: str) -> list[str]:
    """HFCC-Sprachcode (auch zusammengesetzt wie "NldEng") -> Whisper-Codes.

    Ein Teil, den Whisper nicht kennt (Uigurisch, "Mul" = mehrsprachig …),
    ergibt ``None`` in der Liste – dann ist der Hinweis unvollständig.
    """
    parts = [code[i:i + 3].lower() for i in range(0, len(code), 3)] or [""]
    return [ISO3_TO_WHISPER.get(p) for p in parts]


# ---------------------------------------------------------------------------
# Datei lesen
# ---------------------------------------------------------------------------
_COLUMNS = ["freq", "start", "stop", "ciraf", "loc", "power", "azimuth", "slew", "ant",
            "days", "fdate", "tdate", "mod", "afrq", "lang", "adm", "brc", "fmo", "req",
            "old", "alt1", "alt2", "alt3", "notes"]


def _table(text: str, width: int = 3) -> dict[str, str]:
    out = {}
    for line in text.lstrip("﻿").splitlines():
        if line.startswith(";") or len(line) <= width:
            continue
        out[line[:width].strip()] = line[width:].strip()
    return out


def _ddmmyy(s: str) -> str:
    return s[4:6] + s[2:4] + s[0:2] if len(s) == 6 else ""


def parse_schedule(text: str) -> list[dict]:
    """Hauptdatei im ITU-Spaltenformat -> Liste von Zeilen-Dicts."""
    lines = text.splitlines()
    ruler = next((ln for ln in lines if ln.startswith(";----+")), None)
    if ruler is None:
        raise ValueError("kein HFCC-Format (Linealzeile fehlt)")
    cuts = [0] + [i for i, c in enumerate(ruler) if c == "+"] + [len(ruler) + 40]
    rows = []
    for ln in lines:
        if ln.startswith(";") or not ln.strip():
            continue
        f = dict(zip(_COLUMNS, (ln[a:b].strip() for a, b in zip(cuts, cuts[1:]))))
        try:
            f["freq"] = int(f["freq"])
            f["start"], f["stop"] = int(f["start"]), int(f["stop"])
            f["power"] = int(f["power"] or 0)
        except (KeyError, ValueError):
            continue
        f["from"], f["to"] = _ddmmyy(f.get("fdate", "")), _ddmmyy(f.get("tdate", ""))
        rows.append(f)
    return rows


def _on_air(row: dict, when: datetime) -> bool:
    t = when.hour * 100 + when.minute
    a, b = row["start"], row["stop"]
    if not (a <= t < b if a < b else t >= a or t < b):
        return False
    # Sendetag = Tag des Beginns; über Mitternacht gilt der Vortag
    day = when if (a < b or t >= a) else when - timedelta(days=1)
    days = row.get("days") or "1234567"
    if str(day.isoweekday() % 7 + 1) not in days:          # 1 = Sonntag
        return False
    d = day.strftime("%y%m%d")
    return (not row["from"] or row["from"] <= d) and (not row["to"] or d <= row["to"])


class Schedule:
    """Eine geladene Saison mit Index nach Frequenz."""

    def __init__(self, zip_bytes: bytes, season: str = ""):
        self.season = season
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            names = {n.lower(): n for n in z.namelist()}

            def read(name: str, enc: str = "latin-1") -> str:
                return z.read(names[name]).decode(enc, errors="replace")

            main = next((n for n in names if n.endswith("all00.txt")), None)
            if main is None:
                raise ValueError("HFCC-Zip ohne Hauptdatei")
            rows = parse_schedule(read(main))
            self.broadcasters = _table(read("broadcas.txt")) if "broadcas.txt" in names else {}
            self.languages = _table(read("language.txt", "utf-8-sig")) if "language.txt" in names else {}
            self.sites = {k: v[:30].strip() for k, v in
                          (_table(read("site.txt")) if "site.txt" in names else {}).items()}
        self.by_freq: dict[int, list[dict]] = {}
        for r in rows:
            self.by_freq.setdefault(r["freq"], []).append(r)
        self.rows = len(rows)

    def on_air(self, freq_khz: float, when: Optional[datetime] = None) -> list[dict]:
        """Sendungen auf ``freq_khz`` (±2 kHz) zum Zeitpunkt (UTC), stärkste zuerst."""
        when = when or datetime.now(timezone.utc)
        f = int(round(freq_khz))
        hits = []
        for k in range(f - FREQ_TOLERANCE_KHZ, f + FREQ_TOLERANCE_KHZ + 1):
            for r in self.by_freq.get(k, ()):
                if _on_air(r, when):
                    hits.append(self._describe(r))
        # doppelte Zeilen (gleiche Sendung, mehrere Antennen) zusammenfassen
        seen, out = set(), []
        for h in sorted(hits, key=lambda h: -h["power"]):
            key = (h["broadcaster"], h["lang"], h["site"], h["start"], h["stop"])
            if key not in seen:
                seen.add(key)
                out.append(h)
        return out

    def _describe(self, r: dict) -> dict:
        langs = whisper_langs(r["lang"])
        name = self.broadcasters.get(r["brc"], r["brc"])
        return {
            "short": short_name(name, r["brc"]),
            "lang_de": german_lang(langs, self.languages.get(r["lang"], r["lang"])),
            "freq": r["freq"], "start": f'{r["start"]:04d}', "stop": f'{r["stop"]:04d}',
            "broadcaster": self.broadcasters.get(r["brc"], r["brc"]), "brc": r["brc"],
            "lang": r["lang"], "lang_name": self.languages.get(r["lang"], r["lang"]),
            "whisper": langs,
            "site": self.sites.get(r["loc"], r["loc"]), "power": r["power"],
            "azimuth": r.get("azimuth", ""),
        }


def short_name(name: str, code: str) -> str:
    """Für die enge LCD-Zeile: "… (USAGM)" -> "USAGM", sehr lange -> Kürzel."""
    known = {"CRI": "CRI", "CNR": "CNR", "BBC": "BBC", "KBS": "KBS", "NHK": "NHK",
             "AIR": "AIR", "TRT": "TRT", "AWR": "AWR", "FEC": "FEBC", "IRB": "IRIB"}
    if code in known:
        return known[code]
    if name.endswith(")") and "(" in name:
        inner = name[name.rindex("(") + 1:-1]
        if len(inner) <= 12 and inner.isupper():
            return inner
    return name if len(name) <= 26 else code


def german_lang(langs: list, fallback: str) -> str:
    from .translate import LANG_NAMES
    names = [LANG_NAMES.get(c) for c in langs]
    if names and all(names):
        return " / ".join(names)
    return EXTRA_NAMES.get(fallback, fallback)


# Sprachen ohne Whisper-Unterstützung, die auf Kurzwelle oft vorkommen
EXTRA_NAMES = {"Uighur": "Uigurisch", "Multiple languages": "mehrsprachig",
               "Undetermined": "unbestimmt", "Tigrinya": "Tigrinya", "Oromo": "Oromo",
               "Kinyarwanda": "Kinyarwanda", "Esperanto": "Esperanto", "Kurdish": "Kurdisch",
               "Kirghiz": "Kirgisisch", "Dari": "Dari", "Hausa": "Hausa"}


def candidates(entries: list[dict]) -> Optional[list[str]]:
    """Whisper-Sprachen, die laut Plan in Frage kommen.

    ``None``, wenn nichts bekannt ist oder eine Sendung eine Sprache hat, die
    Whisper nicht kennt – dann darf Whisper frei erkennen.
    """
    out: list[str] = []
    for e in entries:
        for code in e["whisper"]:
            if code is None:
                return None
            if code not in out:
                out.append(code)
    return out or None


# ---------------------------------------------------------------------------
# Laden und Zwischenspeichern
# ---------------------------------------------------------------------------
class HFCC:
    """Holt die passende Saison einmal und hält sie im Speicher."""

    def __init__(self, cache_dir: os.PathLike | str, base_url: str = DEFAULT_BASE,
                 refresh_days: float = 7.0, log: Callable[[str], None] = lambda t: None,
                 fetch: Optional[Callable[[str], bytes]] = None):
        self.cache_dir = Path(cache_dir)
        self.base_url = base_url.rstrip("/")
        self.refresh_days = refresh_days
        self.log = log
        self.fetch = fetch or self._http_get
        self.schedule: Optional[Schedule] = None
        self.error: Optional[str] = None
        self._lock = threading.Lock()
        self._busy = False

    @staticmethod
    def _http_get(url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "Satellit"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()

    def _file(self, season: str) -> Path:
        return self.cache_dir / f"{season}allx2.zip"

    def ensure(self, background: bool = True) -> None:
        """Saison laden (aus dem Zwischenspeicher, sonst/zu alt aus dem Netz)."""
        with self._lock:
            if self._busy:
                return
            season = season_for(datetime.now(timezone.utc).date())
            fresh = self.schedule is not None and self.schedule.season == season
            path = self._file(season)
            stale = not path.exists() or \
                time.time() - path.stat().st_mtime > self.refresh_days * 86400
            if fresh and not stale:
                return
            self._busy = True
        if background:
            threading.Thread(target=self._load, args=(season,), name="hfcc", daemon=True).start()
        else:
            self._load(season)

    def _fresh(self, season: str) -> bool:
        p = self._file(season)
        return p.exists() and time.time() - p.stat().st_mtime <= self.refresh_days * 86400

    def _from_cache(self, season: str) -> bool:
        try:
            self.schedule = Schedule(self._file(season).read_bytes(), season)
            return True
        except Exception:
            return False

    def _download(self, season: str) -> bool:
        try:
            data = self.fetch(f"{self.base_url}/{season}/{season}allx2.zip")
            sched = Schedule(data, season)
        except Exception as exc:
            self.error = f"{season.upper()}: {exc}"
            return False
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._file(season).with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, self._file(season))
        self.schedule, self.error = sched, None
        self.log(f"Sendeplan HFCC {season.upper()} geladen ({sched.rows} Sendungen)")
        return True

    def _load(self, season: str) -> None:
        try:
            # erst der Zwischenspeicher: sofort etwas anzeigen, auch offline
            if self.schedule is None or self.schedule.season != season:
                if not (self._file(season).exists() and self._from_cache(season)):
                    prev = previous_season(season)
                    if self._file(prev).exists():
                        self._from_cache(prev)
            if self._fresh(season):
                return
            if self._download(season):
                return
            # neue Saison noch nicht veröffentlicht -> die alte tut es solange
            have = self.schedule.season if self.schedule else None
            if have != season and not self._fresh(previous_season(season)):
                self._download(previous_season(season))
            if self.error:
                self.log("Sendeplan HFCC nicht ladbar: " + self.error)
        finally:
            with self._lock:
                self._busy = False

    def on_air(self, freq_khz: float, when: Optional[datetime] = None) -> list[dict]:
        """Sendungen auf ``freq_khz`` (±2 kHz) zum Zeitpunkt (UTC), stärkste zuerst."""
        when = when or datetime.now(timezone.utc)
        f = int(round(freq_khz))
        hits = []
        for k in range(f - FREQ_TOLERANCE_KHZ, f + FREQ_TOLERANCE_KHZ + 1):
            for r in self.by_freq.get(k, ()):
                if _on_air(r, when):
                    hits.append(self._describe(r))
        # doppelte Zeilen (gleiche Sendung, mehrere Antennen) zusammenfassen
        seen, out = set(), []
        for h in sorted(hits, key=lambda h: -h["power"]):
            key = (h["broadcaster"], h["lang"], h["site"], h["start"], h["stop"])
            if key not in seen:
                seen.add(key)
                out.append(h)
        return out

    def _describe(self, r: dict) -> dict:
        langs = whisper_langs(r["lang"])
        return {
            "freq": r["freq"], "start": f'{r["start"]:04d}', "stop": f'{r["stop"]:04d}',
            "broadcaster": self.broadcasters.get(r["brc"], r["brc"]), "brc": r["brc"],
            "lang": r["lang"], "lang_name": self.languages.get(r["lang"], r["lang"]),
            "whisper": langs,
            "site": self.sites.get(r["loc"], r["loc"]), "power": r["power"],
            "azimuth": r.get("azimuth", ""),
        }


def candidates(entries: list[dict]) -> Optional[list[str]]:
    """Whisper-Sprachen, die laut Plan in Frage kommen.

    ``None``, wenn nichts bekannt ist oder eine Sendung eine Sprache hat, die
    Whisper nicht kennt – dann darf Whisper frei erkennen.
    """
    out: list[str] = []
    for e in entries:
        for code in e["whisper"]:
            if code is None:
                return None
            if code not in out:
                out.append(code)
    return out or None


# ---------------------------------------------------------------------------
# Laden und Zwischenspeichern
# ---------------------------------------------------------------------------
class HFCC:
    """Holt die passende Saison einmal und hält sie im Speicher."""

    def __init__(self, cache_dir: os.PathLike | str, base_url: str = DEFAULT_BASE,
                 refresh_days: float = 7.0, log: Callable[[str], None] = lambda t: None,
                 fetch: Optional[Callable[[str], bytes]] = None):
        self.cache_dir = Path(cache_dir)
        self.base_url = base_url.rstrip("/")
        self.refresh_days = refresh_days
        self.log = log
        self.fetch = fetch or self._http_get
        self.schedule: Optional[Schedule] = None
        self.error: Optional[str] = None
        self._lock = threading.Lock()
        self._busy = False

    @staticmethod
    def _http_get(url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "Satellit"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()

    def _file(self, season: str) -> Path:
        return self.cache_dir / f"{season}allx2.zip"

    def ensure(self, background: bool = True) -> None:
        """Saison laden (aus dem Zwischenspeicher, sonst/zu alt aus dem Netz)."""
        with self._lock:
            if self._busy:
                return
            season = season_for(datetime.now(timezone.utc).date())
            fresh = self.schedule is not None and self.schedule.season == season
            path = self._file(season)
            stale = not path.exists() or \
                time.time() - path.stat().st_mtime > self.refresh_days * 86400
            if fresh and not stale:
                return
            self._busy = True
        if background:
            threading.Thread(target=self._load, args=(season,), name="hfcc", daemon=True).start()
        else:
            self._load(season)

    def _load(self, season: str) -> None:
        try:
            # erst den Zwischenspeicher: sofort etwas anzeigen, auch offline
            for s in (season, previous_season(season)):
                p = self._file(s)
                if p.exists() and (self.schedule is None or self.schedule.season != s):
                    try:
                        self.schedule = Schedule(p.read_bytes(), s)
                        break
                    except Exception:
                        pass
                elif p.exists():
                    break
            path = self._file(season)
            if path.exists() and time.time() - path.stat().st_mtime <= self.refresh_days * 86400:
                return
            for s in (season, previous_season(season)):   # neue Saison evtl. noch nicht da
                if self.schedule is not None and self.schedule.season == season and s != season:
                    break
                try:
                    data = self.fetch(f"{self.base_url}/{s}/{s}allx2.zip")
                    sched = Schedule(data, s)
                except Exception as exc:
                    self.error = f"{s.upper()}: {exc}"
                    continue
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                tmp = self._file(s).with_suffix(".tmp")
                tmp.write_bytes(data)
                os.replace(tmp, self._file(s))
                self.schedule, self.error = sched, None
                self.log(f"Sendeplan HFCC {s.upper()} geladen ({sched.rows} Sendungen)")
                return
            if self.error:
                self.log("Sendeplan HFCC nicht ladbar: " + self.error)
        finally:
            with self._lock:
                self._busy = False

    def on_air(self, freq_khz: float, when: Optional[datetime] = None) -> list[dict]:
        sched = self.schedule
        return sched.on_air(freq_khz, when) if sched is not None else []

    def state(self) -> dict:
        s = self.schedule
        return {"season": s.season.upper() if s else None,
                "rows": s.rows if s else 0, "error": self.error}
