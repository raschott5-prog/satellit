"""Schalter zwischen Grundgerät und Funk-Teil."""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from satellit import web
from satellit.config import Config
from satellit.engine import Engine
from satellit.output import SilentOutput

ROOT = Path(__file__).resolve().parent.parent


def _cfg(tmp_path, **data):
    c = Config(path=os.path.join(tmp_path, "c.json")).load()
    c.data["stations"] = [
        {"id": "a", "name": "Rauschen", "kind": "noise", "noise": 0.05},
        {"id": "k", "name": "Kiwi", "kind": "kiwi", "host": "x", "freq_khz": 7225},
    ]
    c.data["schedule"]["enabled"] = False
    c.data["watcher"]["enabled"] = False
    c.data["same"]["sources"] = []
    c.data.update(data)
    return c


def test_new_installation_starts_as_plain_device(tmp_path):
    c = Config(path=os.path.join(tmp_path, "c.json")).load()
    assert c.get("funk", "enabled") is False and c.get("mode") == "program"
    assert all(s["kind"] not in ("kiwi", "ubersdr", "websdr") for s in c.data["stations"])
    wake = next(e for e in c.data["schedule"]["entries"] if e.get("wake"))
    assert wake["station"] == "voegel" and wake["fade"] == 3600.0   # eine Stunde
    eng = Engine(c, output=SilentOutput())
    assert eng.funk is None
    st = eng.state()
    assert st["funk"]["enabled"] is False and st["mode"] == "program"
    assert "translate" not in st and "same" not in st and "watcher" not in st


def test_plain_device_does_not_import_the_funk_part(tmp_path):
    code = (
        "import sys; from satellit.config import Config; from satellit.engine import Engine;"
        "from satellit.output import SilentOutput; import satellit.web;"
        f"c = Config(path={str(tmp_path / 'c.json')!r}).load();"
        "e = Engine(c, output=SilentOutput());"
        "print([m for m in sys.modules if m.startswith('satellit.funk.')"
        " or m.split('.')[0] in ('faster_whisper', 'websocket', 'opuslib')])")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]"


def test_sdr_station_is_silent_while_funk_is_off(tmp_path):
    eng = Engine(_cfg(tmp_path), output=SilentOutput())
    src = eng._source_for_station("k")
    assert src.status == "error" and "Funk-Teil" in src.error


def test_switch_at_runtime(tmp_path):
    c = _cfg(tmp_path)
    eng = Engine(c, output=SilentOutput())
    eng.start()
    try:
        eng.set_funk(True)
        assert eng.funk is not None and c.get("funk", "enabled") is True
        assert c.get("mode") == "radio"
        assert eng.state()["funk"]["enabled"] and "translate" in eng.state()
        assert eng.mixer.tap == eng.funk.translator.feed
        eng.set_funk(False)
        assert eng.funk is None and c.get("funk", "enabled") is False
        assert c.get("mode") == "program" and eng.mixer.tap is None
        assert eng.state()["mode"] == "program"
    finally:
        eng.stop()


@pytest.mark.parametrize("stations, funk, mode", [
    ([{"id": "k", "kind": "kiwi", "host": "x", "freq_khz": 1}], True, "radio"),
    ([{"id": "s", "kind": "stream", "url": "http://x"}], False, "program"),
])
def test_old_config_keeps_its_habits(tmp_path, stations, funk, mode):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"version": 2, "mode": "radio", "stations": stations}))
    c = Config(path=p).load()
    assert c.get("funk", "enabled") is funk and c.get("mode") == mode
    assert json.loads(p.read_text())["funk"] == {"enabled": funk}   # gleich festgeschrieben


@pytest.fixture
def server(tmp_path):
    c = _cfg(tmp_path)
    eng = Engine(c, output=SilentOutput())
    eng.start()
    handler = type("H", (web._Handler,), {"engine": eng, "config": c})
    httpd = web.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.2)
    yield f"http://127.0.0.1:{httpd.server_address[1]}", eng
    httpd.shutdown()
    eng.stop()


def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=5).read())


def test_web_without_funk(server):
    base, eng = server
    r = urllib.request.urlopen(base + "/radio", timeout=5)
    assert r.geturl().endswith("/programm")              # Radio-Ansicht gibt es nicht
    for path, body in (("/api/translate", {"enabled": True}),
                       ("/api/same/test", {"event": "TOR"}),
                       ("/api/mode", {"mode": "radio"})):
        with pytest.raises(urllib.error.HTTPError) as exc:
            _post(base + path, body)
        assert exc.value.code == 409
    # der Schalter selbst darf nicht über /api/config umgangen werden
    _post(base + "/api/config", {"funk": {"enabled": True}})
    assert eng.funk is None


def test_web_switch(server):
    base, eng = server
    r = _post(base + "/api/funk", {"enabled": True})
    assert r["enabled"] is True and isinstance(r["missing"], list)
    assert eng.funk is not None
    assert b"<html" in urllib.request.urlopen(base + "/radio", timeout=5).read().lower()
    assert _post(base + "/api/funk", {"enabled": False})["enabled"] is False
    assert eng.funk is None
