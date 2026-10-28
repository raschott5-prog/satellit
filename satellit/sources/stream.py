"""Internet-Stream-Quelle über ffmpeg.

ffmpeg dekodiert jedes übliche Format (MP3, AAC, Ogg, HLS …) und liefert auf
stdout rohes PCM (48 kHz, Stereo, float32), das direkt in den Ringpuffer geht.
.pls/.m3u-Playlists werden vorher aufgelöst. Kein ffmpeg oder kein Netz →
Status ``error``, die Engine bleibt beim alten Sender.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from urllib.parse import urlparse

import numpy as np

from ..audio import CHANNELS, SAMPLE_RATE
from .base import Source

_READ = 8192  # float32-Werte pro Lesevorgang


def ffmpeg_path() -> str | None:
    """ffmpeg im PATH, sonst (macOS/Windows) das aus dem pip-Paket imageio-ffmpeg.

    Unter Linux nicht: dessen statisches ffmpeg stürzt bei der Namensauflösung
    ab, und ein System-ffmpeg ist dort ohnehin üblich.
    """
    exe = shutil.which("ffmpeg")
    if exe or sys.platform.startswith("linux"):
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def resolve_playlist(url: str, timeout: float = 8.0) -> str:
    """.pls/.m3u -> erste echte Stream-URL (sonst unverändert zurück)."""
    low = url.lower().split("?")[0]
    if not (low.endswith(".pls") or low.endswith(".m3u") or low.endswith(".m3u8")):
        return url
    if low.endswith(".m3u8"):
        return url     # HLS kann ffmpeg selbst
    try:
        import requests
        text = requests.get(url, timeout=timeout).text
    except Exception:
        return url
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("file"):          # .pls: File1=http://...
            return line.split("=", 1)[1].strip()
        if line and not line.startswith("#"):          # .m3u: nackte URL
            if urlparse(line).scheme in ("http", "https"):
                return line
    return url


class StreamSource(Source):
    kind = "stream"
    rebuffer = True

    def __init__(self, url: str, name: str = "", gain: float = 1.0, **kw):
        super().__init__(name=name or url, **kw)
        self.url = url
        self.gain = gain
        self._proc: subprocess.Popen | None = None

    def run(self) -> None:
        exe = ffmpeg_path()
        if not exe:
            self.error = "ffmpeg nicht gefunden (PATH prüfen / mit ausliefern)"
            self.status = "error"
            return
        url = resolve_playlist(self.url)
        cmd = [
            exe, "-hide_banner", "-loglevel", "error",
            "-reconnect", "1", "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-user_agent", "SatellitRadio",
            "-i", url,
            "-f", "f32le", "-acodec", "pcm_f32le",
            "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "-",
        ]
        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, bufsize=10 ** 7)
        raw = b""
        bytes_per = 4 * CHANNELS
        last_data = time.time()
        while not self._stop.is_set():
            chunk = self._proc.stdout.read(_READ * 4)
            if not chunk:
                if self._proc.poll() is not None:
                    self.error = "ffmpeg beendet (Stream weg?)"
                    self.status = "error"
                    break
                if time.time() - last_data > self._timeout:
                    self.status = "stalled"
                time.sleep(0.05)
                continue
            last_data = time.time()
            raw += chunk
            usable = len(raw) - (len(raw) % bytes_per)
            if usable <= 0:
                continue
            samples = np.frombuffer(raw[:usable], dtype=np.float32)
            raw = raw[usable:]
            block = samples.reshape(-1, CHANNELS) * self.gain
            # Server schicken am Anfang oft einen großen Schub: lieber warten,
            # als im vollen Puffer ungespielten Ton zu überschreiben
            if not self._emit_paced(block, headroom_seconds=1.0):
                break
        self._cleanup()

    def _cleanup(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=1.5)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass

    def stop(self) -> None:
        self._cleanup()
        super().stop()
