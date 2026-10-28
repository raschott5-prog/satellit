# Satellit unter Windows

Zwei Wege: schnell aus Python heraus, oder als eigenständiges Programm mit
Tray-Symbol und ffmpeg dabei.

## 1. Schnellstart (Python vorhanden)

1. Python 3.10+ installieren (python.org, Haken „Add python.exe to PATH").
2. ffmpeg besorgen (gyan.dev oder BtbN-Builds), `ffmpeg.exe` entweder in den
   PATH legen **oder** in den Ordner `ffmpeg\` neben `run-satellit.bat`.
3. Abhängigkeiten installieren:
   ```
   pip install -r requirements.txt
   ```
4. **`run-satellit.bat` doppelklicken.** Es öffnet die Oberfläche im Browser
   (http://localhost:8080) und legt ein Tray-Symbol an.

Fehlt `sounddevice`/eine Soundausgabe, läuft Satellit stumm weiter und zeigt
das an – die Bedienung funktioniert trotzdem.

## 2. Eigenständiges Programm bauen (ohne Python beim Nutzer)

Mit PyInstaller entsteht ein Ordner `dist\Satellit\` mit `Satellit.exe`,
der mitgelieferten Oberfläche und – wenn vorhanden – ffmpeg.

```
pip install pyinstaller
:: ffmpeg.exe vorher nach .\ffmpeg\ffmpeg.exe legen, dann wird es eingepackt
pyinstaller satellit.spec
```

Ergebnis starten: `dist\Satellit\Satellit.exe` (Tray, kein Konsolenfenster).
`run-satellit.bat` findet eine daneben liegende `Satellit.exe` automatisch.

Für eine Version **mit** mitlaufendem Konsolenfenster in `satellit.spec`
`console=True` setzen.

## 3. Automatisch starten / aus dem Standby wecken

Für das Weckprogramm (z. B. 6:30) kann Satellit den Rechner rechtzeitig aus
dem Energiesparmodus holen. Das erledigt eine geplante Aufgabe mit Wake-Timer:

```
python -m satellit.wake 06:25
```

Das legt die Aufgabe `SatellitWecken` an (`<WakeToRun>true</WakeToRun>`), die
täglich um 06:25 den Rechner weckt und Satellit startet. Entfernen:

```
python -m satellit.wake --remove
```

Voraussetzung: im BIOS/Energieoptionen müssen Aufwachtimer erlaubt sein
(Energieoptionen → Energiesparplan → Erweitert → Ruhezustand →
„Aufwachtimer zulassen").

Für Autostart beim Anmelden eine Verknüpfung auf `run-satellit.bat` in den
Autostart-Ordner legen (`shell:startup`).

## 4. Ins Heimnetz öffnen (Pi/Handy)

Standardmäßig hört Satellit nur auf `localhost`. Für Zugriff vom Handy:

```
Satellit.exe --listen 0.0.0.0
```

oder in der Konfiguration unter `%APPDATA%\Satellit\config.json`:
`"web": { "listen": "0.0.0.0", "port": 8080 }`. Dann die Windows-Firewall den
Port durchlassen lassen.

## Pfade

- Konfiguration: `%APPDATA%\Satellit\config.json`
- Ansagen und Musik: `%APPDATA%\Satellit\media\` (Musik in `media\musik\`)
- Oberfläche: `http://localhost:8080`
