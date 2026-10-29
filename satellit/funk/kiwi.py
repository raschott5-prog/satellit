"""KiwiSDR-Quelle: Audio-Websocket, IMA-ADPCM, S-Meter, Kurz-Abfrage.

Implementiert den für Satellit nötigen Ausschnitt des KiwiSDR-SND-Protokolls:
Verbindung aufbauen, Modus/Frequenz setzen, ``SND``-Frames empfangen,
IMA-ADPCM nach PCM dekodieren, von 12 kHz auf 48 kHz bringen und den S-Meter-
Wert je Frame herausreichen. Derselbe Frame-Aufbau wird von
``tests/fake_kiwi.py`` erzeugt, sodass der Pfad ohne echten Empfänger prüfbar
ist.

Fairness: Satellit meldet sich als ``SatellitRadio``, die Wache fragt nur kurz
und selten ab (siehe watcher.py). Dieses Modul blockiert keinen Slot länger
als nötig.
"""

from __future__ import annotations

import struct
import time

import numpy as np

from ..audio import CHANNELS, SAMPLE_RATE
from ..sources.base import Source

KIWI_RATE = 12_000           # Standard-Audiorate eines KiwiSDR
RESAMPLE = SAMPLE_RATE // KIWI_RATE   # 4

# --- IMA-ADPCM --------------------------------------------------------------
_STEP = [
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41,
    45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190,
    209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
    876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499,
    2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845,
    8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385,
    24623, 27086, 29794, 32767,
]
_INDEX = [-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8]


def adpcm_decode(data: bytes, state: list | None = None) -> np.ndarray:
    """IMA-ADPCM (4 Bit/Sample, mono) -> int16-PCM. ``state`` = [pred, index]."""
    if state is None:
        state = [0, 0]
    pred, index = state
    out = np.empty(len(data) * 2, dtype=np.int16)
    o = 0
    for byte in data:
        for nibble in (byte & 0x0F, (byte >> 4) & 0x0F):
            step = _STEP[index]
            diff = step >> 3
            if nibble & 1:
                diff += step >> 2
            if nibble & 2:
                diff += step >> 1
            if nibble & 4:
                diff += step
            if nibble & 8:
                pred -= diff
            else:
                pred += diff
            pred = max(-32768, min(32767, pred))
            index = max(0, min(88, index + _INDEX[nibble]))
            out[o] = pred
            o += 1
    state[0], state[1] = pred, index
    return out


def adpcm_encode(pcm: np.ndarray, state: list | None = None) -> bytes:
    """int16-PCM -> IMA-ADPCM. Gegenstück zu :func:`adpcm_decode` (Attrappe)."""
    if state is None:
        state = [0, 0]
    pred, index = state
    pcm = np.asarray(pcm, dtype=np.int32)
    out = bytearray()
    nibbles: list[int] = []
    for sample in pcm:
        step = _STEP[index]
        diff = int(sample) - pred
        nibble = 0
        if diff < 0:
            nibble = 8
            diff = -diff
        mask = 4
        tmp = step
        vpdiff = step >> 3
        for bit in (4, 2, 1):
            if diff >= tmp:
                nibble |= bit
                diff -= tmp
                vpdiff += tmp
            tmp >>= 1
        if nibble & 8:
            pred -= vpdiff
        else:
            pred += vpdiff
        pred = max(-32768, min(32767, pred))
        index = max(0, min(88, index + _INDEX[nibble]))
        nibbles.append(nibble & 0x0F)
    for i in range(0, len(nibbles) - 1, 2):
        out.append(nibbles[i] | (nibbles[i + 1] << 4))
    if len(nibbles) % 2:
        out.append(nibbles[-1])
    state[0], state[1] = pred, index
    return bytes(out)


def smeter_to_dbm(raw: int) -> float:
    """12-Bit-S-Meter-Rohwert eines Kiwi-Frames -> dBm."""
    return 0.1 * (raw & 0x0FFF) - 127.0


# --- Verbindung -------------------------------------------------------------
_resolved: dict[str, str] = {}


def resolve_host(host: str) -> str:
    """Umleitungen auflösen (``*.proxy.kiwisdr.com`` -> ``*.proxy2…:8073``).

    Öffentliche Kiwis hinter dem kiwisdr.com-Proxy leiten per HTTP 307 weiter;
    websocket-client folgt dem nicht. Einmal per HTTP nachgehen, merken.
    """
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.rstrip("/")
    if host in _resolved:
        return _resolved[host]
    final = host
    try:
        import requests
        from urllib.parse import urlsplit
        r = requests.get(f"http://{host}/", timeout=8, stream=True,
                         headers={"User-Agent": "SatellitRadio"})
        final = urlsplit(r.url).netloc or host
        r.close()
    except Exception:
        pass            # dann eben direkt versuchen
    _resolved[host] = final
    return final


def _connect(host: str, freq_khz: float, mode: str, password: str = ""):
    """Baut die SND-Websocket-Verbindung auf und setzt Modus/Frequenz.

    Liefert das offene ``websocket``-Objekt. Wirft, wenn websocket-client
    fehlt oder der Empfänger nicht erreichbar/voll ist.
    """
    try:
        import websocket  # websocket-client
    except ImportError as exc:   # pragma: no cover
        raise RuntimeError("Paket 'websocket-client' fehlt "
                           "(pip install websocket-client)") from exc

    host = resolve_host(host)
    ts = int(time.time())
    url = f"ws://{host}/kiwi/{ts}/SND"
    ws = websocket.create_connection(
        url, timeout=10,
        header=["User-Agent: SatellitRadio"],
    )
    ws.send(f"SET auth t=kiwi p={password}")
    low, high = (-4900, 4900) if mode in ("am", "sam") else (
        (300, 2700) if mode in ("usb", "cwu") else (-2700, -300))
    ws.send(f"SET mod={mode} low_cut={low} high_cut={high} freq={freq_khz:.2f}")
    ws.send("SET agc=1 hang=0 thresh=-130 slope=6 decay=1000 manGain=50")
    ws.send(f"SET AR OK in={KIWI_RATE} out={KIWI_RATE}")
    ws.send("SET squelch=0 max=0")
    ws.send("SET keepalive")
    return ws


#: Abweisungen des Kiwi (``MSG badp=N``), Wortlaut nach kiwiclient
BADP = {
    "1": "falsches Passwort oder alle freien Kanäle belegt",
    "2": "Kiwi startet noch – gleich noch einmal versuchen",
    "3": "Admin-Verbindung von dieser IP nicht erlaubt",
    "4": "nur aus dem lokalen Netz des Kiwi erreichbar",
    "5": "Kiwi erlaubt nur eine Verbindung pro IP-Adresse",
    "6": "Kiwi aktualisiert gerade – in einer Minute noch einmal",
}


def _rejection(frame: bytes) -> str | None:
    """``MSG``-Frame mit Abweisung -> Klartext, sonst None."""
    if frame[:3] != b"MSG":
        return None
    for item in bytes(frame[4:]).decode("latin-1").split():
        key, _, value = item.partition("=")
        if key == "badp" and value != "0":
            return "Kiwi weist ab: " + BADP.get(value, f"badp={value}")
        if key == "too_busy" and value != "0":
            return "Kiwi weist ab: alle Kanäle belegt"
    return None


def _parse_snd(frame: bytes) -> tuple[float, bytes] | None:
    """SND-Binärframe -> (s_meter_dbm, adpcm_bytes) oder None."""
    if len(frame) < 10 or frame[:3] != b"SND":
        return None
    # [0:3]='SND' [3]=flags [4:8]=seq(uint32 LE) [8:10]=smeter(uint16 BE)
    smeter = struct.unpack(">H", frame[8:10])[0]
    return smeter_to_dbm(smeter), frame[10:]


class KiwiSource(Source):
    kind = "kiwi"
    rebuffer = True

    def __init__(self, host: str, freq_khz: float, mode: str = "am",
                 name: str = "", gain: float = 1.0, password: str = "", **kw):
        super().__init__(name=name or f"{host} {freq_khz}kHz", **kw)
        self.host = host
        self.freq_khz = float(freq_khz)
        self.mode = mode
        self.gain = gain
        self.password = password
        self._ws = None

    def run(self) -> None:
        self._ws = _connect(self.host, self.freq_khz, self.mode, self.password)
        state = [0, 0]
        last_ka = time.time()
        while not self._stop.is_set():
            try:
                frame = self._ws.recv()
            except Exception as exc:
                self.error = f"Verbindung verloren: {exc}"
                self.status = "error"
                break
            if isinstance(frame, str):
                continue   # MSG-Zeilen ignorieren wir hier
            reason = _rejection(frame)
            if reason:
                self.error = reason     # sonst stünde nur „Verbindung verloren“ da
                self.status = "error"
                break
            parsed = _parse_snd(frame)
            if parsed is None:
                continue
            dbm, payload = parsed
            self.s_meter_dbm = dbm
            pcm = adpcm_decode(payload, state).astype(np.float32) / 32768.0
            if RESAMPLE > 1 and len(pcm):
                pcm = np.interp(
                    np.linspace(0, len(pcm), len(pcm) * RESAMPLE, endpoint=False),
                    np.arange(len(pcm)), pcm).astype(np.float32)
            block = np.repeat(pcm[:, None], CHANNELS, axis=1) * self.gain
            self._emit(block)
            if time.time() - last_ka > 5:
                try:
                    self._ws.send("SET keepalive")
                except Exception:
                    pass
                last_ka = time.time()
        self._close()

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


def probe_smeter(host: str, freq_khz: float, mode: str, seconds: float = 3.0,
                 password: str = "") -> list[float]:
    """Kurze S-Meter-Abfrage für die Wache. Verbindet, misst ``seconds``
    lang, trennt wieder – belegt den Slot nur für diese Zeit."""
    ws = _connect(host, freq_khz, mode, password)
    values: list[float] = []
    deadline = time.time() + seconds
    try:
        ws.settimeout(1.0)
        while time.time() < deadline:
            try:
                frame = ws.recv()
            except Exception:
                break
            if isinstance(frame, (bytes, bytearray)):
                parsed = _parse_snd(frame)
                if parsed:
                    values.append(parsed[0])
    finally:
        try:
            ws.close()
        except Exception:
            pass
    return values
