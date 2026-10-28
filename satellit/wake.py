"""Rechner aus dem Standby wecken.

Für den Hörfahrplan (z. B. 6:30 Weckprogramm) kann Satellit den Rechner
rechtzeitig aus dem Energiesparmodus holen:

* Windows: eine geplante Aufgabe mit Wake-Timer (``<WakeToRun>true``),
  registriert über ``schtasks /Create /XML``.
* Linux:   ``rtcwake`` (RTC-Alarm; Root nötig). Nur Vorbereitung/Kommando,
  kein automatisches Suspendieren.

Bewusst eigenständig und ohne Abhängigkeiten – ein Hilfswerkzeug, das man
einmal einrichtet.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta

TASK_NAME = "SatellitWecken"


def _next_occurrence(hhmm: str) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    now = datetime.now()
    t = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if t <= now:
        t += timedelta(days=1)
    return t


# --- Windows ---------------------------------------------------------------
def _win_task_xml(when: datetime, command: str) -> str:
    start = when.strftime("%Y-%m-%dT%H:%M:%S")
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Satellit: Rechner wecken und starten</Description></RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{start}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Settings>
    <WakeToRun>true</WakeToRun>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
  </Settings>
  <Actions><Exec><Command>{command}</Command></Exec></Actions>
</Task>"""


def setup_windows(hhmm: str, command: str | None = None) -> bool:
    """Legt/aktualisiert die Weck-Aufgabe an. ``hhmm`` z. B. "06:25"."""
    if not sys.platform.startswith("win"):
        raise RuntimeError("setup_windows nur unter Windows")
    when = _next_occurrence(hhmm)
    if command is None:
        command = f'"{sys.executable}" -m satellit'
    xml = _win_task_xml(when, command)
    fd, path = tempfile.mkstemp(suffix=".xml")
    try:
        # Task Scheduler erwartet UTF-16
        with os.fdopen(fd, "w", encoding="utf-16") as fh:
            fh.write(xml)
        res = subprocess.run(
            ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", path, "/F"],
            capture_output=True, text=True)
        if res.returncode != 0:
            print("schtasks:", res.stderr.strip())
            return False
        print(f"Weck-Aufgabe '{TASK_NAME}' für {when:%d.%m. %H:%M} eingerichtet.")
        return True
    finally:
        os.unlink(path)


def remove_windows() -> bool:
    res = subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
                         capture_output=True, text=True)
    return res.returncode == 0


# --- Linux -----------------------------------------------------------------
def rtcwake_command(hhmm: str, mode: str = "mem") -> list[str]:
    """Baut den ``rtcwake``-Aufruf (zum manuellen Ausführen vorm Suspend)."""
    when = _next_occurrence(hhmm)
    return ["sudo", "rtcwake", "-m", mode, "-l", "-t", str(int(when.timestamp()))]


def setup_linux(hhmm: str) -> list[str]:
    cmd = rtcwake_command(hhmm)
    print("Vor dem Suspend ausführen (RTC-Weckalarm setzen):")
    print("  " + " ".join(cmd))
    return cmd


# --- CLI -------------------------------------------------------------------
def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="satellit.wake",
                                description="Weck-Timer für den Hörfahrplan")
    p.add_argument("time", nargs="?", default="06:25", help="Weckzeit HH:MM")
    p.add_argument("--remove", action="store_true", help="Weck-Aufgabe entfernen (Windows)")
    args = p.parse_args(argv)
    if sys.platform.startswith("win"):
        return 0 if (remove_windows() if args.remove else setup_windows(args.time)) else 1
    setup_linux(args.time)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
