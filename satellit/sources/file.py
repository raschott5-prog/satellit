"""Lokale Dateien: einzelne Einspielung oder ganzer Musikordner.

* :class:`FileSource` – eine Datei, endlich (Ansage, Gong, eigene Aufnahme)
  oder als Schleife (z. B. Pausenmusik). Meldet ``finished``, sobald der
  letzte Ton wirklich ausgespielt ist – darauf baut die Einspielungs-Ebene:
  nicht die Uhr beendet eine Ansage, sondern das Dateiende.
* :class:`FolderSource` – alle Audiodateien eines Ordners, gemischt, endlos.
  Typischer Ersatzbetrieb: läuft ohne Internet.

WAV wird ohne ffmpeg gelesen (Standardbibliothek + numpy), alles andere
(MP3, OGG, FLAC, M4A …) über ffmpeg.
"""

from __future__ import annotations

import random
import subprocess
import wave
from pathlib import Path

import numpy as np

from ..audio import CHANNELS, SAMPLE_RATE, as_stereo
from .base import Source
from .stream import ffmpeg_path

AUDIO_EXT = {".wav", ".mp3", ".ogg", ".oga", ".opus", ".flac", ".m4a", ".aac"}


def read_wav(path: str | Path) -> np.ndarray:
    """WAV -> (frames, 2) float32 bei 48 kHz. 8/16/24/32-Bit-PCM."""
    with wave.open(str(path), "rb") as wf:
        ch, width, rate = wf.getnchannels(), wf.getsampwidth(), wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    if width == 1:
        data = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128) / 128
    elif width == 2:
        data = np.frombuffer(raw, "<i2").astype(np.float32) / 32768
    elif width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3)
        v = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8)
             | (b[:, 2].astype(np.int32) << 16))
        v = np.where(v & 0x800000, v - 0x1000000, v)
        data = v.astype(np.float32) / 8388608
    elif width == 4:
        data = np.frombuffer(raw, "<i4").astype(np.float32) / 2147483648
    else:
        raise ValueError(f"WAV mit {width * 8} Bit nicht unterstützt")
    data = data.reshape(-1, ch)
    if rate != SAMPLE_RATE and len(data):
        n_out = int(round(len(data) * SAMPLE_RATE / rate))
        x_old = np.arange(len(data))
        x_new = np.linspace(0, len(data) - 1, n_out)
        data = np.stack([np.interp(x_new, x_old, data[:, c]) for c in range(ch)],
                        axis=1).astype(np.float32)
    return as_stereo(data)


def duration_seconds(path: str | Path) -> float | None:
    """Dauer einer Datei (WAV direkt, sonst None – reicht für die Anzeige)."""
    try:
        if str(path).lower().endswith(".wav"):
            with wave.open(str(path), "rb") as wf:
                return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return None
    return None


class _Decoder:
    """Gemeinsamer Lesepfad: WAV nativ, sonst ffmpeg-Prozess."""

    def __init__(self, owner: Source):
        self.owner = owner
        self.proc: subprocess.Popen | None = None

    def play(self, path: Path, gain: float) -> bool:
        """Spielt eine Datei komplett in den Puffer. False = abgebrochen."""
        if path.suffix.lower() == ".wav":
            return self.owner._emit_paced(read_wav(path) * gain)
        exe = ffmpeg_path()
        if not exe:
            raise RuntimeError("ffmpeg fehlt – nur WAV ohne ffmpeg abspielbar")
        cmd = [exe, "-hide_banner", "-loglevel", "error", "-i", str(path),
               "-f", "f32le", "-acodec", "pcm_f32le", "-ar", str(SAMPLE_RATE),
               "-ac", str(CHANNELS), "-"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL)
        frame_bytes = 4 * CHANNELS
        rest = b""
        try:
            while True:
                chunk = self.proc.stdout.read(SAMPLE_RATE * frame_bytes // 4)
                if not chunk:
                    break
                chunk = rest + chunk
                usable = len(chunk) - len(chunk) % frame_bytes
                rest = chunk[usable:]
                block = np.frombuffer(chunk[:usable], np.float32).reshape(-1, CHANNELS)
                if not self.owner._emit_paced(block * gain):
                    return False
        finally:
            self.close()
        return True

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None


class FileSource(Source):
    kind = "file"

    def __init__(self, path: str | Path, name: str = "", gain: float = 1.0,
                 loop: bool = False, **kw):
        kw.setdefault("prebuffer_seconds", 0.25)
        kw.setdefault("fail_fast_seconds", 0.5)
        super().__init__(name=name or Path(path).stem, **kw)
        self.path = Path(path)
        self.gain = gain
        self.loop = loop
        self.eof = False
        self._dec = _Decoder(self)

    def run(self) -> None:
        if not self.path.is_file():
            self.error = f"Datei fehlt: {self.path.name}"
            self.status = "error"
            return
        while not self._stop.is_set():
            if not self._dec.play(self.path, self.gain):
                return
            if not self.loop:
                break
        self.eof = True
        if self.status == "connecting" and self.buffer.available > 0:
            self.status = "playing"      # sehr kurze Datei unter Vorpuffer
            self.was_ready = True

    @property
    def ready(self) -> bool:
        if self.status != "playing":
            return False
        return self.buffer.available >= self._prebuffer or self.eof

    @property
    def finished(self) -> bool:
        """Letzter Ton ausgespielt (bzw. Datei unspielbar)."""
        return self.status == "error" or (self.eof and self.buffer.available == 0)

    def stop(self) -> None:
        self._dec.close()
        super().stop()


class FolderSource(Source):
    """Ordner mit Musik: gemischt, endlos. Läuft ohne Netz."""

    kind = "folder"

    def __init__(self, path: str | Path, name: str = "", gain: float = 1.0,
                 shuffle: bool = True, **kw):
        kw.setdefault("prebuffer_seconds", 0.25)
        kw.setdefault("fail_fast_seconds", 0.5)
        super().__init__(name=name or Path(path).name, **kw)
        self.path = Path(path)
        self.gain = gain
        self.shuffle = shuffle
        self.current: str | None = None
        self._dec = _Decoder(self)

    def files(self) -> list[Path]:
        if not self.path.is_dir():
            return []
        return sorted(p for p in self.path.iterdir()
                      if p.is_file() and p.suffix.lower() in AUDIO_EXT)

    def run(self) -> None:
        files = self.files()
        if not files:
            self.error = f"Ordner leer oder fehlt: {self.path}"
            self.status = "error"
            return
        bad = 0
        while not self._stop.is_set():
            order = files[:]
            if self.shuffle:
                random.shuffle(order)
            for f in order:
                self.current = f.stem
                try:
                    if not self._dec.play(f, self.gain):
                        return
                    bad = 0
                except Exception:
                    bad += 1
                    if bad >= len(files):
                        self.error = "keine Datei im Ordner abspielbar"
                        self.status = "error"
                        return
            files = self.files() or files      # neu eingelegte Titel aufnehmen

    def stop(self) -> None:
        self._dec.close()
        super().stop()

    def describe(self) -> dict:
        d = super().describe()
        d["title"] = self.current
        return d
