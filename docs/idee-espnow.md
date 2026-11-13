# Idee: ESP32-Zimmerboxen mit ESP-NOW und gemeinsamer Uhr

Stand: Idee, nichts gebaut. Gedacht fürs Grundgerät, z. B. im Altersheim
(siehe [`beispiel-altersheim.md`](beispiel-altersheim.md)).

## Grundgedanke

Satellit läuft an einer Stelle im Haus. In den Zimmern, Fluren und im
Gemeinschaftsraum stehen kleine Boxen: ein ESP32, ein I2S-Verstärker (z. B.
MAX98357), ein Lautsprecher, eine SD-Karte – zusammen um die 10 €.

Die Boxen bekommen **keinen Dauerstrom aus dem WLAN des Hauses**. Netzlast
entsteht nur, wenn es nötig ist:

| Was | Wie | Last |
|---|---|---|
| Uhrzeit | ein Gateway holt sie per NTP und verteilt sie per ESP-NOW | ein paar Byte pro Minute |
| Programm, Signale | Befehle per ESP-NOW („Kaffeezeit“, „Gong“, „Nachtruhe“, „leiser“) | winzige Pakete |
| Klänge | liegen auf der SD-Karte der Box | keine im Betrieb |
| Neue Klänge, neuer Plan | nur bei Bedarf, nachts oder auf Knopfdruck | kurz, geplant |

## Warum eine gemeinsame Uhr

Mit einer gemeinsamen Uhr braucht ein Signal-Lied keinen Live-Ton:
Jede Box kennt den Plan und spielt „Kaffeezeit“ selbst um **16:00:00** – im
ganzen Haus gleichzeitig, auch auf dem Flur, wo man mehrere Boxen hört.
Der ESP-NOW-Befehl ist dann nur noch Bestätigung und Auslöser für Dinge
außerhalb des Plans. Geht ein Paket verloren, spielt die Box trotzdem
pünktlich.

- **Nur das Gateway braucht das WLAN des Hauses** (oder gar keins: Satellit
  gibt die Uhrzeit über USB mit). Ein Gerät im Heimnetz statt dreißig – das
  vereinfacht auch das Gespräch mit der Haus-IT, und Gäste-WLANs mit
  Anmeldeseite oder Client-Isolation sind kein Hindernis.
- Uhrzeit per ESP-NOW-Broadcast mit Laufzeitausgleich: Genauigkeit im
  Bereich weniger Millisekunden, mehr als genug für Räume und Flure.
- Fällt das Gateway aus, laufen die Boxen mit ihrer letzten Uhrzeit und ihrem
  Plan weiter (Drift eines ESP32 ohne Abgleich: grob Sekunden pro Tag).

## Später: Live-Ton

Das laufende Programm live in die Zimmer ist möglich, aber anspruchsvoller:
ESP-NOW schafft praktisch 0,5–1 Mbit/s, Mono mit ADPCM braucht etwa
128 kbit/s; Broadcast-Pakete werden nicht bestätigt (Redundanz/FEC nötig);
mit der gemeinsamen Uhr können Pakete einen Abspielzeitpunkt tragen, dann
klingen alle Boxen zeitgleich. In Satellit wäre das eine weitere Ausgabe:
PCM → ADPCM → USB (921600 Baud reichen) → Gateway → ESP-NOW.

## Grenzen

- **Kein Notruf, kein Sicherheitssystem.** Komfort und Tagesstruktur, nicht
  mehr.
- ESP-NOW teilt sich 2,4 GHz mit dem WLAN des Hauses. Ist das Gateway im
  WLAN, funkt ESP-NOW auf dessen Kanal – das passt, muss aber bei der
  Einrichtung bedacht werden.
- Ergänzt die Auracast-Idee: ESP-NOW für Zimmerlautsprecher, Auracast für
  Hörgeräte.

## Erster Versuch

Zwei ESP32 (Gateway + eine Box): Gateway nimmt Uhrzeit und Befehle von
Satellit über USB an und sendet sie per ESP-NOW; die Box spielt einen Gong
von der SD-Karte zur geplanten Sekunde. Daran sieht man, wie genau zwei Boxen
gleichzeitig spielen.
