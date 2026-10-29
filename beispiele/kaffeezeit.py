"""„Kaffeezeit“ – ein kleiner, sanfter Walzer für Violine mit Begleitung.

Signal-Lied des Beispiels Altersheim (docs/beispiel-altersheim.md):
    python beispiele/kaffeezeit.py kaffeezeit.wav

Eigene Komposition (frei verwendbar, CC0), synthetisch erzeugt:
Violine (Obertöne, Bogenstrich, Vibrato), gezupfte Begleitung, weicher Bass,
etwas Raumhall. D-Dur, 3/4-Takt, ruhiges Kaffeehaus-Tempo.
"""
import sys
import wave

import numpy as np

SR = 44100
BPM = 84
BEAT = 60.0 / BPM
rng = np.random.default_rng(7)


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


# --- Melodie: (MIDI, Schläge) -------------------------------------------------
A4, B4, Cs5, D5, E5, Fs5, G5, A5, B5, Cs6, D6 = 69, 71, 73, 74, 76, 78, 79, 81, 83, 85, 86
MELODIE = [
    [(A4, 1), (D5, 1), (Fs5, 1)],
    [(A5, 2), (G5, 1)],
    [(Fs5, 1), (E5, 1), (D5, 1)],
    [(E5, 3)],
    [(B4, 1), (E5, 1), (G5, 1)],
    [(B5, 2), (A5, 1)],
    [(G5, 1), (Fs5, 1), (E5, 1)],
    [(A5, 3)],
    [(A4, 1), (D5, 1), (Fs5, 1)],
    [(A5, 2), (B5, 1)],
    [(D6, 1.5), (Cs6, 0.5), (B5, 1)],
    [(A5, 3)],
    [(G5, 1), (B5, 1), (G5, 1)],
    [(Fs5, 1), (A5, 1), (Fs5, 1)],
    [(E5, 1), (G5, 1), (Cs5, 1)],
    [(D5, 5)],                       # Schluss, ausklingen lassen
]
# Akkord pro Takt: Bass + zwei Begleittöne
D, A, Em, G, Bm, A7 = ([38, 57, 62], [45, 57, 61], [40, 55, 59],
                       [43, 59, 62], [47, 54, 62], [45, 55, 61])
AKKORDE = [D, D, D, A, Em, G, A7, A, D, D, Bm, D, G, D, A7, D]
VORSPIEL = 1                         # ein Takt nur Begleitung


def violine(f, dur, laut=0.9):
    n = int(dur * SR)
    t = np.arange(n) / SR
    # Vibrato setzt nach dem Bogenansatz langsam ein
    vib = 0.0045 * np.clip((t - 0.18) / 0.35, 0, 1) * np.sin(2 * np.pi * 5.4 * t)
    phase = 2 * np.pi * f * np.cumsum(1 + vib) / SR
    sig = np.zeros(n)
    for k in range(1, 14):
        if f * k > SR / 2.2:
            break
        a = 1.0 / k ** 1.15
        a *= 1.0 + 0.8 * np.exp(-((f * k - 3000) / 900) ** 2)   # „Korpus“-Resonanz
        sig += a * np.sin(k * phase + rng.uniform(0, 6.28))
    sig += 0.02 * rng.standard_normal(n) * np.exp(-t / 0.08)     # Bogengeräusch beim Ansatz
    att, rel = min(0.09, dur / 3), min(0.18, dur / 3)
    env = np.ones(n)
    env[: int(att * SR)] = np.linspace(0, 1, int(att * SR)) ** 1.5
    env[-int(rel * SR):] *= np.linspace(1, 0, int(rel * SR))
    env *= 0.85 + 0.15 * np.sin(np.pi * np.clip(t / dur, 0, 1))  # leichtes An- und Abschwellen
    return laut * sig * env / 3.2


def zupfen(f, dur, laut=0.35):
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = sum(np.sin(2 * np.pi * f * k * t) / k ** 1.6 for k in range(1, 6))
    return laut * sig * np.exp(-t / 0.35) * np.clip(t / 0.004, 0, 1)


def bass(f, dur, laut=0.45):
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t)
    env = np.clip(t / 0.04, 0, 1) * np.exp(-t / 0.9)
    return laut * sig * env


def hall(x, sek=1.8, anteil=0.22):
    n = int(sek * SR)
    t = np.arange(n) / SR
    ir = rng.standard_normal(n) * np.exp(-t / (sek / 5))
    ir[: int(0.02 * SR)] = 0
    ir /= np.sqrt((ir ** 2).sum())
    nfft = 1 << int(np.ceil(np.log2(len(x) + n)))
    wet = np.fft.irfft(np.fft.rfft(x, nfft) * np.fft.rfft(ir, nfft), nfft)[: len(x) + n]
    out = np.zeros(len(x) + n)
    out[: len(x)] += x
    return (1 - anteil) * out + anteil * wet * 6


def setzen(spur, sig, start):
    i = int(start * SR)
    spur[i: i + len(sig)] += sig[: len(spur) - i]


def main(ziel):
    takte = len(MELODIE) + VORSPIEL
    laenge = (takte * 3 + 3) * BEAT
    spur = np.zeros(int(laenge * SR))
    for nr, akk in enumerate([D] + AKKORDE):
        t0 = nr * 3 * BEAT
        schluss = nr == takte - 1
        setzen(spur, bass(hz(akk[0]), 3 * BEAT + (2 if schluss else 0)), t0)
        if not schluss:
            for schlag in (1, 2):
                for ton in akk[1:]:
                    setzen(spur, zupfen(hz(ton), BEAT * 1.4), t0 + schlag * BEAT)
        else:
            for i, ton in enumerate(akk[1:]):            # Schlussakkord leicht gebrochen
                setzen(spur, zupfen(hz(ton), 2.5, 0.3), t0 + 0.06 * i)
    t = VORSPIEL * 3 * BEAT
    for takt in MELODIE:
        for ton, schlaege in takt:
            dauer = schlaege * BEAT
            setzen(spur, violine(hz(ton), dauer * 1.02 + (0.8 if schlaege >= 5 else 0)), t)
            t += dauer
    out = hall(spur)
    out[-int(0.5 * SR):] *= np.linspace(1, 0, int(0.5 * SR))
    out = 0.8 * out / np.max(np.abs(out))
    stereo = np.stack([out, np.roll(out, int(0.012 * SR)) * 0.97], axis=1)
    with wave.open(ziel, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((stereo * 32767).astype(np.int16).tobytes())
    print(ziel, f"{len(out) / SR:.1f} s")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "kaffeezeit.wav")
