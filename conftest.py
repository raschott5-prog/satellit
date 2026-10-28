"""Macht das Paket in den Tests importierbar (Projektwurzel auf sys.path)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
