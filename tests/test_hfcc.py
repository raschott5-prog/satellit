"""HFCC-Sendeplan: Format lesen, Sendetage (1 = Sonntag), Saison, Laden."""

import io
import os
import time
import zipfile
from datetime import date, datetime, timezone

from satellit import hfcc
from satellit.config import Config
from satellit.engine import Engine
from satellit.output import SilentOutput

RULER = (";----+----+----+------------------------------+---+----+-------+---+---+-------+"
         "------+------+-+-----+----------+---+---+---+-----+-+-----+-----+-----+-------")
HEAD = (";FREQ STRT STOP CIRAF ZONES                    LOC POWR AZIMUTH SLW ANT DAYS    "
        "FDATE  TDATE MOD AFRQ LANGUAGE   ADM BRC FMO REQ# OLD ALT1 ALT2  ALT3  NOTES")


def _row(freq, start, stop, loc, power, days, lang, brc, fdate="251026", tdate="280327"):
    cols = [f"{freq:5d}", start, stop, f"{'56':<30}", f"{loc:<3}", f"{power:4d}", f"{'308':<7}",
            f"{'0':>3}", "100", f"{days:<7}", fdate, tdate, "D", "     ", f"{lang:<10}",
            "CHN", f"{brc:<3}", "CRI", "  123", " ", "     ", "     ", "     ", ""]
    return " ".join(cols)


def _zip(rows):
    main = "\r\n".join(["; B26 ALL", RULER, HEAD, RULER] + rows) + "\r\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("B26all00.TXT", main)
        z.writestr("broadcas.txt", ";x\r\nCRI China Radio International\r\nOMR SunDance\r\n")
        z.writestr("site.txt", ";x\r\nURU Urumqi                         CHN 43N35 087E30\r\n"
                               "NIJ Nijmegen                       HOL 51N50 005E50\r\n")
        z.writestr("language.txt", "﻿;x\r\nHrv Croatian\r\nNld Dutch\r\nUig Uighur\r\n")
    return buf.getvalue()


ROWS = [
    _row(7225, "2100", "2200", "URU", 500, "1234567", "Hrv", "CRI"),
    _row(7225, "0000", "2400", "NIJ", 15, "1234567", "Nld", "OMR"),
    _row(7205, "2330", "0300", "URU", 50, "1234567", "Uig", "CRI"),
    _row(9999, "1000", "1100", "NIJ", 15, "1", "Nld", "OMR"),            # nur sonntags
]
UTC = timezone.utc


def test_season():
    assert hfcc.season_for(date(2026, 10, 24)) == "a26"
    assert hfcc.season_for(date(2026, 10, 25)) == "b26"     # letzter Oktobersonntag
    assert hfcc.season_for(date(2027, 2, 1)) == "b26"
    assert hfcc.season_for(date(2027, 3, 28)) == "a27"
    assert hfcc.previous_season("b26") == "a26" and hfcc.previous_season("a27") == "b26"


def test_on_air_and_candidates():
    s = hfcc.Schedule(_zip(ROWS), "b26")
    hits = s.on_air(7225, datetime(2026, 10, 26, 21, 40, tzinfo=UTC))
    assert [h["short"] for h in hits] == ["CRI", "SunDance"]           # stärkste zuerst
    assert hits[0]["lang_de"] == "Kroatisch" and hits[0]["site"] == "Urumqi"
    assert hfcc.candidates(hits) == ["hr", "nl"]
    # Uigurisch kennt Whisper nicht -> kein Hinweis, Whisper erkennt frei
    late = s.on_air(7205, datetime(2026, 10, 27, 0, 40, tzinfo=UTC))
    assert len(late) == 1 and hfcc.candidates(late) is None
    # außerhalb der Gültigkeit
    assert s.on_air(7225, datetime(2027, 4, 1, 21, 40, tzinfo=UTC)) == []


def test_days_start_on_sunday():
    s = hfcc.Schedule(_zip(ROWS), "b26")
    sunday, monday = datetime(2026, 11, 1, 10, 30, tzinfo=UTC), datetime(2026, 11, 2, 10, 30, tzinfo=UTC)
    assert s.on_air(9999, sunday) and not s.on_air(9999, monday)


def test_loader_caches_and_falls_back(tmp_path):
    urls = []

    def fetch(url):
        urls.append(url)
        if "/b26/" in url:
            raise OSError("404")              # neue Saison noch nicht veröffentlicht
        return _zip(ROWS)

    h = hfcc.HFCC(tmp_path, fetch=fetch)
    h._load("b26")
    assert h.schedule.season == "a26" and urls[-1].endswith("/a26/a26allx2.zip")
    ok = hfcc.HFCC(tmp_path, fetch=lambda url: _zip(ROWS))
    ok._load("b26")
    assert ok.schedule.season == "b26" and (tmp_path / "b26allx2.zip").exists()
    offline = hfcc.HFCC(tmp_path, fetch=lambda url: (_ for _ in ()).throw(OSError("offline")))
    offline._load("b26")                      # Zwischenspeicher frisch -> gar kein Netz
    assert offline.schedule.season == "b26" and offline.error is None


def test_engine_hint_for_shortwave_station(tmp_path):
    c = Config(path=os.path.join(tmp_path, "c.json"))
    c.data["stations"] = [{"id": "k", "name": "CRI", "kind": "kiwi", "host": "x", "freq_khz": 7225},
                          {"id": "s", "name": "Stream", "kind": "stream", "url": "http://x"}]
    c.data["schedule"]["enabled"] = False
    eng = Engine(c, output=SilentOutput())
    eng.hfcc.fetch = lambda url: _zip(ROWS)
    eng.hfcc._load(hfcc.season_for(datetime.now(UTC).date()))
    eng._committed_key = "st:k"
    assert eng.on_air("s") == []
    expected = eng.hfcc.on_air(7225)
    assert [e["short"] for e in eng.on_air("k")] == [e["short"] for e in expected]
    assert eng._language_hint() == hfcc.candidates(expected)
