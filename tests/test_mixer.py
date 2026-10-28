"""Mixer: Equal-Power, Überblendung, Begrenzer, Pegelausgleich."""

import numpy as np

from satellit.audio import BLOCK, silence
from satellit.mixer import Deck, Mixer, equal_power
from satellit.sources.silence import SilenceSource


def test_equal_power_constant():
    for x in np.linspace(0, 1, 11):
        gA, gB = equal_power(x)
        assert abs(gA ** 2 + gB ** 2 - 1.0) < 1e-9
    assert equal_power(0) == (1.0, 0.0)
    assert abs(equal_power(1)[1] - 1.0) < 1e-9


def test_crossfade_moves_toward_target():
    m = Mixer(auto_level=False)
    m.deck_a.source = SilenceSource().start()
    m.deck_b.source = SilenceSource().start()
    m.set_crossfade(1.0, seconds=0.1)
    start = m.crossfade
    for _ in range(50):
        m.process(BLOCK)
    assert m.crossfade > start
    assert abs(m.crossfade - 1.0) < 1e-6


def test_limiter_bounds_output():
    m = Mixer(auto_level=False)

    class Loud:
        ready = True
        def read(self, n):
            return np.full((n, 2), 5.0, dtype=np.float32)   # weit über 1.0

    m.deck_a.source = Loud()
    out = m.process(BLOCK)
    assert np.max(np.abs(out)) <= m.limiter_ceiling + 1e-6


def test_master_ramp_down():
    m = Mixer(auto_level=False)
    m.deck_a.source = SilenceSource().start()
    m.set_master(0.0, seconds=0.1)
    for _ in range(60):
        m.process(BLOCK)
    assert m.master < 1e-6


def test_deck_gain_applied():
    class Const:
        ready = True
        def read(self, n):
            return np.ones((n, 2), dtype=np.float32)
    d = Deck(source=Const(), gain=0.5)
    block = d.read(BLOCK)
    assert np.allclose(block, 0.5)


def test_deck_handles_broken_source():
    class Broken:
        ready = True
        def read(self, n):
            raise RuntimeError("boom")
    d = Deck(source=Broken())
    assert np.allclose(d.read(BLOCK), 0.0)   # darf nicht werfen
