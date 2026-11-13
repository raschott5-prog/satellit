import numpy as np

from satellit.audio import BLOCK, SAMPLE_RATE
from satellit.lautheit import Lautheit, Merker, k_leistung, lufs
from satellit.mixer import Mixer


class Sinus:
    """Quelle: Sinus mit fester Amplitude auf beiden Kanälen."""

    def __init__(self, amp, f=997.0):
        self.amp, self.f, self.t = amp, f, 0
        self.ready = True

    def read(self, frames):
        n = np.arange(self.t, self.t + frames)
        self.t += frames
        s = (self.amp * np.sin(2 * np.pi * self.f * n / SAMPLE_RATE)).astype(np.float32)
        return np.stack([s, s], axis=1)


def db(x):
    return 20 * np.log10(x)


def pegel_lufs(block):
    return lufs(k_leistung(block))


def test_messung_wie_bs1770():
    # 997-Hz-Sinus, 0 dBFS auf einem Kanal = −3,01 LUFS (BS.1770-Prüfwert)
    n = np.arange(BLOCK)
    s = np.sin(2 * np.pi * 997 * n / SAMPLE_RATE)
    block = np.stack([s, np.zeros_like(s)], axis=1)
    assert abs(pegel_lufs(block) - -3.01) < 0.3


def test_laute_und_leise_quelle_landen_beim_ziel():
    for amp in (0.4, 0.05):          # ≈ −8 und ≈ −26 LUFS
        m = Mixer(auto_level=True)
        m.deck_a.assign(Sinus(amp), key="st:x")
        for _ in range(int(25 * SAMPLE_RATE / BLOCK)):
            out = m.process()
        assert abs(pegel_lufs(out / m.volume) - -16.0) < 0.5


def test_leise_quelle_wird_hoechstens_10_db_angehoben():
    m = Mixer(auto_level=True)
    m.deck_a.assign(Sinus(0.003), key="st:x")      # ≈ −50 LUFS
    for _ in range(int(20 * SAMPLE_RATE / BLOCK)):
        m.process()
    assert m.deck_a.lautheit.gain_db == 10.0


def test_kein_sprung_beim_nachregeln():
    lh = Lautheit()
    src = Sinus(0.9)
    alt = 1.0
    for _ in range(int(10 * SAMPLE_RATE / BLOCK)):
        lh.messen(src.read(BLOCK))
        g0, g1 = lh.schritt(BLOCK)
        assert abs(g0 - alt) < 1e-9                 # nahtlos
        assert abs(db(g1) - db(g0)) < 6.0 * BLOCK / SAMPLE_RATE + 1e-6
        alt = g1


def test_pause_hebt_den_pegel_nicht():
    lh = Lautheit()
    src = Sinus(0.2)
    for _ in range(int(25 * SAMPLE_RATE / BLOCK)):
        lh.messen(src.read(BLOCK)); lh.schritt(BLOCK)
    vorher = lh.gain_db
    leise = Sinus(0.002)                            # Pause/Ausklingen: −40 dB
    for _ in range(int(10 * SAMPLE_RATE / BLOCK)):
        lh.messen(leise.read(BLOCK)); lh.schritt(BLOCK)
    stille = np.zeros((BLOCK, 2), np.float32)
    for _ in range(int(10 * SAMPLE_RATE / BLOCK)):
        lh.messen(stille); lh.schritt(BLOCK)
    assert abs(lh.gain_db - vorher) < 0.2


def test_gemerkter_wert_gilt_sofort(tmp_path):
    mk = Merker(tmp_path / "lautheit.json")
    mk.set("st:laut", -8.0)
    mk.speichern()
    mk2 = Merker(tmp_path / "lautheit.json")
    assert mk2.get("st:laut") == -8.0
    m = Mixer(auto_level=True)
    m.deck_a.assign(Sinus(0.5), key="st:laut", gemerkt=mk2.get("st:laut"))
    assert m.deck_a.lautheit.gain_db == -8.0


def test_ohne_auto_level_unveraendert():
    m = Mixer(auto_level=False)
    src = Sinus(0.5)
    m.deck_a.assign(src, key="st:x")
    out = m.process()
    assert m.deck_a.loudness["gain_db"] == 0.0
    assert np.max(np.abs(out)) <= 0.5 * m.volume + 1e-3


def test_sender_kann_angleich_abwaehlen(tmp_path):
    from satellit.config import Config
    from satellit.engine import Engine
    from satellit.output import SilentOutput
    c = Config(path=tmp_path / "c.json")
    c.data["stations"] = [
        {"id": "laut", "name": "Laut", "kind": "noise", "noise": 0.05, "freq": 98.4},
        {"id": "schlaf", "name": "Schlaf", "kind": "noise", "noise": 0.05, "freq": 90.0,
         "loudness": False},
    ]
    c.data["schedule"]["enabled"] = False
    eng = Engine(c, output=SilentOutput())
    assert eng._lautheit_an("st:laut") is True
    assert eng._lautheit_an("st:schlaf") is False
    assert eng._lautheit_an("fb:schlaf") is False
    assert eng._lautheit_an("off") is True
