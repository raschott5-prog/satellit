"""Quellen-Fabrik: aus einem Konfig-Eintrag die passende Quelle bauen."""

from __future__ import annotations

from typing import Any

from pathlib import Path

from .base import Source
from .file import FileSource, FolderSource
from .kiwi import KiwiSource
from .silence import SilenceSource
from .stream import StreamSource
from .ubersdr import UberSDRSource

__all__ = ["Source", "StreamSource", "KiwiSource", "UberSDRSource",
           "SilenceSource", "FileSource", "FolderSource", "make_source"]


def make_source(spec: dict[str, Any], *, uuid: str = "",
                media_dir: str | Path | None = None) -> Source:
    """Erzeugt eine Quelle aus einem Stations-/Kanal-Dict.

    Unbekannte oder unvollständige Angaben ergeben eine Stillequelle, damit
    nie etwas abstürzt – der Fehler steht dann im Status.
    """
    kind = spec.get("kind", "stream")
    name = spec.get("name", "")
    gain = float(spec.get("gain", 1.0))
    kw: dict[str, Any] = {}
    if spec.get("buffer") is not None:    # Vorlauf in s, sonst Standard 0,6 s
        kw["prebuffer_seconds"] = float(spec["buffer"])
    try:
        if kind == "stream":
            return StreamSource(url=spec["url"], name=name, gain=gain, **kw)
        if kind == "kiwi":
            return KiwiSource(host=spec["host"], freq_khz=spec["freq_khz"],
                              mode=spec.get("mode", "am"), name=name, gain=gain,
                              password=spec.get("password", ""), **kw)
        if kind == "ubersdr":
            return UberSDRSource(host=spec["host"], freq_khz=spec["freq_khz"],
                                 mode=spec.get("mode", "am"), name=name, gain=gain,
                                 user_session_id=uuid, **kw)
        if kind in ("file", "folder"):
            p = Path(spec["path"])
            if not p.is_absolute() and media_dir is not None:
                p = Path(media_dir) / p
            if kind == "file":
                return FileSource(p, name=name, gain=gain,
                                  loop=bool(spec.get("loop", True)))
            return FolderSource(p, name=name, gain=gain,
                                shuffle=bool(spec.get("shuffle", True)))
        if kind in ("silence", "noise"):
            return SilenceSource(name=name or "—",
                                 noise=float(spec.get("noise", 0.0)))
    except KeyError as exc:
        s = SilenceSource(name=name or "(unvollständig)")
        s.error = f"Feld fehlt: {exc}"
        s.status = "error"
        return s
    s = SilenceSource(name=name or f"(unbekannt: {kind})")
    s.error = f"unbekannte Quellenart: {kind}"
    s.status = "error"
    return s
