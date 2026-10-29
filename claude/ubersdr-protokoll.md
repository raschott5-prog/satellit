# UberSDR als Quelle für Satellit – Notizen (Stand 08.10.2026)

Repo: https://github.com/madpsy/ka9q_ubersdr (GPLv3, Go-Server auf ka9q-radio, RX-888 MKII)
Verzeichnis: https://instances.ubersdr.org/api/instances (54 Instanzen am 08.10.2026)
Referenz-Client: `clients/python/radio_client.py`

## Ablauf einer Audio-Verbindung

1. `GET /api/description` – Empfängername, Frequenzbereich, Default-Frequenz/-Modus
2. `POST /connection` mit `{"user_session_id": "<uuid>"}` → `allowed`, `reason`, `max_session_time`, `client_ip`
3. Websocket `ws(s)://host:port/ws?frequency=<Hz>&mode=am&user_session_id=<uuid>&bandwidthLow=-5000&bandwidthHigh=5000&format=opus&version=4`
4. Nach Connect `{"type":"get_status"}` senden → `status` mit `sessionId`
5. Keepalive: `{"type":"ping"}` alle ~10 s → `pong`
6. Umstimmen ohne neue Verbindung: `{"type":"tune", ...}`
7. Binärframes: Opus (`format=opus`) oder PCM v4 (Magic `0x344D4350`, adaptiver Prädiktor + Rice, bit-exakt zu dekodieren)

Modi: usb, lsb, cwu, cwl, am, sam, fm, nfm (+ IQ-Modi)

## Grenzen (Server-Defaults, pro Instanz einstellbar)

- `max_session_time: 3600` – danach Kick; die UUID bleibt **1 Stunde gesperrt**
- `max_sessions_ip: 2` – max. 2 UUIDs pro IP
- `session_timeout: 0` – kein Idle-Kick (Default)
- `max_daily_time_per_ip` – optional, rollierend 24 h
- Beobachtet im Verzeichnis: `max_clients` 20–60, `max_session_time` 0 / 3600 / 7200

## Folgerungen für Satellit

- **Eine feste UUID pro Installation.** Keine UUID-Rotation, um Sitzungsgrenzen zu umgehen – das unterläuft genau die Fairness-Regel des Betreibers.
- `max_session_time` aus `/connection` lesen und **vor Ablauf weich überblenden**: auf eine andere Instanz, den Stream-Fallback oder einen Kiwi. Wechsel auf eine *andere* Instanz ist legitim, neue UUID auf derselben nicht.
- Instanzen mit `max_session_time: 0` für lange Fahrplan-Blöcke bevorzugen.
- `format=opus` zuerst (libopus/opuslib), PCM v4 nur, falls nötig – `pcm_v4.py` ist GPLv3 und wiederverwendbar, wenn Satellit GPLv3 wird.
- User-Agent `SatellitRadio` setzen.
- Server bietet zusätzlich KiwiSDR-Emulation (Port 8073) und WebSDR-Emulation – auf öffentlichen Instanzen aber nicht garantiert erreichbar.

## Nebenfund

`static/oldradio/` im Repo: Röhrenradio-Oberfläche mit Plugin-System (`radios/<id>/config.json`, `template.html`, `style.css`) und einer **Grundig**-Vorlage (nur MW 600–2000 kHz, nur AM). Gute Vorlage für die Skala von Satellit.

## Umsetzung in 0.1 (Stand jetzt)

`satellit/funk/ubersdr.py` (bis 0.3: `satellit/sources/ubersdr.py`): `/connection` → Websocket (`format=opus&version=4`)
→ `get_status`, Ping-Keepalive, Opus-Dekodierung (opuslib). Feste UUID pro
Installation (in `config.json`), `needs_handover` 30 s vor Sitzungsende statt
UUID-Rotation. PCM-v4-Pfad vorgesehen, aber noch nicht implementiert.
