"""Übersetzer: Schnitt in Sprechpausen, Halluzinationsfilter, Mithören über den Mixer."""

import os
import time

import numpy as np

from satellit.audio import BLOCK, SAMPLE_RATE
from satellit.config import Config
from satellit.engine import Engine
from satellit.output import SilentOutput
from satellit.translate import (FRAME, Translator, cut_point, drop_repeats, keep_segment,
                                to_whisper,
                                WHISPER_RATE)


def _tone(seconds, amp=0.3, f=440.0):
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (amp * np.sin(2 * np.pi * f * t)).astype(np.float32)


def _quiet(seconds):
    return np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32)


class FakeBackend:
    """Statt Whisper: merkt sich die Abschnitte und „übersetzt“ fest."""

    def __init__(self, text="Hello from the radio.", lang="fr", prob=0.9):
        self.calls, self.text, self.lang, self.prob = [], text, lang, prob

    def __call__(self, audio16, language):
        self.calls.append(len(audio16) / WHISPER_RATE)
        return ([{"text": " " + self.text, "no_speech_prob": 0.1,
                  "avg_logprob": -0.3, "compression_ratio": 1.2}], self.lang, self.prob)


def _feed(tr, mono):
    stereo = np.repeat(mono[:, None], 2, axis=1)
    for i in range(0, len(stereo), BLOCK):
        tr.feed(stereo[i:i + BLOCK])


def _wait(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


# --- Bausteine --------------------------------------------------------------
def test_cut_waits_for_min_length():
    assert cut_point(_tone(3), 5, 12) is None


def test_cut_in_speech_pause():
    buf = np.concatenate([_tone(6.5), _quiet(0.5), _tone(3)])
    cut = cut_point(buf, 5, 12)
    assert cut is not None
    assert 6.5 <= cut / SAMPLE_RATE <= 7.0


def test_cut_finds_pause_under_noise_floor():
    rng = np.random.default_rng(0)
    buf = np.concatenate([_tone(6), _quiet(0.6), _tone(3)])
    buf = buf + 0.08 * rng.standard_normal(len(buf)).astype(np.float32)   # Kurzwelle
    cut = cut_point(buf, 5, 12)
    assert cut is not None and 6.0 <= cut / SAMPLE_RATE <= 6.7


def test_repeat_loops_are_collapsed():
    assert drop_repeats("I was told. I was told. I was told! Then he left.") == \
        "I was told. Then he left."
    assert drop_repeats("Yes. No. Yes.") == "Yes. No. Yes."


def test_cut_forced_at_max_without_pause():
    buf = _tone(12.5)
    cut = cut_point(buf, 5, 12)
    assert cut is not None and cut / SAMPLE_RATE >= 9


def test_cut_is_frame_aligned():
    cut = cut_point(np.concatenate([_tone(5.5), _quiet(1)]), 5, 12)
    assert cut % FRAME == 0


def test_downsample_to_16k_keeps_speech_band():
    x = to_whisper(_tone(1, f=1000))
    assert len(x) == WHISPER_RATE
    assert 0.15 < np.sqrt(np.mean(x[100:-100] ** 2)) < 0.25      # 0,3/√2 ≈ 0,21
    # 20 kHz (oberhalb 8 kHz) darf nicht als Alias durchkommen
    assert np.sqrt(np.mean(to_whisper(_tone(1, f=20000))[100:-100] ** 2)) < 0.01


def test_filter_drops_hallucinations_and_noise():
    ok = {"text": "The ship is leaving port.", "no_speech_prob": 0.1,
          "avg_logprob": -0.4, "compression_ratio": 1.3}
    assert keep_segment(ok)
    assert not keep_segment({**ok, "text": " Thank you for watching!"})
    assert not keep_segment({**ok, "text": "Thanks."})
    assert not keep_segment({**ok, "no_speech_prob": 0.9, "avg_logprob": -1.2})
    # live mit medium auf CRI Französisch: Satz stimmt, Modell meldet trotzdem 0.71
    assert keep_segment({**ok, "no_speech_prob": 0.71, "avg_logprob": -0.68})
    assert keep_segment({**ok, "avg_logprob": -1.2})      # wackelig, aber behalten
    assert not keep_segment({**ok, "avg_logprob": -1.7})
    assert not keep_segment({**ok, "compression_ratio": 3.0})
    assert not keep_segment({**ok, "text": "   "})


# --- Translator mit Ersatz-Modell -------------------------------------------
def test_translator_produces_line_with_station_and_language():
    fake = FakeBackend()
    tr = Translator({"enabled": True}, label_fn=lambda: "Radio France", backend=fake).start()
    try:
        time.sleep(0.3)
        _feed(tr, np.concatenate([_tone(6), _quiet(0.6), _tone(1)]))
        assert _wait(lambda: tr.lines)
        line = tr.lines[0]
        assert line["text"] == "Hello from the radio."
        assert line["station"] == "Radio France"
        assert line["lang"] == "fr" and line["lang_name"] == "Französisch"
        assert line["sure"] is True
        assert 6 <= fake.calls[0] <= 7
    finally:
        tr.stop()


def test_unsure_language_is_marked_not_dropped():
    tr = Translator({"enabled": True}, backend=FakeBackend(lang="sw", prob=0.2)).start()
    try:
        time.sleep(0.3)
        _feed(tr, np.concatenate([_tone(6), _quiet(0.6)]))
        assert _wait(lambda: tr.lines)
        assert tr.lines[0]["sure"] is False
    finally:
        tr.stop()


def test_shaky_translation_is_marked_not_dropped():
    tr = Translator({"enabled": True},
                    backend=lambda a, l: ([{"text": "The ship is leaving.", "no_speech_prob": 0.2,
                                            "avg_logprob": -1.2, "compression_ratio": 1.0}],
                                          "fr", 0.95)).start()
    try:
        time.sleep(0.3)
        _feed(tr, np.concatenate([_tone(6), _quiet(0.6)]))
        assert _wait(lambda: tr.lines)
        assert tr.lines[0]["text"] == "The ship is leaving."
        assert tr.lines[0]["sure"] is False
    finally:
        tr.stop()


def test_silence_never_reaches_model():
    fake = FakeBackend()
    tr = Translator({"enabled": True}, backend=fake).start()
    try:
        time.sleep(0.3)
        _feed(tr, _quiet(13))
        time.sleep(0.8)
        assert fake.calls == [] and not tr.lines
    finally:
        tr.stop()


def test_station_change_discards_half_chunk():
    fake = FakeBackend()
    label = ["A"]
    tr = Translator({"enabled": True}, label_fn=lambda: label[0], backend=fake).start()
    try:
        time.sleep(0.3)
        _feed(tr, _tone(4))            # 4 s auf Sender A, noch kein Abschnitt
        time.sleep(0.4)
        label[0] = "B"
        time.sleep(0.4)
        _feed(tr, np.concatenate([_tone(5.5), _quiet(0.6)]))
        assert _wait(lambda: tr.lines)
        assert tr.lines[0]["station"] == "B"
        assert fake.calls[0] < 6.5     # nichts von A mit drin
    finally:
        tr.stop()


def test_disabled_translator_ignores_audio():
    tr = Translator({"enabled": False}, backend=FakeBackend())
    _feed(tr, _tone(2))
    assert len(tr._blocks) == 0
    assert tr.state()["status"] == "aus"


# --- Engine: Mithören über den Mixer ----------------------------------------
def _engine(tmp_path):
    c = Config(path=os.path.join(tmp_path, "c.json"))
    c.data["stations"] = [
        {"id": "a", "name": "Rauschen", "kind": "noise", "noise": 0.05, "freq": 98.4},
    ]
    c.data["schedule"]["enabled"] = False
    c.data["watcher"]["enabled"] = False
    c.data["same"]["sources"] = []
    c.data["translate"].update({"min_seconds": 1.0, "max_seconds": 2.0})
    return Engine(c, output=SilentOutput())


def test_engine_taps_mixer_before_volume(tmp_path):
    eng = _engine(tmp_path)
    fake = FakeBackend()
    eng.translator.backend = fake
    eng.start()
    try:
        eng.tune("a")
        eng.set_muted(True)            # stumm – übersetzt trotzdem
        eng.set_translate(True)
        assert eng.config.get("translate", "enabled") is True
        assert _wait(lambda: eng.translator.lines, timeout=8), "Mixer-Abgriff liefert nichts"
        st = eng.state()["translate"]
        assert st["enabled"] and st["lines"]
    finally:
        eng.stop()


def test_phrase_loops_inside_a_sentence_are_collapsed():
    # live auf 7205 kHz so durchgerutscht (eine Zeile, kein Satzende dazwischen)
    assert drop_repeats("Who will be half of the military who will be half of the "
                        "military who will be half of the military") == \
        "Who will be half of the military"
    assert drop_repeats("we will prepare the 8-star-large-large-large-large with paper.") == \
        "we will prepare the 8-star-large with paper."
    # kurze, natürliche Doppelungen bleiben
    assert drop_repeats("No, no. It was very very cold.") == "No, no. It was very very cold."


def test_auto_threads():
    from satellit.translate import auto_threads
    assert auto_threads(3) == 3
    assert 2 <= auto_threads(0) <= 8


class _Seg:
    def __init__(self, text):
        self.text, self.no_speech_prob, self.avg_logprob, self.compression_ratio = \
            text, 0.0, -0.2, 1.0


class _Info:
    language, language_probability = "fr", 0.9


def test_whisper_backend_stops_between_segments():
    from satellit.translate import WhisperBackend
    stop = {"now": False}
    produced = []

    class FakeModel:
        def transcribe(self, audio, **kw):
            def gen():
                for i in range(5):
                    produced.append(i)
                    stop["now"] = i == 1          # Beenden während Segment 2
                    yield _Seg(f"part {i}")
            return gen(), _Info()

    be = WhisperBackend(cancel=lambda: stop["now"])
    be._model = FakeModel()
    segs, lang, prob = be(np.zeros(16000, dtype=np.float32), None)
    assert [s["text"] for s in segs] == ["part 0", "part 1"]
    assert produced == [0, 1], "nach dem Abbruch kein weiteres Segment rechnen"


def test_stop_waits_for_running_translation():
    started = []

    def slow(audio, lang):
        started.append(time.time())
        time.sleep(0.8)
        return [{"text": "Late.", "avg_logprob": -0.2}], "fr", 0.9

    tr = Translator({"enabled": True}, backend=slow).start()
    time.sleep(0.3)
    _feed(tr, np.concatenate([_tone(6), _quiet(0.6)]))
    assert _wait(lambda: started)
    tr.stop()
    assert not tr._thread.is_alive(), "Thread läuft nach stop() noch (Absturz beim Beenden)"
    assert tr.backend is None


def test_backend_disables_temperature_fallback_by_default():
    from satellit.translate import WhisperBackend
    seen = {}

    class FakeModel:
        def transcribe(self, audio, **kw):
            seen.update(kw)
            return iter([]), _Info()

    be = WhisperBackend()
    be._model = FakeModel()
    be(np.zeros(16000, dtype=np.float32), None)
    assert seen["temperature"] == 0.0
    be.fallback, seen = True, {}
    be._model.transcribe = lambda audio, **kw: (seen.update(kw), (iter([]), _Info()))[1]
    be(np.zeros(16000, dtype=np.float32), None)
    assert "temperature" not in seen


def test_model_loads_from_cache_without_network_first(monkeypatch):
    import sys
    import types
    from satellit.translate import WhisperBackend
    calls = []

    class FakeWhisperModel:
        def __init__(self, name, local_files_only=False, **kw):
            calls.append(local_files_only)
            if local_files_only and name == "fehlt":
                raise FileNotFoundError("nicht im Cache")

    monkeypatch.setitem(sys.modules, "faster_whisper",
                        types.SimpleNamespace(WhisperModel=FakeWhisperModel))
    WhisperBackend("small").load()
    assert calls == [True], "vorhandenes Modell ohne Netz laden"
    calls.clear()
    WhisperBackend("fehlt").load()
    assert calls == [True, False], "fehlendes Modell dann doch herunterladen"


def test_model_switch_reloads_in_own_thread(monkeypatch):
    """Ein Modellwechsel verwirft das alte Modell erst im Übersetzer-Thread."""
    import satellit.translate as tr
    loaded = []

    class FakeWhisper(tr.WhisperBackend):
        def load(self):
            loaded.append(self.model_name)

        def __call__(self, audio16, language):
            return [], "en", 1.0

    monkeypatch.setattr(tr, "WhisperBackend", FakeWhisper)
    monkeypatch.setattr(tr, "available", lambda: True)
    t = Translator({"enabled": True}).start()
    try:
        for _ in range(50):
            if loaded:
                break
            time.sleep(0.05)
        assert loaded == ["small"]
        t.apply({"enabled": True, "model": "medium"})
        assert t.backend is not None          # nicht aus fremdem Thread weggenommen
        for _ in range(50):
            if loaded[-1] == "medium":
                break
            time.sleep(0.05)
        assert loaded == ["small", "medium"]
        assert t.backend.model_name == "medium"
    finally:
        t.stop()


def test_plan_language_wins_when_whisper_guesses_otherwise():
    """Sendeplan sagt Kroatisch/Niederländisch, Whisper rät Tschechisch -> Kroatisch."""
    from satellit.translate import WhisperBackend
    calls = []

    class Info:
        def __init__(self, lang):
            self.language, self.language_probability = lang, 0.46
            self.all_language_probs = [("cs", 0.46), ("hr", 0.30), ("nl", 0.01)]

    class FakeModel:
        def transcribe(self, audio, language=None, **kw):
            calls.append(language)
            return iter([_Seg(f"text {language}")]), Info(language or "cs")

    be = WhisperBackend()
    be._model = FakeModel()
    segs, lang, prob = be(np.zeros(16000, dtype=np.float32), None, ["hr", "nl"])
    assert calls == [None, "hr"] and lang == "hr" and prob == 0.30
    assert segs[0]["text"] == "text hr"
    # Whisper traut keiner Plan-Sprache etwas zu -> bleibt bei seiner Erkennung
    calls.clear()
    segs, lang, _ = be(np.zeros(16000, dtype=np.float32), None, ["nl"])
    assert calls == [None] and lang == "cs"
    # erkannt wie geplant -> kein zweiter Durchgang
    calls.clear()
    be(np.zeros(16000, dtype=np.float32), None, ["cs"])
    assert calls == [None]


def test_translator_marks_plan_language_as_sure():
    seen = {}

    def backend(audio, lang, hint=None):
        seen["hint"] = hint
        return [{"text": "Hello radio friends", "no_speech_prob": 0.1,
                 "avg_logprob": -0.5, "compression_ratio": 1.2}], "hr", 0.3

    t = Translator({"enabled": True}, label_fn=lambda: "CRI", backend=backend,
                   hint_fn=lambda: ["hr", "nl"])
    t._process(np.random.default_rng(0).normal(0, 0.1, SAMPLE_RATE * 6).astype(np.float32), "CRI")
    line = t.lines[0]
    assert seen["hint"] == ["hr", "nl"]
    assert line["plan"] is True and line["sure"] is True      # 0.3 < 0.5, aber laut Plan
