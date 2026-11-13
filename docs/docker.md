# Satellit im Container (Docker / Podman)

Für Linux-Rechner, Heimserver und den Raspberry Pi (amd64 und arm64). Der
Container bringt Python, PortAudio und ein eigenes, reines Audio-ffmpeg mit;
auf dem Rechner selbst muss außer Docker oder Podman nichts installiert sein.

**Nicht für Windows und macOS:** Docker Desktop reicht dort keinen Ton aus dem
Container durch. Dafür gibt es die Beta-Pakete (siehe Releases).

## Starten

Mit Docker:

```
docker compose up -d --build
```

Mit Podman (ohne Root, kein Hintergrunddienst nötig):

```
podman-compose up -d --build
```

Danach ist die Oberfläche unter <http://localhost:8080> erreichbar.
Einstellungen, Medien und Chronik landen im Ordner `satellit-daten/` neben
`compose.yaml` (im Container: `/config/satellit/`). Beim ersten Start legt
Satellit dort die Startkonfiguration an.

Ohne Compose, z. B. für einen schnellen Test auf Port 8090:

```
podman build -t satellit .
podman run -d --name satellit --userns=keep-id \
  -p 127.0.0.1:8090:8080 \
  -v ./satellit-daten:/config:Z \
  -v /run/user/$(id -u)/pulse/native:/run/pulse/native \
  satellit
```

## Ton

Der Container spielt über den PulseAudio-Anschluss des Rechners
(`/run/user/<UID>/pulse/native`). Unter PipeWire stellt `pipewire-pulse` diesen
Anschluss bereit – Easy Effects, kombinierte Ausgänge usw. greifen also wie
bei einem normal installierten Satellit. In der Lautstärkeregelung erscheint
der Container als „ALSA plug-in [python3.12]“.

Der Anschluss gehört dem angemeldeten Benutzer. Darum läuft Satellit im
Container als UID 1000:

- **Docker:** `user: "1000:1000"` in `compose.yaml` reicht. Wer eine andere
  UID hat, passt dort `user` und den Pfad zum Anschluss an.
- **Podman ohne Root:** zusätzlich `--userns=keep-id` (in `compose.yaml` die
  Zeile `userns_mode: keep-id` einkommentieren). Ohne das wird UID 1000 im
  Container auf eine fremde UID abgebildet und der Anschluss ist gesperrt.
  `x-podman: in_pod: false` in `compose.yaml` sorgt dafür, dass
  podman-compose keinen Pod anlegt – mit Pod verweigert Podman `keep-id`.
  Docker überspringt `x-`-Einträge.

Läuft kein PulseAudio/PipeWire (z. B. ein Server ohne Sitzung), startet
Satellit trotzdem und meldet, dass die Soundausgabe fehlt.

## Erreichbarkeit

`compose.yaml` gibt die Oberfläche nur auf dem eigenen Rechner frei
(`127.0.0.1:8080`). Fürs Heimnetz die Zeile auf `"8080:8080"` ändern. Die
Oberfläche hat keine Anmeldung – nur in vertrauten Netzen öffnen.

## Funk-Teil

Beim Bauen zuschalten (`compose.yaml` → `build.args`):

| Schalter | Wirkung |
|---|---|
| `FUNK: "1"` | KiwiSDR und UberSDR (websocket-client, opuslib) |
| `UEBERSETZER: "1"` | Whisper-Übersetzer (faster-whisper, Image deutlich größer, Modell wird beim ersten Einschalten geladen) |

Die WebSDR-Quelle (PA3FWM) braucht einen Chromium und ist im Container nicht
vorgesehen.

## Größe und ffmpeg

Das Image ist rund 240 MB groß. Das Debian-ffmpeg allein zöge über 400 MB
Bibliotheken für Video, Grafik und X11 nach; das Dockerfile baut stattdessen
ffmpeg aus den offiziellen Quellen nur mit dem, was Satellit braucht
(HTTP/HTTPS/HLS, MP3, AAC, Ogg/Vorbis, Opus, FLAC, WAV → PCM), rund 3 MB.
Version und Prüfsumme stehen im Dockerfile (`FFMPEG_VERSION`,
`FFMPEG_SHA256`). Bei einem Versionswechsel die Signatur des Tarballs mit dem
FFmpeg-Release-Schlüssel prüfen und die neue Prüfsumme eintragen.

Ein Sender, dessen Format fehlt, meldet sich in der Oberfläche als Fehler
(„ffmpeg beendet“). Dann im Dockerfile den passenden Demuxer/Decoder ergänzen.

Das so gebaute ffmpeg steht unter der LGPL 3.0 (FFmpeg-Lizenz mit
`--enable-version3`); die Quellen sind die im Dockerfile genannten.

## Aktualisieren

```
git pull
docker compose up -d --build      # bzw. podman-compose
```

Die Daten in `satellit-daten/` bleiben erhalten.
