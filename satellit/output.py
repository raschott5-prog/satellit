"""Audioausgabe: PortAudio (sounddevice), WAV-Datei oder stumm.

Die Ausgabe zieht im Audiotakt Blöcke aus einem Callback (``engine.render``).
Fehlt ``sounddevice``/PortAudio, läuft das Programm stumm weiter und meldet
das – so verlangt es die README. Für Tests schreibt ``WavOutput`` in eine
Datei, ``SilentOutput`` taktet nur die Engine, ohne etwas abzuspielen.
"""

from __future__ import annotations

import threading
import time
import wave

import numpy as np

from .audio import BLOCK, CHANNELS, SAMPLE_RATE


class SilentOutput:
    """Treibt die Engine in Echtzeit, ohne Ton auszugeben."""

    def __init__(self):
        self._stop = threading.Event()
        self._t: threading.Thread | None = None
        self.kind = "silent"
        self.info = "stumm (keine Soundausgabe)"

    def start(self, callback) -> None:
        self._callback = callback
        self._stop.clear()
        self._t = threading.Thread(target=self._run, name="out-silent", daemon=True)
        self._t.start()

    def _run(self) -> None:
        period = BLOCK / SAMPLE_RATE
        nxt = time.time()
        while not self._stop.is_set():
            self._callback(BLOCK)
            nxt += period
            delay = nxt - time.time()
            if delay > 0:
                time.sleep(delay)
            else:
                nxt = time.time()

    def stop(self) -> None:
        self._stop.set()
        if self._t:
            self._t.join(timeout=1.0)


class WavOutput:
    """Schreibt den Masterton in eine 16-Bit-WAV-Datei (für Tests)."""

    def __init__(self, path: str, seconds: float | None = None):
        self.path = path
        self.seconds = seconds
        self._stop = threading.Event()
        self._t: threading.Thread | None = None
        self.kind = "wav"
        self.info = f"WAV -> {path}"

    def start(self, callback) -> None:
        self._callback = callback
        self._stop.clear()
        self._t = threading.Thread(target=self._run, name="out-wav", daemon=True)
        self._t.start()

    def _run(self) -> None:
        total = int((self.seconds or 0) * SAMPLE_RATE)
        written = 0
        with wave.open(self.path, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            while not self._stop.is_set():
                block = np.asarray(self._callback(BLOCK))
                pcm = np.clip(block, -1, 1)
                wf.writeframes((pcm * 32767).astype(np.int16).tobytes())
                written += len(block)
                if total and written >= total:
                    break
                time.sleep(0.001)
        self._stop.set()

    def stop(self) -> None:
        self._stop.set()
        if self._t:
            self._t.join(timeout=2.0)


class PortAudioOutput:
    """Echtzeit-Ausgabe über sounddevice/PortAudio."""

    def __init__(self, device=None):
        self.device = device
        self._stream = None
        self._callback = None
        self.kind = "portaudio"
        self.info = ""

    def start(self, callback) -> None:
        import sounddevice as sd    # kann ImportError/OSError werfen
        self._callback = callback

        def _cb(outdata, frames, time_info, status):
            outdata[:] = np.asarray(self._callback(frames), dtype=np.float32)

        self._stream = sd.OutputStream(
            samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32",
            blocksize=BLOCK, device=self.device, callback=_cb)
        self._stream.start()
        self.info = f"PortAudio-Gerät {self.device if self.device is not None else 'Standard'}"

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None


def make_output(device=None, wav: str | None = None, seconds: float | None = None):
    """Beste verfügbare Ausgabe wählen und zurückgeben (nie None)."""
    if wav:
        return WavOutput(wav, seconds)
    try:
        import sounddevice  # noqa: F401
        out = PortAudioOutput(device=device)
        # sofort prüfen, ob PortAudio wirklich geht
        import sounddevice as sd
        sd.check_output_settings(samplerate=SAMPLE_RATE, channels=CHANNELS,
                                 dtype="float32", device=device)
        return out
    except Exception as exc:
        o = SilentOutput()
        o.info = f"stumm – keine Soundausgabe ({type(exc).__name__})"
        print(f"[output] {o.info}")
        return o


def list_devices() -> list[dict]:
    try:
        import sounddevice as sd
        devs = []
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_output_channels", 0) > 0:
                devs.append({"index": i, "name": d["name"],
                             "channels": d["max_output_channels"]})
        return devs
    except Exception:
        return []
