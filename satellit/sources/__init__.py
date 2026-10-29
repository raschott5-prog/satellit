"""Quellen-Fabrik: aus einem Konfig-Eintrag die passende Quelle bauen.

Hier liegen nur die Quellen des Grundgeräts. Web-SDR-Empfänger (``kiwi``,
``ubersdr``, ``websdr``) gehören zum Funk-Teil und werden nur gebaut, wenn
er eingeschaltet ist (``funk=True``).
"""

from __future__ import annotations

from typing import Any

from pathlib import Path

from .base import Source
from .file import FileSource, FolderSource
from .silence import ErrorSource, SilenceSource
from .stream import StreamSource

__all__ = ["Source", "StreamSource", "SilenceSource", "ErrorSource", "FileSource",
           "FolderSource", "make_source", "FUNK_KINDS"]

#: gleichlautend mit ``satellit.funk.FUNK_KINDS`` – hier ohne den Funk-Teil zu laden
FUNK_KINDS = ("kiwi", "ubersdr", "websdr")


def _error(name: str, text: str) -> ErrorSource:
    return ErrorSource(name=name, error=text)


def make_source(spec: dict[str, Any], *, uuid: str = "",
                media_dir: str | Path | None = None, funk: bool = False) -> Source:
    """Erzeugt eine Quelle aus einem Stations-/Kanal-Dict.

    Unbekannte oder unvollständige Angaben ergeben eine ``ErrorSource``, damit
    nie etwas abstürzt – der Fehler steht im Status, die Engine nimmt den Ersatz.
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
        if kind in FUNK_KINDS:
            if not funk:
                return _error(name or kind, "gehört zum Funk-Teil – der ist ausgeschaltet")
            from ..funk import make_source as make_funk_source
            return make_funk_source(spec, uuid=uuid, **kw)
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
        return _error(name or "(unvollständig)", f"Feld fehlt: {exc}")
    except ValueError as exc:
        return _error(name or "(ungültig)", str(exc))
    return _error(name or f"(unbekannt: {kind})", f"unbekannte Quellenart: {kind}")
