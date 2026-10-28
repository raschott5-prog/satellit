#!/usr/bin/env python3
"""SAME-Generator: Header -> WAV (analog zu fake_kiwi.py).

Erzeugt gültige, verrauschte oder teildefekte SAME-Aussendungen zum Prüfen
des Dekoders und der Best-of-3-Auswertung.

    python tests/fake_same.py --event TOR --fips 024031 --out tor.wav
    python tests/fake_same.py --event RWT --noise -6 --drop 0.01 --out noisy.wav
"""

from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from satellit.same import SAMEGenerator, SAMPLE_RATE, build_header   # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SAME-WAV-Generator")
    ap.add_argument("--event", default="RWT")
    ap.add_argument("--org", default="WXR")
    ap.add_argument("--fips", nargs="+", default=["000000"])
    ap.add_argument("--purge", default="0030")
    ap.add_argument("--station", default="KEC55")
    ap.add_argument("--attention", choices=["nwr", "eas"], default=None)
    ap.add_argument("--voice", type=float, default=0.0, help="Sekunden Dummy-Sprache")
    ap.add_argument("--noise", type=float, default=None, help="Rausch-dB relativ (z. B. -6)")
    ap.add_argument("--drop", type=float, default=0.0, help="Dropout-Wahrscheinlichkeit")
    ap.add_argument("--no-eom", action="store_true")
    ap.add_argument("--out", default="same.wav")
    args = ap.parse_args(argv)

    hdr = build_header(org=args.org, event=args.event, locations=args.fips,
                       purge=args.purge, station=args.station)
    print("Header:", hdr)
    gen = SAMEGenerator()
    sig = gen.message(hdr, attention=args.attention, voice_seconds=args.voice,
                      with_eom=not args.no_eom, noise_db=args.noise,
                      drop_prob=args.drop)
    pcm = (np.clip(sig, -1, 1) * 32767).astype(np.int16)
    with wave.open(args.out, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())
    print(f"{len(sig)/SAMPLE_RATE:.1f} s -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
