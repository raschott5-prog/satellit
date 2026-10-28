"""Engine: verbindet Quellen, Mixer, Zeitplan, Wache, SAME, Übersetzer und Einspielungen.

Prioritätsleiter (höher gewinnt) für das, was *läuft*:

    4  SAME EAN           nationaler Notfall – schlägt alles
    3  SAME-Warnung       Tornado/Sturzflut … fürs eigene Gebiet
    2  Wache              Betrieb auf einem beobachteten Kanal
    1  Hand/Zeitplan      Basisauswahl (Hand gilt bis zum nächsten Eintrag)
    0  Schlummern         Master langsam auf 0

Darüber liegt die **Einspielungs-Ebene** (Ansagen, Gong, eigene Aufnahmen).
Sie ersetzt das Programm nicht, sondern legt sich darüber (Musik wird
abgesenkt) oder ersetzt es kurz (``mode: replace``). Regeln – bewusst fest
definiert:

* Eine Einspielung endet mit **ihrem Dateiende**, nie mit der Uhr. Wechselt
  währenddessen das Programm laut Zeitplan, wechselt es *darunter*; danach
  kommt die Musik schon auf dem neuen Programm zurück.
* Überlappen Einspielungen, laufen sie **nacheinander**, ohne die Musik
  zwischendurch hochzufahren. Reihenfolge = Fälligkeit (bei gleicher Zeit
  die Reihenfolge im Plan).
* Mehr als ``max_delay_minutes`` verspätet (Stau, Rechner im Standby) →
  verworfen und protokolliert, nie Stunden später nachgeholt.
* Stumm schaltet sofort alles leise und bricht eine laufende Einspielung ab;
  während Stumm fällige werden übersprungen. Ein SAME-Alarm bricht sie ab.
  Alles landet im Protokoll.

Ersatzbetrieb: Fällt die Programmquelle aus (Stream weg, kein Internet),
übernimmt die Ersatzquelle (Standard: lokaler Musikordner). Die ausgefallene
Quelle wird regelmäßig neu versucht; kommt sie wieder, wird zurückgeblendet.
"""

from __future__ import annotations

import collections
import threading
import time
import uuid as uuidlib
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

from .audio import BLOCK, SAMPLE_RATE
from .media import ensure_demo, resolve as media_resolve
from .mixer import Mixer
from .same import SAMEStream
from .scheduler import Scheduler
from .sources import Source, StreamSource, make_source
from .sources.file import FileSource
from .sources.silence import SilenceSource
from . import hfcc as hfcc_mod
from .translate import Translator
from .watcher import Watcher, WatchChannel

L_SLEEP, L_BASE, L_WATCH, L_SAME_WARN, L_SAME_EAN = 0, 1, 2, 3, 4
RETRY_SECONDS = 60.0
#: Nicht mehr gehörte Quellen nach so vielen Sekunden schließen. Jede offene
#: Kiwi-Verbindung belegt einen der wenigen Plätze eines fremden Empfängers.
IDLE_CLOSE_SECONDS = 15.0


class Engine:
    def __init__(self, config, output=None):
        self.config = config
        self.mixer = Mixer(auto_level=config.get("audio", "auto_level", default=True))
        self.mixer.noise_level = float(config.get("audio", "noise_level", default=0.006))
        vol = float(config.get("audio", "volume", default=0.5))
        self.mixer.volume = self.mixer.volume_to = vol
        self.mixer.overlay_gain = float(config.get("announce", "gain", default=1.0))
        self.output = output

        self.scheduler = Scheduler(
            config.get("schedule", "entries", default=[]),
            enabled=config.get("schedule", "enabled", default=True))

        self.uuid = self._installation_uuid()
        self._sources: dict[str, Source] = {}
        self._last_used: dict[str, float] = {}
        self._lock = threading.Lock()

        # Schichten
        self.base = {"mode": "off"}
        self.manual_active = False
        self.layer_watch: Optional[dict] = None
        self.layer_same: Optional[dict] = None
        self._applied_occurrence = None
        self.fallback_active = False
        self._wake_from_zero = False   # Weck-Eintrag: erst auf 0, dann einblenden

        # Einspielungen
        self.queue: collections.deque = collections.deque()
        self.oneshot: Optional[dict] = None
        self._last_due_check = datetime.now()

        # Anzeige
        self.committed_label = "—"
        self.committed_reason = "start"
        self._committed_key: Optional[str] = None
        self._committed_source = None
        self._pending: Optional[dict] = None
        self.log: collections.deque = collections.deque(maxlen=100)

        self.watcher = Watcher(config.data.get("watcher", {}),
                               on_activity=self._on_watch_activity,
                               on_clear=self._on_watch_clear,
                               is_listening=self._is_listening)
        self._same_streams: list[tuple[Source, SAMEStream]] = []
        self.last_same: list[dict] = []

        self.hfcc = hfcc_mod.HFCC(
            config.path.parent / "hfcc",
            base_url=config.get("hfcc", "base_url", default=hfcc_mod.DEFAULT_BASE),
            refresh_days=float(config.get("hfcc", "refresh_days", default=7)),
            log=self._log)
        self._on_air_cache: tuple[float, dict] = (0.0, {})
        self.translator = Translator(config.data.get("translate", {}),
                                     label_fn=lambda: self.committed_label, log=self._log,
                                     hint_fn=self._language_hint)
        self.mixer.tap = self.translator.feed

        self._control = threading.Thread(target=self._control_loop, name="engine", daemon=True)
        self._same_thread = threading.Thread(target=self._same_loop, name="same", daemon=True)
        self._stop = threading.Event()
        self._start_time = time.time()
        self.started = False

    # =====================================================================
    # Lebenszyklus
    # =====================================================================
    def start(self) -> None:
        if self.started:
            return
        self.started = True
        try:
            ensure_demo(self.config.media_dir)
        except OSError as exc:
            self._log("Medienordner nicht anlegbar: " + str(exc))
        self.mixer.deck_a.source = SilenceSource(name="—").start()
        self._committed_source = self.mixer.deck_a.source
        self._init_base()
        self._last_due_check = datetime.now()
        if self.config.get("mode", default="radio") == "radio":
            self._start_same_monitors()
            if self.config.get("watcher", "enabled", default=True):
                self.watcher.start()
        self._control.start()
        self._same_thread.start()
        self.translator.start()
        if self.output is not None:
            self.output.start(self.render)
        self._log("gestartet")

    def stop(self) -> None:
        self._stop.set()
        self.watcher.stop()
        self.translator.stop()
        if self.output is not None:
            self.output.stop()
        self._end_oneshot(None, quiet=True)
        for s in list(self._sources.values()):
            s.stop()
        for src, _ in self._same_streams:
            src.stop()
        self.started = False

    def render(self, frames: int = BLOCK) -> np.ndarray:
        return self.mixer.process(frames)

    def _log(self, text: str) -> None:
        self.log.appendleft({"t": datetime.now().strftime("%d.%m. %H:%M:%S"), "text": text})

    # =====================================================================
    # Basisauswahl / Zeitplan
    # =====================================================================
    def _installation_uuid(self) -> str:
        u = self.config.get("ubersdr_uuid")
        if not u:
            u = str(uuidlib.uuid4())
            self.config.update({"ubersdr_uuid": u})
        return u

    def _init_base(self) -> None:
        occ = self.scheduler.current_occurrence()
        if occ is None:
            stations = self.config.data.get("stations", [])
            if stations:
                fb = self.config.get("fallback")
                first = next((s for s in stations if s["id"] != fb), stations[0])
                self.base = {"mode": "station", "id": first["id"]}
        else:
            self._apply_entry(occ[1])
            self._applied_occurrence = (occ[0], occ[1].id)

    def _apply_entry(self, entry) -> None:
        self.manual_active = False
        if entry.action == "sleep":
            self.base = {"mode": "sleep", "fade": entry.fade}
        else:
            self.base = {"mode": "station", "id": entry.station,
                         "fade": entry.fade, "wake": entry.wake}
            self._wake_from_zero = bool(entry.wake)

    def reload_schedule(self) -> None:
        self.scheduler.load(self.config.get("schedule", "entries", default=[]))
        self.scheduler.enabled = self.config.get("schedule", "enabled", default=True)

    def _source_for_station(self, station_id: str) -> Optional[Source]:
        """Quelle holen (gecacht). Ausgefallene werden nach RETRY_SECONDS neu versucht."""
        with self._lock:
            self._last_used[station_id] = time.time()
            src = self._sources.get(station_id)
            if src is not None:
                dead = src.failed or (not src.ready and src.waited_too_long())
                if not dead or time.time() - src.started_at < RETRY_SECONDS:
                    return src
                src.stop()   # neuer Versuch mit frischer Quelle
            spec = self.config.station(station_id)
            if spec is None:
                return None
            src = make_source(spec, uuid=self.uuid, media_dir=self.config.media_dir).start()
            self._sources[station_id] = src
            return src

    @staticmethod
    def _source_dead(src) -> bool:
        if src is None:
            return True
        if getattr(src, "failed", False):
            return True
        return (not getattr(src, "ready", True)
                and getattr(src, "waited_too_long", lambda: False)())

    # =====================================================================
    # Bedienung (Web-API)
    # =====================================================================
    def tune(self, station_id: str) -> bool:
        if self.config.station(station_id) is None:
            return False
        self.base = {"mode": "station", "id": station_id,
                     "fade": self.config.get("audio", "crossfade_seconds", default=4.0)}
        self.manual_active = True
        return True

    def back_to_program(self) -> None:
        if self.layer_watch:
            ch = self.layer_watch.get("channel")
            if ch:
                self.watcher.dismiss(ch)
            self._release_watch()

    def set_volume(self, value: float) -> None:
        self.mixer.set_volume(value)
        self.config.update({"audio": {"volume": round(float(self.mixer.volume_to), 3)}})

    def set_muted(self, muted: bool) -> None:
        self.mixer.set_muted(muted)
        if muted and self.oneshot:
            self._end_oneshot("abgebrochen (stumm geschaltet)")
        self._log("stumm" if muted else "Ton wieder an")

    def play_now(self, files: list[str], label: str = "", mode: str = "duck") -> bool:
        """Einspielung sofort in die Warteschlange (Testknopf „im Raum“)."""
        files = [f for f in files if f]
        if not files:
            return False
        self._enqueue({"files": files, "label": label or files[-1], "mode": mode,
                       "due": time.time(), "source": "Hand"})
        return True

    def stop_oneshot(self) -> None:
        if self.oneshot:
            self._end_oneshot("von Hand gestoppt")
        if self.queue:
            self._log(f"{len(self.queue)} wartende Einspielung(en) verworfen")
            self.queue.clear()

    def set_translate(self, enabled: bool) -> None:
        self.translator.set_enabled(enabled)
        self.config.update({"translate": {"enabled": bool(enabled)}})

    def set_translate_model(self, model: str) -> None:
        self.config.update({"translate": {"model": model}})
        self.translator.apply(self.config.data.get("translate", {}))
        self._log(f"Übersetzer: Modell {model}")

    # =====================================================================
    # Sendeplan (HFCC)
    # =====================================================================
    def on_air(self, station_id: Optional[str]) -> list[dict]:
        """Was laut HFCC gerade auf der Frequenz dieses Kiwi/UberSDR-Senders läuft."""
        spec = self.config.station(station_id) if station_id else None
        if not spec or spec.get("kind") not in ("kiwi", "ubersdr") or not spec.get("freq_khz"):
            return []
        if not self.config.get("hfcc", "enabled", default=True):
            return []
        self.hfcc.ensure()                 # lädt beim ersten Bedarf im Hintergrund
        return self.hfcc.on_air(float(spec["freq_khz"]))

    def _current_station(self) -> Optional[str]:
        key = self._committed_key or ""
        return key.split(":", 1)[1] if key[:3] in ("st:", "fb:") else None

    def _language_hint(self) -> Optional[list]:
        return hfcc_mod.candidates(self.on_air(self._current_station()))

    def _on_air_all(self) -> dict:
        """Für die Anzeige: alle Kurzwellensender, höchstens alle 30 s neu."""
        t, cached = self._on_air_cache
        if time.time() - t < 30:
            return cached
        out = {}
        for spec in self.config.data.get("stations", []):
            hits = self.on_air(spec.get("id"))
            if hits:
                out[spec["id"]] = hits[:4]
        self._on_air_cache = (time.time(), out)
        return out

    # =====================================================================
    # Wache
    # =====================================================================
    def _on_watch_activity(self, ch: WatchChannel) -> None:
        src = make_source({"kind": "kiwi", "host": ch.host, "freq_khz": ch.freq_khz,
                           "mode": ch.mode, "name": ch.name}).start()
        self.layer_watch = {"channel": ch, "source": src, "label": ch.name}
        self._log(f"Wache: Betrieb auf {ch.name}")

    def _on_watch_clear(self, ch: WatchChannel) -> None:
        if self.layer_watch and self.layer_watch.get("channel") is ch:
            self._release_watch()

    def _release_watch(self) -> None:
        if self.layer_watch:
            src = self.layer_watch.get("source")
            if isinstance(src, Source):
                src.stop()
        self.layer_watch = None

    def _is_listening(self, ch: WatchChannel) -> bool:
        src = self.mixer.active_deck().source
        host = getattr(src, "host", None)
        fk = getattr(src, "freq_khz", None)
        return bool(host and fk and
                    (host.split("://")[-1], round(float(fk), 1)) == ch.key())

    # =====================================================================
    # SAME
    # =====================================================================
    def _start_same_monitors(self) -> None:
        same = self.config.data.get("same", {})
        if not same.get("enabled", True):
            return
        for spec in same.get("sources", []):
            if spec.get("kind", "stream") != "stream" or not spec.get("url"):
                continue
            src = StreamSource(url=spec["url"], name=spec.get("name", "NWR")).start()
            self._same_streams.append((src, SAMEStream(on_header=self._on_same_header)))

    def _same_loop(self) -> None:
        period = BLOCK / SAMPLE_RATE
        while not self._stop.is_set():
            any_audio = False
            for src, stream in self._same_streams:
                block = src.read(BLOCK)
                if np.any(block):
                    any_audio = True
                stream.feed(block)
            time.sleep(period if any_audio else period * 2)

    def _on_same_header(self, header) -> None:
        if header.is_eom:
            if self.layer_same:
                self.layer_same["until"] = time.time()
            return
        same = self.config.data.get("same", {})
        events = same.get("events", {})
        self.last_same.insert(0, header.as_dict())
        self.last_same = self.last_same[:20]
        ev = header.event
        is_ean = ev == "EAN"
        if ev in events.get("tests", []):
            return
        if not (is_ean or header.matches_area(same.get("fips", []))):
            return
        if ev in events.get("watches", []) and not is_ean:
            return
        srcs = same.get("sources") or [{}]
        spec = srcs[0]
        src = StreamSource(url=spec.get("url", ""), name="SAME").start() \
            if spec.get("url") else SilenceSource(name="SAME").start()
        self.layer_same = {"header": header, "source": src,
                           "label": f"⚠ {header.event_name()}",
                           "level": L_SAME_EAN if is_ean else L_SAME_WARN,
                           "until": time.time() + max(60, header.purge_minutes() * 60),
                           "fade": same.get("fade_seconds", 3.0)}
        self._log(f"SAME: {header.event_name()} – übernimmt")

    # =====================================================================
    # Einspielungen
    # =====================================================================
    def _enqueue(self, item: dict) -> None:
        self.queue.append(item)
        self._log(f"Einspielung eingereiht: {item['label']}")

    def _check_due(self, now: datetime) -> None:
        since = self._last_due_check
        if now <= since:
            return          # Uhr zurückgestellt (Sommerzeit-Ende): nichts doppelt
        self._last_due_check = now
        if now - since > timedelta(days=1):       # Uhr gesprungen: nicht fluten
            since = now - timedelta(days=1)
        for at, e in self.scheduler.due_plays(since, now)[:50]:
            label = e.label or ", ".join(e.play)
            item = {"files": list(e.play), "label": label, "mode": e.mode,
                    "due": at.timestamp(), "source": "Plan", "entry": e.id}
            if self.mixer.muted:
                self._log(f"übersprungen (stumm): {label}")
                continue
            self._enqueue(item)

    def _open_file(self, name: str) -> Optional[FileSource]:
        path = media_resolve(self.config.media_dir, name)
        if path is None or not path.is_file():
            self._log(f"Datei fehlt: {name}")
            return None
        return FileSource(path, loop=False).start()

    def _tick_oneshot(self) -> None:
        ann = self.config.data.get("announce", {})
        duck_level = float(ann.get("duck_level", 0.15))
        duck_s = float(ann.get("duck_seconds", 0.8))
        release_s = float(ann.get("release_seconds", 1.5))
        max_delay = float(ann.get("max_delay_minutes", 10)) * 60

        if self.layer_same and self.oneshot:
            self._end_oneshot("abgebrochen (Alarm)")
            return

        os_ = self.oneshot
        if os_ is None:
            if not self.queue or self.mixer.muted or self.layer_same:
                return
            item = self.queue.popleft()
            if time.time() - item["due"] > max_delay:
                self._log(f"verworfen (zu spät): {item['label']}")
                return
            self.oneshot = {"item": item, "idx": 0, "src": None, "phase": "open"}
            os_ = self.oneshot

        item, phase = os_["item"], os_["phase"]

        if phase == "open":
            src = self._open_file(item["files"][os_["idx"]])
            if src is None:
                self._advance_file()
                return
            os_["src"], os_["phase"], os_["t"] = src, "arming", time.time()
            return

        src: FileSource = os_["src"]
        if phase == "arming":
            if src.ready:
                target = 0.0 if item["mode"] == "replace" else duck_level
                self.mixer.set_duck(target, duck_s)
                os_["phase"] = "ducking"
            elif src.failed or time.time() - os_["t"] > 10:
                self._log(f"nicht abspielbar: {src.error or src.path.name}")
                src.stop()
                self._advance_file()
            return

        if phase == "ducking":
            if self.mixer.duck_settled:
                self.mixer.deck_o.source = src
                self.mixer.overlay_on = True
                os_["phase"] = "playing"
                if os_["idx"] == 0:
                    self._log(f"läuft: {item['label']}")
            return

        if phase == "playing":
            if src.finished:
                self.mixer.overlay_on = False
                src.stop()
                self._advance_file()
            return

        if phase == "releasing":
            if self.queue and not self.mixer.muted:
                # nächste Einspielung direkt anschließen, Musik bleibt unten
                self.oneshot = None
                return
            if self.mixer.duck_settled:
                self.oneshot = None
            return

    def _advance_file(self) -> None:
        """Nächste Datei der Einspielung – oder Einspielung abschließen."""
        os_ = self.oneshot
        if os_ is None:
            return
        os_["idx"] += 1
        if os_["idx"] < len(os_["item"]["files"]):
            os_["phase"] = "open"
            return
        self._log(f"gespielt: {os_['item']['label']}")
        if self.queue and not self.mixer.muted:
            self.oneshot = None                 # Anschluss, ohne hochzufahren
            return
        release_s = float(self.config.get("announce", "release_seconds", default=1.5))
        self.mixer.set_duck(1.0, release_s)
        os_["phase"] = "releasing"
        os_["src"] = None

    def _end_oneshot(self, reason: Optional[str], quiet: bool = False) -> None:
        os_ = self.oneshot
        self.mixer.overlay_on = False
        self.mixer.deck_o.source = None
        if os_ and os_.get("src") is not None:
            os_["src"].stop()
        self.mixer.set_duck(1.0, 0.3)
        self.oneshot = None
        if reason and os_ and not quiet:
            self._log(f"{reason}: {os_['item']['label']}")

    # =====================================================================
    # Steuer-Schleife
    # =====================================================================
    def _control_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as exc:
                self._log(f"interner Fehler: {exc}")
            self._stop.wait(0.1)

    def _tick(self) -> None:
        now = datetime.now()
        if self.scheduler.enabled:
            occ = self.scheduler.current_occurrence(now)
            key = (occ[0], occ[1].id) if occ else None
            if occ is not None and key != self._applied_occurrence:
                self._applied_occurrence = key
                self._apply_entry(occ[1])
            self._check_due(now)

        if self.layer_same and time.time() >= self.layer_same["until"]:
            src = self.layer_same.get("source")
            if isinstance(src, Source):
                src.stop()
            self.layer_same = None

        self._tick_oneshot()
        desired = self._resolve()
        self._drive(desired)
        self._drive_master(desired)
        self._close_idle_sources()

    def _close_idle_sources(self) -> None:
        """Quellen schließen, die weder laufen, einblenden noch angefragt sind."""
        now = time.time()
        busy = {id(self._committed_source), id((self._pending or {}).get("source")),
                id(self.mixer.active_deck().source)}
        if self.mixer.crossfade != self.mixer.crossfade_to:      # blendet noch aus
            busy.add(id(self.mixer.standby_deck().source))
        idle = []
        with self._lock:
            for sid, src in list(self._sources.items()):
                if id(src) in busy:
                    self._last_used[sid] = now
                elif now - self._last_used.get(sid, now) > IDLE_CLOSE_SECONDS:
                    del self._sources[sid]
                    self._last_used.pop(sid, None)
                    idle.append(src)
        for src in idle:      # stop() wartet auf den Thread – nicht im Takt der Steuerung
            threading.Thread(target=src.stop, name="close-idle", daemon=True).start()

    def _resolve(self) -> dict:
        if self.layer_same:
            s = self.layer_same
            return {"key": "same", "source": s["source"], "label": s["label"],
                    "reason": "SAME", "fade": s["fade"], "level": s["level"]}
        if self.layer_watch:
            w = self.layer_watch
            return {"key": "watch:" + w["label"], "source": w["source"],
                    "label": w["label"], "reason": "Wache", "fade": 4.0, "level": L_WATCH}
        if self.base.get("mode") == "station":
            sid = self.base["id"]
            src = self._source_for_station(sid)
            # eigener Ersatz des Senders (z. B. dieselbe Frequenz auf einem
            # zweiten Kiwi), sonst der allgemeine
            fb = (self.config.station(sid) or {}).get("fallback") or self.config.get("fallback")
            # Ersatz, solange die Quelle tot ist – und nach einem Ausfall so
            # lange, bis sie wieder wirklich Ton liefert (nicht schon beim Verbinden)
            need_fb = self._source_dead(src) or (
                self.fallback_active and not getattr(src, "ready", False))
            if need_fb and fb and fb != sid and self.config.station(fb):
                fsrc = self._source_for_station(fb)
                if not self._source_dead(fsrc):
                    if not self.fallback_active:
                        self.fallback_active = True
                        self._log(f"Ersatzbetrieb: {self._station_name(sid)} ausgefallen"
                                  f" → {self._station_name(fb)}")
                    return {"key": "fb:" + fb, "source": fsrc,
                            "label": self._station_name(fb), "reason": "Ersatz",
                            "fade": 3.0, "level": L_BASE}
            if self.fallback_active and getattr(src, "ready", False):
                self.fallback_active = False
                self._log(f"{self._station_name(sid)} wieder da – zurück")
            return {"key": "st:" + sid, "source": src, "label": self._station_name(sid),
                    "reason": "Hand" if self.manual_active else "Zeitplan",
                    # beim Wecken nur kurz überblenden – der alte Sender soll
                    # nicht unter dem langen Einblenden weiterlaufen
                    "fade": 1.0 if self.base.get("wake") else self.base.get("fade", 4.0),
                    "level": L_BASE, "wake": self.base.get("wake", False),
                    "wake_fade": self.base.get("fade", 0.0)}
        if self.base.get("mode") == "sleep":
            return {"key": self._committed_key or "sleep",
                    "source": self.mixer.active_deck().source,
                    "label": self.committed_label, "reason": "Schlummern",
                    "fade": self.base.get("fade", 60.0), "level": L_SLEEP}
        return {"key": "off", "source": self.mixer.active_deck().source,
                "label": "—", "reason": "—", "fade": 4.0, "level": L_SLEEP}

    def _drive(self, desired: dict) -> None:
        if self._pending is not None:
            src = self._pending["source"]
            if src is not None and getattr(src, "ready", True):
                self.mixer.set_crossfade(self._pending["target"], self._pending["fade"])
                self.committed_label = self._pending["label"]
                self.committed_reason = self._pending["reason"]
                self._committed_key = self._pending["key"]
                self._committed_source = src
                self._pending = None
            elif src is None or self._source_dead(src):
                self._pending = None   # kam nicht -> alten Sender behalten

        if desired["source"] is None:
            return
        # gleicher Sender UND dieselbe Quelle -> nichts zu tun; nach einem
        # Neuverbinden ist es ein neues Objekt, dann muss der Mixer umsteigen
        if desired["key"] == self._committed_key and desired["source"] is self._committed_source:
            return
        if self._pending is not None and self._pending["key"] == desired["key"] \
                and self._pending["source"] is desired["source"]:
            return
        standby = self.mixer.standby_deck()
        standby.source = desired["source"]
        standby.gain = 1.0
        standby.label = desired["label"]
        target = 1.0 if standby is self.mixer.deck_b else 0.0
        self._pending = {"source": desired["source"], "target": target,
                         "fade": desired["fade"], "label": desired["label"],
                         "reason": desired["reason"], "key": desired["key"]}

    def _drive_master(self, desired: dict) -> None:
        if desired["reason"] == "Schlummern":
            self.mixer.set_master(0.0, desired["fade"])
        elif desired.get("wake"):
            # Einblenden beginnt bei null, auch wenn vorher etwas lief
            if self._wake_from_zero and self.mixer.master > 0.0:
                self.mixer.set_master(0.0, 1.0)
                return
            self._wake_from_zero = False
            # Dauer: die eigene fade des Eintrags, mindestens wake_seconds
            secs = max(float(desired.get("wake_fade") or 0.0),
                       float(self.config.get("audio", "wake_seconds", default=90.0)))
            self.mixer.set_master(1.0, secs)
        else:
            self.mixer.set_master(1.0, 3.0)

    # =====================================================================
    # Status
    # =====================================================================
    def _station_name(self, sid: str) -> str:
        spec = self.config.station(sid)
        return spec.get("name", sid) if spec else sid

    def _missing_files(self) -> dict[str, list[str]]:
        """Einspielungen im Plan, deren Datei fehlt – vorab sichtbar machen."""
        out = {}
        for e in self.scheduler.entries:
            if e.action != "play":
                continue
            miss = [f for f in e.play
                    if not ((p := media_resolve(self.config.media_dir, f)) and p.is_file())]
            if miss:
                out[e.id] = miss
        return out

    def state(self) -> dict:
        src = self._committed_source
        os_ = self.oneshot
        oneshot = None
        if os_ is not None:
            oneshot = {"label": os_["item"]["label"], "phase": os_["phase"],
                       "file": os_["item"]["files"][min(os_["idx"],
                                                        len(os_["item"]["files"]) - 1)]}
        return {
            "mode": self.config.get("mode", default="radio"),
            "playing": {
                "label": self.committed_label, "reason": self.committed_reason,
                "title": getattr(src, "current", None),
                "source_status": src.describe() if isinstance(src, Source) else None,
            },
            "volume": round(self.mixer.volume_to, 3),
            "muted": self.mixer.muted,
            "master": round(self.mixer.master, 3),
            "crossfade": round(self.mixer.crossfade, 3),
            "duck": round(self.mixer.duck, 3),
            "base": self.base, "manual": self.manual_active,
            "fallback_active": self.fallback_active,
            "pending": (self._pending or {}).get("label"),
            "oneshot": oneshot,
            "queue": [q["label"] for q in self.queue],
            "schedule": {**self.scheduler.state(), "missing": self._missing_files()},
            "on_air": self._on_air_all(),
            "on_air_now": self._current_station(),
            "hfcc": self.hfcc.state(),
            "watcher": self.watcher.state(),
            "same": {"enabled": self.config.get("same", "enabled", default=True),
                     "fips": self.config.get("same", "fips", default=[]),
                     "recent": self.last_same[:10],
                     "active": self.layer_same["label"] if self.layer_same else None},
            "translate": self.translator.state(),
            "sources": {sid: s.describe() for sid, s in self._sources.items()},
            "log": list(self.log)[:30],
            "uptime": round(time.time() - self._start_time, 1),
        }
