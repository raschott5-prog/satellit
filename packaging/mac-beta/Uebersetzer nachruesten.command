#!/bin/bash
# Rüstet den Übersetzer (Sprache erkennen -> Englisch) nach.
# Lädt ca. 150 MB Programmpakete, beim ersten Einschalten in Satellit
# zusätzlich das Sprachmodell (ca. 460 MB).
. "$(dirname "$0")/_gemeinsam.sh"
[ -x .venv/bin/python ] || fehler "Bitte zuerst einmal „Satellit starten.command“ doppelklicken."
echo "  Installiere den Übersetzer (faster-whisper) ..."
.venv/bin/python -m pip install --disable-pip-version-check -q "faster-whisper>=1.0" \
    || fehler "Installation fehlgeschlagen."
echo
echo "  Fertig. Satellit über das Symbol in der Menüleiste beenden und neu"
echo "  starten, dann in der Oberfläche den Übersetzer einschalten."
read -r -p "  Eingabetaste zum Schließen ... " _
