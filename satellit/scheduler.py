"""Hörfahrplan / Wochenplan – ein Zeitplan für Radio- und Programm-Modus.

Drei Arten von Einträgen:

    {"time": "06:30", "station": "mw1", "fade": 90, "wake": true}     # Programm
                     (wake: von null einblenden, über fade, mind. wake_seconds)
    {"time": "23:00", "action": "sleep", "fade": 120}                 # Ausblenden
    {"time": "10:00", "play": ["gong.wav", "grippe.mp3"],             # Einspielung
     "days": ["mo", "di", "mi", "do", "fr"], "mode": "duck"}

Gemeinsame Felder: ``id`` (stabil, für die Bedienung), ``days`` (Standard:
alle), ``enabled`` (aus = dauerhaft aus), ``skip_date`` (ISO-Datum: nur an
diesem Tag aussetzen).

Programm-Einträge (station/sleep) legen fest, *was läuft*: es gilt der
zuletzt fällige. Einspielungen sind *Ereignisse*: zur Uhrzeit fällig, danach
spielt die Engine sie bis zum Dateiende – das Ende eines Zeitfensters
schneidet nie mitten in eine Ansage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

DAY_NAMES = ["mo", "di", "mi", "do", "fr", "sa", "so"]
_DAY_ALIASES = {**{n: i for i, n in enumerate(DAY_NAMES)},
                "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
BASE_KINDS = {"tune", "sleep"}


def parse_days(days) -> set[int]:
    if not days:
        return set(range(7))
    out: set[int] = set()
    for d in days:
        if isinstance(d, int) and 0 <= d <= 6:
            out.add(d)
        elif isinstance(d, str) and d.strip().lower()[:3] in _DAY_ALIASES:
            out.add(_DAY_ALIASES[d.strip().lower()[:3]])
        elif isinstance(d, str) and d.strip().lower()[:2] in _DAY_ALIASES:
            out.add(_DAY_ALIASES[d.strip().lower()[:2]])
    return out or set(range(7))


@dataclass
class ScheduleEntry:
    time: str                 # "HH:MM"
    station: Optional[str] = None
    action: str = "tune"      # tune | sleep | play
    fade: float = 8.0
    wake: bool = False
    id: str = ""
    days: set[int] = field(default_factory=lambda: set(range(7)))
    enabled: bool = True
    skip_date: Optional[str] = None
    play: list[str] = field(default_factory=list)
    mode: str = "duck"        # duck | replace (nur Einspielungen)
    label: str = ""

    def minutes(self) -> int:
        h, m = self.time.split(":")
        return int(h) * 60 + int(m)

    def runs_on(self, day: date) -> bool:
        if not self.enabled or day.weekday() not in self.days:
            return False
        return self.skip_date != day.isoformat()

    def at(self, day: date) -> datetime:
        h, m = self.time.split(":")
        return datetime(day.year, day.month, day.day, int(h), int(m))

    @classmethod
    def from_dict(cls, d: dict, index: int = 0) -> "ScheduleEntry":
        play = d.get("play") or []
        if isinstance(play, str):
            play = [play]
        if play:
            action = "play"
        elif d.get("action") == "sleep":
            action = "sleep"
        else:
            action = "tune"
        return cls(time=d.get("time", "00:00"), station=d.get("station"),
                   action=action, fade=float(d.get("fade", 8.0)),
                   wake=bool(d.get("wake", False)),
                   id=str(d.get("id") or f"e{index}"),
                   days=parse_days(d.get("days")),
                   enabled=bool(d.get("enabled", True)),
                   skip_date=d.get("skip_date"), play=list(play),
                   mode=d.get("mode", "duck"), label=d.get("label", ""))

    def as_dict(self) -> dict:
        return {"id": self.id, "time": self.time, "station": self.station,
                "action": self.action, "fade": self.fade, "wake": self.wake,
                "days": [DAY_NAMES[i] for i in sorted(self.days)],
                "enabled": self.enabled, "skip_date": self.skip_date,
                "play": self.play, "mode": self.mode, "label": self.label}


class Scheduler:
    def __init__(self, entries: list[dict] | None = None, enabled: bool = True):
        self.enabled = enabled
        self.entries: list[ScheduleEntry] = []
        self.load(entries or [])

    def load(self, entries: list[dict]) -> None:
        self.entries = sorted((ScheduleEntry.from_dict(e, i) for i, e in enumerate(entries)),
                              key=lambda e: e.minutes())

    def by_id(self, entry_id: str) -> Optional[ScheduleEntry]:
        return next((e for e in self.entries if e.id == entry_id), None)

    # --- Vorkommen --------------------------------------------------------
    def occurrences(self, start: datetime, end: datetime,
                    kinds: set[str] | None = None) -> list[tuple[datetime, ScheduleEntry]]:
        """Alle Vorkommen im Intervall (start, end], zeitlich sortiert."""
        if not self.enabled:
            return []
        out = []
        day = start.date()
        while day <= end.date():
            for e in self.entries:
                if kinds and e.action not in kinds:
                    continue
                if e.runs_on(day):
                    t = e.at(day)
                    if start < t <= end:
                        out.append((t, e))
            day += timedelta(days=1)
        out.sort(key=lambda x: x[0])
        return out

    def current_occurrence(self, now: Optional[datetime] = None):
        """Zuletzt fällig gewordener Programm-Eintrag (bis 8 Tage zurück)."""
        now = now or datetime.now()
        occ = self.occurrences(now - timedelta(days=8), now, BASE_KINDS)
        return occ[-1] if occ else None

    def current(self, now: Optional[datetime] = None) -> Optional[ScheduleEntry]:
        occ = self.current_occurrence(now)
        return occ[1] if occ else None

    def next_occurrence(self, now: Optional[datetime] = None, kinds=None):
        now = now or datetime.now()
        occ = self.occurrences(now, now + timedelta(days=8), kinds)
        return occ[0] if occ else None

    def next(self, now: Optional[datetime] = None) -> Optional[ScheduleEntry]:
        occ = self.next_occurrence(now)
        return occ[1] if occ else None

    def due_plays(self, since: datetime, now: datetime):
        """Einspielungen, die im Intervall (since, now] fällig wurden."""
        return self.occurrences(since, now, {"play"})

    # --- Anzeige ----------------------------------------------------------
    def week(self) -> list[list[dict]]:
        """Pro Wochentag (Mo..So) die Einträge, die an dem Tag laufen."""
        out = []
        for d in range(7):
            out.append([e.as_dict() for e in self.entries if d in e.days])
        return out

    def state(self, now: Optional[datetime] = None) -> dict:
        now = now or datetime.now()
        cur = self.current_occurrence(now)
        nxt = self.next_occurrence(now)
        return {
            "enabled": self.enabled,
            "current": cur[1].as_dict() if cur else None,
            "next": ({**nxt[1].as_dict(), "at": nxt[0].isoformat(timespec="minutes")}
                     if nxt else None),
            "entries": [e.as_dict() for e in self.entries],
            "week": self.week(),
            "today": now.weekday(),
        }
