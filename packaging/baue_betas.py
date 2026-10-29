"""Beta-Pakete für Windows und macOS bauen.

    python packaging/baue_betas.py [--kontakt ADRESSE] [--ziel ORDNER]

Ein Paket = Vorlage (``windows-beta/`` bzw. ``mac-beta/``) + ``satellit/``,
``static/`` und ``LICENSE`` aus dem Projekt, als Zip. Ohne ``--kontakt``
verweisen die Pakete auf die GitHub-Issues. Mit ``--kontakt`` steht stattdessen
diese (E-Mail-)Adresse drin – sie wird nur beim Bauen eingesetzt und nie im
Repo gespeichert.

Zeilenenden und Dateirechte bleiben erhalten (``.bat`` mit CRLF, ``.command``
und ``.sh`` ausführbar). Unter Linux oder macOS bauen.
"""

from __future__ import annotations

import argparse
import shutil
import stat
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from satellit import __version__  # noqa: E402

ISSUES = "https://github.com/raschott5-prog/satellit/issues"
ISSUES_KURZ = "github.com/raschott5-prog/satellit/issues"

PAKETE = {
    "windows": ("windows-beta", "Satellit-{v}-Beta"),
    "mac": ("mac-beta", "Satellit-{v}-Beta-Mac"),
}


def kontakt_einsetzen(text: str, kontakt: str) -> str:
    """Hinweise auf die GitHub-Issues durch eine E-Mail-Adresse ersetzen."""
    for alt, neu in (
        ("als Meldung (Issue) einstellen unter:", "per E-Mail schicken an:"),
        (f"    {ISSUES}", f"    {kontakt}"),
        (f"unter {ISSUES_KURZ} melden.", f"an {kontakt} schicken."),
        (f'MAIL="{ISSUES}"', f'MAIL="{kontakt}"'),
        ("als Meldung unter $MAIL einstellen.", "an $MAIL schicken."),
    ):
        text = text.replace(alt, neu)
    return text


def _ignore(_dir, names):
    return [n for n in names if n == "__pycache__" or n.endswith((".pyc", ".pyo"))]


def baue(was: str, ziel: Path, kontakt: str | None) -> Path:
    vorlage, ordnername = PAKETE[was]
    kurz = ".".join(__version__.split(".")[:2])          # 0.4.1 -> 0.4
    name = ordnername.format(v=kurz)
    arbeit = ziel / f"satellit-{kurz}-beta-{was}"
    if arbeit.exists():
        shutil.rmtree(arbeit)
    arbeit.mkdir(parents=True)
    for f in sorted((ROOT / "packaging" / vorlage).iterdir()):
        dst = arbeit / f.name
        if kontakt and f.suffix in (".txt", ".bat", ".command", ".sh"):
            # binär lesen/schreiben: CRLF der .bat-Dateien bleibt unangetastet
            dst.write_bytes(kontakt_einsetzen(f.read_bytes().decode("utf-8"),
                                              kontakt).encode("utf-8"))
            shutil.copymode(f, dst)
        else:
            shutil.copy2(f, dst)
    shutil.copytree(ROOT / "satellit", arbeit / "satellit", ignore=_ignore)
    shutil.copytree(ROOT / "static", arbeit / "static", ignore=_ignore)
    shutil.copytree(ROOT / "beispiele", arbeit / "beispiele", ignore=_ignore)
    for doc in (ROOT / "docs").glob("beispiel-*.md"):     # Beschreibung gleich daneben
        shutil.copy2(doc, arbeit / "beispiele" / doc.name)
    shutil.copy2(ROOT / "LICENSE", arbeit / "LICENSE")

    zip_pfad = ziel / f"satellit-{kurz}-beta-{was}.zip"
    with zipfile.ZipFile(zip_pfad, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(arbeit.rglob("*")):
            info = zipfile.ZipInfo.from_file(p, f"{name}/{p.relative_to(arbeit)}")
            if p.is_dir():
                z.writestr(info, b"")
                continue
            if p.suffix in (".command", ".sh"):          # Doppelklick unter macOS
                info.external_attr = (stat.S_IFREG | 0o755) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, p.read_bytes())
    return zip_pfad


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kontakt", help="E-Mail statt GitHub-Issues (nur im Paket)")
    ap.add_argument("--ziel", default=str(ROOT / "dist"), help="Ausgabeordner")
    ap.add_argument("--nur", choices=sorted(PAKETE), help="nur ein Paket bauen")
    a = ap.parse_args()
    ziel = Path(a.ziel).expanduser()
    ziel.mkdir(parents=True, exist_ok=True)
    for was in ([a.nur] if a.nur else sorted(PAKETE)):
        print(baue(was, ziel, a.kontakt))


if __name__ == "__main__":
    main()
