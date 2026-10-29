import io

import numpy as np

from satellit.audio import CHANNELS, SAMPLE_RATE
from satellit.sources import make_source
from satellit.funk import websdr
from satellit.funk.websdr import WebSDRSource, browser_cmd, page_url, tune_arg


def test_page_url_and_tune_arg():
    assert tune_arg(5505, "USB") == "5505usb"
    assert tune_arg(7095.5, "lsb") == "7095.5lsb"
    assert page_url("hackgreensdr.org:8901", 5505, "usb") == \
        "http://hackgreensdr.org:8901/?tune=5505usb"
    assert page_url("http://websdr.ewi.utwente.nl:8901/", 3413, "usb") == \
        "http://websdr.ewi.utwente.nl:8901/?tune=3413usb"


def test_browser_runs_headless_with_own_profile():
    cmd = browser_cmd("/usr/bin/chromium", "/tmp/p", "http://x/?tune=1usb")
    assert "--headless=new" in cmd and "--user-data-dir=/tmp/p" in cmd
    assert "--remote-debugging-port=0" in cmd and cmd[-1] == "http://x/?tune=1usb"


def test_factory_builds_websdr_source():
    src = make_source({"kind": "websdr", "url": "http://hackgreensdr.org:8901/",
                       "freq_khz": 5505, "mode": "usb", "name": "Shannon", "buffer": 3},
                      funk=True)
    assert isinstance(src, WebSDRSource) and src.rebuffer
    assert src.describe()["kind"] == "websdr" and src.describe()["prebuffer_s"] == 3.0


def test_websdr_needs_the_funk_part():
    src = make_source({"kind": "websdr", "url": "http://x", "freq_khz": 5505})
    assert not isinstance(src, WebSDRSource)
    assert src.status == "error" and "Funk-Teil" in src.error


def test_unknown_mode_and_missing_fields_become_silence_with_error():
    bad = make_source({"kind": "websdr", "url": "http://x", "freq_khz": 1, "mode": "dsb"},
                      funk=True)
    assert bad.status == "error" and "Modus" in bad.error
    incomplete = make_source({"kind": "websdr", "freq_khz": 5505}, funk=True)
    assert incomplete.status == "error" and "url" in incomplete.error


def test_only_linux_for_now(monkeypatch):
    monkeypatch.setattr(websdr.sys, "platform", "darwin")
    assert websdr.missing_tools() and "Linux" in websdr.missing_tools()[0]
    src = WebSDRSource("http://x", 5505)
    src.run()
    assert src.status == "error" and "Linux" in src.error


def test_missing_browser_reported(monkeypatch):
    monkeypatch.setattr(websdr.sys, "platform", "linux")
    monkeypatch.setattr(websdr.shutil, "which",
                        lambda name: None if "chrom" in name else "/usr/bin/" + name)
    assert websdr.missing_tools() == ["Chromium"]


class _Proc:
    def __init__(self, data=b""):
        self.stdout = io.BytesIO(data)
        self.pid = 0

    def poll(self):
        return None


def test_pump_turns_parec_floats_into_blocks():
    frames = SAMPLE_RATE // 2
    pcm = np.full((frames, CHANNELS), 0.25, dtype=np.float32)
    src = WebSDRSource("http://x", 5505, gain=2.0, prebuffer_seconds=0.2)
    src.status = "connecting"
    src._chrome, src._parec = _Proc(), _Proc(pcm.tobytes())
    src._pump()                       # liest bis zum Ende, meldet dann den Abriss
    assert src.was_ready and src.buffer.available == frames
    assert np.allclose(src.buffer.pull(frames), 0.5)
    assert src.status == "error" and "parec" in src.error
