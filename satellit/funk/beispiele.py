"""Beispielsender für den Funk-Teil.

Wer den Funk-Teil zum ersten Mal einschaltet und noch keine eigenen
Web-SDR-Empfänger eingetragen hat, bekommt diese Liste – zum Ausprobieren,
nicht als Empfehlung. Alles öffentliche WebSDR (PA3FWM) von Funkamateuren
und Universitäten; ob ein Empfänger gerade läuft und was auf der Frequenz
zu hören ist, hängt von Tageszeit, Ausbreitung und Betreiber ab.

Getestet am 29.10.2026 (Abend in Mitteleuropa):

* Shannon VOLMET – Flugwetter auf Englisch, rund um die Uhr
* 40 m Enschede – Amateurfunk, abends oft Russisch
* Washington DC, Mittelwelle – Spanisch und Koreanisch (Ortssender, am
  dortigen Tag per Bodenwelle stabil, nach Sonnenuntergang Schwund)
* Los Angeles, Mittelwelle – Spanisch

Mit dem Übersetzer zusammen zeigen sie die Grundidee: Lokalradio aus aller
Welt, das man live mitlesen kann.
"""

from __future__ import annotations

SUFFIX = " (Beispiel)"

STATIONS = [
    {"id": "bsp-shannon", "name": "Shannon VOLMET 5505 USB – Hack Green",
     "kind": "websdr", "url": "http://hackgreensdr.org:8901/",
     "freq_khz": 5505, "mode": "usb", "buffer": 3},
    {"id": "bsp-enschede-40m", "name": "40 m 7095 LSB – Enschede",
     "kind": "websdr", "url": "http://websdr.ewi.utwente.nl:8901/",
     "freq_khz": 7095, "mode": "lsb", "buffer": 3},
    {"id": "bsp-dc-900", "name": "Washington 900 AM Spanisch – NA5B",
     "kind": "websdr", "url": "http://na5b.com:8901/",
     "freq_khz": 900, "mode": "am", "buffer": 3},
    {"id": "bsp-dc-1310", "name": "Washington 1310 AM Koreanisch – NA5B",
     "kind": "websdr", "url": "http://na5b.com:8901/",
     "freq_khz": 1310, "mode": "am", "buffer": 3},
    {"id": "bsp-la-1330", "name": "Los Angeles 1330 AM Spanisch – KJ6EO",
     "kind": "websdr", "url": "http://kj6eo.com:8901/",
     "freq_khz": 1330, "mode": "am", "buffer": 3},
    {"id": "bsp-la-1390", "name": "Los Angeles 1390 AM Spanisch – KJ6EO",
     "kind": "websdr", "url": "http://kj6eo.com:8901/",
     "freq_khz": 1390, "mode": "am", "buffer": 3},
]


def stations() -> list[dict]:
    """Frische Kopien, als Beispiel gekennzeichnet (Name + ``"example": true``)."""
    return [dict(s, name=s["name"] + SUFFIX, example=True) for s in STATIONS]


def missing_in(existing: list[dict]) -> list[dict]:
    """Beispiele, die noch nicht drin sind – nur wenn es noch gar keine
    Web-SDR-Sender gibt (wer eigene hat, bekommt nichts untergeschoben)."""
    from . import FUNK_KINDS
    if any(s.get("kind") in FUNK_KINDS for s in existing):
        return []
    ids = {s.get("id") for s in existing}
    return [s for s in stations() if s["id"] not in ids]
