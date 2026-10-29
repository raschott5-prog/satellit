# SAME als Wache für Satellit – Notizen (Stand 14.10.2026)

SAME (Specific Area Message Encoding) ist die digitale Kopfzeile vor
EAS- und NOAA-Weather-Radio-Durchsagen in den USA. Rein maschinenlesbar –
also eine natürliche Erweiterung der Wache: nicht S-Meter-Aktivität raten,
sondern den Header dekodieren und gezielt auf **Ereignis + Gebiet** reagieren.

## Signal

- AFSK, **520,833 Bit/s** (520 5/6). Mark (1) = 2083,3 Hz, Space (0) = 1562,5 Hz
  – das sind 4 bzw. 3 Schwingungen pro Bit. Bei 48 kHz fällt das sauber auf
  92,16 Samples/Bit; Bittakt aus der Präambel rückgewinnen.
- 8-Bit-ASCII, **LSB zuerst**, Bit 8 = 0.
- Der Kopf wird **dreimal** gesendet, ~1 s Pause dazwischen → Dekoder nimmt
  Best-of-3 (zeichen- oder bitweise Mehrheit), daher auch bei verrauschtem
  Empfang robust.

## Rahmen

```
[16× 0xAB Präambel] ZCZC-ORG-EEE-PSSCCC-PSSCCC…+TTTT-JJJHHMM-LLLLLLLL-
```

- `ORG` Absender: `WXR` (NWS), `CIV` (Behörde), `EAS` (Sender), `PEP` (national).
- `EEE` Ereignis: `TOR` Tornadowarnung, `SVR` schweres Gewitter, `FFW` Sturzflut,
  `EAN` nationaler Notfall, `RWT`/`RMT` Wochen-/Monatstest …
- `PSSCCC` Gebiet (FIPS), bis zu 31×: P = Kreisteil (0 = ganz), SS = Bundesstaat,
  CCC = County. `000000` = ganze USA.
- `+TTTT` Gültigkeit (hhmm), `JJJHHMM` Ausgabezeit UTC (julianischer Tag + Uhrzeit).
- `LLLLLLLL` Senderkennung (8 Zeichen, mit Leerzeichen aufgefüllt).

Danach optional Aufmerksamkeitston (NWR 1050 Hz; EAS-Zweiton 853+960 Hz),
dann die Sprachdurchsage, am Ende **EOM**: Präambel + `NNNN`, ebenfalls 3×.

## Woher das Signal kommt

- NWR liegt auf **162 MHz (VHF)** – weder Kiwi noch UberSDR (beide ≤ 30 MHz)
  empfangen das. Für die Web-Quellen also raus.
- Realistisch: **Internet-Streams von NWR** (sauber, zweckgebaut) oder
  EAS-Kopfzeilen auf **MW/UKW-Sendern**, die ohnehin schon als Quelle laufen.
- **Keinen** Kiwi-/UberSDR-Platz dauerhaft nur für den seltenen SAME-Fall
  blockieren – das widerspricht der Fairness-Regel. SAME bevorzugt aus
  NWR-Streams dekodieren; MW/UKW nur nebenbei, wenn der Sender sowieso läuft.

## Folgerungen für Satellit

- Eigenes Modul `satellit/funk/same.py` (bis 0.3: `satellit/same.py`): reiner Dekoder, Eingang 48-kHz-PCM eines
  beliebigen Decks bzw. einer Quelle, Ausgang geparste Header-Objekte mit
  Konfidenz. Kein eigener Netz- oder Audiozugriff – hängt sich an vorhandene PCM.
- Als Geschwister zur Wache in die Engine hängen (`watcher.py` bleibt S-Meter,
  `same.py` liefert diskrete Ereignisse). Vorteil gegenüber der S-Meter-Wache:
  SAME hat **klaren Anfang (Header) und Ende (EOM / `+TTTT`)** – Übernahmedauer
  = bis EOM oder Gültigkeit abgelaufen, kein 2-aus-10-Raten.
- Konfiguration: Liste eigener FIPS-Codes (Gebiet) + Ereignisfilter. Reaktion
  nach Schwere: Warnungen → umschalten + Durchsage; Beobachtungen → nur Hinweis;
  Tests → protokollieren, optional Gong.
- Prioritätsleiter: `EAN` schlägt Fahrplan, Wache und Handauswahl. Sonstige
  Warnungen wie die Wache (nur wenn kein wichtigerer Grund aktiv).
- Übergänge: bei echter Warnung kürzer überblenden als die 15-s-Weckrampe – der
  Aufmerksamkeitston ist ohnehin das Signal. Equal-Power bleibt, nur schneller.
- Entprellen: gleicher Header (ORG + EEE + Gebiet + `JJJHHMM`) auf mehreren
  Quellen nur **einmal** auslösen.

## Umsetzung in 0.1 (Stand jetzt)

Umgesetzt wie oben: `same.py` als reiner Dekoder (`SAMEDecoder`/`SAMEStream`),
in der Engine als eigener Thread neben der Wache, Prioritätsleiter
`EAN › Warnung(Gebiet) › Wache › Hand/Fahrplan › Schlummern`, Entprellen über
`dedup_key`, Test-Einspeisung über die Oberfläche bzw. `POST /api/same/test`.
Generator (`SAMEGenerator`, `tests/fake_same.py`) erzeugt gültige/verrauschte
Bursts; der Round-Trip inkl. Best-of-3 ist Teil der Testsuite.

## Noch offen

- Lokaler VHF-Empfang (RTL-SDR auf 162,400–162,550 MHz) als eigene Quelle, falls
  jemand NWR direkt hören will – eigenes Hardware-Thema, später.
- FIPS-Tabelle (State/County ↔ Code) für eine lesbare Gebietsauswahl in der
  Oberfläche.
- Header als Klartext hörbar ansagen (TTS) für Barrierefreiheit?
