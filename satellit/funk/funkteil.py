"""Der Funk-Teil an der Engine: Wache, SAME, HFCC-Sendeplan, Übersetzer.

Die Engine kennt davon nur eine schmale Schnittstelle:

* ``layer()``      – Schicht über dem Programm (SAME vor Wache) oder None,
* ``alarm``        – läuft ein SAME-Alarm? (bricht Einspielungen ab),
* ``tick()``       – einmal pro Steuertakt (abgelaufene Alarme lösen),
* ``back_to_program()``, ``on_air()``, ``apply()``, ``state()``,
* ``start()``/``stop()`` – beim Ein- und Ausschalten des Funk-Teils.

Prioritätsleiter (höher gewinnt), ergänzt die des Grundgeräts
(1 Hand/Zeitplan, 0 Schlummern):

    4  SAME EAN           nationaler Notfall – schlägt alles
    3  SAME-Warnung       Tornado/Sturzflut … fürs eigene Gebiet
    2  Wache              Betrieb auf einem beobachteten Kanal
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import numpy as np

from ..audio import BLOCK, SAMPLE_RATE
from ..sources import Source, StreamSource
from ..sources.silence import SilenceSource
from . import hfcc as hfcc_mod
from . import make_source as make_funk_source
from .same import SAMEStream
from .translate import Translator
from .watcher import Watcher, WatchChannel

L_WATCH, L_SAME_WARN, L_SAME_EAN = 2, 3, 4
SDR_KINDS = ("kiwi", "ubersdr", "websdr")


class Funkteil:
    def __init__(self, engine):
        self.engine = engine
        config = self.config = engine.config
        self.layer_watch: Optional[dict] = None
        self.layer_same: Optional[dict] = None
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
            log=engine._log)
        self._on_air_cache: tuple[float, dict] = (0.0, {})
        self.translator = Translator(config.data.get("translate", {}),
                                     label_fn=lambda: engine.committed_label,
                                     log=engine._log, hint_fn=self._language_hint)
        self._stop = threading.Event()
        self._same_thread: Optional[threading.Thread] = None

    # --- Lebenszyklus -----------------------------------------------------
    def start(self) -> None:
        self._stop.clear()
        if self.config.get("mode", default="radio") == "radio":
            self._start_same_monitors()
            if self.config.get("watcher", "enabled", default=True):
                self.watcher.start()
        self._same_thread = threading.Thread(target=self._same_loop, name="same", daemon=True)
        self._same_thread.start()
        self.translator.start()
        self.engine.mixer.tap = self.translator.feed

    def stop(self) -> None:
        self._stop.set()
        if self.engine.mixer.tap == self.translator.feed:
            self.engine.mixer.tap = None
        self.watcher.stop()
        self.translator.stop()
        self._release_watch()
        self._release_same()
        for src, _ in self._same_streams:
            src.stop()
        self._same_streams.clear()

    def apply(self, data: dict) -> None:
        """Nach einer Konfig-Änderung über die Oberfläche."""
        self.watcher.apply(data.get("watcher", {}))
        self.translator.apply(data.get("translate", {}))

    # --- Schnittstelle zur Engine -----------------------------------------
    @property
    def alarm(self) -> bool:
        return self.layer_same is not None

    def tick(self) -> None:
        if self.layer_same and time.time() >= self.layer_same["until"]:
            self._release_same()

    def layer(self) -> Optional[dict]:
        if self.layer_same:
            s = self.layer_same
            return {"key": "same", "source": s["source"], "label": s["label"],
                    "reason": "SAME", "fade": s["fade"], "level": s["level"]}
        if self.layer_watch:
            w = self.layer_watch
            return {"key": "watch:" + w["label"], "source": w["source"],
                    "label": w["label"], "reason": "Wache", "fade": 4.0, "level": L_WATCH}
        return None

    def back_to_program(self) -> None:
        if self.layer_watch:
            ch = self.layer_watch.get("channel")
            if ch:
                self.watcher.dismiss(ch)
            self._release_watch()

    # --- Sendeplan (HFCC) -------------------------------------------------
    def on_air(self, station_id: Optional[str]) -> list[dict]:
        """Was laut HFCC gerade auf der Frequenz dieses SDR-Senders läuft."""
        spec = self.config.station(station_id) if station_id else None
        if not spec or spec.get("kind") not in SDR_KINDS or not spec.get("freq_khz"):
            return []
        if not self.config.get("hfcc", "enabled", default=True):
            return []
        self.hfcc.ensure()                 # lädt beim ersten Bedarf im Hintergrund
        return self.hfcc.on_air(float(spec["freq_khz"]))

    def _language_hint(self) -> Optional[list]:
        return hfcc_mod.candidates(self.on_air(self.engine._current_station()))

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

    # --- Wache ------------------------------------------------------------
    def _on_watch_activity(self, ch: WatchChannel) -> None:
        src = make_funk_source({"kind": "kiwi", "host": ch.host, "freq_khz": ch.freq_khz,
                                "mode": ch.mode, "name": ch.name}).start()
        self.layer_watch = {"channel": ch, "source": src, "label": ch.name}
        self.engine._log(f"Wache: Betrieb auf {ch.name}")

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
        src = self.engine.mixer.active_deck().source
        host = getattr(src, "host", None)
        fk = getattr(src, "freq_khz", None)
        return bool(host and fk and
                    (host.split("://")[-1], round(float(fk), 1)) == ch.key())

    # --- SAME -------------------------------------------------------------
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
            for src, stream in list(self._same_streams):
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
        self.engine._log(f"SAME: {header.event_name()} – übernimmt")

    def _release_same(self) -> None:
        if self.layer_same:
            src = self.layer_same.get("source")
            if isinstance(src, Source):
                src.stop()
        self.layer_same = None

    # --- Übersetzer -------------------------------------------------------
    def set_translate(self, enabled: bool) -> None:
        self.translator.set_enabled(enabled)
        self.config.update({"translate": {"enabled": bool(enabled)}})

    def set_translate_model(self, model: str) -> None:
        self.config.update({"translate": {"model": model}})
        self.translator.apply(self.config.data.get("translate", {}))
        self.engine._log(f"Übersetzer: Modell {model}")

    # --- Status -----------------------------------------------------------
    def state(self) -> dict:
        return {
            "on_air": self._on_air_all(),
            "on_air_now": self.engine._current_station(),
            "hfcc": self.hfcc.state(),
            "watcher": self.watcher.state(),
            "same": {"enabled": self.config.get("same", "enabled", default=True),
                     "fips": self.config.get("same", "fips", default=[]),
                     "recent": self.last_same[:10],
                     "active": self.layer_same["label"] if self.layer_same else None},
            "translate": self.translator.state(),
        }
