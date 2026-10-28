"""Startpunkt:  ``python -m satellit``

Optionen siehe README. Baut Konfiguration, Ausgabe, Engine und Web-Server
zusammen und läuft, bis der Server beendet wird.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import Config, default_config_path
from .engine import Engine
from .output import make_output
from .web import serve


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="satellit",
        description="Satellit – virtuelles Weltempfänger-Radio")
    p.add_argument("--listen", default=None,
                   help="Adresse der Oberfläche (z. B. 0.0.0.0 fürs ganze Heimnetz)")
    p.add_argument("--port", type=int, default=None, help="Port (Standard 8080)")
    p.add_argument("--device", type=int, default=None, help="Audiogerät (Index)")
    p.add_argument("--wav", default=None,
                   help="statt Lautsprecher in diese WAV-Datei schreiben (Tests)")
    p.add_argument("--config", default=None, help="andere Konfigurationsdatei")
    p.add_argument("--mode", choices=["radio", "program"], default=None,
                   help="Oberfläche: radio (Skala, SDR) oder program (Wochenplan, Ansagen)")
    p.add_argument("--list-devices", action="store_true",
                   help="Audiogeräte auflisten und beenden")
    p.add_argument("--version", action="version", version=f"Satellit {__version__}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_devices:
        from .output import list_devices
        devs = list_devices()
        for d in devs:
            print(f"  [{d['index']}] {d['name']}  ({d['channels']} Kanäle)")
        if not devs:
            print("(keine Ausgabegeräte / sounddevice fehlt)")
        return 0

    config = Config(path=args.config or default_config_path()).load()
    if args.mode:
        config.update({"mode": args.mode})

    listen = args.listen or config.get("web", "listen", default="127.0.0.1")
    port = args.port or config.get("web", "port", default=8080)
    device = args.device if args.device is not None \
        else config.get("audio", "device", default=None)

    output = make_output(device=device, wav=args.wav)
    print(f"Ausgabe: {output.info}")

    engine = Engine(config, output=output)
    engine.start()
    try:
        serve(engine, config, listen=listen, port=port)
    finally:
        engine.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
