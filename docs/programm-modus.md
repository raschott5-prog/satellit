# Programm-Modus

Satellit hat zwei Gesichter auf einem Kern:

| | Radio-Modus | Programm-Modus |
|---|---|---|
| Für | Radiointeressierte, Funkamateure | Praxis, Hospiz, Laden, Hotel, Schule, Museum |
| Oberfläche | Skala, Frequenzen, Wache, SAME | Wochenplan, Lautstärke, Ansagen |
| Quellen | Streams, KiwiSDR, UberSDR, WebSDR, Dateien | Musikordner, Streams, Dateien |
| Engine, Mixer, Zeitplan | gemeinsam | gemeinsam |

Der Radio-Modus gehört zum **Funk-Teil** (seit 0.4 abschaltbar, Schalter
„Funk & Kurzwelle“ unten in dieser Ansicht). Ist der Funk-Teil aus – so
starten neue Installationen –, gibt es nur den Programm-Modus; Web-SDR,
Wache, SAME und Übersetzer werden dann gar nicht erst geladen.

Umschalten zwischen den Ansichten (mit Funk-Teil): Link oben bzw. unten in
der Oberfläche, `--mode program` beim Start, oder `"mode": "program"` in der
Konfiguration. Wache und SAME laufen im Programm-Modus nicht mit.

## Bedienung

- **Jetzt** – was läuft, warum (nach Plan / von Hand / Ersatzbetrieb), laufende
  Ansage mit **Stoppen**.
- **Als Nächstes** – Uhrzeit, Inhalt, Countdown, **Diesmal aussetzen**.
- **Lautstärke** – ein Regler, ein großer **Stumm**-Knopf. Standard 50 %.
- **Wochenplan** – Mo–So, heute hervorgehoben. Eintrag anklicken:
  **Ausschalten** (dauerhaft), **Nur heute aussetzen**, bei Ansagen
  **Jetzt im Raum abspielen**. Fehlt eine Datei, ist der Eintrag rot markiert.
- **Einspielungen & Musik** – **Vorschau** spielt nur am eigenen Gerät
  (Browser, z. B. mit Kopfhörer), **Im Raum** über die Lautsprecher.
  Dateien per Ziehen-und-Ablegen hochladen (MP3, WAV, OGG, FLAC, M4A; max. 50 MB).
- **Protokoll** – was wann gelaufen, übersprungen oder abgebrochen ist.

## Regeln für Einspielungen (verbindlich)

1. **Das Dateiende beendet eine Ansage, nie die Uhr.** Wechselt das Programm
   laut Plan während einer Ansage, wechselt es *darunter*; die Musik kommt
   danach bereits auf dem neuen Programm zurück.
2. **Überlappung:** Einspielungen laufen nacheinander in der Reihenfolge ihrer
   Fälligkeit (gleiche Uhrzeit: Reihenfolge im Plan). Zwischen direkt
   aufeinanderfolgenden Ansagen bleibt die Musik unten.
3. **Verspätung:** Wer mehr als `max_delay_minutes` (Standard 10) zu spät dran
   ist – Rechner war im Standby, lange Warteschlange –, wird verworfen und
   protokolliert. Nichts wird Stunden später nachgeholt.
4. **Stumm** schaltet sofort leise und bricht eine laufende Ansage ab. Planmäßig
   fällige Ansagen werden während Stumm übersprungen; von Hand ausgelöste
   warten, bis der Ton wieder an ist.
5. **Fehlende Datei:** wird übersprungen und protokolliert; weitere Dateien
   derselben Einspielung (z. B. Gong → Ansage) laufen trotzdem.
6. **Alarm (SAME) bricht ab** und wird protokolliert (nur mit Funk-Teil im Radio-Modus).
7. **Sommerzeit-Ende / Uhr zurück:** nichts wird doppelt ausgelöst.

Darstellung: `"mode": "duck"` (Standard) senkt die Musik auf `duck_level`
(15 %) ab und legt die Ansage darüber; `"mode": "replace"` blendet die Musik
für die Dauer ganz aus.

## Ohne Internet

Fällt die Programmquelle aus (Stream weg, Router aus), übernimmt die
**Ersatzquelle** – Standard ist der lokale Ordner `media/musik`. Die
ausgefallene Quelle wird jede Minute neu versucht; liefert sie wieder Ton,
wird zurückgeblendet. Ansagen sind immer lokale Dateien und brauchen nie Netz.

## Plan-Einträge in `config.json`

```json
{"time": "07:30", "station": "musik"},
{"time": "08:00", "station": "radio", "days": ["mo","di","mi","do","fr"]},
{"time": "09:00", "play": ["gong.wav", "grippe.mp3"], "label": "Grippeimpfung",
 "days": ["mo","di","mi","do","fr"], "mode": "duck"},
{"time": "18:00", "action": "sleep", "fade": 120}
```

`days` fehlt = täglich. `enabled: false` = aus. `skip_date` setzt die
Oberfläche selbst („nur heute aussetzen").

## Anwendungsideen

Arztpraxis/Wartebereich (Hinweise, Handy lautlos) · Ladenfunk (Musik +
getaktete Durchsagen) · Hotel/Gastro (Tagesstimmung) · Schule (Gong,
Durchsagen, Pausenmusik) · Museum (Raum-Loops) · Funkamateur (eigene
Aufnahmen zeitgesteuert, Clubabend-Erinnerung). Technisch immer dasselbe.
