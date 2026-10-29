# Beta-Pakete

Vorlagen für die Tester-Pakete. Ein Paket = dieser Ordner + `satellit/`,
`static/` und `LICENSE` aus dem Projekt, als Zip:

- `windows-beta/` → `Satellit-0.4-Beta/` (Doppelklick `Satellit-starten.bat`)
- `mac-beta/` → `Satellit-0.4-Beta-Mac/` (Doppelklick `Satellit starten.command`;
  die `.command`-Dateien müssen ausführbar bleiben, Zip unter Linux/macOS bauen)

Bauen (Version kommt aus `satellit/__init__.py`, Ausgabe nach `dist/`):

```
python packaging/baue_betas.py                       # Kontakt: GitHub-Issues
python packaging/baue_betas.py --kontakt name@example.org --ziel ~/pakete
```

Die Pakete starten mit eingeschaltetem Funk-Teil (Kurzwelle über KiwiSDR,
Übersetzer nachrüstbar); die LIESMICH erklärt, wie man aufs schlichte
Grundgerät umschaltet. Die WebSDR-Quelle ist vorerst Linux-only und daher
nicht in den Startkonfigurationen. Keine `ubersdr_uuid` in der
Startkonfiguration – jede Installation erzeugt ihre eigene.

Dazu kommt der Ordner `beispiele/` (Konfigurationen samt Beschreibung, z. B.
das Altersheim).

Kontakt in den Vorlagen sind die GitHub-Issues. Für die verteilten Beta-Zips
kann dort stattdessen eine E-Mail-Adresse eingetragen werden.
