"""SAME-Dekoder: Round-Trip, Rauschen, Parser, Gebiet/Ereignis, EOM."""

import numpy as np
import pytest

from satellit import same


def _hdr(**kw):
    kw.setdefault("org", "WXR")
    kw.setdefault("event", "TOR")
    kw.setdefault("locations", ["024031", "051059"])
    kw.setdefault("purge", "0045")
    kw.setdefault("station", "KEC55")
    kw.setdefault("issued", "2871830")
    return same.build_header(**kw)


def test_roundtrip_clean():
    hdr = _hdr()
    sig = same.SAMEGenerator().message(hdr, with_eom=True)
    res = same.SAMEDecoder().decode(sig)
    headers = [h for h in res if not h.is_eom]
    assert headers, "kein Header dekodiert"
    assert headers[0].raw.rstrip("-") == hdr.rstrip("-")
    assert any(h.is_eom for h in res), "EOM nicht erkannt"


@pytest.mark.parametrize("db", [0, -3, -6, -9, -12])
def test_roundtrip_noisy(db):
    hdr = _hdr(event="SVR")
    sig = same.SAMEGenerator().message(hdr, noise_db=db, with_eom=False)
    headers = [h for h in same.SAMEDecoder().decode(sig) if not h.is_eom]
    assert headers and headers[0].raw.rstrip("-") == hdr.rstrip("-")


def test_parse_fields():
    h = same.parse_header(_hdr(event="FFW", purge="0100"))
    assert h is not None
    assert h.org == "WXR" and h.event == "FFW"
    assert h.locations == ["024031", "051059"]
    assert h.purge_minutes() == 60
    assert "Sturzflut" in h.event_name()
    assert h.originator_name() == "National Weather Service"


def test_parse_rejects_garbage():
    assert same.parse_header("not a header") is None
    assert same.parse_header("ZCZC-XX-YY") is None


def test_area_matching():
    h = same.parse_header(_hdr(locations=["024031"]))
    assert h.matches_area(["024031"]) is True
    assert h.matches_area(["099999"]) is False
    allusa = same.parse_header(_hdr(locations=["000000"]))
    assert allusa.matches_area(["024031"]) is True       # 000000 = ganze USA


def test_dedup_key_stable():
    a = same.parse_header(_hdr())
    b = same.parse_header(_hdr())
    assert a.dedup_key() == b.dedup_key()
    c = same.parse_header(_hdr(issued="2871900"))
    assert a.dedup_key() != c.dedup_key()


def test_stream_dedups_repeats():
    hdr = _hdr(event="TOR")
    sig = same.SAMEGenerator().message(hdr, with_eom=True)
    seen = []
    st = same.SAMEStream(on_header=lambda h: seen.append(h), window_seconds=20)
    # in 1-s-Blöcken füttern, mehrfach – darf nur einmal auslösen
    block = 48000
    for i in range(0, len(sig), block):
        st.feed(sig[i:i + block])
    for _ in range(3):
        st.feed(np.zeros(block, dtype=np.float32))
    warns = [h for h in seen if not h.is_eom]
    assert len(warns) == 1, f"erwartet 1 Auslösung, war {len(warns)}"


def test_adpcm_roundtrip():
    from satellit.sources.kiwi import adpcm_decode, adpcm_encode
    t = np.linspace(0, 0.2, 2400, endpoint=False)
    pcm = (np.sin(2 * np.pi * 440 * t) * 20000).astype(np.int16)
    enc = adpcm_encode(pcm, [0, 0])
    dec = adpcm_decode(enc, [0, 0])
    # IMA-ADPCM ist verlustbehaftet, aber hoch korreliert
    n = min(len(pcm), len(dec))
    corr = np.corrcoef(pcm[:n], dec[:n])[0, 1]
    assert corr > 0.95, f"ADPCM-Korrelation zu niedrig: {corr:.3f}"
