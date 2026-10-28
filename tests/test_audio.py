"""Ringpuffer und Audio-Hilfen."""

import numpy as np

from satellit.audio import CHANNELS, RingBuffer, as_stereo, rms, silence


def test_ring_push_pull():
    rb = RingBuffer(capacity_frames=1000)
    block = np.ones((100, CHANNELS), dtype=np.float32)
    rb.push(block)
    assert rb.available == 100
    out = rb.pull(100)
    assert out.shape == (100, CHANNELS)
    assert np.allclose(out, 1.0)
    assert rb.available == 0


def test_ring_underrun_returns_silence():
    rb = RingBuffer(capacity_frames=1000)
    rb.push(np.ones((10, CHANNELS), dtype=np.float32))
    out = rb.pull(100)
    assert out.shape == (100, CHANNELS)
    assert rb.underruns == 1
    assert np.allclose(out[10:], 0.0)


def test_ring_wraps():
    rb = RingBuffer(capacity_frames=128)
    for _ in range(4):
        rb.push(np.full((50, CHANNELS), 0.25, dtype=np.float32))
    assert rb.available <= 128
    out = rb.pull(64)
    assert out.shape == (64, CHANNELS)


def test_as_stereo_from_mono():
    mono = np.arange(10, dtype=np.float32)
    st = as_stereo(mono)
    assert st.shape == (10, CHANNELS)
    assert np.allclose(st[:, 0], st[:, 1])


def test_rms_and_silence():
    assert rms(silence(100)) == 0.0
    ones = np.ones((100, CHANNELS), dtype=np.float32)
    assert abs(rms(ones) - 1.0) < 1e-6
