"""Programm-Modus: Dateiquellen, Wochenplan, Einspielungs-Regeln, Ersatzbetrieb."""

import os
import time
import wave
from datetime import datetime, timedelta

import numpy as np
import pytest

from satellit.config import Config
from satellit.engine import Engine
from satellit.media import resolve, safe_name
from satellit.mixer import Mixer
from satellit.output import SilentOutput
from satellit.scheduler import Scheduler
from satellit.sources.file import FileSource, FolderSource, read_wav


def write_wav(path, seconds=0.4, rate=48000, freq=440.0, channels=1):
    t = np.arange(int(rate * seconds)) / rate
    s = (np.sin(2 * np.pi * freq * t) * 0.4 * 32767).astype("<i2")
    if channels == 2:
        s = np.repeat(s[:, None], 2, axis=1)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(s.tobytes())
    return path


def wait_for(cond, timeout=8.0, step=0.02):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if cond():
            return True
        time.sleep(step)
    return False


# --- Dateiquellen -----------------------------------------------------------
def test_read_wav_resamples(tmp_path):
    p = write_wav(tmp_path / "a.wav", seconds=1.0, rate=44100)
    data = read_wav(p)
    assert data.shape[1] == 2
    assert abs(len(data) - 48000) <= 2


def test_file_source_finishes(tmp_path):
    p = write_wav(tmp_path / "a.wav", seconds=0.3)
    src = FileSource(p, loop=False).start()
    assert wait_for(lambda: src.ready)
    pulled = 0
    while not src.finished and pulled < 48000 * 2:
        pulled += int(np.count_nonzero(np.any(src.read(1024), axis=1)))
        time.sleep(0.001)
    assert src.finished
    assert abs(pulled - int(0.3 * 48000)) < 1500


def test_file_source_missing(tmp_path):
    src = FileSource(tmp_path / "fehlt.wav").start()
    assert wait_for(lambda: src.status == "error")
    assert src.finished and "fehlt" in src.error


def test_folder_source_plays(tmp_path):
    write_wav(tmp_path / "x.wav")
    write_wav(tmp_path / "y.wav")
    src = FolderSource(tmp_path).start()
    assert wait_for(lambda: src.ready)
    assert src.current in ("x", "y")
    src.stop()


def test_folder_source_empty(tmp_path):
    src = FolderSource(tmp_path).start()
    assert wait_for(lambda: src.failed)


# --- Medien-Sicherheit ------------------------------------------------------
def test_safe_name_rejects_paths_and_types():
    assert safe_name("../../etc/passwd") is None
    assert safe_name("evil.exe") is None
    assert safe_name("..\\x.mp3") == "x.mp3"
    assert safe_name("Ansage Grippe.mp3") == "Ansage Grippe.mp3"


def test_resolve_stays_inside(tmp_path):
    assert resolve(tmp_path, "../x.wav") is None
    assert resolve(tmp_path, "musik/a.mp3") == (tmp_path / "musik" / "a.mp3").resolve()


# --- Mixer: Ducking / Overlay / Stumm --------------------------------------
class Const:
    ready = True

    def __init__(self, v):
        self.v = v

    def read(self, n):
        return np.full((n, 2), self.v, dtype=np.float32)


def test_duck_and_overlay():
    m = Mixer(auto_level=False)
    m.deck_a.source = Const(0.5)
    m.deck_o.source = Const(0.2)
    m.set_duck(0.2, seconds=0.05)
    for _ in range(20):
        m.process(1024)
    assert m.duck_settled and abs(m.duck - 0.2) < 1e-9
    m.overlay_on = True
    out = m.process(1024)
    assert np.allclose(out, 0.5 * 0.2 + 0.2, atol=1e-4)


def test_mute_silences_quickly():
    m = Mixer(auto_level=False)
    m.deck_a.source = Const(0.5)
    m.set_muted(True)
    for _ in range(30):            # 0,3 s Rampe ≈ 14 Blöcke
        out = m.process(1024)
    assert np.max(np.abs(out)) < 1e-6


# --- Wochenplan -------------------------------------------------------------
WED = datetime(2026, 10, 14, 9, 30)   # Mittwoch


def test_days_filter_and_current():
    s = Scheduler([
        {"id": "a", "time": "08:00", "station": "x", "days": ["mo", "di"]},
        {"id": "b", "time": "08:00", "station": "y", "days": ["mi"]},
    ])
    assert s.current(WED).id == "b"
    assert s.current(WED + timedelta(days=-1)).id == "a"     # Dienstag


def test_disabled_and_skip_today():
    s = Scheduler([
        {"id": "p", "time": "09:00", "play": ["g.wav"]},
        {"id": "q", "time": "09:10", "play": ["g.wav"], "enabled": False},
        {"id": "r", "time": "09:20", "play": ["g.wav"], "skip_date": "2026-10-14"},
    ])
    due = s.due_plays(WED.replace(hour=8), WED)
    assert [e.id for _, e in due] == ["p"]
    # am nächsten Tag läuft r wieder
    thu = WED + timedelta(days=1)
    assert "r" in [e.id for _, e in s.due_plays(thu.replace(hour=8), thu)]


def test_due_window_is_half_open():
    s = Scheduler([{"id": "p", "time": "09:00", "play": ["g.wav"]}])
    at = WED.replace(hour=9, minute=0)
    assert len(s.due_plays(at - timedelta(seconds=1), at)) == 1
    assert len(s.due_plays(at, at + timedelta(seconds=5))) == 0   # nicht doppelt


def test_next_includes_plays():
    s = Scheduler([
        {"id": "m", "time": "08:00", "station": "x"},
        {"id": "p", "time": "10:00", "play": ["g.wav"]},
    ])
    assert s.next(WED).id == "p"


def test_config_assigns_stable_ids(tmp_path):
    p = tmp_path / "c.json"
    c = Config(path=p).load()
    ids = [e["id"] for e in c.data["schedule"]["entries"]]
    assert all(ids) and len(set(ids)) == len(ids)
    c2 = Config(path=p).load()
    assert [e["id"] for e in c2.data["schedule"]["entries"]] == ids


# --- Engine: Einspielungs-Regeln --------------------------------------------
@pytest.fixture
def eng(tmp_path):
    c = Config(path=os.path.join(tmp_path, "c.json"))
    c.data["mode"] = "program"
    c.data["stations"] = [
        {"id": "prog", "name": "Programm", "kind": "noise", "noise": 0.02},
        {"id": "musik", "name": "Musik (lokal)", "kind": "folder", "path": "musik"},
        {"id": "kaputt", "name": "Internet", "kind": "file", "path": "gibtsnicht.wav"},
        {"id": "kaputt2", "name": "Kiwi A", "kind": "file", "path": "gibtsnicht.wav",
         "fallback": "prog"},
    ]
    c.data["fallback"] = "musik"
    c.data["schedule"]["entries"] = []
    c.data["schedule"]["enabled"] = False
    c.data["watcher"]["enabled"] = False
    c.data["same"]["sources"] = []
    c.data["announce"].update(duck_seconds=0.1, release_seconds=0.1)
    md = c.media_dir
    (md / "musik").mkdir(parents=True)
    write_wav(md / "musik" / "t1.wav", seconds=2.0, freq=220)
    write_wav(md / "kurz.wav", seconds=0.3)
    e = Engine(c, output=SilentOutput())
    e.start()
    yield e
    e.stop()


def labels(e):
    return [l["text"] for l in reversed(e.log)]


def test_announcement_plays_to_end_and_restores(eng):
    eng.tune("prog")
    assert wait_for(lambda: eng.committed_label == "Programm")
    eng.play_now(["kurz.wav"], "Ansage")
    assert wait_for(lambda: eng.oneshot and eng.oneshot["phase"] == "playing")
    assert eng.mixer.duck < 0.5
    assert wait_for(lambda: eng.oneshot is None and eng.mixer.duck_settled)
    assert eng.mixer.duck == 1.0
    assert "gespielt: Ansage" in labels(eng)


def test_overlap_runs_back_to_back_without_raising(eng):
    eng.tune("prog")
    assert wait_for(lambda: eng.committed_label == "Programm")
    eng.play_now(["kurz.wav"], "Eins")
    eng.play_now(["kurz.wav"], "Zwei")
    assert wait_for(lambda: "gespielt: Eins" in labels(eng))
    # zwischen den Ansagen fährt die Musik nicht hoch
    assert eng.mixer.duck_to < 1.0
    assert wait_for(lambda: "gespielt: Zwei" in labels(eng))
    log = labels(eng)
    assert log.index("gespielt: Eins") < log.index("läuft: Zwei")


def test_schedule_change_does_not_cut_announcement(eng):
    eng.tune("prog")
    assert wait_for(lambda: eng.committed_label == "Programm")
    write_wav(eng.config.media_dir / "lang.wav", seconds=1.5)
    eng.play_now(["lang.wav"], "Lang")
    assert wait_for(lambda: eng.oneshot and eng.oneshot["phase"] == "playing")
    eng.tune("musik")                  # Programmwechsel mitten in der Ansage
    time.sleep(0.4)
    assert eng.oneshot is not None and eng.oneshot["phase"] == "playing"
    assert wait_for(lambda: "gespielt: Lang" in labels(eng))
    assert wait_for(lambda: eng.committed_label == "Musik (lokal)")


def test_stale_announcement_dropped(eng):
    eng._enqueue({"files": ["kurz.wav"], "label": "Alt", "mode": "duck",
                  "due": time.time() - 3600, "source": "Plan"})
    assert wait_for(lambda: "verworfen (zu spät): Alt" in labels(eng))


def test_mute_cuts_and_skips(eng):
    write_wav(eng.config.media_dir / "lang.wav", seconds=2.0)
    eng.play_now(["lang.wav"], "Lang")
    assert wait_for(lambda: eng.oneshot and eng.oneshot["phase"] == "playing")
    eng.set_muted(True)
    assert eng.oneshot is None
    assert any("abgebrochen (stumm" in t for t in labels(eng))
    eng.play_now(["kurz.wav"], "Während stumm")
    time.sleep(0.4)
    assert eng.oneshot is None         # wartet, spielt nicht leise ins Leere
    eng.set_muted(False)
    assert wait_for(lambda: "gespielt: Während stumm" in labels(eng))


def test_missing_file_logged_and_skipped(eng):
    eng.play_now(["gibtsnicht.mp3", "kurz.wav"], "Teilweise")
    assert wait_for(lambda: "gespielt: Teilweise" in labels(eng))
    assert "Datei fehlt: gibtsnicht.mp3" in labels(eng)


def test_fallback_when_source_dead(eng):
    eng.tune("kaputt")
    assert wait_for(lambda: eng.committed_label == "Musik (lokal)", timeout=6)
    assert eng.fallback_active
    assert eng.committed_reason == "Ersatz"


def test_station_specific_fallback_wins(eng):
    eng.tune("kaputt2")
    # "Programm" ist auch der Startsender – daher auf Sender UND Grund warten
    assert wait_for(lambda: (eng.committed_label, eng.committed_reason)
                    == ("Programm", "Ersatz"), timeout=6)
    assert eng.fallback_active


def test_scheduled_play_is_triggered(eng):
    now = datetime.now()
    hhmm = (now + timedelta(minutes=1)).strftime("%H:%M")
    eng.config.data["schedule"]["entries"] = [
        {"id": "x", "time": hhmm, "play": ["kurz.wav"], "label": "Geplant"}]
    eng.config.data["schedule"]["enabled"] = True
    eng.reload_schedule()
    # Fälligkeit simulieren: letzte Prüfung kurz vor dem Termin
    due = datetime.strptime(hhmm, "%H:%M").replace(year=now.year, month=now.month,
                                                   day=now.day)
    if due < now:
        due += timedelta(days=1)
    eng._last_due_check = due - timedelta(seconds=1)
    eng._check_due(due)
    assert wait_for(lambda: "gespielt: Geplant" in labels(eng))


def test_state_reports_missing_files(eng):
    eng.config.data["schedule"]["entries"] = [
        {"id": "m", "time": "09:00", "play": ["gong.wav", "fehlt.mp3"]}]
    eng.reload_schedule()
    st = eng.state()
    assert st["schedule"]["missing"] == {"m": ["fehlt.mp3"]}
