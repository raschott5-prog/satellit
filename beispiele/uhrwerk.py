"""„Uhrwerk“ – Drum-Solo um das Ticken einer alten Bahnhofsuhr herum.

Die Uhr ist der Taktgeber: Tick-Tack jede Sekunde, und jede volle Minute
der „Klack“ des springenden Minutenzeigers. Jeder Klack schaltet das
Schlagzeug eine Stufe härter. Am Ende bleibt nur die Uhr.
Eigene Komposition (frei verwendbar, CC0), nutzt die Instrumente aus drumsolo.py.

    python uhrwerk.py uhrwerk.wav
"""
import sys
import wave

import numpy as np

import drumsolo as ds

SR = ds.SR
ds.BPM = 120                       # vier Schläge pro Takt = zwei Uhr-Sekunden
ds.BEAT = 0.5
rng = np.random.default_rng(1902)

VORLAUF = 8.0                      # Uhr allein, dann der erste Klack
MINUTEN = 4


def _t(sek):
    return np.arange(int(sek * SR)) / SR


def tick(hoch):
    """Hemmung einer mechanischen Uhr: kurzer Metallklick plus Holzgehäuse."""
    t = _t(0.12)
    moden = (2350, 3480, 5120) if hoch else (2120, 3210, 4760)
    metall = sum(np.sin(2 * np.pi * f * t) * np.exp(-t / d)
                 for f, d in zip(moden, (0.012, 0.008, 0.005)))
    holz = np.sin(2 * np.pi * (420 if hoch else 380) * t) * np.exp(-t / 0.03)
    klick = rng.standard_normal(len(t)) * np.exp(-t / 0.0015)
    return 0.5 * metall + 0.45 * holz + 0.35 * klick


def klack():
    """Minutensprung einer Nebenuhr: Relais zieht an, Zeiger schlägt, rasselt nach."""
    t = _t(0.6)
    schlag = np.sin(2 * np.pi * np.cumsum(140 + 260 * np.exp(-t / 0.01)) / SR) * np.exp(-t / 0.09)
    blech = sum(np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) * np.exp(-t / 0.16)
                for f in (910, 1460, 2270, 3390))
    rasseln = np.zeros(len(t))
    for k in range(5):                                  # Zeiger federt nach
        i = int((0.035 + 0.028 * k) * SR)
        n = int(0.01 * SR)
        rasseln[i:i + n] += rng.standard_normal(n) * 0.6 * 0.6 ** k
    return 1.1 * schlag + 0.35 * blech + rasseln


def uhr_einsetzen(spur, ende):
    s = 0
    while s < ende:
        if (s - VORLAUF) % 60 == 0 and s >= VORLAUF:
            klg = klack() * 0.9
            _mono(spur, klg, s)
        _mono(spur, tick(s % 2 == 0) * 0.55, float(s))
        s += 1


def _mono(spur, sig, zeit):
    i = int(zeit * SR)
    n = min(len(sig), len(spur.l) - i)
    if n > 0:
        spur.l[i:i + n] += sig[:n] * 0.7
        spur.r[i:i + n] += sig[:n] * 0.7


def intensitaet(minute, anteil):
    """Stufen je Minute, innerhalb der Minute sanft ansteigend."""
    stufen = [(0.08, 0.22), (0.30, 0.50), (0.55, 0.74), (0.80, 1.0)]
    a, b = stufen[minute]
    return a + (b - a) * anteil


def main(ziel):
    ende_drums = VORLAUF + 60 * MINUTEN
    nachlauf = 10.0
    spur = ds.Spur(ende_drums + nachlauf + 4)
    T = 4 * ds.BEAT                                     # 2 s pro Takt
    takte_pro_minute = int(60 / T)
    for minute in range(MINUTEN):
        for k in range(takte_pro_minute):
            t0 = VORLAUF + minute * 60 + k * T
            letzter = minute == MINUTEN - 1 and k == takte_pro_minute - 1
            if letzter:                                 # Wirbel bis zum letzten Klack
                for i in range(16):
                    tt = "sn" if i < 8 else ["hoch", "mitte", "tief", "stand"][(i - 8) // 2]
                    spur.schlag(tt, t0 + i * T / 16, 0.7 + 0.3 * i / 16)
                continue
            x = intensitaet(minute, k / takte_pro_minute)
            nr = minute * takte_pro_minute + k
            ds.takt(spur, t0, x, nr)
            if minute >= 1 and k == 0:                  # Becken auf jeden Klack
                spur.schlag("crash", t0, 0.5 + 0.15 * minute)
    for was in ("bd", "crash", "stand", "sn"):         # Schlussschlag mit dem Klack
        spur.schlag(was, ende_drums, 1.0)
    # Uhr: die Spur der Trommeln bekommt Hall, die Uhr bleibt nah und trocken
    links, rechts = ds.hall(spur)
    uhr = ds.Spur(len(spur.l) / SR)
    uhr_einsetzen(uhr, ende_drums + nachlauf)
    links = ds.daempfen(links + uhr.l * 4.5)
    rechts = ds.daempfen(rechts + uhr.r * 4.5)
    n = int((ende_drums + nachlauf + 0.3) * SR)
    stereo = np.stack([links[:n], rechts[:n]], axis=1)
    aus = int(4 * SR)                                   # die Uhr verklingt am Ende
    stereo[-aus:] *= np.linspace(1, 0, aus)[:, None] ** 1.5
    stereo = 0.85 * stereo / np.max(np.abs(stereo))
    with wave.open(ziel, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((stereo * 32767).astype(np.int16).tobytes())
    print(ziel, f"{len(stereo) / SR:.1f} s")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "uhrwerk.wav")
