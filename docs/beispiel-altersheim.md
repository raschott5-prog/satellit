# Beispiel: Altersheim – die Bewohner machen ihr Programm

Satellit als Grundgerät (ohne Funk-Teil) im Gemeinschaftsraum eines Alters-
oder Pflegeheims. Die Idee:

- **Die Bewohner bestimmen selbst**, welche Musik wann läuft – demokratisch,
  z. B. einmal im Monat im Bewohnerrat oder per Wunschzettel.
- **Keine Ansagen.** Nur Programmwechsel – Schlager am Vormittag, leise
  Klassik zum Essen, Tanzcafé am Nachmittag.
- **Lieder sind die Signale.** Um 16:00 Uhr läuft ein kleiner Walzer –
  und alle wissen: Jetzt gibt es Kaffee. Eine Art innerer Wecker, freundlicher
  als jeder Gong und jede Durchsage.

Die fertige Konfiguration liegt in [`beispiele/altersheim.json`](../beispiele/altersheim.json).

## Der Tag im Beispiel

| Zeit | Was läuft | Wie |
|---|---|---|
| 07:00 | Guten-Morgen-Musik | eine halbe Stunde lang von ganz leise auf normal |
| 08:30 | Schlager (sonntags Kirchenlieder) | sanfter Wechsel |
| 10:30 | Volksmusik (Mo/Mi/Fr) oder Operette & Wienerlied (Di/Do/Sa/So) | sanfter Wechsel |
| 11:55 | *Lied zum Mittagessen* | Signal-Lied (im Beispiel ausgeschaltet – zum Ausprobieren) |
| 12:00 | Leise Klassik | zum Mittagessen |
| 13:00 | Mittagsruhe | über 5 Minuten ausblenden |
| 14:30 | Tanzcafé | über 10 Minuten wieder einblenden |
| **16:00** | **„Kaffeezeit“** | **Signal-Lied: Musik setzt aus, das Lied läuft, danach weiter Tanzcafé** |
| 18:00 | Leise Klassik | zum Abendbrot |
| 19:00 | Abendlieder | |
| 20:30 | Nachtruhe | eine halbe Stunde lang ausblenden |

Signal-Lieder sind Einspielungen mit `"mode": "replace"`: Die Musik wird
ganz weggeblendet, das Lied läuft **bis zu seinem Ende** (nie abgeschnitten),
dann kommt das Programm sanft zurück – wenn inzwischen ein Wechsel fällig war,
schon das neue.

## Das Signal-Lied „Kaffeezeit“

Mitgeliefert: **„Kaffeezeit“**, ein kleiner Walzer in D-Dur für Violine mit
gezupfter Begleitung, rund 40 Sekunden – eine eigene Komposition für
Satellit, frei verwendbar (CC0). Erzeugt mit
[`beispiele/kaffeezeit.py`](../beispiele/kaffeezeit.py) (nur numpy), wer
Tempo oder Klang ändern möchte: `python beispiele/kaffeezeit.py kaffeezeit.wav`.

Natürlich kann jedes andere Lied das Signal sein – etwa der Klassiker
„Der Kaffee ist fertig“ von Peter Cornelius. Der ist urheberrechtlich
geschützt und gehört deshalb nicht zum Beispiel; mit Lizenz für den
Gemeinschaftsraum (siehe unten) einfach die eigene Datei eintragen.

## Demokratisch planen

Satellit stimmt nicht selbst ab – das machen die Bewohner, so wie sie es
gewohnt sind. Ein bewährter Ablauf:

1. **Wunschzettel** im Gemeinschaftsraum: Welche Musik zu welcher Tageszeit?
   Welches Lied soll zum Kaffee, zum Mittagessen, zum Abend laufen?
2. **Abstimmung** im Bewohnerrat oder per Strichliste, z. B. einmal im Monat.
3. Eine Pflegekraft oder ein Angehöriger trägt das Ergebnis ein: in der
   Programm-Ansicht ist der Wochenplan zu sehen, Einträge lassen sich mit
   einem Klick an- und ausschalten oder „heute aussetzen“.
4. Die Musik kommt in die passenden Ordner (Schlager, Volksmusik …) –
   Bewohner und Angehörige bringen gern ihre Lieblingsstücke mit.

Ideen für weitere Signal-Lieder: ein Morgenlied zum Frühstück, ein Lied
zum Abendbrot, ein Geburtstagslied (als Einspielung nur an dem Tag:
`"skip_date"` bzw. per Hand „Im Raum“ abspielen).

## Einrichten

1. Satellit installieren (Grundgerät genügt: `requirements.txt`).
2. `beispiele/altersheim.json` als Konfiguration verwenden – entweder an die
   übliche Stelle kopieren (Linux `~/.config/satellit/config.json`,
   Windows `%APPDATA%\Satellit\config.json`, macOS
   `~/Library/Application Support/Satellit/config.json`) oder beim Start
   angeben: `python -m satellit --config beispiele/altersheim.json`.
3. Im Medienordner (neben der `config.json`, Unterordner `media/`) die Ordner
   `morgen`, `schlager`, `volksmusik`, `operette`, `klassik`, `tanzcafe`,
   `abend`, `kirche` und `musik` anlegen und mit Musik füllen.
4. Das Signal-Lied `beispiele/media/kaffeezeit.mp3` in den Medienordner
   kopieren – oder in der Programm-Ansicht hochladen. Für weitere
   Signal-Lieder (z. B. `mittagessen.mp3`) genauso.
   Fehlt eine Datei, zeigt die Oberfläche das am Planeintrag an.
5. Die Oberfläche ist im Heimnetz erreichbar (`"listen": "0.0.0.0"`), z. B.
   vom Tablet im Stationszimmer: `http://<rechner>:8080`. Wer das nicht
   möchte, setzt `"listen": "127.0.0.1"`.

Fällt ein Ordner aus (leer, Stick abgezogen), spielt „Allerlei“ aus dem
Ordner `musik` weiter. Internet braucht das Beispiel nicht.

## Musikrechte

Musik im Gemeinschaftsraum gilt in der Regel als **öffentliche Wiedergabe**
und braucht eine Lizenz der Verwertungsgesellschaft (Deutschland: GEMA,
Österreich: AKM, Schweiz: SUISA) – viele Heime haben schon eine. Die Dateien
selbst müssen rechtmäßig erworben sein. Satellit liefert keine Musik mit.
