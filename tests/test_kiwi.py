"""KiwiSDR: Proxy-Umleitung auflösen (ohne Netz)."""

import sys
import types

from satellit.sources import kiwi


def _fake_requests(monkeypatch, final_url=None, fail=False):
    calls = []

    class Resp:
        url = final_url

        def close(self):
            pass

    def get(url, **kw):
        calls.append(url)
        if fail:
            raise OSError("kein Netz")
        return Resp()

    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(get=get))
    monkeypatch.setattr(kiwi, "_resolved", {})
    return calls


def test_proxy_redirect_is_followed_once(monkeypatch):
    calls = _fake_requests(monkeypatch, "http://abc.proxy.kiwisdr.com:8073/")
    assert kiwi.resolve_host("http://abc.proxy.kiwisdr.com/") == "abc.proxy.kiwisdr.com:8073"
    assert kiwi.resolve_host("abc.proxy.kiwisdr.com") == "abc.proxy.kiwisdr.com:8073"
    assert calls == ["http://abc.proxy.kiwisdr.com/"], "Ergebnis wird gemerkt"


def test_unreachable_host_is_used_directly(monkeypatch):
    _fake_requests(monkeypatch, fail=True)
    assert kiwi.resolve_host("kiwi.example:8073") == "kiwi.example:8073"


def test_rejection_messages_are_readable():
    assert kiwi._rejection(b"MSG badp=5") == \
        "Kiwi weist ab: Kiwi erlaubt nur eine Verbindung pro IP-Adresse"
    assert kiwi._rejection(b"MSG badp=0") is None
    assert kiwi._rejection(b"MSG too_busy=8") == "Kiwi weist ab: alle Kanäle belegt"
    assert kiwi._rejection(b"MSG sample_rate=12000.0") is None
    assert kiwi._rejection(b"SND\x00" + bytes(20)) is None
