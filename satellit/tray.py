"""Tray-Symbol (Windows/Linux/macOS).

Startet Satellit im Hintergrund und legt ein Symbol in den Infobereich mit
Menü „Oberfläche öffnen" und „Beenden". Braucht ``pystray`` und ``Pillow``;
fehlen sie, startet ``main`` ersatzweise den normalen Konsolenbetrieb.

Start:  ``python -m satellit.tray``  (oder über run-satellit.bat)
"""

from __future__ import annotations

import sys
import webbrowser

from .config import Config, default_config_path
from .engine import Engine
from .output import make_output
from .web import _Handler, make_servers, serve_background


def _icon_image():
    """Kleines Satellit-Zifferblatt als Icon (PIL)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (20, 18, 14, 255))
    d = ImageDraw.Draw(img)
    d.ellipse((6, 6, 58, 58), outline=(255, 181, 77, 255), width=3)
    d.line((32, 32, 50, 18), fill=(255, 107, 90, 255), width=3)   # Zeiger
    for a in range(10, 55, 8):
        d.line((a, 14, a, 18), fill=(255, 181, 77, 180), width=1)
    return img


def run(config_path=None, open_browser=True) -> int:
    try:
        import pystray
    except ImportError:
        print("pystray/Pillow fehlen – starte normalen Konsolenbetrieb.")
        from .__main__ import main
        return main([])

    config = Config(path=config_path or default_config_path()).load()
    listen = config.get("web", "listen", default="127.0.0.1")
    port = config.get("web", "port", default=8080)
    url = f"http://localhost:{port}"

    output = make_output(device=config.get("audio", "device", default=None))
    engine = Engine(config, output=output)
    engine.start()

    _Handler.engine = engine
    _Handler.config = config
    servers = make_servers(listen, port, _Handler)
    serve_background(servers)
    print(f"Satellit läuft – {url}")

    def _open(icon, item):
        webbrowser.open(url)

    def _quit(icon, item):
        icon.stop()

    icon = pystray.Icon(
        "satellit", _icon_image(), "Satellit",
        menu=pystray.Menu(
            pystray.MenuItem("Oberfläche öffnen", _open, default=True),
            pystray.MenuItem("Beenden", _quit),
        ))
    if open_browser:
        webbrowser.open(url)
    try:
        icon.run()        # blockiert bis „Beenden"
    finally:
        for s in servers:
            s.shutdown()
        engine.stop()
    return 0


if __name__ == "__main__":
    sys.exit(run())
