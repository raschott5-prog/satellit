import numpy as np

from satellit.audio import BLOCK, SAMPLE_RATE
from satellit.sources import make_source
from satellit.sources.base import RESUME_FADE, Source


class NetSource(Source):
    rebuffer = True

    def run(self):
        pass


def feed(src, seconds):
    src._emit(np.full((int(SAMPLE_RATE * seconds), 2), 0.5, dtype=np.float32))


def test_buffer_from_station_entry():
    src = make_source({"kind": "stream", "url": "http://x/s.mp3", "buffer": 10})
    assert src.describe()["prebuffer_s"] == 10.0
    assert src.buffer._cap >= SAMPLE_RATE * 20     # Vorlauf passt bequem hinein
    assert make_source({"kind": "stream", "url": "http://x"}).describe()["prebuffer_s"] == 0.6
    assert make_source({"kind": "stream", "url": "http://x", "buffer": 999}) \
        .describe()["prebuffer_s"] == 30.0


def test_ready_only_after_configured_buffer():
    src = NetSource(prebuffer_seconds=3.0)
    src.status = "connecting"
    feed(src, 2.0)
    assert not src.ready
    feed(src, 1.5)
    assert src.ready and src.status == "playing"


def test_empty_network_source_rebuffers_before_playing_on():
    src = NetSource(prebuffer_seconds=1.0)
    src.status = "connecting"
    feed(src, 1.0)
    while src.buffer.available >= BLOCK:
        assert np.all(src.read(BLOCK) == 0.5)
    src.read(BLOCK)                                  # läuft leer
    assert src.buffering and src.rebuffers == 1
    feed(src, 0.5)                                   # Schub reicht noch nicht
    assert np.all(src.read(BLOCK) == 0.0)
    assert src.buffer.available >= int(0.5 * SAMPLE_RATE) - 1
    feed(src, 2.5)                                   # Vorlauf wieder voll
    first = src.read(BLOCK)
    assert not src.buffering
    assert first[0, 0] == 0.0 and 0.0 < first[-1, 0] < 0.5   # blendet ein
    for _ in range(int(RESUME_FADE * SAMPLE_RATE) // BLOCK + 1):
        src.read(BLOCK)
    assert np.all(src.read(BLOCK) == 0.5)                # wieder voll da


def test_dropout_tail_is_faded_not_cut():
    src = NetSource(prebuffer_seconds=0.2)
    src.status = "connecting"
    feed(src, 0.2)
    feed(src, (BLOCK // 2) / SAMPLE_RATE)
    while src.buffer.available >= BLOCK:
        src.read(BLOCK)
    tail = src.read(BLOCK)
    assert src.buffering
    assert tail[0, 0] > 0.4
    nz = tail[tail[:, 0] != 0, 0]
    assert nz[-1] < 0.05                                 # endet leise
