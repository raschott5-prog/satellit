"""Mitgelieferte Beispiel-Konfigurationen müssen sich laden lassen."""

import json
import shutil
from pathlib import Path

import pytest

from satellit.config import Config
from satellit.engine import Engine
from satellit.output import SilentOutput

BEISPIELE = sorted((Path(__file__).resolve().parent.parent / "beispiele").glob("*.json"))


@pytest.mark.parametrize("pfad", BEISPIELE, ids=lambda p: p.stem)
def test_beispiel_laedt(tmp_path, pfad):
    shutil.copy(pfad, tmp_path / "config.json")
    c = Config(path=tmp_path / "config.json").load()
    eng = Engine(c, output=SilentOutput())
    roh = json.loads(pfad.read_text(encoding="utf-8"))
    assert len(eng.scheduler.entries) == len(roh["schedule"]["entries"])
    ids = {s["id"] for s in c.data["stations"]}
    for e in eng.scheduler.entries:              # jeder Programmwechsel hat seinen Sender
        assert e.station is None or e.station in ids, e.id
    assert c.get("fallback") in ids
    for st in c.data["stations"]:                # mitgelieferte Dateien sind da
        if st["kind"] == "file":
            assert (pfad.parent / "media" / st["path"]).is_file(), st["path"]


def test_altersheim_ohne_ansagen_mit_kaffeezeit(tmp_path):
    shutil.copy(BEISPIELE[0].parent / "altersheim.json", tmp_path / "config.json")
    c = Config(path=tmp_path / "config.json").load()
    eng = Engine(c, output=SilentOutput())
    assert eng.funk is None and eng.state()["mode"] == "program"
    plays = [e for e in eng.scheduler.entries if e.play]
    assert all(e.mode == "replace" for e in plays)          # Lied statt Durchsage
    kaffee = eng.scheduler.by_id("kaffee")
    assert kaffee.play == ["kaffeezeit.mp3"] and kaffee.enabled
    # das Signal-Lied liegt dem Beispiel bei
    assert (BEISPIELE[0].parent / "media" / "kaffeezeit.mp3").stat().st_size > 100_000
    assert "kaffee" in eng.state()["schedule"]["missing"]   # Oberfläche zeigt: Datei fehlt


def test_guten_morgen_ist_lang_genug_zum_einblenden():
    import subprocess
    from satellit.sources.stream import ffmpeg_path
    c = json.loads((BEISPIELE[0].parent / "guten-morgen.json").read_text(encoding="utf-8"))
    weck = [e for e in c["schedule"]["entries"] if e.get("wake")]
    datei = BEISPIELE[0].parent / "media" / "good-morning-lang.mp3"
    probe = subprocess.run([ffmpeg_path(), "-i", str(datei)], capture_output=True, text=True)
    h, m, s = probe.stderr.split("Duration: ")[1].split(",")[0].split(":")
    laenge = int(h) * 3600 + int(m) * 60 + float(s)
    assert all(laenge > e["fade"] + 60 for e in weck)   # Finale erst nach dem Einblenden


def test_klangstuecke_liegen_bei():
    media = BEISPIELE[0].parent / "media"
    for name in ("kaffeezeit.mp3", "good-morning.mp3", "good-morning-lang.mp3", "fernzug.mp3"):
        assert (media / name).stat().st_size > 100_000, name
    for skript in ("kaffeezeit.py", "goodmorning.py", "fernzug.py", "uhrwerk.py", "drumsolo.py"):
        assert (BEISPIELE[0].parent / skript).is_file(), skript
