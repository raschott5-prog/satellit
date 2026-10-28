"""Konfiguration: Laden/Speichern, Mischen, Zugriff."""

import json
import os

from satellit.config import Config, default_config, _merge


def test_save_and_load_roundtrip(tmp_path):
    p = tmp_path / "config.json"
    c = Config(path=p)
    c.data["web"]["port"] = 9999
    c.save()
    assert p.exists()
    c2 = Config(path=p).load()
    assert c2.get("web", "port") == 9999


def test_defaults_present():
    d = default_config()
    assert d["audio"]["crossfade_seconds"] > 0
    assert "stations" in d and "same" in d and "watcher" in d


def test_merge_keeps_unknown_and_overrides():
    base = {"a": 1, "nest": {"x": 1, "y": 2}}
    over = {"a": 2, "nest": {"y": 9, "z": 3}}
    m = _merge(base, over)
    assert m["a"] == 2
    assert m["nest"] == {"x": 1, "y": 9, "z": 3}


def test_station_lookup():
    c = Config(path="/tmp/does-not-matter.json")
    c.data["stations"] = [{"id": "fm1", "name": "Eins"}, {"id": "mw1", "name": "Zwei"}]
    assert c.station("mw1")["name"] == "Zwei"
    assert c.station("nope") is None


def test_corrupt_file_falls_back(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{ this is not json")
    c = Config(path=p).load()
    assert c.get("web", "port") == 8080             # Standard
    assert (tmp_path / "config.json.bad").exists()  # Kaputtes beiseitegelegt


def test_update_persists(tmp_path):
    p = tmp_path / "c.json"
    c = Config(path=p).load()
    c.update({"same": {"fips": ["012345"]}})
    assert json.loads(p.read_text())["same"]["fips"] == ["012345"]
    # andere same-Felder bleiben erhalten
    assert "events" in json.loads(p.read_text())["same"]
