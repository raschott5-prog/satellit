@echo off
REM ============================================================
REM  Satellit 0.3 Beta - Doppelklick genuegt.
REM  Beim ersten Start wird eine eigene Python-Umgebung im Ordner
REM  .venv angelegt (braucht Internet, 1-3 Minuten).
REM ============================================================
setlocal
cd /d "%~dp0"
title Satellit
if exist "%~dp0ffmpeg\ffmpeg.exe" set "PATH=%~dp0ffmpeg;%PATH%"

if not exist ".venv\Scripts\pythonw.exe" (
    call :einrichten
    if errorlevel 1 goto :fehler
)

REM Startkonfiguration nur beim allerersten Mal hinlegen - nie ueberschreiben
if not exist "%APPDATA%\Satellit\config.json" (
    if not exist "%APPDATA%\Satellit" mkdir "%APPDATA%\Satellit"
    copy /y "start-config.json" "%APPDATA%\Satellit\config.json" >nul
)

start "" ".venv\Scripts\pythonw.exe" -m satellit.tray
exit /b 0


:einrichten
echo.
echo  Erster Start: Satellit richtet sich ein (braucht Internet, 1-3 Minuten) ...
echo.
call :python_suchen
if not defined PY (
    echo  Python 3.10 oder neuer wurde nicht gefunden.
    echo.
    echo  Bitte installieren: https://www.python.org/downloads/
    echo  Beim Installieren den Haken "Add python.exe to PATH" setzen,
    echo  danach diese Datei noch einmal doppelklicken.
    exit /b 1
)
echo  Gefunden: %PY%
%PY% -m venv .venv
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
    rmdir /s /q .venv
    exit /b 1
)
echo  Fertig eingerichtet.
exit /b 0


:python_suchen
set "PY="
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul
    if not errorlevel 1 set "PY=py -3"
)
if defined PY exit /b 0
where python >nul 2>nul
if not errorlevel 1 (
    python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
exit /b 0


:fehler
echo.
echo  Satellit konnte nicht eingerichtet werden (siehe oben).
echo  Bitte ein Foto/Kopie dieses Fensters unter github.com/raschott5-prog/satellit/issues melden.
echo.
pause
exit /b 1
