# Idee: Satellit sendet weiter (Streaming-Server, Umcodieren)

Stand: Idee vom 2026-11-04, noch nichts gebaut.

## Worum es geht

Satellit stellt sich heute ein Programm zusammen: Sender, Fahrplan, Wecken,
Einspielungen, Übersetzer. Das Ergebnis hört man nur am eigenen Rechner. Die
Idee: Satellit gibt genau diese Mischung zusätzlich als eigenen Stream aus.
Andere Geräte hören dann dasselbe Programm, ohne selbst einen Fahrplan zu
haben.

Beispiele:

- **Mehrere Räume:** Hospiz, Altersheim oder Wohnung. Ein Satellit macht
  das Programm, in jedem Zimmer reicht ein einfacher Empfänger: Webradio,
  ein Handy, ein Pi am Lautsprecher, VLC.
- **Schwache Leitung:** Campingplatz-WLAN (etwa 3 Mbit/s, geteilt) oder LTE.
  Ein starker Rechner holt die Quellen ab, auch Kurzwelle über KiwiSDR mit
  Übersetzer. Weiter geht nur ein kleiner Datenstrom, zum Beispiel
  Opus mit 32–48 kbit/s statt mehrerer MP3/AAC-Streams.
- **Funk-Teil zentral:** Kiwi, WebSDR (unsichtbarer Chromium) und Whisper
  laufen nur auf einem Gerät. Grundgeräte wie der Pi oder der Mama-Laptop
  bekommen das Ergebnis als ganz normalen Stream-Sender (`kind: stream`).

## Umcodieren

Umcodieren steckt zweimal drin:

1. **Ausgang:** Satellit mischt intern mit 48 kHz Stereo float32. Für den
   Stream codiert ffmpeg das um, als MP3 (läuft überall), AAC oder Opus
   (beste Qualität bei wenig Bandbreite). ffmpeg ist schon eine Abhängigkeit.
   Mehrere Qualitätsstufen wären möglich, etwa 128 kbit/s fürs Heimnetz und
   32 kbit/s fürs Campingplatz-WLAN.
2. **Eingang:** Satellit gleicht die Quellen schon heute an. Jeder Sender
   wird auf 48 kHz Stereo float32 umgerechnet und hat seinen eigenen `gain`.
   Für die Weitergabe würde eine echte Lautheits-Angleichung helfen, etwa
   ffmpeg `loudnorm` oder EBU R128, damit nicht jeder Senderwechsel lauter
   oder leiser wird.

## Woran man sich anschließen kann

| Baustein | Stand 2026-11 | Bewertung |
|---|---|---|
| **Icecast 2** | in Debian, GPL, gepflegt | erste Wahl als Server |
| **SHOUTcast DNAS 2.x** (`sc_serv`) | noch offiziell bei Nullsoft: `download.nullsoft.com/shoutcast/tools/sc_serv2_linux_x64-latest.tar.gz` (auch 32 Bit, Win64) | geht, ist aber proprietäre Freeware, also nicht mitliefern |
| **SHOUTcast Transcoder** (`sc_trans`) | bei Nullsoft nicht mehr erhältlich (404). Die letzte Version 10.07.2011 gibt es nur noch im Internet Archive (Linux 32/64 Bit, ohne Prüfsummen) | totes Programm, nicht darauf aufbauen. Satellit übernimmt seine Aufgaben (Playlist, Zeitplan, Umcodieren) selbst |
| **Liquidsoap** | in Debian, gepflegt | moderner Ersatz für sc_trans, für Satellit aber eher Konkurrenz als Baustein |

Icecast und SHOUTcast nehmen beide einen Quell-Stream per HTTP an, Icecast
per `PUT`/`SOURCE`, SHOUTcast 2 auch im Icecast-Stil. ffmpeg kann das direkt:
`-f mp3 icecast://source:<pw>@host:8000/satellit`. Damit braucht Satellit
keinen eigenen Server-Code und spricht beide Server an.

Für den einfachsten Fall im Heimnetz ginge es auch ganz ohne Server.
Satellit liefert selbst unter `/stream.mp3` oder `/stream.opus` aus, und
ffmpeg schreibt in die HTTP-Antwort. Wenige Hörer, kein zusätzliches
Programm.

## Mögliche Umsetzung (Skizze)

- Neuer Ausgang neben `PortAudioOutput`/`WavOutput`/`SilentOutput`: `StreamOutput`
  bekommt die fertigen Blöcke vom Mixer, also nach Lautstärke, Fades und
  Ducking, und schiebt sie per Pipe in einen ffmpeg-Prozess.
- Config-Schlüssel, zum Beispiel:

  ```json
  "relay": {
    "enabled": false,
    "mode": "http",
    "codec": "opus",
    "bitrate": 48,
    "icecast": "icecast://source:PASSWORT@localhost:8000/satellit",
    "loudnorm": true
  }
  ```

- Titel als ICY- oder Icecast-Metadaten aus `playing.label`, etwa
  „Exclusively Pink Floyd“. Passt zum offenen Punkt „Titelanzeige
  (ICY-Metadaten)“.
- Lokale Ausgabe und Stream unabhängig schalten. Ein „stummer Sender“,
  der nur streamt, wäre für Pi und Server sinnvoll.
- Stummschalten oder „ausblenden“ im Fahrplan: Der Stream läuft mit Stille
  weiter, statt abzubrechen, damit die Empfänger nicht neu verbinden müssen.

## Offene Fragen

- Weitersenden von Fremdsendern ist nur im eigenen Haus oder Netz
  unproblematisch. Öffentlich erreichbar wäre es eine Weiterverbreitung
  (Urheberrecht, GEMA). Darum standardmäßig nur LAN bzw. `127.0.0.1`, und
  ein Hinweis in der Doku.
- KiwiSDR- und WebSDR-Betreiber erlauben die Nutzung für Einzelhörer.
  Weitersenden an viele Hörer verträgt sich schlecht mit der Fairness
  (siehe README, „Fairness gegenüber KiwiSDR-/UberSDR-Betreibern“).
- Verzögerung: Puffer und Codec ergeben einige Sekunden. Für Radio egal,
  für Wecken mit Uhrzeit-Ansage merkbar.
