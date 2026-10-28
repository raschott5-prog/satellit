#!/bin/bash
# Satellit 0.3 Beta für macOS – Doppelklick genügt.
# Beim ersten Start wird eine eigene Python-Umgebung im Ordner .venv
# angelegt (braucht Internet, 1–3 Minuten).
. "$(dirname "$0")/_gemeinsam.sh"

if [ ! -x .venv/bin/python ]; then
    echo
    echo "  Erster Start: Satellit richtet sich ein (braucht Internet, 1–3 Minuten) ..."
    echo
    if ! python_suchen; then
        echo "  Python 3.10 oder neuer wurde nicht gefunden."
        echo "  Bitte installieren: https://www.python.org/downloads/macos/"
        echo "  (den „macOS 64-bit universal2 installer“), danach diese Datei"
        echo "  noch einmal doppelklicken."
        open "https://www.python.org/downloads/macos/"
        read -r -p "  Eingabetaste zum Schließen ... " _
        exit 1
    fi
    echo "  Gefunden: $PY"
    "$PY" -m venv .venv || fehler "Die Python-Umgebung konnte nicht angelegt werden."
    if ! .venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt; then
        rm -rf .venv
        fehler "Die Programmpakete konnten nicht installiert werden."
    fi
    echo "  Fertig eingerichtet."
fi

startkonfiguration
zertifikate
nohup .venv/bin/python -m satellit.tray > "$CONF_DIR/satellit.log" 2>&1 &
disown
echo
echo "  Satellit läuft – oben in der Menüleiste erscheint ein Satellit-Symbol,"
echo "  die Oberfläche öffnet sich gleich im Browser."
echo "  Dieses Fenster kann geschlossen werden."
echo
