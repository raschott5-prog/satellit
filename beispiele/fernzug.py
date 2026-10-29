"""„Fernzug“ – Metall, Elektronik und vorbeifahrende Züge, die Bahnhofsuhr gibt den Takt.

Eigene Komposition (frei verwendbar, CC0), alles synthetisch (keine Samples): Amboss und Rohr
gehämmert, elektronischer Puls, Schienenstöße im Tempo, Signalhorn mit
Doppler-Effekt. Jede volle Minute schaltet der Klack der Uhr eine Stufe weiter.
Nutzt Uhr und Trommeln aus uhrwerk.py/drumsolo.py.

    python fernzug.py fernzug.wav
"""
import sys
import wave

import numpy as np

import drumsolo as ds
import uhrwerk as uw

SR = ds.SR
BEAT = 0.5                             # 120/min: zwei Schläge pro Uhr-Sekunde
STEP = BEAT / 4                        # Sechzehntel
VORLAUF = uw.VORLAUF
MINUTEN = 4
C = 343.0                              # Schallgeschwindigkeit
rng = np.random.default_rng(1977)


def _t(sek):
    return np.arange(int(sek * SR)) / SR


# --- Metall -------------------------------------------------------------------
def amboss(v, hoch=True):
    t = _t(0.7)
    grund = 640.0 if hoch else 470.0
    sig = sum(np.sin(2 * np.pi * grund * r * t + rng.uniform(0, 6)) * np.exp(-t / d) / (i + 1) ** 0.5
              for i, (r, d) in enumerate([(1, 0.35), (2.76, 0.22), (5.40, 0.12), (8.93, 0.06)]))
    schlag = rng.standard_normal(len(t)) * np.exp(-t / 0.002)
    return v * (0.6 * sig + 0.5 * schlag)


def rohr(v):
    t = _t(0.9)
    sig = sum(np.sin(2 * np.pi * 185 * r * t) * np.exp(-t / d)
              for r, d in [(1, 0.5), (2.32, 0.3), (4.25, 0.15), (6.63, 0.08)])
    dumpf = np.sin(2 * np.pi * 70 * t) * np.exp(-t / 0.05)
    return v * (0.5 * sig + 0.6 * dumpf + 0.3 * rng.standard_normal(len(t)) * np.exp(-t / 0.003))


# --- Elektronik ---------------------------------------------------------------
def puls(f, dur, v=0.25):
    """Sequenzer-Bass: Rechteck, Filter schließt nach dem Anschlag."""
    t = _t(dur)
    roh = np.sign(np.sin(2 * np.pi * f * t)) + 0.5 * np.sign(np.sin(2 * np.pi * f * 2.003 * t))
    weich = np.convolve(roh, np.ones(18) / 18, "same")
    hell = 0.6 * np.exp(-t / 0.05)
    sig = (1 - hell) * weich + hell * roh
    env = np.clip(t / 0.003, 0, 1) * np.exp(-t / (dur * 0.6))
    return v * sig * env


def e_kick(v):
    t = _t(0.35)
    f = 50 + 110 * np.exp(-t / 0.02)
    return v * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.18)


def e_snare(v):
    t = _t(0.25)
    r = rng.standard_normal(len(t))
    r = r - np.convolve(r, np.ones(10) / 10, "same")
    return v * (0.7 * r * np.exp(-t / 0.07) + 0.4 * np.sin(2 * np.pi * 240 * t) * np.exp(-t / 0.03))


# --- Zug ----------------------------------------------------------------------
def zug(dauer, t_vorbei, v_ms, wagen, richtung=1, abstand=12.0, horn=True):
    """Ein vorbeifahrender Zug als Stereo-Paar. t_vorbei: Spitze passiert den Hörer."""
    n = int(dauer * SR)
    t = np.arange(n) / SR
    laenge = wagen * 26.0
    # Position der Zugmitte entlang des Gleises (Hörer bei x=0)
    x_spitze = richtung * v_ms * (t - t_vorbei)
    x_mitte = x_spitze - richtung * laenge / 2
    r = np.sqrt(x_mitte ** 2 + abstand ** 2)
    nah = np.clip(1 - (np.abs(x_mitte) - laenge / 2) / 400, 0, 1) ** 2   # Pegel mit Entfernung
    pan = np.clip(x_mitte / (np.abs(x_mitte) + 30), -1, 1)
    # Rollen: tiefes Rauschen, dichter wenn nah
    roll = rng.standard_normal(n)
    roll = np.convolve(roll, np.ones(120) / 120, "same") * 6
    roll *= 0.25 + 0.75 * nah
    sig = roll * nah * 0.35
    # Schienenstöße: pro Wagen zwei Drehgestelle mit je zwei Achsen (ta-dam ta-dam)
    takt = 26.0 / v_ms
    stoss = np.zeros(n)
    klick_t = _t(0.12)
    klick = (np.sin(2 * np.pi * 95 * klick_t) * np.exp(-klick_t / 0.04)
             + 0.5 * np.sin(2 * np.pi * 1150 * klick_t) * np.exp(-klick_t / 0.015))
    vorbei_ende = t_vorbei + laenge / v_ms
    for k in range(int((dauer + 60) / takt)):
        basis = t_vorbei - 30 + k * takt
        for versatz in (0.0, 2.5 / v_ms, (26 - 5) / v_ms, (26 - 2.5) / v_ms):
            tz = basis + versatz
            i = int(tz * SR)
            if 0 <= i < n - len(klick):
                w = 1.0 if t_vorbei <= tz <= vorbei_ende else 0.15
                stoss[i:i + len(klick)] += klick * w
    sig += stoss * nah * 0.9
    links = sig * np.sqrt((1 - pan) / 2)
    rechts = sig * np.sqrt((1 + pan) / 2)
    if horn:                                           # Zweiklang-Horn mit Doppler
        x_lok = x_spitze
        r_lok = np.sqrt(x_lok ** 2 + abstand ** 2)
        v_rad = richtung * v_ms * x_lok / r_lok        # >0: entfernt sich
        dop = C / (C + v_rad)
        an = (t > t_vorbei - 4.5) & (t < t_vorbei + 1.5)
        env = np.convolve(an.astype(float), np.ones(int(0.08 * SR)) / int(0.08 * SR), "same")
        h = np.zeros(n)
        for f0 in (311.0, 370.0):
            ph = 2 * np.pi * np.cumsum(f0 * dop) / SR
            h += sum(np.sin(k * ph) / k for k in range(1, 7))
        h *= env * 0.18 * (12 / np.maximum(r_lok, 12))
        pan_l = np.clip(x_lok / (np.abs(x_lok) + 30), -1, 1)
        links += h * np.sqrt((1 - pan_l) / 2)
        rechts += h * np.sqrt((1 + pan_l) / 2)
    return links, rechts


# --- Muster -------------------------------------------------------------------
# 16 Sechzehntel pro Takt (2 s = zwei Uhr-Sekunden): (Schritt, Instrument, Stärke)
HAEMMERN_A = [(0, "hoch", 1.0), (3, "hoch", 0.6), (6, "hoch", 0.8), (8, "rohr", 0.9),
              (11, "hoch", 0.6), (12, "tief", 0.8), (14, "hoch", 0.5)]
HAEMMERN_B = HAEMMERN_A + [(2, "tief", 0.5), (5, "rohr", 0.5), (9, "hoch", 0.5),
                           (10, "tief", 0.6), (15, "hoch", 0.7)]
BASS = [40, 40, 52, 40, 43, 40, 47, 45]               # Achtel, E-Moll-Färbung


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def setzen(l, r, sig, zeit, pan=0.0):
    i = int(zeit * SR)
    n = min(len(sig), len(l) - i)
    if n > 0 and i >= 0:
        l[i:i + n] += sig[:n] * np.sqrt((1 - pan) / 2)
        r[i:i + n] += sig[:n] * np.sqrt((1 + pan) / 2)


def main(ziel):
    ende = VORLAUF + 60 * MINUTEN
    nach = 14.0
    gesamt = ende + nach + 2
    L = np.zeros(int(gesamt * SR))
    R = np.zeros_like(L)
    T = 16 * STEP
    for minute in range(MINUTEN):
        for k in range(int(60 / T)):
            t0 = VORLAUF + minute * 60 + k * T
            fort = k / (60 / T)
            # Puls ab Stufe 1, wird heller/lauter
            for s in range(8):
                v = (0.10 + 0.05 * minute + 0.04 * fort)
                setzen(L, R, puls(hz(BASS[s]), STEP * 2 * 0.9, v), t0 + s * 2 * STEP, -0.1)
            if minute >= 1:                            # Hämmern
                muster = HAEMMERN_B if minute >= 3 else HAEMMERN_A
                for schritt, was, st in muster:
                    v = st * (0.35 + 0.15 * minute + 0.1 * fort)
                    sig = rohr(v) if was == "rohr" else amboss(v, hoch=was == "hoch")
                    setzen(L, R, sig, t0 + schritt * STEP,
                           {"hoch": -0.45, "tief": 0.4, "rohr": 0.1}[was])
            if minute >= 2:                            # elektronische Trommeln
                for s in range(4):
                    setzen(L, R, e_kick(0.8 if s in (0, 2) else 0.5), t0 + s * BEAT)
                    if s in (1, 3):
                        setzen(L, R, e_snare(0.45 + 0.1 * (minute - 2)), t0 + s * BEAT)
                    if minute >= 3:
                        setzen(L, R, e_kick(0.45), t0 + s * BEAT + 3 * STEP)
            if k == 0 and minute >= 1:                 # Metall-Akzent auf jeden Klack
                setzen(L, R, rohr(0.9), t0)
                setzen(L, R, amboss(0.7), t0)
    # Züge: einer nähert sich ab Stufe 1 und fährt in Stufe 3 vorbei, einer zurück
    v_zug = 26.0 / (2 * BEAT)                          # ein Wagen pro Uhr-Sekunde ≈ 94 km/h
    for t_vorbei, richtung, wagen in ((VORLAUF + 150, 1, 12), (VORLAUF + 200, -1, 10)):
        start = t_vorbei - 110
        zl, zr = zug(gesamt - start, t_vorbei - start, v_zug, wagen, richtung)
        zl, zr = zl * 2.5, zr * 2.5                     # der Zug soll man spüren
        i = int(start * SR)
        L[i:i + len(zl)] += zl[: len(L) - i]
        R[i:i + len(zr)] += zr[: len(R) - i]
    # Schluss: alles bricht mit dem letzten Klack ab
    for sig in (rohr(1.0), amboss(1.0), e_kick(1.0)):
        setzen(L, R, sig, ende)
    # Hall auf alles außer der Uhr
    spur = ds.Spur(gesamt)
    spur.l[:] = L[: len(spur.l)]
    spur.r[:] = R[: len(spur.r)]
    links, rechts = ds.hall(spur, sek=1.8, anteil=0.2)
    uhr = ds.Spur(gesamt)
    uw.uhr_einsetzen(uhr, ende + nach)
    links = ds.daempfen(links + uhr.l * 4.5, 9000, 14000)
    rechts = ds.daempfen(rechts + uhr.r * 4.5, 9000, 14000)
    n = int((ende + nach) * SR)
    stereo = np.stack([links[:n], rechts[:n]], axis=1)
    aus = int(5 * SR)
    stereo[-aus:] *= np.linspace(1, 0, aus)[:, None] ** 1.5
    stereo = 0.85 * stereo / np.max(np.abs(stereo))
    with wave.open(ziel, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((stereo * 32767).astype(np.int16).tobytes())
    print(ziel, f"{len(stereo) / SR:.1f} s")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "fernzug.wav")
