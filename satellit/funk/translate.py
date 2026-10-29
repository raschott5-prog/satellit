"""Übersetzer: hört beim Programm mit, erkennt die Sprache und übersetzt ins Englische.

Wie der SAME-Dekoder ein reiner Mithörer: Der Mixer reicht jeden fertig
gemischten Block (nach der Überblendung, vor Lautstärke und Stumm) an
``feed`` weiter. Ein eigener Thread sammelt daraus Abschnitte von 5–12 s,
schneidet bevorzugt in Sprechpausen und lässt sie von Whisper übersetzen
(``task="translate"`` – Whisper kann nur ins Englische übersetzen, dafür aus
rund 100 Sprachen, und erkennt die Sprache selbst).

Kurzwelle und Amateurfunk sind schmalbandig und verrauscht. Whisper erfindet
dann gern Sätze („Thank you for watching“). Deshalb wird gefiltert:

* Abschnitte ohne Sprache (VAD) oder fast stumm gehen gar nicht erst ins Modell.
* Segmente mit hoher Nicht-Sprache-Wahrscheinlichkeit, sehr niedriger
  Sicherheit oder Wiederholungsschleifen (Kompressionsrate) fliegen raus.
* Schleifen, die durchrutschen – derselbe Satz oder dieselbe Wortfolge
  mehrfach hintereinander –, werden auf ein Vorkommen gekürzt.
* Bekannte Floskeln, die Whisper aus Rauschen halluziniert, fliegen raus.
* Mittlere Sicherheit und unsichere Spracherkennung werden nicht verworfen,
  sondern markiert – lieber ein Bruchstück mit Fragezeichen als gar nichts.

``faster-whisper`` ist optional. Fehlt es, meldet der Zustand das, und alles
andere läuft wie bisher. Das Modell wird erst beim Einschalten geladen.
"""

from __future__ import annotations

import collections
import importlib.util
import os
import re
import threading
import time
from typing import Callable, Optional

import numpy as np

from ..audio import BLOCK, SAMPLE_RATE

WHISPER_RATE = 16_000
DECIM = SAMPLE_RATE // WHISPER_RATE          # 3
FRAME = SAMPLE_RATE // 10                    # 100-ms-Blöcke für die Pausensuche
BACKLOG_SECONDS = 60.0                       # mehr Rückstand wird verworfen

#: Sätze, die Whisper aus Rauschen oder Musik erfindet (klein, ohne Satzzeichen).
HALLUCINATIONS = {
    "you", "thank you", "thanks", "thank you very much", "thank you for watching",
    "thanks for watching", "thank you for listening", "thanks for listening",
    "please subscribe", "subscribe to the channel", "like and subscribe",
    "see you next time", "see you in the next video", "bye", "bye bye",
    "subtitles by the amaraorg community", "subtitles by", "amaraorg",
    "music", "applause", "silence", "no", "oh", "hmm", "so",
}

#: Deutsche Namen der häufigsten Sprachen (Rest: Kürzel).
LANG_NAMES = {
    "af": "Afrikaans", "ar": "Arabisch", "bg": "Bulgarisch", "bn": "Bengalisch",
    "ca": "Katalanisch", "cs": "Tschechisch", "cy": "Walisisch", "da": "Dänisch",
    "de": "Deutsch", "el": "Griechisch", "en": "Englisch", "es": "Spanisch",
    "et": "Estnisch", "fa": "Persisch", "fi": "Finnisch", "fr": "Französisch",
    "he": "Hebräisch", "hi": "Hindi", "hr": "Kroatisch", "hu": "Ungarisch",
    "id": "Indonesisch", "is": "Isländisch", "it": "Italienisch", "ja": "Japanisch",
    "ko": "Koreanisch", "lt": "Litauisch", "lv": "Lettisch", "ms": "Malaiisch",
    "nl": "Niederländisch", "no": "Norwegisch", "pl": "Polnisch", "pt": "Portugiesisch",
    "ro": "Rumänisch", "ru": "Russisch", "sk": "Slowakisch", "sl": "Slowenisch",
    "sq": "Albanisch", "sr": "Serbisch", "sv": "Schwedisch", "sw": "Suaheli",
    "ta": "Tamil", "th": "Thai", "tl": "Tagalog", "tr": "Türkisch",
    "uk": "Ukrainisch", "ur": "Urdu", "vi": "Vietnamesisch", "zh": "Chinesisch",
}

SHAKY_LOGPROB = -1.0          # darunter: Zeile als unsicher markieren
DROP_LOGPROB = -1.5           # darunter: verwerfen
HINT_MIN_PROB = 0.02          # Sendeplan-Sprache nur, wenn Whisper ihr so viel zutraut

DEFAULTS = {
    "enabled": False,
    "model": "small",          # tiny, base, small, medium, large-v3
    "language": None,          # None = automatisch erkennen, sonst z. B. "fr"
    "beam": 1,
    "fallback": False,         # Whisper-Neuversuche mit Temperatur: auf Kurzwelle 3–4× so teuer
    "threads": 0,              # 0 = automatisch: Kerne − 2
    "min_seconds": 5.0,
    "max_seconds": 12.0,
    "min_lang_prob": 0.5,      # darunter: Sprache unsicher -> markiert
    "keep_lines": 50,
}


# Wählbare Modelle mit ungefährer Downloadgröße (Systran/faster-whisper-*)
MODELS = {"tiny": "75 MB", "base": "145 MB", "small": "480 MB",
          "medium": "1,5 GB", "large-v3": "3 GB"}


def installed_models() -> set:
    """Modelle, die schon im Hugging-Face-Cache liegen (ohne Download nutzbar)."""
    try:
        from huggingface_hub.constants import HF_HUB_CACHE
    except Exception:
        return set()
    return {m for m in MODELS
            if os.path.isdir(os.path.join(HF_HUB_CACHE, f"models--Systran--faster-whisper-{m}"))}


def available() -> bool:
    """Ist faster-whisper installiert?"""
    return importlib.util.find_spec("faster_whisper") is not None


def lang_name(code: Optional[str]) -> str:
    if not code:
        return "?"
    return LANG_NAMES.get(code, code)


# ---------------------------------------------------------------------------
# Signalverarbeitung
# ---------------------------------------------------------------------------
def _lowpass_taps(n: int = 63, cutoff_hz: float = 7000.0) -> np.ndarray:
    t = np.arange(n) - (n - 1) / 2
    h = np.sinc(2 * cutoff_hz / SAMPLE_RATE * t) * np.hamming(n)
    return (h / h.sum()).astype(np.float32)


_TAPS = _lowpass_taps()


def to_whisper(mono48: np.ndarray) -> np.ndarray:
    """48-kHz-Mono auf 16 kHz (Tiefpass gegen Aliasing, dann jedes 3. Sample)."""
    if len(mono48) == 0:
        return np.zeros(0, dtype=np.float32)
    return np.convolve(mono48, _TAPS, mode="same")[::DECIM].astype(np.float32)


def cut_point(buf: np.ndarray, min_s: float, max_s: float) -> Optional[int]:
    """Index, an dem der 48-kHz-Puffer geschnitten wird, oder None (weiter sammeln).

    Bevorzugt eine Sprechpause nach ``min_s``; ohne Pause spätestens bei
    ``max_s`` am leisesten Moment der letzten 3 s.
    """
    n = len(buf) // FRAME
    lo = int(min_s * 10)
    if n < lo:
        return None
    rms = np.sqrt(np.mean(buf[: n * FRAME].reshape(n, FRAME) ** 2, axis=1))
    # Pause = nahe am Grundrauschen. Bei Kurzwelle füllt Rauschen die Pausen,
    # daher relativ zum leisesten Block statt zu null.
    floor, med = float(rms.min()), float(np.median(rms))
    hits = []
    if med - floor > 0.2 * med:          # gleichmäßiger Ton/Rauschen: keine Pausen
        hits = np.nonzero(rms[lo:] < floor + 0.3 * (med - floor) + 1e-5)[0]
    if len(hits):
        return (lo + int(hits[0]) + 1) * FRAME
    if n >= int(max_s * 10):
        a = max(lo, n - 30)
        return (a + int(np.argmin(rms[a:])) + 1) * FRAME
    return None


def auto_threads(threads: int) -> int:
    """``threads`` aus der Konfiguration; 0 = Kerne − 2 (mind. 2, höchstens 8)."""
    if threads and threads > 0:
        return int(threads)
    return max(2, min(8, (os.cpu_count() or 4) - 2))


def _norm(text: str) -> str:
    return re.sub(r"[^a-z ]", "", text.lower()).strip()


MAX_LOOP_WORDS = 15


def _collapse_word_loops(text: str) -> str:
    """Dieselbe Wortfolge mehrfach hintereinander -> einmal.

    Ab drei Wörtern reicht eine Wiederholung, kürzere Folgen müssen dreimal
    kommen („no, no“ oder „very very“ bleiben stehen). Bindestrich-Ketten
    („large-large-large“) zählen als einzelne Wörter.
    """
    text = re.sub(r"\b(\w+)(?:-\1\b){2,}", r"\1", text, flags=re.IGNORECASE)
    words = text.split()
    norm = [_norm(w) for w in words]
    out: list[str] = []
    i = 0
    while i < len(words):
        step = 1
        for n in range(min(MAX_LOOP_WORDS, (len(words) - i) // 2), 0, -1):
            pat = norm[i:i + n]
            if not all(pat):
                continue
            k = 1
            while norm[i + k * n:i + (k + 1) * n] == pat:
                k += 1
            if k >= (2 if n >= 3 else 3):
                step = n * k
                out.extend(words[i:i + n])
                break
        else:
            out.append(words[i])
        i += step
    return " ".join(out)


def drop_repeats(text: str) -> str:
    """Wiederholungsschleifen kürzen: Satz oder Wortfolge mehrfach hintereinander -> einmal."""
    out: list[str] = []
    for sent in re.split(r"(?<=[.!?])\s+", _collapse_word_loops(text.strip())):
        if sent and (not out or _norm(sent) != _norm(out[-1])):
            out.append(sent)
    return " ".join(out)


def keep_segment(seg: dict) -> bool:
    """Ein Whisper-Segment behalten? (Rausch-Halluzinationen aussortieren)"""
    text = seg.get("text", "").strip()
    if not text:
        return False
    # Wie Whisper selbst: "keine Sprache" nur, wenn das Modell dabei auch beim
    # Text unsicher ist. medium meldet bei Kurzwellenrauschen oft 0.7 und mehr,
    # obwohl der Satz stimmt – allein darauf verworfen, ging gutes Material verloren.
    if seg.get("no_speech_prob", 0.0) > 0.6 and seg.get("avg_logprob", 0.0) < SHAKY_LOGPROB:
        return False
    if seg.get("avg_logprob", 0.0) < DROP_LOGPROB:
        return False
    if seg.get("compression_ratio", 1.0) > 2.4:      # „the the the the …“
        return False
    return _norm(text) not in HALLUCINATIONS


# ---------------------------------------------------------------------------
# Whisper-Anbindung (austauschbar, damit die Tests ohne Modell laufen)
# ---------------------------------------------------------------------------
class WhisperBackend:
    """faster-whisper auf der CPU (int8). Lädt beim ersten Aufruf von ``load``."""

    def __init__(self, model: str = "small", threads: int = 0, beam: int = 1,
                 cancel: Callable[[], bool] = lambda: False, fallback: bool = False):
        self.model_name, self.threads, self.beam = model, auto_threads(threads), beam
        self.fallback = fallback
        self.cancel = cancel          # zwischen zwei Segmenten abbrechen (Beenden)
        self._model = None

    def load(self) -> None:
        if self._model is None:
            from faster_whisper import WhisperModel
            kw = dict(device="cpu", compute_type="int8", cpu_threads=self.threads)
            # Erst nur den lokalen Cache: sonst fragt Hugging Face bei jedem Start
            # online nach (über LTE hing das Laden so Minuten). Netz nur, wenn
            # das Modell noch nie geladen wurde.
            try:
                self._model = WhisperModel(self.model_name, local_files_only=True, **kw)
            except Exception:
                self._model = WhisperModel(self.model_name, **kw)

    def _transcribe(self, audio16: np.ndarray, language: Optional[str]):
        return self._model.transcribe(
            audio16, language=language, task="translate", beam_size=self.beam,
            vad_filter=True, condition_on_previous_text=False,
            # Ohne Fallback: verrauschte Abschnitte nicht bis zu 5× neu rechnen;
            # was dabei als Schleife herauskommt, fangen die Filter ab.
            **({} if self.fallback else {"temperature": 0.0}))

    def __call__(self, audio16: np.ndarray, language: Optional[str],
                 candidates: Optional[list] = None):
        """-> (segmente als dicts, sprache, sprach-wahrscheinlichkeit)

        ``candidates``: Sprachen laut Sendeplan. Erkennt Whisper eine andere,
        wird mit der wahrscheinlichsten Kandidatin neu übersetzt – sofern
        Whisper ihr überhaupt etwas zutraut (sonst sendet gerade wohl jemand,
        der nicht im Plan steht).
        """
        self.load()
        segs, info = self._transcribe(audio16, language)
        lang, prob = info.language, float(info.language_probability)
        if language is None and candidates and lang not in candidates:
            probs = dict(info.all_language_probs or [])
            best = max(candidates, key=lambda c: probs.get(c, 0.0))
            if probs.get(best, 0.0) >= HINT_MIN_PROB:
                segs, info = self._transcribe(audio16, best)   # Generator: noch nichts gerechnet
                lang, prob = best, probs[best]
        out = []
        for s in segs:                # Generator: jedes Segment wird hier erst gerechnet
            out.append({"text": s.text, "no_speech_prob": s.no_speech_prob,
                        "avg_logprob": s.avg_logprob,
                        "compression_ratio": s.compression_ratio})
            if self.cancel():
                break
        return out, lang, prob


# ---------------------------------------------------------------------------
# Der Mithörer
# ---------------------------------------------------------------------------
class Translator:
    def __init__(self, cfg: Optional[dict] = None,
                 label_fn: Callable[[], str] = lambda: "",
                 log: Callable[[str], None] = lambda text: None,
                 backend=None,
                 hint_fn: Callable[[], Optional[list]] = lambda: None):
        self.cfg = {**DEFAULTS, **(cfg or {})}
        self.label_fn, self.log = label_fn, log
        self.hint_fn = hint_fn        # Sprachen laut Sendeplan (HFCC) oder None
        self.backend = backend
        self.enabled = bool(self.cfg["enabled"])
        self.status = "aus"
        self.error: Optional[str] = None
        self.lines: collections.deque = collections.deque(maxlen=int(self.cfg["keep_lines"]))
        self.skipped_seconds = 0.0
        self.load = 0.0               # Rechenzeit / Audiodauer, gleitend
        self._blocks: collections.deque = collections.deque(
            maxlen=int(BACKLOG_SECONDS * SAMPLE_RATE / BLOCK))
        self._stop = threading.Event()
        self._reload = False          # Modell wechseln – erledigt der eigene Thread
        self._thread: Optional[threading.Thread] = None

    # --- Steuerung --------------------------------------------------------
    def start(self) -> "Translator":
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="translate", daemon=True)
            self._thread.start()
        return self

    def stop(self, timeout: float = 20.0) -> None:
        """Anhalten und auf den Thread warten.

        Ein Daemon-Thread, der beim Programmende noch in CTranslate2 rechnet,
        reißt den Prozess mit ``terminate called without an active exception``
        ab. Deshalb hier warten; das laufende Segment wird noch fertig.
        """
        self._stop.set()
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(timeout)

    def set_enabled(self, on: bool) -> None:
        on = bool(on)
        if on and not self.enabled:
            self.error = None              # nach einem Fehler neuer Versuch
            self._blocks.clear()
        self.enabled = on
        self.log("Übersetzer an" if on else "Übersetzer aus")

    def apply(self, cfg: Optional[dict]) -> None:
        """Neue Einstellungen; anderes Modell -> beim nächsten Abschnitt neu laden."""
        new = {**DEFAULTS, **(cfg or {})}
        if new["model"] != self.cfg["model"] or new["threads"] != self.cfg["threads"]:
            self.error = None              # z. B. fehlgeschlagener Download: neuer Versuch
            if isinstance(self.backend, WhisperBackend):
                self._reload = True
        if isinstance(self.backend, WhisperBackend):
            self.backend.beam = int(new["beam"])
            self.backend.fallback = bool(new["fallback"])
        self.cfg = new
        if bool(new["enabled"]) != self.enabled:
            self.set_enabled(new["enabled"])

    def clear(self) -> None:
        self.lines.clear()

    # --- Audio-Thread -----------------------------------------------------
    def feed(self, block: np.ndarray) -> None:
        """Vom Mixer im Audiotakt aufgerufen – nur einreihen, nie rechnen."""
        if not self.enabled:
            return
        if len(self._blocks) == self._blocks.maxlen:
            self.skipped_seconds += len(block) / SAMPLE_RATE
        self._blocks.append(np.array(block, dtype=np.float32, copy=True))

    # --- eigener Thread ---------------------------------------------------
    def _loop(self) -> None:
        buf = np.zeros(0, dtype=np.float32)
        label = None
        while not self._stop.is_set():
            if not self.enabled or self.error:
                self.status = "aus" if not self.enabled else "Fehler"
                buf = np.zeros(0, dtype=np.float32)
                self._stop.wait(0.3)
                continue
            if self._reload:              # hier, nicht in apply(): das Modell rechnet in diesem Thread
                self._reload, self.backend = False, None
            if self.backend is None:
                if not self._load_backend():
                    continue
            # neuer Sender: halben Abschnitt des alten nicht mitübersetzen
            cur = self.label_fn()
            if cur != label:
                label, buf = cur, np.zeros(0, dtype=np.float32)
                self._blocks.clear()
            buf = self._drain(buf)
            cut = cut_point(buf, float(self.cfg["min_seconds"]), float(self.cfg["max_seconds"]))
            if cut is None:
                self.status = "hört zu"
                self._stop.wait(0.2)
                continue
            chunk, buf = buf[:cut], buf[cut:]
            if self.label_fn() != label:       # während des Sammelns umgeschaltet
                continue
            self._process(chunk, label)
        self.backend = None           # Modell im eigenen Thread freigeben

    def _drain(self, buf: np.ndarray) -> np.ndarray:
        parts = [buf]
        while self._blocks:
            b = self._blocks.popleft()
            parts.append(b.mean(axis=1) if b.ndim == 2 else b)
        return np.concatenate(parts) if len(parts) > 1 else buf

    def _load_backend(self) -> bool:
        if not available():
            self.error = "faster-whisper nicht installiert"
            self.log("Übersetzer: " + self.error)
            return False
        self.status = f"lädt Modell {self.cfg['model']} …"
        try:
            be = WhisperBackend(self.cfg["model"], int(self.cfg["threads"]),
                                int(self.cfg["beam"]), cancel=self._stop.is_set,
                                fallback=bool(self.cfg["fallback"]))
            be.load()
        except Exception as exc:                      # Download/Modell kaputt
            self.error = str(exc) or exc.__class__.__name__
            self.log("Übersetzer: Modell nicht ladbar: " + self.error)
            return False
        self.backend = be
        self._blocks.clear()          # was beim Laden auflief, ist veraltet
        return True

    def _process(self, chunk48: np.ndarray, label: str) -> None:
        secs = len(chunk48) / SAMPLE_RATE
        if float(np.sqrt(np.mean(chunk48 ** 2))) < 1e-4:
            return                                   # Funkstille: Modell schonen
        self.status = "übersetzt …"
        t0 = time.time()
        fixed = self.cfg.get("language")
        hint = None if fixed else self._hint()
        try:
            audio = to_whisper(chunk48)
            segs, lang, prob = (self.backend(audio, fixed, hint) if hint
                                else self.backend(audio, fixed))
        except Exception as exc:
            self.log(f"Übersetzer: Fehler im Modell: {exc}")
            return
        took = time.time() - t0
        self.load = 0.7 * self.load + 0.3 * (took / max(secs, 0.1))
        kept = [s for s in segs if keep_segment(s)]
        text = drop_repeats(" ".join(s["text"].strip() for s in kept))
        if not text:
            return
        shaky = any(s.get("avg_logprob", 0.0) < SHAKY_LOGPROB for s in kept)
        self.lines.appendleft({
            "t": time.strftime("%H:%M:%S"), "station": label,
            "lang": lang, "lang_name": lang_name(lang), "prob": round(prob, 2),
            # passt die Sprache zum Sendeplan, gilt sie als sicher
            "plan": bool(hint) and lang in hint,
            "sure": (prob >= float(self.cfg["min_lang_prob"]) or bool(hint) and lang in hint)
                    and not shaky,
            "text": text, "secs": round(took, 1),
        })

    def _hint(self) -> Optional[list]:
        try:
            return self.hint_fn() or None
        except Exception:
            return None

    # --- Anzeige ----------------------------------------------------------
    def state(self) -> dict:
        have = installed_models()
        return {
            "available": available() or self.backend is not None,
            "enabled": self.enabled,
            "status": self.error and f"Fehler: {self.error}" or self.status,
            "model": self.cfg["model"],
            "models": [{"name": m, "size": size, "installed": m in have}
                       for m, size in MODELS.items()],
            "language": self.cfg.get("language"),
            "load": round(self.load, 2),
            "skipped_seconds": round(self.skipped_seconds),
            "lines": list(self.lines)[:30],
        }
