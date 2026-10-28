"""Hörfahrplan: aktueller/nächster Eintrag, Umlauf über Mitternacht."""

from datetime import datetime

from satellit.scheduler import Scheduler

ENTRIES = [
    {"time": "06:30", "station": "mw1", "fade": 90, "wake": True},
    {"time": "08:30", "station": "fm1", "fade": 8},
    {"time": "23:00", "action": "sleep", "fade": 120},
]


def at(h, m):
    return datetime(2026, 10, 14, h, m)


def test_current_entry():
    s = Scheduler(ENTRIES)
    assert s.current(at(7, 0)).station == "mw1"
    assert s.current(at(9, 0)).station == "fm1"
    assert s.current(at(23, 30)).action == "sleep"


def test_before_first_wraps_to_last():
    s = Scheduler(ENTRIES)
    cur = s.current(at(3, 0))          # vor 06:30 -> letzter von „gestern"
    assert cur.action == "sleep"


def test_next_entry_and_wrap():
    s = Scheduler(ENTRIES)
    assert s.next(at(7, 0)).station == "fm1"
    assert s.next(at(23, 30)).station == "mw1"   # nach letztem -> erster morgen


def test_wake_flag_and_sort():
    s = Scheduler([ENTRIES[2], ENTRIES[0], ENTRIES[1]])   # unsortiert rein
    times = [e.time for e in s.entries]
    assert times == ["06:30", "08:30", "23:00"]
    assert s.current(at(6, 45)).wake is True


def test_disabled_returns_none():
    s = Scheduler(ENTRIES, enabled=False)
    assert s.current(at(7, 0)) is None
    assert s.state()["enabled"] is False
