# Gemeinsame Teile der .command-Dateien (wird mit "." eingebunden).
cd "$(dirname "$0")" || exit 1
CONF_DIR="$HOME/Library/Application Support/Satellit"
MAIL="https://github.com/raschott5-prog/satellit/issues"
# Homebrew-ffmpeg bevorzugen, falls vorhanden (aus dem Finder fehlt sonst der PATH)
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

python_suchen() {
    # /usr/bin/python3 bewusst nicht: ohne Entwicklerwerkzeuge öffnet macOS
    # dafür einen Installationsdialog, und die Version ist meist zu alt.
    for py in /Library/Frameworks/Python.framework/Versions/3.*/bin/python3 \
              /opt/homebrew/bin/python3 /usr/local/bin/python3; do
        [ -x "$py" ] || continue
        if "$py" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
            PY="$py"
        fi
    done
    [ -n "$PY" ]
}

zertifikate() {
    # Python von python.org kennt ohne "Install Certificates" keine
    # Zertifikate – die von certifi nehmen (für wss:// und https://).
    SSL_CERT_FILE="$(.venv/bin/python -c 'import certifi; print(certifi.where())' 2>/dev/null)"
    [ -n "$SSL_CERT_FILE" ] && export SSL_CERT_FILE
}

startkonfiguration() {
    # nur beim allerersten Mal hinlegen – nie überschreiben
    if [ ! -f "$CONF_DIR/config.json" ]; then
        mkdir -p "$CONF_DIR" && cp start-config.json "$CONF_DIR/config.json"
    fi
}

fehler() {
    echo
    echo "  $1"
    echo "  Bitte den Inhalt dieses Fensters (oder ein Foto) als Meldung unter $MAIL einstellen."
    echo
    read -r -p "  Eingabetaste zum Schließen ... " _
    exit 1
}
