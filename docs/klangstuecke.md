# Mitgelieferte Klangstücke

Satellit liefert keine fremde Musik mit. Damit die Beispiele trotzdem sofort
klingen, liegen ein paar **eigene Kompositionen** bei – synthetisch erzeugt
mit kleinen Python-Skripten (nur numpy), frei verwendbar (CC0). Die MP3s
liegen in `beispiele/media/`, die Skripte daneben in `beispiele/`.

| Stück | Datei | Länge | Stil | Gedacht für |
|---|---|---|---|---|
| Kaffeezeit | `kaffeezeit.mp3` | 0:40 | kleiner Walzer, Violine | Signal-Lied ([Altersheim](beispiel-altersheim.md)) |
| Good Morning | `good-morning.mp3` | 1:12 | Country-Pop der 70er, Pfiff | Signal-Lied |
| Good Morning (lang) | `good-morning-lang.mp3` | 11:44 | wird von selbst voller | Wecken über 10 Minuten ([Guten Morgen](beispiel-guten-morgen.md)) |
| Fernzug | `fernzug.mp3` | 4:22 | Metall, Elektronik, Züge | Programm, Ausstellung, Raum-Loop |

## Fernzug

Eine alte Bahnhofsuhr gibt den Takt: Tick-Tack jede Sekunde, und jede volle
Minute der Klack des springenden Minutenzeigers. Jeder Klack schaltet das
Stück eine Stufe weiter:

| Zeit | Was passiert |
|---|---|
| 0:00 | nur die Uhr |
| 0:08 | elektronischer Puls |
| 1:08 | Hämmern auf Metall – Amboss und Rohr, maschinell im Uhrtakt |
| 2:08 | elektronische Trommeln, ein Zug rollt aus der Ferne heran |
| ~2:38 | der Zug fährt vorbei: Schienenstöße im Tempo, Signalhorn mit Doppler-Effekt, links → rechts |
| 3:08 | dichter, zweiter Zug aus der Gegenrichtung |
| 4:08 | alles bricht mit dem letzten Klack ab – der Zug verschwindet, die Uhr tickt weiter |

Die Züge fahren so schnell, dass jeder Wagen (26 m) in genau einer
Uhr-Sekunde vorbeizieht (≈ 94 km/h) – die Schienenstöße rattern im Takt.
Die Uhr bleibt trocken und nah, alles andere hat Raumhall; so ist sie auch
im lautesten Teil zu hören.

Passt z. B. als Raum-Loop in einer Ausstellung (Eisenbahn, Industrie,
Elektronische Musik) oder einfach als Programmpunkt.

Der Stil erinnert an die elektronische Musik der 70er mit Metallklängen und
Zügen. Es ist bewusst **nichts gesampelt**: Um genau so einen Metall-Rhythmus
ging der Rechtsstreit „Metall auf Metall“ (Kraftwerk gegen Pelham, bis zum
EuGH 2019) – auch kurze, wiedererkennbare Samples brauchen eine Erlaubnis.
Hier ist jeder Schlag selbst erzeugt.

## Neu erzeugen

```
python beispiele/kaffeezeit.py kaffeezeit.wav
python beispiele/goodmorning.py good-morning.wav
python beispiele/goodmorning.py good-morning-lang.wav lang
python beispiele/fernzug.py fernzug.wav        # nutzt uhrwerk.py und drumsolo.py
python beispiele/uhrwerk.py uhrwerk.wav        # nur Uhr und Schlagzeug
python beispiele/drumsolo.py drumsolo.wav 3.7  # Schlagzeug, sanft bis hart
```

Tempo, Länge, Klang und Lautstärke stehen als Konstanten oben in den
Skripten. Die Ergebnisse sind reproduzierbar (feste Zufallszahlen).
