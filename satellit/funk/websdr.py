"""WebSDR-Quelle (PA3FWM-WebSDR, z. B. Enschede/Twente, Hack Green).

Der WebSDR-Ton ist ein eigenes Format, dessen Client-Code PA3FWM nur
unverändert im Original-Client erlaubt – kein Nachbau, kein Reverse
Engineering. Satellit nutzt deshalb **den Original-Client selbst**:

1. eine eigene virtuelle Soundkarte (PulseAudio/PipeWire ``null-sink``),
2. ein unsichtbarer Chromium (``--headless=new``) öffnet die WebSDR-Seite
   und spielt nur in diese Senke – die Lautsprecher bleiben unberührt,
3. Frequenz und Modus per DevTools-Protokoll (``setfreqtune``/``set_mode``),
   denn manche WebSDR überschreiben den Modus aus ``?tune=`` mit dem
   Bandstandard (Hack Green stellte 5505 kHz auf LSB),
4. ``parec`` liest den Monitor der Senke als 48 kHz Stereo float32.

Vorerst nur Linux (``pactl``, ``parec``, Chromium). Die Serverliste von
websdr.org wird bewusst nicht eingebunden (Weiterverwendung nur mit
Erlaubnis) – Empfänger trägt man von Hand als Sender ein.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request

import numpy as np

from ..audio import CHANNELS, SAMPLE_RATE
from ..sources.base import Source

MODES = ("usb", "lsb", "am", "fm", "cw")
BROWSERS = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")
PAGE_TIMEOUT = 30.0      # s bis der Client geladen ist
CHUNK = 4800             # Frames pro Lesen (0,1 s)


def find_browser(preferred: str = "") -> str | None:
    for name in ((preferred,) if preferred else ()) + BROWSERS:
        path = shutil.which(name)
        if path:
            return path
    return None


def missing_tools(browser: str = "") -> list[str]:
    """Was fehlt für eine WebSDR-Quelle auf diesem Rechner? Leer = alles da."""
    if not sys.platform.startswith("linux"):
        return ["Linux (WebSDR-Quelle vorerst nur unter Linux)"]
    out = [t for t in ("pactl", "parec") if shutil.which(t) is None]
    if find_browser(browser) is None:
        out.append("Chromium")
    return out


def page_url(url: str, freq_khz: float, mode: str) -> str:
    """WebSDR-Adresse mit ``?tune=`` – erster Versuch, wird danach per
    DevTools bestätigt."""
    base = url if "://" in url else "http://" + url
    if not base.endswith("/"):
        base += "/"
    return f"{base}?tune={tune_arg(freq_khz, mode)}"


def tune_arg(freq_khz: float, mode: str) -> str:
    f = float(freq_khz)
    return f"{f:g}{mode.lower()}"


def browser_cmd(browser: str, profile: str, url: str) -> list[str]:
    return [browser, "--headless=new", f"--user-data-dir={profile}",
            "--no-first-run", "--no-default-browser-check",
            "--remote-debugging-port=0", "--remote-allow-origins=*",
            "--autoplay-policy=no-user-gesture-required", url]


class _DevTools:
    """Minimaler DevTools-Zugang: JavaScript in der WebSDR-Seite ausführen."""

    def __init__(self, profile: str, timeout: float = PAGE_TIMEOUT):
        import websocket  # websocket-client
        port_file = os.path.join(profile, "DevToolsActivePort")
        deadline = time.time() + timeout
        while not os.path.exists(port_file):
            if time.time() > deadline:
                raise RuntimeError("Chromium meldet keinen DevTools-Port")
            time.sleep(0.2)
        port = None
        while port is None:
            try:
                port = int(open(port_file).read().split()[0])
            except (ValueError, IndexError):
                if time.time() > deadline:
                    raise RuntimeError("DevTools-Port unlesbar")
                time.sleep(0.2)
        page = None
        while page is None:
            try:
                tabs = json.load(urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json", timeout=3))
                page = next((t for t in tabs if t.get("type") == "page"), None)
            except Exception:
                pass
            if page is None:
                if time.time() > deadline:
                    raise RuntimeError("keine WebSDR-Seite im Browser")
                time.sleep(0.3)
        self.ws = websocket.create_connection(page["webSocketDebuggerUrl"],
                                              timeout=10, suppress_origin=True)
        self._id = 0

    def eval(self, js: str):
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": "Runtime.evaluate",
                                 "params": {"expression": js, "returnByValue": True}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self._id:
                res = msg.get("result", {})
                if "exceptionDetails" in res:
                    exc = res["exceptionDetails"].get("exception", {})
                    raise RuntimeError("WebSDR-Seite: " + str(
                        exc.get("description") or res["exceptionDetails"].get("text")))
                return res.get("result", {}).get("value")

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass


class WebSDRSource(Source):
    kind = "websdr"
    rebuffer = True

    def __init__(self, url: str, freq_khz: float, mode: str = "usb",
                 name: str = "", gain: float = 1.0, browser: str = "", **kw):
        kw.setdefault("timeout_seconds", 45.0)   # Browser + Seite brauchen etwas
        super().__init__(name=name or f"{url} {freq_khz}kHz", **kw)
        mode = mode.lower()
        if mode not in MODES:
            raise ValueError(f"WebSDR-Modus {mode!r} unbekannt ({', '.join(MODES)})")
        self.url, self.freq_khz, self.mode = url, float(freq_khz), mode
        self.gain = gain
        self.browser = browser
        self._sink = f"satellit_websdr_{os.getpid()}_{id(self) & 0xffff:x}"
        self._module: str | None = None
        self._profile: str | None = None
        self._chrome: subprocess.Popen | None = None
        self._parec: subprocess.Popen | None = None
        self._devtools: _DevTools | None = None

    # --- Lauf -------------------------------------------------------------
    def run(self) -> None:
        missing = missing_tools(self.browser)
        if missing:
            self.error = "fehlt: " + ", ".join(missing)
            self.status = "error"
            return
        try:
            self._open()
            self._tune()
            if not self._stop.is_set():
                self._record()
                self._pump()
        finally:
            self._close()

    def _open(self) -> None:
        self._module = subprocess.run(
            ["pactl", "load-module", "module-null-sink", f"sink_name={self._sink}",
             f"sink_properties=device.description=Satellit-WebSDR"],
            capture_output=True, text=True, check=True, timeout=10).stdout.strip()
        self._profile = tempfile.mkdtemp(prefix="satellit-websdr-")
        env = dict(os.environ, PULSE_SINK=self._sink)
        self._chrome = subprocess.Popen(
            browser_cmd(find_browser(self.browser), self._profile,
                        page_url(self.url, self.freq_khz, self.mode)),
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True)

    def _record(self) -> None:
        """Erst nach dem Einstellen mitschneiden – kein Ton im falschen Modus."""
        self._parec = subprocess.Popen(
            ["parec", "-d", f"{self._sink}.monitor", "--format=float32le",
             f"--rate={SAMPLE_RATE}", f"--channels={CHANNELS}", "--latency-msec=100"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def _tune(self) -> None:
        dt = self._devtools = _DevTools(self._profile)
        arg, mode = json.dumps(tune_arg(self.freq_khz, self.mode)), json.dumps(self.mode)
        js = (f"setfreqtune({arg});"
              f"if (typeof set_mode=='function' && String(mode).toLowerCase()!={mode})"
              f" set_mode({mode});"
              "JSON.stringify({f: freq, m: String(mode).toLowerCase()})")
        deadline = time.time() + PAGE_TIMEOUT
        got: dict = {}
        while not self._stop.is_set():
            # Bandtabelle und Ton-Applet sind erst nach dem Laden der Seite da
            try:
                if dt.eval("document.readyState=='complete' && typeof setfreqtune=="
                           "'function' && !!window.soundapplet"):
                    got = json.loads(dt.eval(js) or "{}")
                    if abs(float(got.get("f", 0)) - self.freq_khz) <= 1 \
                            and got.get("m") == self.mode:
                        return
            except RuntimeError as exc:
                got = {"fehler": str(exc).splitlines()[0]}
            if time.time() > deadline:
                raise RuntimeError(f"WebSDR stellt nicht ein (meldet {got or 'nichts'})")
            time.sleep(0.5)

    def _pump(self) -> None:
        nbytes = CHUNK * CHANNELS * 4
        out = self._parec.stdout
        while not self._stop.is_set():
            if self._chrome.poll() is not None:
                self.error = "Browser beendet"
                self.status = "error"
                return
            data = out.read(nbytes)
            if not data:
                self.error = "parec liefert nichts mehr"
                self.status = "error"
                return
            n = len(data) // (CHANNELS * 4)
            block = np.frombuffer(data[:n * CHANNELS * 4], dtype=np.float32)
            self._emit(block.reshape(n, CHANNELS) * self.gain)

    def _close(self) -> None:
        if self._devtools:
            self._devtools.close()
        for p in (self._parec, self._chrome):
            if p and p.poll() is None:
                try:
                    if p is self._chrome:
                        os.killpg(p.pid, signal.SIGTERM)
                    else:
                        p.terminate()
                    p.wait(timeout=5)
                except Exception:
                    try:
                        p.kill()
                    except Exception:
                        pass
        if self._module:
            subprocess.run(["pactl", "unload-module", self._module],
                           capture_output=True, timeout=10)
            self._module = None
        if self._profile:
            shutil.rmtree(self._profile, ignore_errors=True)
            self._profile = None

    def stop(self) -> None:
        self._stop.set()
        if self._parec and self._parec.poll() is None:
            self._parec.terminate()          # löst das blockierende read
        super().stop()
