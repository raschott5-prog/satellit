@echo off
REM Startet Satellit MIT Konsolenfenster: alle Meldungen sind sichtbar.
REM Fuer Fehlerberichte an die Entwickler. Beenden mit Strg+C.
setlocal
cd /d "%~dp0"
title Satellit (Fehlersuche)
if exist "%~dp0ffmpeg\ffmpeg.exe" set "PATH=%~dp0ffmpeg;%PATH%"
if not exist ".venv\Scripts\python.exe" (
    echo Bitte zuerst einmal Satellit-starten.bat doppelklicken.
    pause
    exit /b 1
)
if not exist "%APPDATA%\Satellit\config.json" (
    if not exist "%APPDATA%\Satellit" mkdir "%APPDATA%\Satellit"
    copy /y "start-config.json" "%APPDATA%\Satellit\config.json" >nul
)
".venv\Scripts\python.exe" -m satellit
pause
