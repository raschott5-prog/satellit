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
    assert lichtorgel.setzen(cfg, {"stille_db": 5})["stille_db"] == 0.0


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


# ---- Ausklingen: bis zur Zieluhrzeit dunkler und unempfindlicher ----
class _Cfg:
    """Minimaler Config-Ersatz mit update() wie satellit.config.Config."""
    def __init__(self, data):
        self.data = data

    def update(self, neu):
        from satellit.config import _merge
        self.data = _merge(self.data, neu)


def test_ausklang_verlauf_und_ende(tmp_path):
    _status(tmp_path, hell=80, stille_db=-40.0)
    cfg = _Cfg({"lichtorgel": {"dir": str(tmp_path)}})
    t0 = time.time()
    ak = lichtorgel.ausklang_starten(cfg, t0 + 3600, jetzt=t0)
    assert ak["von_hell"] == 80 and ak["nach_hell"] == lichtorgel.AUSKLANG_HELL
    assert lichtorgel.ausklang_werte(ak, t0) == (80, -40.0, False)
    h, s, fertig = lichtorgel.ausklang_werte(ak, t0 + 1800)
    assert (h, s, fertig) == (round((80 + 25) / 2), -20.0, False)
    lichtorgel.ausklang_schritt(cfg, jetzt=t0 + 1800)
    assert json.loads((tmp_path / "regler.json").read_text()) == {"hell": h, "stille_db": -20.0}
    assert lichtorgel.zustand(cfg.data, jetzt=t0)["ausklang"]["rest_s"] == 3600
    lichtorgel.ausklang_schritt(cfg, jetzt=t0 + 4000)
    assert json.loads((tmp_path / "regler.json").read_text()) == {"hell": 25, "stille_db": 0.0}
    assert not cfg.data["lichtorgel"]["ausklang"]          # fertig = beendet


def test_ausklang_nie_heller_und_pruefungen(tmp_path):
    _status(tmp_path, hell=10)
    cfg = _Cfg({"lichtorgel": {"dir": str(tmp_path)}})
    t0 = time.time()
    assert lichtorgel.ausklang_starten(cfg, t0 + 600, jetzt=t0)["nach_hell"] == 10
    for falsch in (t0 + 10, t0 + 2 * 86400, "23:00", True):
        with pytest.raises(ValueError):
            lichtorgel.ausklang_starten(cfg, falsch, jetzt=t0)
    lichtorgel.ausklang_stoppen(cfg)
    assert not cfg.data["lichtorgel"]["ausklang"]


def test_ausklang_ohne_lichtorgel(tmp_path):
    cfg = _Cfg({"lichtorgel": {"dir": str(tmp_path)}})
    with pytest.raises(ValueError):
        lichtorgel.ausklang_starten(cfg, time.time() + 600)
    lichtorgel.ausklang_schritt(cfg)                       # ohne Ausklang: nichts


def test_web_ausklang_und_hand_bricht_ab(server):
    url, ordner = server
    _status(ordner)
    r = _req(url + "/api/lichtorgel/ausklang", {"bis_t": time.time() + 1800})
    assert r["ok"] and r["ausklang"]["nach_stille"] == 0.0
    assert _req(url + "/api/state")["lichtorgel"]["ausklang"]["rest_s"] > 1700
    _req(url + "/api/lichtorgel", {"hell": 50})             # Regler von Hand -> Ausklang aus
    assert "ausklang" not in _req(url + "/api/state")["lichtorgel"]
    _req(url + "/api/lichtorgel/ausklang", {"bis_t": time.time() + 1800})
    assert _req(url + "/api/lichtorgel/ausklang", {"stop": True})["ok"]
    assert "ausklang" not in _req(url + "/api/state")["lichtorgel"]
    with pytest.raises(urllib.error.HTTPError) as e:
        _req(url + "/api/lichtorgel/ausklang", {"bis_t": time.time() + 5})
    assert e.value.code == 400
