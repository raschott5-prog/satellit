# Änderungen

Ausführliche Notizen mit Hintergrund stehen bei den
[Releases](https://github.com/raschott5-prog/satellit/releases).

## 0.4.9 – 2026-11-13

- **Schnellstart** oben in der README („In 5 Minuten zum ersten Ton“) und eine
  kurze Übersicht „Was ist neu“ statt gestapelter Neu-in-Abschnitte.
- **CHANGELOG.md** (diese Datei).
- **Automatische Tests bei GitHub:** Bei jedem Push und Pull Request laufen die
  Tests unter Linux mit Python 3.10 bis 3.14 (`.github/workflows/tests.yml`).
- README: `lautheit.json` löschen = alle Sender neu messen.
- Am Programm selbst nichts geändert.

## 0.4.8 – 2026-11-13

- **Gleich laut auf allen Sendern:** Lautheitsmessung nach EBU R128 /
  ITU-R BS.1770 je Sender, langsamer Angleich auf `audio.loudness_target`
  (Standard −16 LUFS, höchstens +10/−15 dB). Ersetzt die alte, schnelle
  RMS-Automatik, die pumpen konnte.
- Gemessene Werte je Sender in `lautheit.json`: beim Umschalten stimmt der
  Pegel sofort.
- Abschalten mit `audio.auto_level: false`, je Sender mit `"loudness": false`.
- `/api/state` zeigt unter `loudness` Messwert und Ausgleich.
- **Container:** Dockerfile und `compose.yaml` für Docker und Podman (Linux,
  amd64 und arm64) mit eigenem, schlankem Audio-ffmpeg; Anleitung
  `docs/docker.md`.

## 0.4.7 – 2026-11-12

- Reißt ein laufender Sender ab, verbindet Satellit nach 10 statt 60 Sekunden
  neu.
- Denselben Sender noch einmal wählen = sofort frisch verbinden.
- Von Hand eingereihte Einspielungen verfallen nicht mehr nach
  `max_delay_minutes`; nach einer verworfenen Einspielung fährt die Musik
  wieder hoch.

## 0.4.6 – 2026-11-01

- **Senderchronik:** Geschichte und Geschichten zu jedem Sender, unveränderliche
  Einträge mit Berichtigungen, Prüfwert-IDs, Import und Export
  (`/api/chronik`). Gespeichert in `chronik.json`.

## 0.4.5 – 2026-10-31

- HFCC-Sendeplan in den ersten vier Wochen einer Saison täglich nachladen
  (`hfcc.new_season_days`, `hfcc.new_season_refresh_days`).
- Sauberes Beenden auch per SIGTERM (räumt WebSDR-Browser und virtuelle
  Soundkarte auf).

## 0.4.4 – 2026-10-29

- Klangstück **„Fernzug“** (4:22): Metall, Elektronik und vorbeifahrende Züge
  im Takt einer Bahnhofsuhr. Übersicht aller Stücke: `docs/klangstuecke.md`.

## 0.4.3 – 2026-10-29

- Beispiel **„Guten Morgen“** (`beispiele/guten-morgen.json`): zehn Minuten
  sanft wecken mit „Good Morning“ in langer und kurzer Fassung.

## 0.4.2 – 2026-10-29

- Beispiel **Altersheim** mit dem Signal-Lied „Kaffeezeit“
  (`docs/beispiel-altersheim.md`).
- Beta-Pakete für Windows und macOS (`packaging/baue_betas.py`); jede
  Installation erzeugt ihre eigene UberSDR-ID.

## 0.4.1 – 2026-10-29

- `satellit.funk` fehlte im pip-Paket; neues Extra `satellit[funk]`.
- Windows-Build nimmt den Funk-Teil ausdrücklich mit.

## 0.4.0 – 2026-10-29

- **Grundgerät und Funk-Teil getrennt**, Schalter „Funk & Kurzwelle“
  (`POST /api/funk`). Das Grundgerät kommt ohne Whisper, Websocket & Co. aus.
- **WebSDR-Quelle** für die PA3FWM-WebSDR über den unveränderten
  Original-Client im unsichtbaren Browser (vorerst nur Linux).
- Beispielsender beim ersten Einschalten des Funk-Teils (Shannon VOLMET,
  Enschede 40 m, Lokalradio aus Washington und Los Angeles).
- Naturklänge zum Wecken als Beispiel im Grundgerät.
- Fehlerhafte Sender lösen sauber den Ersatzbetrieb aus.

## Frühere Versionen

- **0.3** – Live-Übersetzer (faster-whisper, offline auf der CPU).
- **0.2** – Programm-Modus neben dem Radio-Modus: Wochenplan, Ansagen und
  Einspielungen ohne Funkbegriffe.
