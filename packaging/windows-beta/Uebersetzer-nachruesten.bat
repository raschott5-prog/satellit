@echo off
REM Ruestet den Uebersetzer (Sprache erkennen -> Englisch) nach.
REM Laedt ca. 150 MB Programmpakete, beim ersten Einschalten in Satellit
REM zusaetzlich das Sprachmodell (ca. 460 MB). Am besten im WLAN.
setlocal
cd /d "%~dp0"
title Satellit - Uebersetzer nachruesten
if not exist ".venv\Scripts\python.exe" (
    echo Bitte zuerst einmal Satellit-starten.bat doppelklicken.
    pause
    exit /b 1
)
echo Installiere den Uebersetzer (faster-whisper) ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q "faster-whisper>=1.0"
if errorlevel 1 (
    echo.
    echo Installation fehlgeschlagen - bitte Foto/Kopie dieses Fensters unter github.com/raschott5-prog/satellit/issues melden.
    pause
    exit /b 1
)
echo.
echo Fertig. Satellit ueber das Tray-Symbol beenden und neu starten,
echo dann in der Oberflaeche den Uebersetzer einschalten.
pause
