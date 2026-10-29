"""Engine: Handumschaltung, Prioritätsleiter (SAME schlägt Basis)."""

import os
import time

import numpy as np
import pytest

from satellit.config import Config
from satellit.engine import Engine
from satellit.output import SilentOutput
from satellit.funk.same import build_header, parse_header


def _engine(tmp_path):
    c = Config(path=os.path.join(tmp_path, "c.json"))
    c.data["stations"] = [
        {"id": "a", "name": "Rauschen", "kind": "noise", "noise": 0.05, "freq": 98.4},
        {"id": "b", "name": "Stille", "kind": "silence", "freq": 0.783},
    ]
    c.data["funk"] = {"enabled": True}
    c.data["schedule"]["enabled"] = False
    c.data["watcher"]["enabled"] = False
    c.data["same"]["sources"] = []
    c.data["same"]["fips"] = ["024031"]
    return Engine(c, output=SilentOutput())


def test_manual_tune(tmp_path):
    eng = _engine(tmp_path)
    eng.start()
    try:
        assert eng.tune("a")
        time.sleep(0.6)
        assert eng.committed_label == "Rauschen"
        assert eng.tune("b")
        time.sleep(0.6)
        assert eng.committed_label == "Stille"
        assert eng.tune("nope") is False
    finally:
        eng.stop()


def test_same_warning_takes_over_in_area(tmp_path):
    eng = _engine(tmp_path)
    eng.start()
    try:
        eng.tune("a")
        time.sleep(0.5)
        hdr = parse_header(build_header(event="TOR", locations=["024031"]))
        eng.funk._on_same_header(hdr)
        time.sleep(0.6)
        assert eng.funk.layer_same is not None
        assert "Tornadowarnung" in eng.committed_label
        assert eng.committed_reason == "SAME"
    finally:
        eng.stop()


def test_same_ignores_foreign_area(tmp_path):
    eng = _engine(tmp_path)
    eng.start()
    try:
        eng.tune("a")
        time.sleep(0.4)
        eng.funk._on_same_header(parse_header(build_header(event="TOR", locations=["099999"])))
        time.sleep(0.3)
        assert eng.funk.layer_same is None
        assert eng.committed_label == "Rauschen"
    finally:
        eng.stop()


def test_same_test_event_only_logs(tmp_path):
    eng = _engine(tmp_path)
    eng.start()
    try:
        eng.funk._on_same_header(parse_header(build_header(event="RWT", locations=["024031"])))
        time.sleep(0.3)
        assert eng.funk.layer_same is None            # keine Übernahme
        assert any(h["event"] == "RWT" for h in eng.funk.last_same)  # aber protokolliert
    finally:
        eng.stop()


def test_ean_national_takes_over_even_foreign(tmp_path):
    eng = _engine(tmp_path)
    eng.start()
    try:
        eng.tune("a")
        time.sleep(0.4)
        eng.funk._on_same_header(parse_header(build_header(org="PEP", event="EAN",
                                                      locations=["099999"])))
        time.sleep(0.6)
        assert eng.funk.layer_same is not None
        assert eng.funk.layer_same["level"] == 4      # L_SAME_EAN
    finally:
        eng.stop()


def test_render_shape(tmp_path):
    eng = _engine(tmp_path)
    eng.start()
    try:
        block = eng.render(1024)
        assert block.shape == (1024, 2)
        assert block.dtype == np.float32
    finally:
        eng.stop()


def test_running_source_survives_short_buffer_dips():
    # live über LTE: Puffer kurz unter der Startschwelle, Ton kommt aber weiter
    from satellit.sources.base import Source
    s = Source(name="kiwi")
    now = time.time()
    s.started_at = now - 600            # läuft seit zehn Minuten
    s.status, s.was_ready, s.last_audio = "playing", True, now
    assert not s.ready
    assert not s.waited_too_long(), "Puffer-Delle ist kein Ausfall"
    s.last_audio = now - 10             # wirklich nichts mehr gekommen
    assert s.waited_too_long()
    s.last_audio, s.status = now, "error"
    assert s.waited_too_long()


def test_mixer_follows_reconnected_source(tmp_path):
    eng = _engine(tmp_path)
    eng.start()
    try:
        assert eng.tune("a")
        deadline = time.time() + 3
        while eng.committed_label != "Rauschen" and time.time() < deadline:
            time.sleep(0.05)
        old = eng._sources["a"]
        assert eng._committed_source is old
        old.status, old.error = "error", "Verbindung verloren"   # Ausfall
        old.started_at -= 120                                    # Neuversuch fällig
        deadline = time.time() + 5
        while eng._committed_source is old and time.time() < deadline:
            time.sleep(0.05)
        new = eng._committed_source
        assert new is not old, "Mixer spielt noch die alte, gestoppte Quelle"
        assert new is eng._sources["a"] and new.status == "playing"
        assert eng.committed_label == "Rauschen"
    finally:
        eng.stop()


def test_idle_sources_are_closed(tmp_path, monkeypatch):
    import satellit.engine as engine_mod
    monkeypatch.setattr(engine_mod, "IDLE_CLOSE_SECONDS", 0.5)
    eng = _engine(tmp_path)
    eng.start()
    try:
        assert eng.tune("a")
        deadline = time.time() + 3
        while eng.committed_label != "Rauschen" and time.time() < deadline:
            time.sleep(0.05)
        old = eng._sources["a"]
        assert eng.tune("b")
        deadline = time.time() + 3
        while eng.committed_label != "Stille" and time.time() < deadline:
            time.sleep(0.05)
        # Überblendung (4 s) abwarten, dann muss "a" geschlossen werden
        deadline = time.time() + 8
        while "a" in eng._sources and time.time() < deadline:
            time.sleep(0.1)
        assert "a" not in eng._sources, "nicht mehr gehörte Quelle bleibt offen"
        time.sleep(0.5)
        assert old.status == "stopped"
        assert "b" in eng._sources, "laufende Quelle darf nicht geschlossen werden"
    finally:
        eng.stop()


def test_wake_entry_fades_in_from_zero_with_own_fade(tmp_path):
    """Weck-Eintrag: erst auf 0, dann über die eigene (längere) fade einblenden."""
    from satellit.scheduler import ScheduleEntry
    eng = _engine(tmp_path)
    eng.start()
    try:
        eng.tune("a")
        time.sleep(0.6)
        assert eng.mixer.master == 1.0
        eng._apply_entry(ScheduleEntry(time="06:00", station="b", fade=600, wake=True))
        for _ in range(60):
            if eng.mixer.master == 0.0:
                break
            time.sleep(0.05)
        assert eng.mixer.master == 0.0
        time.sleep(0.6)
        assert eng.mixer.master_to == 1.0
        assert 0.0 < eng.mixer.master < 0.01          # 600 s, nicht wake_seconds
        assert eng.committed_label == "Stille"
        assert eng.mixer.crossfade in (0.0, 1.0)      # alter Sender schon ganz weg
        eng._apply_entry(ScheduleEntry(time="06:10", station="a", fade=8))
        time.sleep(0.6)
        assert eng.mixer.master > 0.1                 # normaler Eintrag: zügig hoch
    finally:
        eng.stop()
