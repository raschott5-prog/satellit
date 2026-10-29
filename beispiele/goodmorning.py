"""„Good Morning“ – Country-Pop zum Aufwachen, im Stil der frühen 70er.

    python goodmorning.py good-morning.wav          # kurze Fassung (~70 s, Signal)
    python goodmorning.py good-morning-lang.wav lang # lange Fassung (~11 min, Wecken)


Eigene Komposition (frei verwendbar, CC0), synthetisch erzeugt:
Westerngitarre im Wechselbass, Besen, Mundharmonika, Streicher,
Steel-Gitarre und zum Finale eine gepfiffene Melodie – nach einer Rückung
einen Ganzton höher. G-Dur → A-Dur, 4/4.
"""
import sys
import wave

import numpy as np

SR = 44100
BPM = 104
BEAT = 60.0 / BPM
rng = np.random.default_rng(23)


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


D4, Fs4, G4, A4, B4, C5, D5, E5, G5 = 62, 66, 67, 69, 71, 72, 74, 76, 79
MELODIE = [
    [(D4, 1), (G4, 1), (B4, 1), (D5, 1)],
    [(E5, 2), (D5, 1), (C5, 1)],
    [(B4, 1.5), (A4, 0.5), (G4, 1), (B4, 1)],
    [(A4, 4)],
    [(D4, 1), (G4, 1), (B4, 1), (D5, 1)],
    [(E5, 1), (G5, 1), (E5, 1), (C5, 1)],
    [(D5, 1.5), (C5, 0.5), (B4, 1), (A4, 1)],
    [(G4, 4)],
    [(B4, 1), (B4, 1), (C5, 1), (D5, 1)],
    [(E5, 2), (E5, 1), (D5, 1)],
    [(D5, 1), (B4, 1), (G4, 1), (B4, 1)],
    [(A4, 2), (D5, 2)],
    [(G5, 2), (E5, 1), (D5, 1)],
    [(E5, 1), (D5, 1), (C5, 1), (A4, 1)],
    [(B4, 1.5), (A4, 0.5), (A4, 1), (Fs4, 1)],
    [(G4, 4)],
]
# Zwischenthema (Moll-Färbung, 8 Takte)
THEMA_B = [
    [(E5, 1), (D5, 1), (B4, 2)],
    [(C5, 1), (D5, 1), (E5, 2)],
    [(D5, 1), (B4, 1), (G4, 1), (A4, 1)],
    [(B4, 4)],
    [(E5, 1), (G5, 1), (E5, 1), (D5, 1)],
    [(C5, 2), (E5, 2)],
    [(D5, 1.5), (C5, 0.5), (B4, 1), (A4, 1)],
    [(A4, 4)],
]
G = (43, 50, [55, 59, 62, 67])
C = (48, 43, [55, 60, 64, 67])
Dd = (50, 45, [54, 57, 62, 66])
Em = (40, 47, [55, 59, 64, 67])
AKKORDE = [G, C, G, Dd, G, C, Dd, G, Em, C, G, Dd, G, C, Dd, G]
AKKORDE_B = [Em, C, G, G, Em, C, Dd, Dd]


def tr(akk, n):
    return (akk[0] + n, akk[1] + n, [t + n for t in akk[2]])


# --- Klangerzeuger ------------------------------------------------------------
def saite(f, dur, laut=0.5, hell=0.3):
    """Karplus-Strong, weich (wenig Höhen)."""
    n = int(dur * SR)
    p = max(2, int(SR / f))
    puf = np.convolve(rng.uniform(-1, 1, p), [0.25, 0.5, 0.25], mode="same")
    out = np.empty(n)
    for i in range(n):
        out[i] = puf[i % p]
        puf[i % p] = 0.995 * ((1 - hell) * 0.5 * (puf[i % p] + puf[(i + 1) % p]) + hell * puf[i % p])
    return laut * out * np.clip(np.arange(n) / (0.003 * SR), 0, 1)


def mundharmonika(f, dur, laut=0.45):
    n = int(dur * SR)
    t = np.arange(n) / SR
    bend = 1 - 0.012 * np.exp(-t / 0.05)
    trem = 1 + 0.12 * np.sin(2 * np.pi * 5.8 * t) * np.clip((t - 0.25) / 0.3, 0, 1)
    phase = 2 * np.pi * f * np.cumsum(bend) / SR
    sig = np.zeros(n)
    for k in range(1, 9):
        if f * k > 5000:
            break
        a = (1.0 if k % 2 else 0.7) / k ** 1.2
        a *= 1 + 0.8 * np.exp(-((f * k - 1300) / 600) ** 2)
        sig += a * np.sin(k * phase)
    att, rel = min(0.035, dur / 4), min(0.09, dur / 3)
    env = np.ones(n)
    env[: int(att * SR)] = np.linspace(0, 1, int(att * SR))
    env[-int(rel * SR):] *= np.linspace(1, 0, int(rel * SR))
    return laut * sig * env * trem / 3


def pfeifen(f, dur, laut=0.75):
    n = int(dur * SR)
    t = np.arange(n) / SR
    glide = 1 - 0.02 * np.exp(-t / 0.04)                  # rutscht in den Ton
    vib = 1 + 0.008 * np.sin(2 * np.pi * 6.2 * t) * np.clip((t - 0.15) / 0.2, 0, 1)
    phase = 2 * np.pi * f * np.cumsum(glide * vib) / SR
    sig = np.sin(phase) + 0.06 * np.sin(2 * phase)
    luft = np.convolve(rng.standard_normal(n), np.ones(12) / 12, mode="same")
    sig += 0.04 * luft
    att, rel = min(0.03, dur / 4), min(0.08, dur / 3)
    env = np.ones(n)
    env[: int(att * SR)] = np.linspace(0, 1, int(att * SR))
    env[-int(rel * SR):] *= np.linspace(1, 0, int(rel * SR))
    return laut * sig * env


def streicher(toene, dur, laut=0.10):
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = np.zeros(n)
    for m in toene:
        for verst in (-0.12, 0.0, 0.12):                  # Ensemble: leicht verstimmt
            f = hz(m) * 2 ** (verst / 12)
            vib = 1 + 0.003 * np.sin(2 * np.pi * (5 + verst) * t + rng.uniform(0, 6))
            ph = 2 * np.pi * f * np.cumsum(vib) / SR
            sig += sum(np.sin(k * ph) / k ** 1.6 for k in range(1, 6))
    env = np.clip(t / 0.6, 0, 1) * np.clip((dur - t) / 0.5, 0, 1)
    return laut * sig * env / len(toene)


def steel(m_von, m_nach, dur, laut=0.35):
    """Steel-Gitarre: gleitet von einem Ton zum anderen, singt nach."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    rutsch = np.clip(t / (dur * 0.35), 0, 1)
    m = m_von + (m_nach - m_von) * (1 - (1 - rutsch) ** 2)
    f = 440.0 * 2 ** ((m - 69) / 12) * (1 + 0.004 * np.sin(2 * np.pi * 4.5 * t))
    ph = 2 * np.pi * np.cumsum(f) / SR
    sig = np.sin(ph) + 0.4 * np.sin(2 * ph) + 0.15 * np.sin(3 * ph)
    env = np.clip(t / 0.15, 0, 1) * np.exp(-t / (dur * 0.9))
    return laut * sig * env


def steel_solo(f, dur, laut=0.32):
    """Steel-Gitarre als Melodie: rutscht von unten in jeden Ton."""
    m = 69 + 12 * np.log2(f / 440.0)
    return steel(m - 1.0, m, dur * 1.05, laut)


def gitarre_solo(f, dur, laut=0.45):
    return saite(f, max(dur, 0.6), laut, 0.25)


def streicher_solo(f, dur, laut=0.12):
    m = 69 + 12 * np.log2(f / 440.0)
    return streicher([m], dur + 0.2, laut)


def besen(dur, laut=0.03, betont=False):
    n = int(dur * SR)
    t = np.arange(n) / SR
    r = rng.standard_normal(n)
    r = np.convolve(r, np.ones(10) / 10, mode="same") - np.convolve(r, np.ones(60) / 60, mode="same")
    return laut * (1.7 if betont else 1.0) * r * np.exp(-t / (0.09 if betont else 0.045))


def setzen(spur, sig, start):
    i = int(start * SR)
    if i < len(spur):
        spur[i: i + len(sig)] += sig[: len(spur) - i]


def daempfen(x, ab=4500.0, bis=8000.0):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= np.clip((bis - f) / (bis - ab), 0, 1) ** 2
    return np.fft.irfft(X, len(x))


def hall(x, sek=1.4, anteil=0.17):
    n = int(sek * SR)
    t = np.arange(n) / SR
    ir = rng.standard_normal(n) * np.exp(-t / (sek / 5))
    ir /= np.sqrt((ir ** 2).sum())
    nfft = 1 << int(np.ceil(np.log2(len(x) + n)))
    wet = np.fft.irfft(np.fft.rfft(x, nfft) * np.fft.rfft(ir, nfft), nfft)[: len(x) + n]
    out = np.zeros(len(x) + n)
    out[: len(x)] += x
    return (1 - anteil) * out + anteil * wet * 5


# --- Ablauf -------------------------------------------------------------------
def begleitung(spur, t0, akk, takt_dauer, voll=False, letzter=False):
    grund, wechsel, toene = akk
    b = takt_dauer / 4
    if letzter:
        setzen(spur, saite(hz(grund), 4.0, 0.6), t0)
        for i, ton in enumerate(toene):
            setzen(spur, saite(hz(ton), 4.0, 0.3), t0 + 0.04 * (i + 1))
        setzen(spur, besen(1.4, betont=True), t0)
        return
    for s in range(4):
        ts = t0 + s * b
        if s in (0, 2):
            setzen(spur, saite(hz(grund if s == 0 else wechsel), b * 1.8, 0.6), ts)
        else:
            for i, ton in enumerate(toene):
                setzen(spur, saite(hz(ton), b * 0.9, 0.2), ts + 0.012 * i)
        setzen(spur, besen(b / 2, betont=s in (1, 3), laut=0.04 if voll else 0.03), ts)
        setzen(spur, besen(b / 2, laut=0.018), ts + b / 2)


def melodie(spur, t, takte, instrument, transp=0, oktave=0, dehnung=1.0):
    for takt in takte:
        for ton, schlaege in takt:
            dauer = schlaege * BEAT * dehnung
            setzen(spur, instrument(hz(ton + transp + 12 * oktave), dauer * 0.97), t)
            t += dauer
    return t


def kurz(ziel):
    T = 4 * BEAT
    spur = np.zeros(int(80 * SR))
    t = 0.0
    # 1) Vorspiel
    for _ in range(2):
        begleitung(spur, t, G, T)
        t += T
    # 2) Strophe, Mundharmonika; ab Takt 9 Streicher
    start = t
    for i, akk in enumerate(AKKORDE):
        begleitung(spur, t, akk, T)
        if i >= 8:
            setzen(spur, streicher(akk[2][:3], T + 0.3), t)
        t += T
    melodie(spur, start, MELODIE, mundharmonika)
    # 3) Übergang: Steel-Gitarre gleitet hoch, Rückung nach A-Dur
    begleitung(spur, t, tr(Dd, 2), T)                        # E-Dur als Dominante von A
    setzen(spur, streicher([66, 70, 73], T + 0.3, 0.12), t)
    setzen(spur, steel(71, 76, T * 0.5), t)
    setzen(spur, steel(76, 80, T * 0.55), t + T * 0.5)
    t += T
    # 4) Finale in A-Dur: zweite Hälfte der Melodie, gepfiffen (+ Mundharmonika)
    start = t
    finale = AKKORDE[8:]
    for i, akk in enumerate(finale):
        begleitung(spur, t, tr(akk, 2), T, voll=True)
        setzen(spur, streicher([x + 2 for x in akk[2][:3]] + [akk[2][3] + 2], T + 0.3, 0.13), t)
        if i in (3, 7):
            setzen(spur, steel(akk[0] + 2 + 24, akk[0] + 2 + 31, T * 0.8, 0.22), t + T * 0.5)
        t += T
    melodie(spur, start, MELODIE[8:], pfeifen, transp=2, oktave=1)
    melodie(spur, start, MELODIE[8:], lambda f, d: mundharmonika(f, d, 0.22), transp=2)
    # 5) Schluss: letzte Zeile langsamer, dann Schlussakkord mit Steel
    dehn = 1.35
    tag = MELODIE[14:15]
    for akk in (tr(Dd, 2),):
        begleitung(spur, t, akk, T * dehn)
        setzen(spur, streicher([x + 2 for x in akk[2][:3]], T * dehn + 0.3, 0.13), t)
    melodie(spur, t, tag, pfeifen, transp=2, oktave=1, dehnung=dehn)
    t += T * dehn
    begleitung(spur, t, tr(G, 2), T, letzter=True)
    setzen(spur, streicher([57, 61, 64, 69], 4.5, 0.15), t)
    setzen(spur, pfeifen(hz(G4 + 2 + 12), 3.0, 0.75), t)
    setzen(spur, steel(69 + 7, 69 + 12, 4.0, 0.25), t + 0.3)
    ende = t + 5.0
    spur = spur[: int(ende * SR)]
    schreiben(ziel, spur)


def schreiben(ziel, spur):
    """Höhen abrunden und Hall – blockweise, damit auch lange Fassungen passen."""
    blk, rand = 1 << 20, 1 << 13
    tail = int(1.4 * SR) + rand
    out = np.zeros(len(spur) + tail, dtype=np.float32)
    for a in range(0, len(spur), blk):
        stueck = np.concatenate([spur[a: a + blk], np.zeros(rand)])
        nass = hall(daempfen(stueck))
        out[a: a + len(nass)] += nass[: len(out) - a]
    out = out[: len(spur) + int(1.4 * SR)]
    out[-int(0.8 * SR):] *= np.linspace(1, 0, int(0.8 * SR))
    out = 0.8 * out / np.max(np.abs(out))
    stereo = np.stack([out, np.roll(out, int(0.009 * SR)) * 0.97], axis=1)
    with wave.open(ziel, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((stereo * 32767).astype(np.int16).tobytes())
    print(ziel, f"{len(out) / SR:.1f} s")


def lang(ziel, minuten=13.0):
    """Lange Fassung zum Wecken: wird von selbst immer voller, Finale mit Pfiff.

    Gedacht für ein langes Einblenden (z. B. 10 Minuten): am Anfang, wenn
    Satellit noch ganz leise ist, nur Gitarre – zum Schluss die ganze Band.
    """
    T = 4 * BEAT
    spur = np.zeros(int((minuten * 60 + 90) * SR), dtype=np.float32)
    # (Thema, Soloinstrument, Tonart, Besen, Streicher, Steel-Einwürfe)
    mundh = mundharmonika
    folge = [
        ("A", gitarre_solo, 0, False, False, False),
        ("A", mundh, 0, False, False, False),
        ("B", mundh, 0, False, False, True),
        ("A", steel_solo, 0, False, True, False),
        ("A", mundh, 0, True, True, False),
        ("B", gitarre_solo, 0, True, True, True),
        ("A", streicher_solo, 0, True, False, True),
        ("A", mundh, 0, True, True, True),
        ("B", steel_solo, 0, True, True, False),
        ("A", gitarre_solo, 0, True, True, True),
        ("A", mundh, 0, True, True, True),
        ("B", streicher_solo, 0, True, True, True),
        ("A", steel_solo, 0, True, True, True),
        ("WECHSEL", None, 0, True, True, True),
        ("A", steel_solo, 2, True, True, False),
        ("B", mundh, 2, True, True, True),
        ("A", streicher_solo, 2, True, True, True),
        ("A", mundh, 2, True, True, True),
        ("B", gitarre_solo, 2, True, True, True),
        ("A", steel_solo, 2, True, True, True),
        ("B", mundh, 2, True, True, True),
        ("A", gitarre_solo, 2, True, True, True),
    ]
    t = 0.0
    for _ in range(4):                                  # leises Vorspiel, nur Gitarre
        begleitung_leise(spur, t, G, T)
        t += T
    for thema, solo, k, mit_besen, mit_str, mit_steel in folge:
        if thema == "WECHSEL":                          # Steel gleitet, Rückung nach A
            begleitung(spur, t, tr(Dd, 2), T)
            setzen(spur, streicher([66, 70, 73], T + 0.3, 0.12), t)
            setzen(spur, steel(71, 76, T * 0.5), t)
            setzen(spur, steel(76, 80, T * 0.55), t + T * 0.5)
            t += T
            continue
        takte = MELODIE if thema == "A" else THEMA_B
        akkorde = AKKORDE if thema == "A" else AKKORDE_B
        start = t
        for i, akk in enumerate(akkorde):
            akk = tr(akk, k)
            if mit_besen:
                begleitung(spur, t, akk, T)
            else:
                begleitung_leise(spur, t, akk, T)
            if mit_str:
                setzen(spur, streicher(akk[2][:3], T + 0.3, 0.10), t)
            if mit_steel and i % 4 == 3:
                setzen(spur, steel(akk[0] + 24, akk[0] + 31, T * 0.8, 0.18), t + T * 0.5)
            t += T
        melodie(spur, start, takte, solo, transp=k)
    # Finale: Melodie gepfiffen, Mundharmonika darunter, volle Begleitung
    start = t
    for i, akk in enumerate(AKKORDE):
        akk = tr(akk, 2)
        begleitung(spur, t, akk, T, voll=True)
        setzen(spur, streicher(akk[2][:3] + [akk[2][3]], T + 0.3, 0.13), t)
        if i % 4 == 3:
            setzen(spur, steel(akk[0] + 24, akk[0] + 31, T * 0.8, 0.22), t + T * 0.5)
        t += T
    melodie(spur, start, MELODIE, lambda f, d: pfeifen(f, d, 0.32), transp=2, oktave=1)
    melodie(spur, start, MELODIE, lambda f, d: mundharmonika(f, d, 0.22), transp=2)
    dehn = 1.35
    begleitung(spur, t, tr(Dd, 2), T * dehn)
    setzen(spur, streicher([x + 2 for x in Dd[2][:3]], T * dehn + 0.3, 0.13), t)
    melodie(spur, t, MELODIE[14:15], lambda f, d: pfeifen(f, d, 0.32), transp=2, oktave=1, dehnung=dehn)
    t += T * dehn
    begleitung(spur, t, tr(G, 2), T, letzter=True)
    setzen(spur, streicher([57, 61, 64, 69], 4.5, 0.15), t)
    setzen(spur, pfeifen(hz(G4 + 2 + 12), 3.0, 0.32), t)
    setzen(spur, steel(69 + 7, 69 + 12, 4.0, 0.25), t + 0.3)
    schreiben(ziel, spur[: int((t + 5.0) * SR)])


def begleitung_leise(spur, t0, akk, takt_dauer):
    """Nur Gitarre, gezupft – für den Anfang, wenn es noch fast still ist."""
    grund, wechsel, toene = akk
    b = takt_dauer / 4
    for s in range(4):
        ts = t0 + s * b
        if s in (0, 2):
            setzen(spur, saite(hz(grund if s == 0 else wechsel), b * 1.8, 0.5), ts)
        else:
            setzen(spur, saite(hz(toene[s % len(toene)]), b * 1.5, 0.22), ts)
            setzen(spur, saite(hz(toene[(s + 2) % len(toene)]), b * 1.5, 0.18), ts + b / 2)


if __name__ == "__main__":
    # python goodmorning.py ziel.wav [kurz|lang]
    ziel = sys.argv[1] if len(sys.argv) > 1 else "goodmorning.wav"
    (lang if len(sys.argv) > 2 and sys.argv[2] == "lang" else kurz)(ziel)
