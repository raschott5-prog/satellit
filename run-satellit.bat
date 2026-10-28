@echo off
REM ============================================================
REM  Satellit starten (Windows)
REM  Doppelklick genügt. Nutzt die mitgelieferte Python-Umgebung,
REM  sonst das System-Python. ffmpeg aus dem Unterordner ffmpeg\
REM  wird automatisch gefunden.
REM ============================================================
setlocal
cd /d "%~dp0"

REM ffmpeg aus mitgeliefertem Ordner in den PATH holen (falls vorhanden)
if exist "%~dp0ffmpeg\ffmpeg.exe" set "PATH=%~dp0ffmpeg;%PATH%"

REM gebautes EXE bevorzugen, sonst Python-Modul
if exist "%~dp0Satellit.exe" (
    start "" "%~dp0Satellit.exe"
    goto :eof
)

where py >nul 2>nul
if %errorlevel%==0 (
    py -m satellit.tray
) else (
    python -m satellit.tray
)
endlocal
