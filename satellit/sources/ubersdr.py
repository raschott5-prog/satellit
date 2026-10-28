"""UberSDR-Quelle (ka9q_ubersdr).

Folgt den Projekt-Notizen (``claude/ubersdr-protokoll.md``):

1. ``POST /connection`` mit fester ``user_session_id`` (UUID pro Installation)
2. Websocket ``ws(s)://host/ws?frequency=..&mode=..&format=opus&version=4``
3. nach Connect ``{"type":"get_status"}``, dann Opus-Binärframes
4. Keepalive ``{"type":"ping"}`` alle ~10 s
5. Umstimmen ohne neue Verbindung über ``{"type":"tune", ...}``

Fairness: **keine UUID-Rotation**, um Sitzungsgrenzen zu umgehen. Stattdessen
wird ``max_session_time`` aus ``/connection`` gelesen und rechtzeitig
``needs_handover`` gesetzt – die Engine blendet dann weich auf eine *andere*
Instanz, den Stream-Fallback oder einen Kiwi über.

Opus braucht ``opuslib`` (libopus). Fehlt es, meldet die Quelle das sauber;
der PCM-v4-Pfad ist bewusst nur als Haken vorgesehen (GPLv3-``pcm_v4.py``
nachrüstbar, falls Satellit GPLv3 wird).
"""

from __future__ import annotations

import json
import time

import numpy as np

from ..audio import CHANNELS, SAMPLE_RATE
from .base import Source

HANDOVER_MARGIN = 30.0   # s vor Sitzungsende rechtzeitig überblenden


class UberSDRSource(Source):
    kind = "ubersdr"
    rebuffer = True

    def __init__(self, host: str, freq_khz: float, mode: str = "am",
                 name: str = "", gain: float = 1.0, user_session_id: str = "",
                 fmt: str = "opus", **kw):
        super().__init__(name=name or f"{host} {freq_khz}kHz", **kw)
        self.host = host.split("://", 1)[-1]
        self.secure = host.startswith("https")
        self.freq_hz = int(float(freq_khz) * 1000)
        self.mode = mode
        self.gain = gain
        self.uuid = user_session_id
        self.fmt = fmt
        self.max_session_time = 0.0
        self.needs_handover = False
        self._ws = None

    # --- HTTP-Vorspiel ----------------------------------------------------
    def _http_base(self) -> str:
        return f"{'https' if self.secure else 'http'}://{self.host}"

    def _connection(self) -> dict:
        import requests
        r = requests.post(f"{self._http_base()}/connection",
                          json={"user_session_id": self.uuid},
                          headers={"User-Agent": "SatellitRadio"}, timeout=10)
        r.raise_for_status()
        return r.json()

    # --- Lauf -------------------------------------------------------------
    def run(self) -> None:
        if self.fmt != "opus":
            self.error = "Nur Opus implementiert; PCM v4 nachrüstbar (pcm_v4.py)"
            self.status = "error"
            return
        try:
            import websocket  # websocket-client
        except ImportError:
            self.error = "Paket 'websocket-client' fehlt"
            self.status = "error"
            return
        try:
            import opuslib
        except ImportError:
            self.error = "Paket 'opuslib' (libopus) fehlt – Opus nicht dekodierbar"
            self.status = "error"
            return

        info = self._connection()
        if not info.get("allowed", False):
            self.error = f"abgelehnt: {info.get('reason', 'unbekannt')}"
            self.status = "error"
            return
        self.max_session_time = float(info.get("max_session_time", 0) or 0)

        scheme = "wss" if self.secure else "ws"
        bw_low, bw_high = (-5000, 5000) if self.mode in ("am", "sam") else (
            (0, 3000) if self.mode in ("usb", "cwu") else (-3000, 0))
        url = (f"{scheme}://{self.host}/ws?frequency={self.freq_hz}&mode={self.mode}"
               f"&user_session_id={self.uuid}&bandwidthLow={bw_low}"
               f"&bandwidthHigh={bw_high}&format=opus&version=4")
        self._ws = websocket.create_connection(
            url, timeout=10, header=["User-Agent: SatellitRadio"])
        self._ws.send(json.dumps({"type": "get_status"}))

        decoder = opuslib.Decoder(SAMPLE_RATE, 1)
        last_ping = time.time()
        session_start = time.time()
        self._ws.settimeout(1.0)

        while not self._stop.is_set():
            # rechtzeitig weiche Übergabe anmelden (keine UUID-Rotation!)
            if self.max_session_time > 0:
                left = self.max_session_time - (time.time() - session_start)
                if left <= HANDOVER_MARGIN:
                    self.needs_handover = True
                    self.status = "stalled"
            now = time.time()
            if now - last_ping > 10:
                try:
                    self._ws.send(json.dumps({"type": "ping"}))
                except Exception:
                    pass
                last_ping = now
            try:
                frame = self._ws.recv()
            except Exception:
                continue
            if isinstance(frame, str):
                continue
            try:
                pcm = decoder.decode(bytes(frame), 5760)   # bis 120 ms @48k
                arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
            except Exception:
                continue
            block = np.repeat(arr[:, None], CHANNELS, axis=1) * self.gain
            self._emit(block)
        self._close()

    def retune(self, freq_khz: float, mode: str | None = None) -> None:
        """Umstimmen ohne neue Verbindung (spart Sitzungsaufbau)."""
        self.freq_hz = int(float(freq_khz) * 1000)
        if mode:
            self.mode = mode
        if self._ws is not None:
            try:
                self._ws.send(json.dumps({"type": "tune", "frequency": self.freq_hz,
                                          "mode": self.mode}))
            except Exception:
                pass

    def _close(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    def stop(self) -> None:
        self._close()
        super().stop()
