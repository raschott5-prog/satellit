"""Web-API: Zustand, Umschalten, SAME-Test über HTTP."""

import json
import os
import threading
import time
import urllib.error
import urllib.request

import pytest

from satellit.config import Config
from satellit.engine import Engine
from satellit.output import SilentOutput
from satellit import web


@pytest.fixture
def server(tmp_path):
    c = Config(path=os.path.join(tmp_path, "c.json")).load()
    c.data["stations"] = [
        {"id": "a", "name": "Rauschen", "kind": "noise", "noise": 0.05, "freq": 98.4},
    ]
    c.data["schedule"]["enabled"] = False
    c.data["watcher"]["enabled"] = False
    c.data["same"]["sources"] = []
    c.data["same"]["fips"] = ["024031"]
    eng = Engine(c, output=SilentOutput())
    eng.translator.backend = lambda audio, lang: ([], "en", 1.0)   # kein Whisper im Test
    eng.start()
    handler = type("H", (web._Handler,), {"engine": eng, "config": c})
    httpd = web.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.2)
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()
    eng.stop()


def _req(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST" if body is not None else "GET")
    return json.loads(urllib.request.urlopen(req, timeout=4).read())


def test_index_served(server):
    html = urllib.request.urlopen(server + "/").read().decode()
    assert "SATELLIT" in html


def test_state_and_tune(server):
    assert _req(server + "/api/tune", {"station": "a"})["ok"] is True
    time.sleep(0.5)
    st = _req(server + "/api/state")
    assert st["playing"]["label"] == "Rauschen"
    assert "schedule" in st and "same" in st and "watcher" in st


def test_same_test_takes_over(server):
    _req(server + "/api/tune", {"station": "a"})
    time.sleep(0.4)
    r = _req(server + "/api/same/test", {"event": "TOR", "area": True})
    assert r["ok"] is True
    time.sleep(0.6)
    st = _req(server + "/api/state")
    assert st["same"]["active"] is not None


def test_volume_and_mute(server):
    _req(server + "/api/volume", {"value": 0.3})
    st = _req(server + "/api/state")
    assert abs(st["volume"] - 0.3) < 1e-6
    _req(server + "/api/mute", {"muted": True})
    assert _req(server + "/api/state")["muted"] is True
    _req(server + "/api/mute", {"muted": False})
    assert _req(server + "/api/state")["muted"] is False


def test_static_traversal_blocked(server):
    import urllib.error
    for bad in ("/static/../satellit/engine.py", "/static/%2e%2e/satellit/engine.py",
                "/media/../c.json", "/media/%2e%2e/c.json"):
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(server + bad)
        assert exc.value.code == 404


def test_upload_list_and_serve(server):
    import io, wave as _w
    buf = io.BytesIO()
    with _w.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(48000)
        wf.writeframes(b"\x00\x00" * 4800)
    req = urllib.request.Request(server + "/api/media/Test%20Ansage.wav",
                                 data=buf.getvalue(), method="PUT")
    assert json.loads(urllib.request.urlopen(req).read())["ok"] is True
    names = [m["name"] for m in _req(server + "/api/media")["media"]]
    assert "Test Ansage.wav" in names
    data = urllib.request.urlopen(server + "/media/Test%20Ansage.wav").read()
    assert data[:4] == b"RIFF"


def test_upload_rejects_bad_type(server):
    import urllib.error
    req = urllib.request.Request(server + "/api/media/boese.exe", data=b"MZ", method="PUT")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == 400


def test_entry_toggle_and_mode_page(server):
    cfg = _req(server + "/api/config")
    eid = cfg["schedule"]["entries"][0]["id"]
    assert _req(server + "/api/entry", {"id": eid, "enabled": False})["ok"]
    assert _req(server + "/api/config")["schedule"]["entries"][0]["enabled"] is False
    assert _req(server + "/api/entry", {"id": eid, "skip_today": True})["ok"]
    _req(server + "/api/mode", {"mode": "program"})
    html = urllib.request.urlopen(server + "/").read().decode()
    assert "Wochenplan" in html


def test_config_roundtrip(server):
    _req(server + "/api/config", {"same": {"fips": ["012345"]}})
    cfg = _req(server + "/api/config")
    assert cfg["same"]["fips"] == ["012345"]


def test_translate_toggle(server):
    st = _req(server + "/api/state")["translate"]
    assert st["enabled"] is False and st["available"] is True
    assert _req(server + "/api/translate", {"enabled": True})["enabled"] is True
    assert _req(server + "/api/state")["translate"]["enabled"] is True
    assert _req(server + "/api/config")["translate"]["enabled"] is True
    assert _req(server + "/api/translate", {"enabled": False, "clear": True})["ok"]
    assert _req(server + "/api/state")["translate"]["enabled"] is False
    html = urllib.request.urlopen(server + "/radio").read().decode()
    assert "Übersetzer" in html


def test_translate_model_switch(server):
    st = _req(server + "/api/state")["translate"]
    assert st["model"] == "small"
    assert [m["name"] for m in st["models"]][:4] == ["tiny", "base", "small", "medium"]
    assert _req(server + "/api/translate", {"model": "medium"})["ok"]
    assert _req(server + "/api/state")["translate"]["model"] == "medium"
    assert _req(server + "/api/config")["translate"]["model"] == "medium"
    with pytest.raises(urllib.error.HTTPError):
        _req(server + "/api/translate", {"model": "../../etc"})
    assert _req(server + "/api/state")["translate"]["model"] == "medium"


def test_local_servers_answer_on_ipv4_and_ipv6():
    import socket
    if not socket.has_ipv6:
        pytest.skip("kein IPv6")
    handler = type("H", (web._Handler,), {"engine": None, "config": None})  # /radio braucht keine
    # freien Port suchen, der auf beiden Familien frei ist
    servers = web.make_servers("127.0.0.1", 0, handler)
    port = servers[0].server_address[1]
    for s in servers:
        s.server_close()
    servers = web.make_servers("127.0.0.1", port, handler)
    try:
        families = sorted(s.address_family for s in servers)
        assert socket.AF_INET in families
        if len(servers) == 1:
            pytest.skip("::1 nicht verfügbar")
        web.serve_background(servers)
        for host in ("127.0.0.1", "[::1]"):
            body = urllib.request.urlopen(f"http://{host}:{port}/radio", timeout=5).read()
            assert b"<html" in body.lower()
    finally:
        for s in servers:
            s.shutdown()
            s.server_close()
