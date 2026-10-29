"""Kleiner HTTP-Server (nur Standardbibliothek) + JSON-API.

Seiten
  GET  /                    je nach Modus Radio- oder Programm-Oberfläche
                            (Funk-Teil aus: immer die Programm-Oberfläche)
  GET  /radio, /programm    eine bestimmte Oberfläche (/radio nur mit Funk-Teil)
  GET  /static/<datei>      statische Dateien
  GET  /media/<datei>       Einspielung für die Vorschau im Browser

Zustand / Bedienung
  GET  /api/state           kompletter Zustand (Polling)
  GET  /api/config          Konfiguration      POST /api/config  (teilweise ändern)
  POST /api/tune            {"station": id}
  POST /api/back            zurück zum Programm (Wache verwerfen)
  POST /api/volume          {"value": 0..1}
  POST /api/mute            {"muted": true|false}
  POST /api/play            {"files": [...], "label": "...", "mode": "duck"|"replace"}
                            oder {"entry": id} – Einspielung im Raum abspielen
  POST /api/oneshot/stop    laufende Einspielung stoppen, Warteschlange leeren
  POST /api/entry           {"id": id, "enabled": bool} / {"id": id, "skip_today": bool}
  POST /api/mode            {"mode": "radio"|"program"}  ("radio" nur mit Funk-Teil)
  POST /api/funk            {"enabled": true|false} – Funk-Teil ein-/ausschalten
  GET  /api/media           Medienliste
  PUT  /api/media/<name>    Datei hochladen (Rohdaten, max. 50 MB)
Nur mit eingeschaltetem Funk-Teil (sonst 409):
  POST /api/same/test       {"event": "TOR", "area": true}
  POST /api/translate       {"enabled": true|false}, {"clear": true} und/oder
                            {"model": "small"|"medium"|…}
  GET  /api/devices         Audiogeräte

Alle Dateizugriffe bleiben im Static- bzw. Medienordner (kein ``../``).
"""

from __future__ import annotations

import json
import mimetypes
import socket
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from . import __version__
from .media import MAX_UPLOAD, list_media, resolve, safe_name
from .output import list_devices

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
PAGES = {"radio": "index.html", "program": "program.html"}


def _inside(base: Path, rel: str) -> Path | None:
    base = base.resolve()
    try:
        p = (base / rel).resolve()
    except (OSError, ValueError):
        return None
    return p if base in p.parents else None


class _Handler(BaseHTTPRequestHandler):
    engine = None
    config = None
    server_version = f"Satellit/{__version__}"

    def log_message(self, *a):
        pass

    # --- Helfer -----------------------------------------------------------
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n or n > 1_000_000:
            return {}
        try:
            data = json.loads(self.rfile.read(n).decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _file(self, path: Path | None):
        if path is None or not path.is_file():
            self._json({"error": "not found"}, 404)
            return
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, where: str):
        self.send_response(303)
        self.send_header("Location", where)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _no_funk(self) -> bool:
        """Funk-Schnittstelle bei ausgeschaltetem Funk-Teil: 409 und True."""
        if self.engine.funk is None:
            self._json({"error": "Funk-Teil ist ausgeschaltet"}, 409)
            return True
        return False

    def _path(self) -> str:
        return unquote(self.path.split("?", 1)[0])

    # --- GET --------------------------------------------------------------
    def do_GET(self):
        p = self._path()
        funk = getattr(self.engine, "funk", None) is not None
        if p in ("/", "/index.html"):
            mode = self.config.get("mode", default="radio") if funk else "program"
            self._file(STATIC_DIR / PAGES.get(mode, "index.html"))
        elif p == "/radio":
            if funk:
                self._file(STATIC_DIR / "index.html")
            else:
                self._redirect("/programm")
        elif p in ("/programm", "/program"):
            self._file(STATIC_DIR / "program.html")
        elif p.startswith("/static/"):
            self._file(_inside(STATIC_DIR, p[len("/static/"):]))
        elif p.startswith("/media/"):
            self._file(resolve(self.config.media_dir, p[len("/media/"):]))
        elif p == "/api/state":
            self._json(self.engine.state())
        elif p == "/api/config":
            self._json(self.config.data)
        elif p == "/api/media":
            self._json({"media": list_media(self.config.media_dir)})
        elif p == "/api/devices":
            self._json({"devices": list_devices()})
        else:
            self._json({"error": "unknown"}, 404)

    # --- POST -------------------------------------------------------------
    def do_POST(self):
        p = self._path()
        b = self._body()
        eng = self.engine
        if p == "/api/tune":
            self._json({"ok": eng.tune(str(b.get("station", "")))})
        elif p == "/api/back":
            eng.back_to_program()
            self._json({"ok": True})
        elif p == "/api/volume":
            try:
                eng.set_volume(float(b.get("value", 0.5)))
                self._json({"ok": True})
            except (TypeError, ValueError):
                self._json({"error": "value"}, 400)
        elif p == "/api/mute":
            eng.set_muted(bool(b.get("muted", True)))
            self._json({"ok": True, "muted": eng.mixer.muted})
        elif p == "/api/play":
            self._play(b)
        elif p == "/api/oneshot/stop":
            eng.stop_oneshot()
            self._json({"ok": True})
        elif p == "/api/entry":
            self._entry(b)
        elif p == "/api/mode":
            mode = b.get("mode")
            if mode not in PAGES:
                self._json({"error": "mode"}, 400)
                return
            if mode == "radio" and self._no_funk():
                return
            self.config.update({"mode": mode})
            self._json({"ok": True, "mode": mode})
        elif p == "/api/config":
            if "funk" in b:            # Schalter nur über /api/funk (startet/stoppt Dienste)
                b = {k: v for k, v in b.items() if k != "funk"}
            self.config.update(b)
            eng.reload_schedule()
            if eng.funk is not None:
                eng.funk.apply(self.config.data)
            self._json({"ok": True})
        elif p == "/api/funk":
            eng.set_funk(bool(b.get("enabled", False)))
            self._json({"ok": True, "enabled": eng.funk is not None,
                        "missing": eng._funk_missing()})
        elif p == "/api/same/test":
            if not self._no_funk():
                self._same_test(b)
        elif p == "/api/translate":
            if self._no_funk():
                return
            from .funk.translate import MODELS
            funk = eng.funk
            if b.get("clear"):
                funk.translator.clear()
            if "model" in b:
                if b["model"] not in MODELS:
                    self._json({"error": "model"}, 400)
                    return
                funk.set_translate_model(b["model"])
            if "enabled" in b:
                funk.set_translate(bool(b["enabled"]))
            self._json({"ok": True, "enabled": funk.translator.enabled})
        else:
            self._json({"error": "unknown"}, 404)

    # --- PUT: Upload ------------------------------------------------------
    def do_PUT(self):
        p = self._path()
        if not p.startswith("/api/media/"):
            self._json({"error": "unknown"}, 404)
            return
        name = safe_name(p[len("/api/media/"):])
        n = int(self.headers.get("Content-Length", 0) or 0)
        if name is None:
            self._json({"error": "Dateiname/-typ nicht erlaubt"}, 400)
            return
        if n <= 0 or n > MAX_UPLOAD:
            self._json({"error": "Datei leer oder größer als 50 MB"}, 413)
            return
        md = self.config.media_dir
        md.mkdir(parents=True, exist_ok=True)
        target = resolve(md, name)
        tmp = target.with_suffix(target.suffix + ".part")
        left = n
        with open(tmp, "wb") as fh:
            while left > 0:
                chunk = self.rfile.read(min(65536, left))
                if not chunk:
                    break
                fh.write(chunk)
                left -= len(chunk)
        if left:
            tmp.unlink(missing_ok=True)
            self._json({"error": "Upload unvollständig"}, 400)
            return
        tmp.replace(target)
        self.engine._log(f"Datei hochgeladen: {name}")
        self._json({"ok": True, "name": name})

    # --- Nebenwirkungen ---------------------------------------------------
    def _play(self, b):
        eng = self.engine
        if b.get("entry"):
            e = eng.scheduler.by_id(str(b["entry"]))
            if e is None or not e.play:
                self._json({"error": "Eintrag ohne Einspielung"}, 400)
                return
            ok = eng.play_now(e.play, label=(e.label or ", ".join(e.play)) + " (Test)",
                              mode=e.mode)
        else:
            files = b.get("files") or ([b["file"]] if b.get("file") else [])
            ok = eng.play_now([str(f) for f in files], label=str(b.get("label", "")),
                              mode=b.get("mode", "duck"))
        self._json({"ok": ok})

    def _entry(self, b):
        eid = str(b.get("id", ""))
        fields = {}
        if "enabled" in b:
            fields["enabled"] = bool(b["enabled"])
        if "skip_today" in b:
            fields["skip_date"] = date.today().isoformat() if b["skip_today"] else None
        if not fields or not self.config.set_entry(eid, **fields):
            self._json({"error": "Eintrag unbekannt"}, 404)
            return
        self.engine.reload_schedule()
        e = self.engine.scheduler.by_id(eid)
        label = (e.label or e.station or ", ".join(e.play) or e.action) if e else eid
        if "enabled" in fields:
            self.engine._log(f"{label}: {'an' if fields['enabled'] else 'aus'}")
        if "skip_date" in fields:
            self.engine._log(f"{label}: {'heute ausgesetzt' if fields['skip_date'] else 'heute wieder aktiv'}")
        self._json({"ok": True})

    def _same_test(self, body):
        from .funk.same import build_header, parse_header
        event = str(body.get("event", "RWT"))[:3].upper()
        fips = self.config.get("same", "fips", default=["000000"])
        loc = fips[0] if body.get("area", True) and fips else "000000"
        hdr = build_header(org="WXR", event=event, locations=[loc],
                           purge="0030", station="KEC55")
        parsed = parse_header(hdr)
        if parsed:
            self.engine.funk._on_same_header(parsed)
        self._json({"ok": bool(parsed), "header": hdr})


class _V6Server(ThreadingHTTPServer):
    address_family = socket.AF_INET6

    def __init__(self, addr, handler, dual: bool = False):
        self._dual = dual
        super().__init__(addr, handler)

    def server_bind(self):
        # "::" mit V6ONLY=0 nimmt auch IPv4 an (ein Socket fürs ganze Netz)
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0 if self._dual else 1)
        super().server_bind()


def make_servers(listen: str, port: int, handler) -> list:
    """Server für IPv4 und IPv6.

    ``localhost`` heißt auf vielen Systemen zuerst ``::1`` – manche Browser
    versuchen dann kein IPv4 mehr. Deshalb lokal 127.0.0.1 *und* ::1, fürs
    Heimnetz (0.0.0.0) ein Dual-Stack-Socket auf ``::``. Fehlt IPv6, bleibt
    es still bei IPv4.
    """
    if listen in ("127.0.0.1", "localhost"):
        servers = [ThreadingHTTPServer(("127.0.0.1", port), handler)]
        try:
            servers.append(_V6Server(("::1", port), handler))
        except OSError:
            pass
        return servers
    if listen in ("0.0.0.0", "::"):
        try:
            return [_V6Server(("::", port), handler, dual=True)]
        except OSError:
            return [ThreadingHTTPServer(("0.0.0.0", port), handler)]
    if ":" in listen:
        return [_V6Server((listen, port), handler)]
    return [ThreadingHTTPServer((listen, port), handler)]


def serve_background(servers: list) -> None:
    for s in servers:
        threading.Thread(target=s.serve_forever, name="web", daemon=True).start()


def serve(engine, config, listen="127.0.0.1", port=8080):
    _Handler.engine = engine
    _Handler.config = config
    servers = make_servers(listen, port, _Handler)
    where = "localhost" if listen in ("127.0.0.1", "0.0.0.0", "::") else listen
    print(f"Satellit {__version__} – Oberfläche: http://{where}:{port}")
    serve_background(servers[1:])
    try:
        servers[0].serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for s in servers:
            s.shutdown()
            s.server_close()
    return servers[0]
