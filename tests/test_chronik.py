"""Senderchronik: Einträge, Berichtigungen, Export/Import, Web-API."""

import json
import os

import pytest

from satellit.chronik import Chronik, entry_id, make_entry


def test_add_and_list(tmp_path):
    c = Chronik(tmp_path / "chronik.json")
    e = c.add(station="sr1", text="  Heusweiler, 1422 kHz  ", author="Robert", source="https://x")
    assert e["text"] == "Heusweiler, 1422 kHz"
    assert e["id"] == entry_id(e)
    assert [x["id"] for x in c.entries("sr1")] == [e["id"]]
    assert c.entries("wdr4") == []
    # bleibt nach Neuladen erhalten
    assert Chronik(tmp_path / "chronik.json").entries("sr1")[0]["text"] == "Heusweiler, 1422 kHz"


def test_empty_text_and_station_rejected(tmp_path):
    c = Chronik(tmp_path / "chronik.json")
    with pytest.raises(ValueError):
        c.add(station="sr1", text="   ")
    with pytest.raises(ValueError):
        c.add(station="", text="x")


def test_author_defaults_to_anonym(tmp_path):
    e = Chronik(tmp_path / "c.json").add(station="sr1", text="x")
    assert e["author"] == "anonym"


def test_same_entry_only_once(tmp_path):
    c = Chronik(tmp_path / "c.json")
    kw = dict(station="sr1", text="x", author="a", created="2026-11-01T20:00:00+00:00")
    c.add(**kw)
    c.add(**kw)
    assert len(c.entries("sr1")) == 1


def test_correction_marks_original(tmp_path):
    c = Chronik(tmp_path / "c.json")
    alt = c.add(station="sr1", text="Netz über die A 1", created="2026-11-01T20:00:00+00:00")
    neu = c.add(station="sr1", text="Netz über die A 8", replaces=alt["id"],
                created="2026-11-01T20:05:00+00:00")
    es = {e["id"]: e for e in c.entries("sr1")}
    assert es[alt["id"]]["replaced_by"] == neu["id"]
    assert "replaced_by" not in es[neu["id"]]
    assert c.counts() == {"sr1": 1}
    with pytest.raises(ValueError):
        c.add(station="sr1", text="y", replaces="0000000000000000")


def test_export_import_roundtrip_and_dedupe(tmp_path):
    a = Chronik(tmp_path / "a.json")
    a.add(station="sr1", text="eins", created="2026-11-01T20:00:00+00:00")
    a.add(station="wdr4", text="zwei", created="2026-11-01T20:01:00+00:00")
    b = Chronik(tmp_path / "b.json")
    b.add(station="sr1", text="eigen", created="2026-11-01T19:00:00+00:00")
    assert b.import_(a.export()) == {"added": 2, "known": 0, "invalid": 0}
    assert b.import_(a.export()) == {"added": 0, "known": 2, "invalid": 0}
    assert [e["text"] for e in b.entries("sr1")] == ["eigen", "eins"]
    assert len(a.export("sr1")["entries"]) == 1


def test_import_rejects_tampered_and_foreign(tmp_path):
    a = Chronik(tmp_path / "a.json")
    a.add(station="sr1", text="echt")
    data = a.export()
    data["entries"][0]["text"] = "gefälscht"          # Inhalt geändert, ID nicht
    data["entries"].append({"station": "sr1"})       # unvollständig
    data["entries"].append("Unsinn")
    b = Chronik(tmp_path / "b.json")
    assert b.import_(data) == {"added": 0, "known": 0, "invalid": 3}
    with pytest.raises(ValueError):
        b.import_({"entries": []})                    # kein Format-Kennzeichen
    with pytest.raises(ValueError):
        b.import_({"format": "satellit-chronik"})


def test_damaged_file_is_ignored(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{kaputt", encoding="utf-8")
    c = Chronik(p)
    assert c.entries() == []
    c.add(station="sr1", text="neu")
    assert json.loads(p.read_text(encoding="utf-8"))["format"] == "satellit-chronik"


def test_make_entry_limits():
    e = make_entry(station="sr1", text="x" * 9000, author="y" * 500)
    assert len(e["text"]) == 5000 and len(e["author"]) == 80


# --- Web-API -------------------------------------------------------------

from test_web import _req, server  # noqa: E402,F401  (gemeinsame Test-Instanz)
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402


def test_web_chronik(server):  # noqa: F811
    assert _req(server + "/api/chronik") == {"counts": {}}
    r = _req(server + "/api/chronik", {"station": "a", "text": "Rauscht schön", "author": "Test",
                                       "source": "eigenes Ohr"})
    assert r["ok"] and r["entry"]["station_name"] == "Rauschen"
    lst = _req(server + "/api/chronik?station=a")
    assert [e["text"] for e in lst["entries"]] == ["Rauscht schön"]
    assert _req(server + "/api/chronik")["counts"] == {"a": 1}

    with pytest.raises(urllib.error.HTTPError) as ex:
        _req(server + "/api/chronik", {"station": "a", "text": ""})
    assert ex.value.code == 400

    raw = urllib.request.urlopen(server + "/api/chronik/export?station=a", timeout=4)
    assert "attachment" in raw.headers["Content-Disposition"]
    data = json.loads(raw.read())
    assert _req(server + "/api/chronik/import", data) == {"ok": True, "added": 0, "known": 1,
                                                          "invalid": 0}
    with pytest.raises(urllib.error.HTTPError) as ex:
        _req(server + "/api/chronik/import", {"irgendwas": 1})
    assert ex.value.code == 400
