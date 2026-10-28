"""Medienordner: Einspielungen und lokale Musik.

Alles, was Satellit lokal abspielt, liegt unter einem Ordner (Standard:
``media`` neben der config.json). Dateinamen von außen (Oberfläche, API)
werden hier geprüft – nie ein Pfad außerhalb des Medienordners.
"""

from __future__ import annotations

import re
import wave
from pathlib import Path

import numpy as np

from .sources.file import AUDIO_EXT, duration_seconds

MAX_UPLOAD = 50 * 1024 * 1024
_SAFE = re.compile(r"[^A-Za-z0-9ÄÖÜäöüß._ -]")


def safe_name(name: str) -> str | None:
    """Erlaubter Dateiname oder None (kein Pfad, bekannte Endung)."""
    name = Path(str(name).replace("\\", "/")).name.strip()
    name = _SAFE.sub("_", name)
    if not name or name.startswith(".") or Path(name).suffix.lower() not in AUDIO_EXT:
        return None
    return name


def resolve(media_dir: Path, rel: str) -> Path | None:
    """Relativen Namen (auch ``musik/titel.mp3``) sicher im Medienordner auflösen."""
    base = media_dir.resolve()
    try:
        p = (base / rel).resolve()
    except (OSError, ValueError):
        return None
    if p != base and base not in p.parents:
        return None
    return p


def list_media(media_dir: Path) -> list[dict]:
    """Einspielungen (oberste Ebene) + Unterordner als Musikquellen."""
    out = []
    if not media_dir.is_dir():
        return out
    for p in sorted(media_dir.iterdir(), key=lambda x: x.name.lower()):
        if p.is_file() and p.suffix.lower() in AUDIO_EXT:
            out.append({"name": p.name, "kind": "file", "size": p.stat().st_size,
                        "seconds": duration_seconds(p)})
        elif p.is_dir() and not p.name.startswith("."):
            n = sum(1 for f in p.iterdir() if f.suffix.lower() in AUDIO_EXT)
            out.append({"name": p.name, "kind": "folder", "files": n})
    return out


def ensure_demo(media_dir: Path) -> None:
    """Beim ersten Start: Ordner anlegen und einen weichen Gong erzeugen,
    damit man sofort ohne Internet etwas zum Ausprobieren hat."""
    media_dir.mkdir(parents=True, exist_ok=True)
    (media_dir / "musik").mkdir(exist_ok=True)
    gong = media_dir / "gong.wav"
    if gong.exists():
        return
    sr = 48_000
    t = np.arange(int(sr * 2.4)) / sr
    tone = np.zeros_like(t)
    # zwei Töne (Ding–Dong), mit Obertönen und weichem Abklingen
    for start, f in ((0.0, 659.25), (0.6, 523.25)):
        tt = np.clip(t - start, 0, None)
        env = np.where(t >= start, np.exp(-tt * 2.2) * (1 - np.exp(-tt * 300)), 0)
        tone += env * (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2 * f * tt))
    tone = tone / np.max(np.abs(tone)) * 0.5
    pcm = (tone * 32767).astype("<i2")
    with wave.open(str(gong), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
