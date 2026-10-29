# Satellit – virtuelles Weltempfänger-Radio

Ein Radio für den Schreibtisch oder die Küche, das sich anfühlt wie ein großer
Weltempfänger – aber seine Sender aus dem Netz holt:

- **„UKW“-Sender** sind Internet-Streams. Man trägt die Stream-Adresse ein und
  die Frequenz, auf der der Sender auf der Skala liegen soll.
- **Mittel- und Kurzwelle** (Funk-Teil) kommen live von öffentlichen **KiwiSDR**-, **WebSDR**- und
  **UberSDR**-Empfängern, z. B. der AM-Sender aus der nächsten Großstadt.
- **Hörfahrplan**: Um 6:30 sanft mit AM wecken, um 8:30 auf den „UKW“-Sender
  überblenden, um 23 Uhr langsam ausblenden.
- **Wache**: Prüft einmal pro Minute kurz Kanäle wie das Hurricane Watch Net
  (14.325 MHz USB, 7.268 MHz LSB) und schaltet bei Betrieb automatisch um.
- **SAME-Wache**: Dekodiert die maschinenlesbaren Kopfzeilen von US-Notfall-
  durchsagen (EAS/NOAA Weather Radio) und schaltet gezielt nach **Ereignis +
  Gebiet** (eigene FIPS-Codes) um. `EAN` schlägt alles.
- **Übersetzer** (neu in 0.3): hört beim laufenden Programm mit, erkennt die
  Sprache und übersetzt live ins Englische – offline, auf der CPU. Gedacht für
  exotische Kurzwellenstationen und Amateurfunk: lieber Bruchstücke mit
  Fragezeichen als gar nichts.
- **Weiche Übergänge** überall: Equal-Power-Überblendung mit etwas Sender-
  rauschen, Pegelausgleich zwischen AM und UKW-Stream, Weck-Einblendung über
  Minuten. Ein Weck-Eintrag (`"wake": true`) beginnt immer bei null, auch wenn
  vorher etwas lief, und blendet über seine eigene `fade` ein (mindestens
  `audio.wake_seconds`), z. B. `{"time": "18:00", "station": "wdr4", "fade": 600,
  "wake": true}` = 10 Minuten Fade-in.

Bedienung im Browser unter `http://localhost:8080` – auf Windows, Linux und
dem Raspberry Pi gleich.

### Neu in 0.4

- **Grundgerät und Funk-Teil getrennt**, mit Schalter „Funk & Kurzwelle“
  (siehe unten). Das Grundgerät kommt ohne Whisper, Websocket & Co. aus.
- **WebSDR-Quelle** für die PA3FWM-WebSDR (Enschede, Hack Green, NA5B …),
  über den unveränderten Original-Client im unsichtbaren Browser (Linux).
- **Beispielsender** beim ersten Einschalten des Funk-Teils: Shannon VOLMET,
  40 m aus Enschede, spanisches und koreanisches Lokalradio aus Washington,
  spanisches aus Los Angeles. Zusammen mit dem Übersetzer zeigen sie die
  Grundidee: Früher übersetzten Auslandsdienste ihr Programm für die Welt –
  heute hört man das Lokalradio der Welt und übersetzt beim Hörer.
- Wecken mit Naturklängen als Beispiel im Grundgerät (Ordner `voegel/`,
  eine Stunde von ganz leise auf normal).
- Fehlerhafte Sender (unvollständig, Funk-Teil aus) lösen jetzt sauber den
  Ersatzbetrieb aus, statt still zu spielen.

### Grundgerät und Funk-Teil

Satellit besteht aus zwei sauber getrennten Teilen:

- **Grundgerät** (immer da): Internet-Streams, lokale Musik und Ordner,
  Wochenplan, sanftes Wecken und Einschlafen, Ansagen und Einspielungen,
  Ersatzbetrieb ohne Internet. Keine Funkbegriffe, wenige Abhängigkeiten
  (`requirements.txt`). Gedacht auch für Praxis, Hospiz, Pflegeheim, Laden:
  z. B. morgens eine Stunde lang Vogelgesang von ganz leise auf normal
  (`{"time": "06:30", "station": "voegel", "fade": 3600, "wake": true}`,
  Dateien in den Medienordner `voegel/`).
  Ein ausgearbeitetes Beispiel ist das **Altersheim**, in dem die Bewohner ihr
  Musikprogramm selbst wählen und um 16 Uhr ein Walzer zur Kaffeezeit läuft
  (mitgeliefert: „Kaffeezeit“, eigene Komposition, frei verwendbar):
  [`docs/beispiel-altersheim.md`](docs/beispiel-altersheim.md),
  Konfiguration in [`beispiele/altersheim.json`](beispiele/altersheim.json).
- **Funk-Teil** (`satellit/funk/`, Schalter **„Funk & Kurzwelle“**):
  KiwiSDR, UberSDR, WebSDR, Wache, SAME, HFCC-Sendeplan, Übersetzer,
  Radio-Ansicht mit Skala. Zusatzpakete in `requirements-funk.txt`.

Der Schalter sitzt unten in der Programm-Ansicht (aus der Radio-Ansicht
zurück: „Funk-Teil ausschalten“ unten), per API `POST /api/funk
{"enabled": true}` oder in `config.json` als `"funk": {"enabled": true}`.
Neue Installationen starten als Grundgerät. Eine ältere Konfiguration mit
Web-SDR-Sendern behält beim ersten Start den Funk-Teil. Ist er aus, wird
`satellit.funk` gar nicht erst geladen; Web-SDR-Sender im Plan melden
„gehört zum Funk-Teil“ und der Ersatz (lokale Musik) springt ein.

### Zwei Gesichter, ein Kern (neu in 0.2)

- **Radio-Modus** (nur mit Funk-Teil) – Skala, Frequenzen, KiwiSDR/UberSDR/WebSDR, Wache, SAME.
- **Programm-Modus** – Wochenplan, lokale Musik, Ansagen und Einspielungen,
  großer Lautstärkeregler und Stumm-Knopf. Keine Funkbegriffe. Für Praxis,
  Laden, Hotel, Schule, Museum – oder den Funkamateur, der eigene Aufnahmen
  zeitgesteuert einspielt.

Beide nutzen dieselbe Engine und denselben Zeitplan. Einspielungen enden mit
ihrem Dateiende, nie mitten im Satz; ohne Internet übernimmt lokale Musik.
Regeln und Bedienung: [`docs/programm-modus.md`](docs/programm-modus.md).

## Starten (Entwicklerstand)

Voraussetzungen: Python 3.10+, ffmpeg.

```
pip install -r requirements.txt                 # Grundgerät
pip install -r requirements-funk.txt            # dazu, wer den Funk-Teil will
python -m satellit
```

Unter Linux braucht `sounddevice` die PortAudio-Bibliothek (`apt install
libportaudio2`). Fehlt die Soundausgabe, läuft das Programm stumm weiter und
meldet das.

**Windows** mit Tray-Symbol und ffmpeg dabei: siehe [`docs/windows.md`](docs/windows.md).
Kurz: `run-satellit.bat` doppelklicken, oder mit PyInstaller ein
eigenständiges `Satellit.exe` bauen (`pyinstaller satellit.spec`).

**macOS** (Intel und Apple Silicon): `run-satellit.sh` funktioniert wie unter
Linux. Für Tester gibt es ein Beta-Paket mit `Satellit starten.command`
zum Doppelklicken (Vorlage in [`packaging/mac-beta/`](packaging/mac-beta/)).
ffmpeg muss nicht installiert sein: Fehlt es im PATH, nimmt Satellit unter
macOS und Windows das aus dem pip-Paket `imageio-ffmpeg`.

Optionen:

| Option | Zweck |
|---|---|
| `--listen 0.0.0.0` | Oberfläche im ganzen Heimnetz erreichbar (Pi + Handy) |
| `--port 8080` | anderer Port |
| `--device N` | Audiogerät wählen (`--list-devices` zeigt die Liste) |
| `--wav datei.wav` | statt Lautsprecher in eine Datei schreiben (Tests) |
| `--config pfad` | andere Konfigurationsdatei |
| `--mode program` | Programm-Oberfläche (Standard: `radio`) |

Die Konfiguration liegt unter `%APPDATA%\Satellit\config.json` (Windows) bzw.
`~/.config/satellit/config.json` (Linux) bzw.
`~/Library/Application Support/Satellit/config.json` (macOS) und wird über die Oberfläche
bearbeitet. Die mitgelieferten Beispiel-Sender zeigen nur das Format – echte
Stream-URLs und Empfänger trägt man selbst ein.

## Aufbau

```
Quellen (Stream/ffmpeg, KiwiSDR/Websocket, UberSDR/Opus)  ->  PCM 48 kHz Stereo
        |
Mixer: Deck A / Deck B, Überblendung, Pegelausgleich, Master-Rampe, Begrenzer
        |
Ausgabe: PortAudio (oder stumm / WAV)

Engine: Fahrplan (alle 0,25 s geprüft), Einspielungen, Ersatzbetrieb
  └ Funk-Teil (abschaltbar): Wache (eigener Thread), SAME-Dekoder
    (eigener Thread), Übersetzer (eigener Thread, hört am Mixer mit),
    HFCC, legt seine Schichten über das Programm
Web: kleiner HTTP-Server (nur Standardbibliothek) + eine HTML-Datei
```

| Datei | Inhalt |
|---|---|
| `satellit/audio.py` | Format-Konstanten, thread-sicherer Ringpuffer |
| `satellit/mixer.py` | Zwei Decks, Crossfade, Weck-Rampe, Pegelausgleich, Begrenzer |
| `satellit/config.py` | Konfiguration laden/speichern (plattformübergreifend) |
| `satellit/sources/stream.py` | Internet-Stream über ffmpeg, .pls/.m3u |
| `satellit/sources/file.py` | Lokale Dateien (WAV nativ, sonst ffmpeg), Musikordner |
| `satellit/media.py` | Medienordner, sichere Dateinamen, Demo-Gong |
| `satellit/scheduler.py` | Hörfahrplan |
| `satellit/engine.py` | Verbindet alles, Schalter für den Funk-Teil |
| **Funk-Teil** | |
| `satellit/funk/__init__.py` | Quellenarten, Zusatzpakete, Fabrik für Funkquellen |
| `satellit/funk/funkteil.py` | Andockstelle an der Engine: Schichten, Wache, SAME, HFCC, Übersetzer |
| `satellit/funk/kiwi.py` | KiwiSDR-Protokoll, IMA-ADPCM, S-Meter, Kurz-Abfrage |
| `satellit/funk/ubersdr.py` | UberSDR (Opus), feste UUID, weiche Übergabe |
| `satellit/funk/websdr.py` | PA3FWM-WebSDR über den Original-Client im unsichtbaren Chromium |
| `satellit/funk/watcher.py` | Aktivitätserkennung über das S-Meter |
| `satellit/funk/same.py` | SAME-Dekoder (AFSK, Best-of-3, Parser) + Generator |
| `satellit/funk/translate.py` | Übersetzer: Abschnitte, Pausenschnitt, Whisper, Filter |
| `satellit/funk/hfcc.py` | Sendeplan der HFCC: was läuft auf welcher Kurzwellenfrequenz |
| `satellit/web.py`, `static/program.html`, `static/index.html` | API, Programm-Oberfläche (Grundgerät), Radio-Oberfläche (Funk-Teil) |
| `satellit/output.py` | PortAudio / WAV / stumm |
| `satellit/tray.py`, `satellit/wake.py` | Windows-Tray, Standby-Wecken |

### Verhalten, das man kennen sollte

- Ein neuer Sender wird erst eingeblendet, wenn er wirklich Ton liefert. Bis
  dahin läuft der alte weiter. Kommt der neue nicht (15 s, bei klarem Fehler
  3 s), bleibt der alte.
- Von Hand umschalten gilt bis zum nächsten Fahrplan-Eintrag.
- Fällt ein Sender aus (Kiwi offline, voll, abgewiesen), springt Satellit auf
  den Ersatz: den eigenen des Senders (`"fallback": "<sender-id>"` im
  Sendereintrag, z. B. dieselbe Frequenz auf einem zweiten Kiwi), sonst den
  allgemeinen (`"fallback"` ganz oben, Standard `musik`). Liefert der
  ursprüngliche Sender wieder Ton, geht es zurück.
- **Puffer pro Sender:** Ein Sender startet, sobald 0,6 s Ton vorliegen.
  Liefert ein Stream oder Kiwi schubweise (Hoppeln), bekommt er mehr Vorlauf
  mit `"buffer": <Sekunden>` im Sendereintrag (0,2–30, z. B. `8`). Er wird
  dann so viel später eingeblendet, überbrückt aber Lücken in dieser Länge.
  Läuft der Puffer trotzdem leer, sammelt Satellit erst wieder den vollen
  Vorlauf, statt jeden einzelnen Schub sofort abzuspielen: einmal kurz still
  statt ständigem Stottern. Der Abriss wird dabei weich ausgeblendet (kein
  Knacken) und der Sender danach über 2 s wieder eingeblendet. Der Status zeigt `buffer_s` und `rebuffers`.
- Die Wache schaltet nach 2 Treffern in Folge um und nach 10 ruhigen Abfragen
  zurück (einstellbar). „Zurück zum Programm“ schaltet den Kanal 30 Minuten
  stumm. Hört man den Wache-Kanal ohnehin gerade, wird kein zweiter Kiwi-Slot
  belegt.
- **Prioritätsleiter** (höher gewinnt): `EAN` (national) › SAME-Warnung fürs
  eigene Gebiet › Wache › Hand/Fahrplan › Schlummern. SAME-Beobachtungen geben
  nur einen Hinweis, Tests werden nur protokolliert.

### Übersetzer (neu in 0.3)

Karte „Übersetzer → Englisch“ in der Radio-Ansicht, ein Knopf zum Ein- und
Ausschalten (oder `POST /api/translate {"enabled": true}`). Jede Zeile zeigt
Uhrzeit, erkannte Sprache, die englische Übersetzung und den Sender.

- **Wie:** Der Mixer reicht jeden Block nach der Überblendung an den
  Übersetzer weiter – also *vor* Lautstärke und Stumm: Es wird auch bei leisem
  oder stummem Radio übersetzt. Ein eigener Thread schneidet 5–12 s lange
  Abschnitte, bevorzugt in Sprechpausen (auch unter Kurzwellenrauschen), und
  gibt sie an [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
  (`task=translate`). Whisper übersetzt aus rund 100 Sprachen, aber nur **ins
  Englische**.
- **Filter:** Funkstille geht gar nicht erst ins Modell. Verworfen werden
  Nicht-Sprache, sehr unsichere Segmente, Wiederholungsschleifen und die
  typischen Floskeln, die Whisper aus Rauschen erfindet („Thank you for
  watching“). Unsichere Sprache oder wackelige Übersetzung wird **blass mit
  „?“** angezeigt statt verworfen.
- **Senderwechsel:** Der angefangene Abschnitt des alten Senders wird
  verworfen, nichts wird vermischt.
- **Rechenlast:** Modell `small` braucht auf einem i5-10310U etwa 0,6 s pro
  Sekunde Audio. Kommt der Rechner nicht hinterher, wird alter Rückstand
  übersprungen (Anzeige „… s übersprungen“), der Ton selbst bleibt unberührt.
- **Modell wählen:** Im Register „Übersetzer“ lässt sich das Modell im
  laufenden Betrieb umschalten (`tiny` … `large-v3`); der Ton läuft weiter,
  nur die Übersetzung pausiert, bis das neue Modell geladen ist. Noch nicht
  vorhandene Modelle sind mit ihrer Downloadgröße markiert und werden erst nach
  Rückfrage geladen. Vergleich vom 26.10.2026 (je 1 min Türkisch, Französisch,
  CRI-Kroatisch-Sprachkurs): `medium` übersetzt merklich genauer (Eigennamen,
  ganze Meldungen, seltene Sprachen statt Halluzinationen), braucht aber Last
  ≈ 1,9 statt ≈ 0,8 – live fällt dann etwa jeder zweite Abschnitt weg.
- **Installation:** `pip install faster-whisper`. Beim ersten Einschalten wird
  das Modell geladen (`small` ≈ 460 MB, danach offline). Ohne das Paket ist der
  Knopf ausgegraut, alles andere läuft wie gehabt.

Einstellungen in `config.json` unter `translate`:

| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `model` | `small` | `tiny`/`base` schneller (Raspberry Pi), `medium` genauer |
| `language` | `null` | `null` = Sprache erkennen, sonst fest, z. B. `"fr"` (hilft bei schwachem Signal) |
| `beam` | `1` | größer = genauer, langsamer |
| `fallback` | `false` | Whisper rechnet unsichere Abschnitte mit höherer „Temperatur“ neu – auf Kurzwelle 3–4× so teuer (s. u.) |
| `threads` | `0` | CPU-Threads fürs Modell, `0` = automatisch (Kerne − 2) |
| `min_seconds` / `max_seconds` | `5` / `12` | Abschnittslänge |
| `min_lang_prob` | `0.5` | darunter gilt die erkannte Sprache als unsicher |

Erfahrung aus dem Test (France Info, künstlich auf SSB 300–2700 Hz beschnitten,
mit Fading und Rauschen): bei 10 dB Rauschabstand kommt fast jeder Satz
sinngemäß an, bei 3 dB noch der grobe Inhalt in Bruchstücken, reines Rauschen
bleibt still.

Live-Test über KiwiSDR (Wildeck, `trebor1401.proxy.kiwisdr.com`, 23.10.2026,
Russisch/Türkisch/Persisch/Chinesisch, 8-Kern-Laptop, Modell `small`): Mit
Whisper-Standard (Temperatur-Fallback an) lag die Rechenlast bei 1,6–1,9 –
langsamer als Echtzeit, auf Dauer wären Abschnitte verworfen worden. Bei
verrauschtem Ton verwirft Whisper fast jeden Versuch und rechnet bis zu 5× neu.
Ohne Fallback: Last ≈ 0,5, Übersetzungen gleichwertig, nur mehr
Wiederholungsschleifen – die kürzt bzw. verwirft der Filter.

### Sendeplan: Was läuft gerade? (HFCC)

Die High Frequency Co-ordination Conference veröffentlicht pro Saison die
angemeldeten Sendungen aller großen Kurzwellensender
(`http://www.hfcc.org/data/b26/b26allx2.zip`, ~160 KB). Satellit lädt die
passende Saison beim ersten Kiwi-/UberSDR-Sender, speichert sie im
Konfigordner (`hfcc/`) und erneuert sie wöchentlich. Ist die neue Saison noch
nicht veröffentlicht, gilt die alte weiter.

- **Anzeige:** Das LCD zeigt unter dem Sendernamen z. B.
  „▸ CRI · Kroatisch · Urumqi 500 kW“ (mehr per Tooltip), die Senderliste
  „jetzt: …“ für jede Kurzwellenfrequenz.
- **Übersetzer:** Kommen laut Plan nur Sprachen in Frage, die Whisper kennt,
  bekommt Whisper sie als Kandidaten. Erkennt es eine andere, wird mit der
  wahrscheinlichsten Kandidatin übersetzt – sofern Whisper ihr mindestens 2 %
  zutraut (sonst sendet wohl jemand, der nicht im Plan steht). Eine Sprache,
  die zum Plan passt, gilt als sicher und trägt „▸“.
- Format: festes ITU-Spaltenformat, **Wochentage ab Sonntag** (1 = So).
  HFCC enthält nur angemeldete Kurzwelle – keine Mittelwelle, keine Piraten.
- Live-Abgleich 26./27.10.2026: CRI Französisch 7350, Englisch 7415,
  Arabisch 6100, Kroatisch 7225, Mongolisch 7205 und TRT 5980 stimmten alle.

Abschalten: `"hfcc": {"enabled": false}`.

### SAME (US-Notfalldurchsagen)

Reiner Dekoder, hängt sich an vorhandene PCM (bevorzugt NWR-Internet-Streams;
162 MHz VHF liegt außerhalb von Kiwi/UberSDR). Konfiguration: eigene FIPS-Codes
(Gebiet) + Ereignisfilter in `config.json` unter `same`. Details und Protokoll:
[`claude/same-protokoll.md`](claude/same-protokoll.md) im Projekt.

Ohne echtes Signal lässt sich alles über die Oberfläche („Test-Alarm
einspeisen“) oder die API (`POST /api/same/test`) ausprobieren.

### WebSDR (Enschede, Hack Green, NA5B, …) – neu in 0.4

PA3FWM erlaubt seinen WebSDR-Client nur unverändert; Nachbau und Reverse
Engineering sind untersagt. Satellit baut daher nichts nach, sondern lässt
**den Original-Client** laufen:

* je Quelle eine eigene virtuelle Soundkarte (`pactl load-module module-null-sink`),
* ein unsichtbarer Chromium (`--headless=new`) spielt nur dort hinein,
* Frequenz und Modus werden nach dem Laden per DevTools gesetzt und geprüft
  (manche WebSDR überschreiben den Modus aus `?tune=` mit dem Bandstandard),
* `parec` liest den Monitor der Senke; beim Stoppen verschwinden Browser,
  Profil und Senke wieder.

```json
{"id": "shannon-hg", "name": "Shannon VOLMET 5505 (Hack Green)", "kind": "websdr",
 "url": "http://hackgreensdr.org:8901/", "freq_khz": 5505, "mode": "usb", "buffer": 3}
```

**Beispielsender** (`satellit/funk/beispiele.py`) – eingetragen beim ersten
Einschalten des Funk-Teils, wenn es noch keine eigenen Web-SDR-Sender gibt,
erkennbar an „(Beispiel)“ und `"example": true`:

| Sender | Empfänger | kHz | Was man hört |
|---|---|---|---|
| Shannon VOLMET | Hack Green (GB) | 5505 USB | Flugwetter, rund um die Uhr |
| 40 m Amateurfunk | Enschede (NL) | 7095 LSB | Funkamateure, abends oft Russisch |
| Washington 900 AM | NA5B (USA) | 900 AM | Spanisch: Talk, Technik, Werbung |
| Washington 1310 AM | NA5B (USA) | 1310 AM | Koreanisch: Sport, Gesundheit, Werbung |
| Los Angeles 1330 AM | KJ6EO (USA) | 1330 AM | Spanisch |
| Los Angeles 1390 AM | KJ6EO (USA) | 1390 AM | Spanisch |

US-Mittelwelle ist tagsüber (dortiger Zeit) per Bodenwelle stabil; nach
Sonnenuntergang kommen Schwund und Fremdsender dazu. Die Empfänger gehören
Funkamateuren und Universitäten – bitte fair nutzen.

Modi: `usb`, `lsb`, `am`, `fm`, `cw`. Vorerst **nur Linux** (braucht `pactl`,
`parec`, Chromium). Die Serverliste von websdr.org wird bewusst nicht
eingebunden – ihre Weiterverwendung in automatischen Systemen braucht die
Erlaubnis von PA3FWM; Empfänger trägt man von Hand ein.

### Fairness gegenüber KiwiSDR-/UberSDR-Betreibern

Kiwis und UberSDR-Instanzen haben nur wenige Plätze. Das Programm meldet sich
als `SatellitRadio`, fragt für die Wache höchstens alle 30 s (Standard 60 s)
für wenige Sekunden ab und verteilt die Abfragen reihum. Bei UberSDR **keine
UUID-Rotation**: Satellit nutzt eine feste UUID pro Installation und blendet
vor Ablauf der Sitzungszeit weich auf eine andere Instanz/Quelle über.

## Tests

```
python -m pytest tests

python tests/fake_kiwi.py --port 18073 [--active]      # KiwiSDR-Attrappe
python tests/fake_same.py --event TOR --fips 024031 --out tor.wav   # SAME-WAV
```

Die Suite (117 Tests) läuft ohne Netz, Soundkarte oder optionale Pakete: der
SAME-Round-Trip inklusive Best-of-3 unter Rauschen, Mixer/Begrenzer, Fahrplan,
Konfiguration, Ringpuffer, die Prioritätsleiter der Engine, die Web-API sowie
im Programm-Modus Dateiquellen, Wochenplan, alle Einspielungs-Regeln
(Dateiende, Überlappung, Verspätung, Stumm), Ersatzbetrieb und Upload-Härtung,
sowie der Übersetzer (Pausenschnitt auch unter Rauschen, Filter, Senderwechsel,
Mixer-Abgriff) mit einem Ersatz-Modell statt Whisper.

## Noch offen

- Übersetzer: Originaltext zusätzlich anzeigen (kostet doppelte Rechenzeit),
  Übersetzung ins Deutsche (Whisper kann nur Englisch – z. B. Argos Translate
  dahinter), Zeilen ins Protokoll/als Datei mitschreiben

- Kiwi/UberSDR automatisch aus der öffentlichen Liste nach Region wählen
- Freies Abstimmen auf der Kiwi (Skala als echter Drehknopf)
- OpenWebRX- und WebSDR-Quellen (Twente als Plugin)
- Titelanzeige (ICY-Metadaten) für Streams
- UberSDR PCM-v4-Pfad (derzeit nur Opus); FIPS-Tabelle für lesbare Gebietswahl
- Lokaler VHF-Empfang (RTL-SDR auf 162 MHz) für NWR direkt

## Lizenz

GPL-3.0-or-later (damit der optionale UberSDR-PCM-v4-Dekoder, GPLv3,
wiederverwendet werden darf). Siehe [`LICENSE`](LICENSE).
