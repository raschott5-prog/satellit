#!/bin/sh
# Satellit unter Linux starten (Entwicklerstand, venv in .venv neben diesem Skript)
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt || exit 1
fi
exec .venv/bin/python -m satellit "$@"
