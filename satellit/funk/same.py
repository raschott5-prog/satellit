"""SAME-Dekoder und -Generator.

SAME (Specific Area Message Encoding) ist die digitale Kopfzeile vor
EAS- und NOAA-Weather-Radio-Durchsagen in den USA. Dieses Modul ist ein
reiner Dekoder: Eingang 48-kHz-PCM (mono) eines beliebigen Decks bzw. einer
Quelle, Ausgang geparste Header-Objekte mit Konfidenz. Kein Netz-, kein
Audiozugriff – es hängt sich an vorhandene PCM.

Signal
------
AFSK, 520,8333 Bit/s (520 5/6). Mark (1) = 2083,3 Hz, Space (0) = 1562,5 Hz –
das sind 4 bzw. 3 Schwingungen pro Bit, bei 48 kHz 92,16 Samples/Bit.
8-Bit-ASCII, LSB zuerst, Bit 8 = 0. Der Kopf wird dreimal mit ~1 s Pause
gesendet; der Dekoder nimmt Best-of-3 (zeichenweise Mehrheit).

Rahmen
------
``[16x 0xAB Praeambel] ZCZC-ORG-EEE-PSSCCC-...+TTTT-JJJHHMM-LLLLLLLL-``
EOM: Praeambel + ``NNNN``.

Der Encoder (``encode_header`` / ``SAMEGenerator``) erzeugt genau dieses
Signal und dient den Tests und der Attrappe – analog zu ``fake_kiwi.py``.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

import numpy as np

# --- Signal-Konstanten ------------------------------------------------------
SAMPLE_RATE = 48_000
BAUD = 520.0 + 5.0 / 6.0            # 520,8333…
MARK = 2083.3333333333335          # Bit 1  (4 Schwingungen/Bit)
SPACE = 1562.5                     # Bit 0  (3 Schwingungen/Bit)
FC = (MARK + SPACE) / 2.0          # Entscheidungsmitte ~1822,9 Hz
SAMPLES_PER_BIT = SAMPLE_RATE / BAUD   # 92,16
PREAMBLE_BYTE = 0xAB
PREAMBLE_LEN = 16

ATTN_NWR = 1050.0                  # NOAA-Weather-Radio-Weckton
ATTN_EAS = (853.0, 960.0)          # EAS-Zweiton

_HEADER_RE = re.compile(
    r"ZCZC-(?P<org>[A-Z]{3})-(?P<eee>[A-Z0-9]{3})-"
    r"(?P<locs>\d{6}(?:-\d{6})*)\+(?P<tttt>\d{4})-(?P<julian>\d{7})-"
    r"(?P<station>.{8})-?"
)

ORIGINATORS = {
    "PEP": "Primary Entry Point (national)",
    "CIV": "Behoerde (Civil authorities)",
    "WXR": "National Weather Service",
    "EAS": "EAS-Teilnehmer (Sender)",
}

EVENTS = {
    "EAN": "Emergency Action Notification",
    "NPT": "National Periodic Test",
    "RMT": "Required Monthly Test",
    "RWT": "Required Weekly Test",
    "TOR": "Tornadowarnung",
    "TOA": "Tornado-Beobachtung",
    "SVR": "Schweres Gewitter (Warnung)",
    "SVA": "Schweres Gewitter (Beobachtung)",
    "SVW": "Schweres Gewitter (Warnung)",
    "FFW": "Sturzflut (Warnung)",
    "FFA": "Sturzflut (Beobachtung)",
    "FLW": "Hochwasser (Warnung)",
    "EWW": "Extremer Wind (Warnung)",
    "HUW": "Hurrikan (Warnung)",
    "TSW": "Tsunami (Warnung)",
}


# ---------------------------------------------------------------------------
# Datenobjekte
# ---------------------------------------------------------------------------
@dataclass
class SAMEHeader:
    raw: str
    org: str
    event: str
    locations: list[str]
    purge: str          # TTTT (hhmm Gueltigkeit)
    issued: str         # JJJHHMM (julianischer Tag + UTC-Zeit)
    station: str
    confidence: float = 1.0
    is_eom: bool = False

    # abgeleitet
    def event_name(self) -> str:
        return EVENTS.get(self.event, self.event)

    def originator_name(self) -> str:
        return ORIGINATORS.get(self.org, self.org)

    def purge_minutes(self) -> int:
        try:
            return int(self.purge[:2]) * 60 + int(self.purge[2:])
        except (ValueError, IndexError):
            return 0

    def dedup_key(self) -> tuple:
        """Gleiche Durchsage auf mehreren Quellen nur einmal auslösen."""
        return (self.org, self.event, tuple(self.locations), self.issued)

    def matches_area(self, fips: Iterable[str]) -> bool:
        """Trifft die Durchsage eines der eigenen Gebiete (PSSCCC)?"""
        own = {f[-6:] for f in fips}
        for loc in self.locations:
            if loc == "000000":
                return True                     # ganze USA
            # P (Kreisteil) ignorieren: nur SSCCC vergleichen
            if loc in own or loc[1:] in {o[1:] for o in own}:
                return True
        return False

    def as_dict(self) -> dict:
        return {
            "raw": self.raw, "org": self.org, "org_name": self.originator_name(),
            "event": self.event, "event_name": self.event_name(),
            "locations": self.locations, "purge": self.purge,
            "purge_minutes": self.purge_minutes(), "issued": self.issued,
            "station": self.station.strip(), "confidence": round(self.confidence, 3),
            "is_eom": self.is_eom,
        }


# ---------------------------------------------------------------------------
# Encoder / Generator
# ---------------------------------------------------------------------------
def _afsk(bits: np.ndarray, amplitude: float = 0.5) -> np.ndarray:
    """Bitfolge -> kontinuierlich-phasiges AFSK (float32, mono).

    Phasenakkumulator Sample für Sample – hält die Phase über Bitgrenzen
    stetig und behandelt die krummen 92,16 Samples/Bit korrekt.
    """
    n_bits = len(bits)
    total = int(np.ceil(n_bits * SAMPLES_PER_BIT)) + 1
    freqs = np.where(bits > 0, MARK, SPACE).astype(np.float64)
    out = np.empty(total, dtype=np.float32)
    phase = 0.0
    for i in range(total):
        bit_index = int(i / SAMPLES_PER_BIT)
        if bit_index >= n_bits:
            bit_index = n_bits - 1
        f = freqs[bit_index]
        out[i] = amplitude * np.sin(phase)
        phase += 2.0 * np.pi * f / SAMPLE_RATE
        if phase > 2.0 * np.pi:
            phase -= 2.0 * np.pi
    return out


def _bytes_to_bits(data: bytes) -> np.ndarray:
    """ASCII-Bytes -> Bitstrom, LSB zuerst, 8 Bit je Zeichen."""
    bits = np.empty(len(data) * 8, dtype=np.uint8)
    for i, byte in enumerate(data):
        for b in range(8):
            bits[i * 8 + b] = (byte >> b) & 1   # LSB zuerst
    return bits


def encode_burst(payload: str, amplitude: float = 0.5) -> np.ndarray:
    """Ein einzelner Burst: Praeambel + ASCII-Nutzlast -> AFSK."""
    data = bytes([PREAMBLE_BYTE] * PREAMBLE_LEN) + payload.encode("ascii", "replace")
    return _afsk(_bytes_to_bits(data), amplitude)


def encode_header(
    header: str,
    *,
    repeats: int = 3,
    gap_seconds: float = 1.0,
    amplitude: float = 0.5,
    lead_silence: float = 0.25,
) -> np.ndarray:
    """Vollständige SAME-Aussendung: Header 3x mit 1-s-Pausen (mono float32)."""
    gap = np.zeros(int(gap_seconds * SAMPLE_RATE), dtype=np.float32)
    parts: list[np.ndarray] = [np.zeros(int(lead_silence * SAMPLE_RATE), dtype=np.float32)]
    for i in range(repeats):
        parts.append(encode_burst(header, amplitude))
        if i < repeats - 1:
            parts.append(gap)
    return np.concatenate(parts)


def build_header(
    org: str = "WXR",
    event: str = "RWT",
    locations: Iterable[str] = ("000000",),
    purge: str = "0015",
    station: str = "KEC55",
    issued: Optional[str] = None,
) -> str:
    """Bequemer Bau eines gültigen Headers (für Tests/Attrappe)."""
    if issued is None:
        now = datetime.now(timezone.utc)
        issued = f"{now.timetuple().tm_yday:03d}{now.hour:02d}{now.minute:02d}"
    loc = "-".join(locations)
    st = (station + " " * 8)[:8]
    return f"ZCZC-{org}-{event}-{loc}+{purge}-{issued}-{st}-"


class SAMEGenerator:
    """Erzeugt gültige, verrauschte oder teildefekte Aussendungen – analog
    zu ``tests/fake_kiwi.py``. Praktisch zum Prüfen von Best-of-3."""

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        assert sample_rate == SAMPLE_RATE, "SAME ist auf 48 kHz festgelegt"
        self._rng = np.random.default_rng()

    def message(
        self,
        header: str,
        *,
        attention: Optional[str] = None,   # "nwr" | "eas" | None
        voice_seconds: float = 0.0,
        with_eom: bool = True,
        noise_db: Optional[float] = None,
        drop_prob: float = 0.0,
    ) -> np.ndarray:
        parts = [encode_header(header)]
        if attention == "nwr":
            parts.append(self._tone([ATTN_NWR], 8.0))
        elif attention == "eas":
            parts.append(self._tone(list(ATTN_EAS), 8.0))
        if voice_seconds > 0:
            parts.append(self._rng.standard_normal(
                int(voice_seconds * SAMPLE_RATE)).astype(np.float32) * 0.05)
        if with_eom:
            parts.append(np.zeros(int(0.5 * SAMPLE_RATE), dtype=np.float32))
            parts.append(encode_header("NNNN", gap_seconds=1.0))
        sig = np.concatenate(parts)
        if drop_prob > 0:   # einzelne Samples „verschlucken“ (Dropouts)
            mask = self._rng.random(len(sig)) > drop_prob
            sig = sig * mask
        if noise_db is not None:
            rms = np.sqrt(np.mean(sig ** 2)) or 1e-6
            n_rms = rms * (10 ** (noise_db / 20.0))
            sig = sig + self._rng.standard_normal(len(sig)).astype(np.float32) * n_rms
        return sig.astype(np.float32)

    def _tone(self, freqs: list[float], seconds: float) -> np.ndarray:
        t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
        sig = sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)
        return (sig * 0.4).astype(np.float32)


# ---------------------------------------------------------------------------
# Dekoder
# ---------------------------------------------------------------------------
def _bandpass(x: np.ndarray, low: float = 1100.0, high: float = 2500.0) -> np.ndarray:
    """Grober FFT-Bandpass um das Mark/Space-Band – unterdrückt Sprache/Brumm."""
    n = len(x)
    if n < 16:
        return x
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1.0 / SAMPLE_RATE)
    spec[(freqs < low) | (freqs > high)] = 0
    return np.fft.irfft(spec, n).astype(np.float64)


def _instantaneous_freq(x: np.ndarray) -> np.ndarray:
    """Momentanfrequenz über das analytische Signal (Hilbert per FFT)."""
    n = len(x)
    spec = np.fft.fft(x)
    h = np.zeros(n)
    if n % 2 == 0:
        h[0] = h[n // 2] = 1
        h[1:n // 2] = 2
    else:
        h[0] = 1
        h[1:(n + 1) // 2] = 2
    analytic = np.fft.ifft(spec * h)
    phase = np.unwrap(np.angle(analytic))
    inst = np.diff(phase) / (2.0 * np.pi) * SAMPLE_RATE
    return np.concatenate([inst[:1], inst])


def _bits_lsb_to_byte(bits: list[int]) -> int:
    v = 0
    for i, b in enumerate(bits):
        v |= (b & 1) << i
    return v


class SAMEDecoder:
    """Dekodiert SAME-Header aus einem PCM-Puffer.

    ``decode(samples)`` liefert eine Liste von :class:`SAMEHeader` (Header
    und EOM). Für den Dauerbetrieb siehe :class:`SAMEStream`, der die Engine
    blockweise füttert und fertige Header meldet.
    """

    def __init__(self, min_confidence: float = 0.5):
        self.min_confidence = min_confidence

    def decode(self, samples: np.ndarray) -> list[SAMEHeader]:
        x = np.asarray(samples, dtype=np.float64)
        if x.ndim > 1:
            x = x.mean(axis=1)
        if len(x) < int(PREAMBLE_LEN * 8 * SAMPLES_PER_BIT):
            return []
        x = _bandpass(x)
        peak = np.max(np.abs(x)) or 1.0
        x = x / peak

        inst = _instantaneous_freq(x)
        # Weiches Bit: +1 Richtung Mark, -1 Richtung Space
        soft = np.tanh((inst - FC) / ((MARK - SPACE) / 2.0))

        payloads: list[tuple[str, float]] = []
        for a, b in self._segments(x):
            payloads.extend(self._decode_segment(soft[a:b]))
        headers = self._vote(payloads)
        return [h for h in headers if h.confidence >= self.min_confidence or h.is_eom]

    # --- interne Schritte -------------------------------------------------
    #: LSB-first-Bitmuster eines Praeambel-Bytes (0xAB)
    _PREAMBLE_BITS = np.array([(PREAMBLE_BYTE >> i) & 1 for i in range(8)], dtype=np.uint8)

    def _segments(self, x: np.ndarray) -> list[tuple[int, int]]:
        """Teilt das Signal anhand der Bandenergie in einzelne Bursts.

        Jeder Burst (Header-Aussendung) bekommt so sein eigenes Bit-Raster –
        die 1-s-Pausen zerstören dann keine globale Taktlage.
        """
        win = int(SAMPLES_PER_BIT * 4)
        if win < 1 or len(x) < win:
            return [(0, len(x))]
        n_win = len(x) // win
        energy = np.abs(x[: n_win * win]).reshape(n_win, win).mean(axis=1)
        if energy.max() <= 0:
            return []
        thr = 0.25 * energy.max()
        active = energy > thr
        segs: list[tuple[int, int]] = []
        start = None
        gap_allow = 3            # kurze Lücken innerhalb eines Bursts überbrücken
        quiet = 0
        for i, a in enumerate(active):
            if a:
                if start is None:
                    start = i
                quiet = 0
            elif start is not None:
                quiet += 1
                if quiet > gap_allow:
                    segs.append((start, i - quiet + 1))
                    start = None
        if start is not None:
            segs.append((start, n_win))
        min_len = int(PREAMBLE_LEN * 8 * SAMPLES_PER_BIT * 0.5)
        out = []
        for a, b in segs:
            s, e = max(0, a * win - win), min(len(x), b * win + win)
            if e - s >= min_len:
                out.append((s, e))
        return out or [(0, len(x))]

    def _sample_bits(self, soft: np.ndarray, phase: float) -> np.ndarray:
        """Integrate-and-dump an Bitmitten ab Phasenlage ``phase``."""
        n_bits = int((len(soft) - phase) / SAMPLES_PER_BIT)
        if n_bits <= 0:
            return np.zeros(0)
        idx = (phase + np.arange(n_bits) * SAMPLES_PER_BIT + SAMPLES_PER_BIT / 2.0)
        idx = np.clip(idx.astype(int), 0, len(soft) - 1)
        return soft[idx]

    def _best_phase(self, soft: np.ndarray) -> float:
        """Phasenlage mit der größten Augenöffnung (max. |Soft| an Bitmitten)."""
        best_phase, best_score = 0.0, -1.0
        for p in np.linspace(0, SAMPLES_PER_BIT, 16, endpoint=False):
            vals = self._sample_bits(soft, p)
            score = float(np.mean(np.abs(vals))) if len(vals) else 0.0
            if score > best_score:
                best_score, best_phase = score, p
        return best_phase

    def _decode_segment(self, soft: np.ndarray) -> list[tuple[str, float]]:
        """Einen einzelnen Burst dekodieren: lokale Phase, Praeambel-Suche
        auf Bitebene (beliebige Byte-Ausrichtung), dann ASCII bis zum Ende."""
        if len(soft) < int(PREAMBLE_LEN * 4 * SAMPLES_PER_BIT):
            return []
        phase = self._best_phase(soft)
        softbits = self._sample_bits(soft, phase)
        bits = (softbits > 0).astype(np.uint8)
        conf = np.abs(softbits)
        n = len(bits)
        P = self._PREAMBLE_BITS

        # Alle Bitpositionen, an denen ein Praeambel-Byte steht
        matches = [k for k in range(0, n - 8) if np.array_equal(bits[k:k + 8], P)]
        if len(matches) < 4:
            return []
        # Praeambel-Cluster (benachbarte Treffer) -> ASCII beginnt am Clusterende
        ascii_start = matches[0] + 8
        last = matches[0]
        hits = 1
        for m in matches[1:]:
            if m - last <= 8 * 4:      # noch im selben Praeambel-Feld
                last = m
                hits += 1
            else:
                break
        ascii_start = last + 8
        if hits < 4:
            return []

        chars, confs, bad = [], [], 0
        pos = ascii_start
        while pos < n - 8:
            seg = bits[pos:pos + 8]
            if np.array_equal(seg, P):
                break
            byte = _bits_lsb_to_byte(list(seg))
            c = float(np.mean(conf[pos:pos + 8]))
            if 32 <= byte <= 126:
                chars.append(chr(byte))
                confs.append(c)
                bad = 0
            else:
                bad += 1
                if bad > 2:
                    break
            pos += 8
        text = "".join(chars).rstrip()
        if not text:
            return []
        return [(text, float(np.mean(confs)) if confs else 0.0)]

    def _vote(self, payloads: list[tuple[str, float]]) -> list[SAMEHeader]:
        """Best-of-3: gleiche Bursts gruppieren, zeichenweise Mehrheit."""
        headers: list[SAMEHeader] = []
        hdr_group = [(t, c) for t, c in payloads if t.startswith("ZCZC")]
        eom_group = [(t, c) for t, c in payloads if t.startswith("NNNN") or t.rstrip("-") == "NNNN"]

        if hdr_group:
            voted, conf = self._majority([t for t, _ in hdr_group],
                                         [c for _, c in hdr_group])
            parsed = parse_header(voted, confidence=conf)
            if parsed:
                headers.append(parsed)
        if eom_group:
            headers.append(SAMEHeader(raw="NNNN", org="", event="EOM",
                                      locations=[], purge="", issued="",
                                      station="", confidence=1.0, is_eom=True))
        return headers

    @staticmethod
    def _majority(strings: list[str], confs: list[float]) -> tuple[str, float]:
        if len(strings) == 1:
            return strings[0], confs[0]
        # auf die häufigste Länge bringen
        length = Counter(len(s) for s in strings).most_common(1)[0][0]
        pool = [s for s in strings if len(s) == length] or strings
        length = min(len(s) for s in pool)
        out = []
        for pos in range(length):
            chars = Counter(s[pos] for s in pool)
            out.append(chars.most_common(1)[0][0])
        agreement = len(pool) / max(1, len(strings))
        conf = (sum(confs) / len(confs)) * (0.6 + 0.4 * agreement)
        return "".join(out), float(min(1.0, conf))


def parse_header(text: str, confidence: float = 1.0) -> Optional[SAMEHeader]:
    """ASCII-Header -> :class:`SAMEHeader` oder ``None`` bei Unsinn."""
    m = _HEADER_RE.search(text)
    if not m:
        return None
    locs = m.group("locs").split("-")
    return SAMEHeader(
        raw=m.group(0), org=m.group("org"), event=m.group("eee"),
        locations=locs, purge=m.group("tttt"), issued=m.group("julian"),
        station=m.group("station"), confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Dauerbetrieb: blockweise Fütterung aus der Engine
# ---------------------------------------------------------------------------
class SAMEStream:
    """Hält ein gleitendes Fenster und dekodiert, sobald eine Burst-Folge
    wahrscheinlich komplett ist. Wird von der Engine mit den PCM-Blöcken
    einer Quelle gefüttert; neue Header kommen per Callback zurück.
    """

    def __init__(self, on_header=None, window_seconds: float = 12.0,
                 min_confidence: float = 0.5):
        self.decoder = SAMEDecoder(min_confidence=min_confidence)
        self.on_header = on_header
        self._cap = int(window_seconds * SAMPLE_RATE)
        self._buf = np.zeros(0, dtype=np.float32)
        self._seen: set[tuple] = set()
        self._since_decode = 0
        self._decode_every = int(1.0 * SAMPLE_RATE)   # ~1x pro Sekunde prüfen

    def feed(self, block: np.ndarray) -> list[SAMEHeader]:
        mono = np.asarray(block, dtype=np.float32)
        if mono.ndim > 1:
            mono = mono.mean(axis=1)
        self._buf = np.concatenate([self._buf, mono])[-self._cap:]
        self._since_decode += len(mono)
        found: list[SAMEHeader] = []
        if self._since_decode >= self._decode_every:
            self._since_decode = 0
            for h in self.decoder.decode(self._buf):
                if h.is_eom:
                    found.append(h)
                    continue
                key = h.dedup_key()
                if key not in self._seen:
                    self._seen.add(key)
                    found.append(h)
            if len(self._seen) > 64:
                self._seen = set(list(self._seen)[-32:])
        if self.on_header:
            for h in found:
                try:
                    self.on_header(h)
                except Exception:
                    pass
        return found
