#!/bin/bash
# Startet Satellit MIT sichtbaren Meldungen – für Fehlerberichte.
# Beenden mit Ctrl+C oder durch Schließen des Fensters.
. "$(dirname "$0")/_gemeinsam.sh"
[ -x .venv/bin/python ] || fehler "Bitte zuerst einmal „Satellit starten.command“ doppelklicken."
startkonfiguration
zertifikate
echo "  macOS $(sw_vers -productVersion) · $(uname -m) · $(.venv/bin/python --version)"
.venv/bin/python -m satellit
read -r -p "  Eingabetaste zum Schließen ... " _
