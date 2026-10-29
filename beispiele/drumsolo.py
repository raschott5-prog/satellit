"""Drum-Solo im Stil der späten 60er – von sanft bis hart.

Eigene Komposition (frei verwendbar, CC0), synthetisch erzeugt: tief gestimmte
Toms, Bassdrum, Snare, Hi-Hat, Ride, Crash, Raumhall, Toms im Stereo
verteilt. Die Intensität steigt über die ganze Länge an.

    python drumsolo.py drumsolo.wav [minuten]
"""
import sys
import wave

import numpy as np

SR = 44100
BPM = 118
BEAT = 60.0 / BPM
rng = np.random.default_rng(1968)


# --- Instrumente (Mono-Samples bei Stärke 1) ----------------------------------
def _t(sek):
    return np.arange(int(sek * SR)) / SR


def bassdrum(v):
    t = _t(0.45)
    f = 45 + 75 * np.exp(-t / 0.035)
    sig = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / (0.22 + 0.1 * v))
    klick = rng.standard_normal(len(t)) * np.exp(-t / 0.004) * 0.25 * v
    return sig + klick


def tom(grund, v):
    t = _t(0.9)
    f = grund * (1 + 0.45 * np.exp(-t / 0.05))
    ph = 2 * np.pi * np.cumsum(f) / SR
    sig = (np.sin(ph) + 0.35 * np.sin(1.5 * ph + 0.3)) * np.exp(-t / (0.32 + 0.15 * v))
    fell = np.convolve(rng.standard_normal(len(t)), np.ones(8) / 8, "same") * np.exp(-t / 0.03)
    return sig + 0.3 * v * fell


def snare(v):
    t = _t(0.35)
    ton = np.sin(2 * np.pi * 185 * t) * np.exp(-t / 0.06)
    r = rng.standard_normal(len(t))
    r = r - np.convolve(r, np.ones(14) / 14, "same")
    teppich = r * np.exp(-t / (0.09 + 0.06 * v))
    return 0.6 * ton + (0.5 + 0.5 * v) * teppich


def hihat(v, offen=False):
    t = _t(0.35 if offen else 0.08)
    r = rng.standard_normal(len(t))
    r = r - np.convolve(r, np.ones(4) / 4, "same")
    metall = sum(np.sin(2 * np.pi * f * t) for f in (3150, 4370, 5210, 6830)) * 0.08
    return (r + metall) * np.exp(-t / (0.12 if offen else 0.018))


def becken(v, ride=False):
    t = _t(1.6 if ride else 3.2)
    teile = (415, 587, 789, 1231, 1873, 2511) if ride else (330, 512, 801, 1163, 1677, 2389, 3211)
    metall = sum(np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) / (i + 1) ** 0.4
                 for i, f in enumerate(teile))
    r = rng.standard_normal(len(t))
    r = r - np.convolve(r, np.ones(6) / 6, "same")
    if ride:
        return (0.25 * metall + 0.25 * r) * np.exp(-t / 0.5) + 0.6 * r * np.exp(-t / 0.01)
    return (0.25 * metall + 0.6 * r) * np.exp(-t / 1.1)


TOMS = {"hoch": 196.0, "mitte": 147.0, "tief": 110.0, "stand": 82.0}
PAN = {"hoch": -0.6, "mitte": -0.2, "tief": 0.25, "stand": 0.6,
       "bd": 0.0, "sn": -0.05, "hh": 0.45, "ride": -0.5, "crash": 0.3}


# --- Spur ---------------------------------------------------------------------
class Spur:
    def __init__(self, sek):
        self.l = np.zeros(int(sek * SR), dtype=np.float32)
        self.r = np.zeros_like(self.l)

    def schlag(self, was, zeit, v):
        v = float(np.clip(v, 0.05, 1.0))
        zeit += rng.normal(0, 0.006)                     # menschliches Timing
        if was == "bd":
            s = bassdrum(v)
        elif was == "sn":
            s = snare(v)
        elif was == "hh":
            s = hihat(v)
        elif was == "hho":
            s, was = hihat(v, offen=True), "hh"
        elif was in ("ride", "crash"):
            s = becken(v, ride=was == "ride")
        else:
            s = tom(TOMS[was], v)
        s = s * v ** 1.3
        p = PAN[was]
        i = int(max(zeit, 0) * SR)
        n = min(len(s), len(self.l) - i)
        if n <= 0:
            return
        self.l[i:i + n] += s[:n] * np.sqrt((1 - p) / 2)
        self.r[i:i + n] += s[:n] * np.sqrt((1 + p) / 2)


def takt(spur, t0, x, nr):
    """Ein Takt bei Intensität x (0 = ganz sanft, 1 = volle Kraft)."""
    b = BEAT
    v = 0.4 + 0.6 * x
    if x < 0.25:                                         # sanft: Standtom-Puls, leise Hi-Hat
        for s in range(4):
            spur.schlag("stand", t0 + s * b, v * (1.0 if s in (0, 2) else 0.7))
            spur.schlag("hh", t0 + s * b + b / 2, v * 0.4)
        if nr % 4 == 3:
            for i, tt in enumerate(("tief", "stand")):
                spur.schlag(tt, t0 + 3 * b + i * b / 2, v * 0.8)
        return
    # Grundgroove
    for s in range(4):
        if s in (0, 2) or (x > 0.6 and s == 3):
            spur.schlag("bd", t0 + s * b, v)
        if x > 0.75 and s in (1, 3):
            spur.schlag("bd", t0 + s * b + b / 2, v * 0.8)  # doppelte Bassdrum
        if s in (1, 3) and x > 0.4:
            spur.schlag("sn", t0 + s * b, v)
        teilung = 4 if x > 0.55 else 2
        for k in range(teilung):
            spur.schlag("ride" if x > 0.5 and nr % 8 >= 4 else "hh",
                        t0 + s * b + k * b / teilung, v * (0.55 if k == 0 else 0.35))
        if x <= 0.4:
            spur.schlag("mitte" if s % 2 else "tief", t0 + s * b + b / 2, v * 0.7)
    if x > 0.45 and nr % 4 == 0:
        spur.schlag("crash", t0, v * 0.8)
    # Fills: am Ende jeder Phrase, im Solo-Teil öfter und länger
    fill_alle = 4 if x < 0.6 else 2 if x < 0.85 else 1
    if nr % fill_alle == fill_alle - 1:
        fill(spur, t0, x, v)


def fill(spur, t0, x, v):
    b = BEAT
    reihe = ["hoch", "hoch", "mitte", "mitte", "tief", "tief", "stand", "stand"]
    if x > 0.7 and rng.random() < 0.5:                   # Triolen-Lauf über zwei Schläge
        start, n, schritt = t0 + 2 * b, 6, b / 3
    elif x > 0.55:                                       # Sechzehntel über zwei Schläge
        start, n, schritt = t0 + 2 * b, 8, b / 4
    else:                                                # ruhig: Achtel über einen Schlag
        start, n, schritt = t0 + 3 * b, 2, b / 2
    for i in range(n):
        tt = reihe[int(i * len(reihe) / n)]
        spur.schlag(tt, start + i * schritt, v * (0.75 + 0.25 * i / n))
        if x > 0.8 and i % 2 == 0:                        # Flam: Vorschlag knapp davor
            spur.schlag(tt, start + i * schritt - 0.025, v * 0.45)


def hall(spur, sek=1.6, anteil=0.22):
    n = int(sek * SR)
    t = np.arange(n) / SR
    out = []
    for kanal in (spur.l, spur.r):
        ir = rng.standard_normal(n) * np.exp(-t / (sek / 5))
        ir[: int(0.015 * SR)] = 0
        ir /= np.sqrt((ir ** 2).sum())
        nfft = 1 << int(np.ceil(np.log2(len(kanal) + n)))
        nass = np.fft.irfft(np.fft.rfft(kanal, nfft) * np.fft.rfft(ir, nfft), nfft)[: len(kanal)]
        out.append((1 - anteil) * kanal + anteil * 5 * nass)
    return out


def daempfen(x, ab=8000.0, bis=13000.0):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= np.clip((bis - f) / (bis - ab), 0, 1) ** 2
    return np.fft.irfft(X, len(x))


def main(ziel, minuten=3.7):
    T = 4 * BEAT
    takte = int(minuten * 60 / T)
    spur = Spur(takte * T + 8)
    for nr in range(takte):
        x = (nr / (takte - 1)) ** 1.15                   # langsam, dann schneller steigend
        takt(spur, nr * T, x, nr)
    # Höhepunkt: Wirbel auf Snare und Toms, dann Schlussschlag
    t = takte * T
    for i in range(24):
        tt = "sn" if i < 12 else ["hoch", "mitte", "tief", "stand"][(i - 12) // 3]
        spur.schlag(tt, t + i * BEAT / 6, 0.6 + 0.4 * i / 24)
    t += 4 * BEAT
    for was in ("bd", "crash", "stand", "sn"):
        spur.schlag(was, t, 1.0)
    links, rechts = hall(spur)
    links, rechts = daempfen(links), daempfen(rechts)
    ende = int((t + 4.0) * SR)
    stereo = np.stack([links[:ende], rechts[:ende]], axis=1)
    stereo[-int(0.5 * SR):] *= np.linspace(1, 0, int(0.5 * SR))[:, None]
    stereo = 0.85 * stereo / np.max(np.abs(stereo))
    with wave.open(ziel, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((stereo * 32767).astype(np.int16).tobytes())
    print(ziel, f"{len(stereo) / SR:.1f} s")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "drumsolo.wav",
         float(sys.argv[2]) if len(sys.argv) > 2 else 3.7)
