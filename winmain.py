"""Einstieg für den Windows-Build (Tray, ohne Konsolenfenster)."""
import sys
from satellit.tray import run

if __name__ == "__main__":
    sys.exit(run())
