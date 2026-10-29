# Beispiel: Guten Morgen – zehn Minuten sanft wecken

Kein Handywecker, der um 6:30 schlagartig losdudelt: Satellit blendet über
**zehn Minuten** von ganz leise auf normal ein. Dafür braucht es Musik, die
lang genug ist und **von selbst voller wird** – sonst hört man im Halbschlaf
dreimal dasselbe Stück in Schleife.

Die fertige Konfiguration liegt in [`beispiele/guten-morgen.json`](../beispiele/guten-morgen.json):
werktags um 6:30, am Wochenende um 8:30, danach die eigene Musik, abends
eine Viertelstunde ausblenden.

## „Good Morning“ – ein Weckstück im Country-Pop der frühen 70er

Mitgeliefert, eigene Komposition, frei verwendbar (CC0), in zwei Fassungen:

| Datei | Länge | Wofür |
|---|---|---|
| `beispiele/media/good-morning-lang.mp3` | 11:44 | zum Wecken mit langem Einblenden |
| `beispiele/media/good-morning.mp3` | 1:12 | als Signal-Lied (wie „Kaffeezeit“) |

Die lange Fassung ist so gebaut, dass sie zum Einblenden passt:

| Zeit | Was passiert |
|---|---|
| 0:00 | nur Gitarre, gezupft – Satellit ist hier noch fast unhörbar |
| ab 0:45 | Mundharmonika, dann Steel-Gitarre und Streicher |
| ab 3:30 | Besen auf der Snare, wechselnde Soli, ein Zwischenthema in Moll |
| ~8:15 | Steel-Gitarre gleitet hoch – Rückung von G- nach A-Dur |
| ~10:50 | **Finale: die Melodie wird gepfiffen**, volle Besetzung, etwa 4 dB lauter |
| 11:44 | Schlussakkord |

Bei einem Weck-Eintrag mit `"fade": 600` ist Satellit nach zehn Minuten bei
voller Lautstärke – das Finale kommt also, wenn man wach sein sollte.

Erzeugt mit [`beispiele/goodmorning.py`](../beispiele/goodmorning.py) (nur numpy):

```
python beispiele/goodmorning.py good-morning.wav             # kurze Fassung
python beispiele/goodmorning.py good-morning-lang.wav lang   # lange Fassung
```

Der Stil erinnert an amerikanische Morgen- und Reiselieder der 70er; die
Melodie ist neu. Bekannte Vorbilder wie „City of New Orleans“ („Good
morning America, how are you?“) oder „L.A. International Airport“ sind
urheberrechtlich geschützt und deshalb nicht dabei.

## Einrichten

1. `beispiele/guten-morgen.json` als Konfiguration verwenden (wie beim
   [Altersheim](beispiel-altersheim.md) beschrieben).
2. `beispiele/media/good-morning-lang.mp3` in den Medienordner kopieren
   und eigene Musik in den Unterordner `musik` legen.
3. Der Rechner darf zur Weckzeit nicht im Ruhezustand sein.
