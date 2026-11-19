"""Optionale Lichtorgel: Zustand aus status.json, Vorgaben nach regler.json, Web-API."""

import json
import os
import threading
import time
import urllib.error
import urllib.request

import pytest

from satellit import lichtorgel, web
from satellit.config import Config
from satellit.engine import Engine
from satellit.output import SilentOutput


def _status(ordner, alter=0.0, **werte):
    st = {"t": time.time() - alter, "hell": 78, "stumm": False, "stille_db": -45.0, "pegel_db": -30.2}
    st.update(werte)
    (ordner / "status.json").write_text(json.dumps(st))


def test_ohne_lichtorgel_inaktiv(tmp_path):
    z = lichtorgel.zustand({"lichtorgel": {"dir": str(tmp_path)}})
    assert z["aktiv"] is False


def test_frischer_status_aktiv(tmp_path):
    _status(tmp_path)
    z = lichtorgel.zustand({"lichtorgel": {"dir": str(tmp_path)}})
    assert z["aktiv"] is True and z["hell"] == 78 and z["stille_db"] == -45.0


def test_alter_status_inaktiv(tmp_path):
    _status(tmp_path, alter=60)
    assert lichtorgel.zustand({"lichtorgel": {"dir": str(tmp_path)}})["aktiv"] is False


def test_abgeschaltet_in_config(tmp_path):
    _status(tmp_path)
    cfg = {"lichtorgel": {"dir": str(tmp_path), "enabled": False}}
    assert lichtorgel.zustand(cfg)["aktiv"] is False
    with pytest.raises(ValueError):
        lichtorgel.setzen(cfg, {"hell": 50})


def test_setzen_begrenzt_und_behaelt_felder(tmp_path):
    cfg = {"lichtorgel": {"dir": str(tmp_path)}}
    lichtorgel.setzen(cfg, {"stille_db": -50})
    r = lichtorgel.setzen(cfg, {"hell": 250})
    assert r == {"stille_db": -50.0, "hell": 100}
    assert json.loads((tmp_path / "regler.json").read_text()) == r
    assert lichtorgel.setzen(cfg, {"stille_db": -99})["stille_db"] == -70.0


def test_setzen_lehnt_unsinn_ab(tmp_path):
    cfg = {"lichtorgel": {"dir": str(tmp_path)}}
    for falsch in ({}, {"hell": "viel"}, {"hell": True}, {"stille_db": None}):
        with pytest.raises(ValueError):
            lichtorgel.setzen(cfg, falsch)


@pytest.fixture
def server(tmp_path):
    c = Config(path=os.path.join(tmp_path, "c.json")).load()
    c.data["stations"] = [{"id": "a", "name": "Rauschen", "kind": "noise", "noise": 0.05, "freq": 98.4}]
    c.data["schedule"]["enabled"] = False
    c.data["lichtorgel"] = {"dir": str(tmp_path / "lo")}
    (tmp_path / "lo").mkdir()
    eng = Engine(c, output=SilentOutput())
    eng.start()
    handler = type("H", (web._Handler,), {"engine": eng, "config": c})
    httpd = web.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.2)
    yield f"http://127.0.0.1:{httpd.server_address[1]}", tmp_path / "lo"
    httpd.shutdown()
    eng.stop()


def _req(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"},
                                 method="POST" if body is not None else "GET")
    return json.loads(urllib.request.urlopen(req, timeout=4).read())


def test_web_inaktiv_lehnt_ab(server):
    url, _ = server
    assert _req(url + "/api/state")["lichtorgel"]["aktiv"] is False
    with pytest.raises(urllib.error.HTTPError) as e:
        _req(url + "/api/lichtorgel", {"hell": 40})
    assert e.value.code == 409


def test_web_aktiv_setzt_regler(server):
    url, ordner = server
    _status(ordner)
    assert _req(url + "/api/state")["lichtorgel"]["aktiv"] is True
    r = _req(url + "/api/lichtorgel", {"hell": 40, "stille_db": -52})
    assert r["ok"] is True
    assert json.loads((ordner / "regler.json").read_text()) == {"hell": 40, "stille_db": -52.0}
