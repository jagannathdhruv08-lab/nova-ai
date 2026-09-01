"""Tests for brain.py additions: llm_chat_stream, ask_nova_stream, llm_json.

Fully hermetic - brain._PROVIDERS is replaced with fake clients; no
network access ever happens.
"""
import pytest

import brain


# --------------------------------------------------------------------------
# fakes
# --------------------------------------------------------------------------
class _Delta:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.delta = _Delta(content)


class _StreamEvent:
    def __init__(self, content):
        self.choices = [_Choice(content)]


class _Completions:
    def __init__(self, chunks=None, fn=None):
        self._chunks = chunks or []
        self._fn = fn
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self._fn is not None:
            return self._fn(kwargs)
        if not kwargs.get("stream"):
            # non-stream path (llm_json)
            msg = type("M", (), {"content": "".join(self._chunks)})()
            choice = type("C", (), {"message": msg})()
            return type("R", (), {"choices": [choice]})()
        return iter([_StreamEvent(c) for c in self._chunks])


class _Chat:
    def __init__(self, completions):
        self.completions = completions


class FakeClient:
    def __init__(self, completions):
        self.chat = _Chat(completions)


def _provider(name, client):
    return {"name": name, "client": client, "model": "test-model",
            "min_max_tokens": 0, "cooldown_until": 0.0}


@pytest.fixture(autouse=True)
def clean_brain_state(monkeypatch):
    """Isolate provider chain + rate-limit + offline-probe state per test."""
    monkeypatch.setattr(brain, "_PROVIDERS", [])
    monkeypatch.setattr(brain, "_RATE_LIMITED_UNTIL", 0.0)
    monkeypatch.setattr(brain, "_RATE_LIMIT_MESSAGE", "")
    # Keep every test hermetic: no real socket probes, no lazy Ollama
    # attach, no keep-warm thread.
    monkeypatch.setattr(brain, "_internet_ok", lambda force=False: True)
    monkeypatch.setattr(brain, "_ensure_ollama_provider", lambda: False)
    monkeypatch.setattr(brain, "_start_keep_warm", lambda: None)
    monkeypatch.setattr(brain, "_keep_warm_started", False)
    monkeypatch.setattr(brain, "_internet_state", {"ok": None, "at": 0.0})
    yield


# --------------------------------------------------------------------------
# llm_chat_stream
# --------------------------------------------------------------------------
def test_stream_assembles_chunks_in_order():
    client = FakeClient(_Completions(chunks=["Hel", "lo ", "world"]))
    brain._PROVIDERS = [_provider("Groq", client)]
    seen = []
    text, used = brain.llm_chat_stream(
        [{"role": "user", "content": "hi"}], on_delta=seen.append)
    assert text == "Hello world"
    assert used == "Groq"
    assert seen == ["Hel", "lo ", "world"]
    assert client.chat.completions.last_kwargs["stream"] is True


def test_stream_falls_back_when_first_provider_fails():
    failing = FakeClient(_Completions(fn=lambda kw: (_ for _ in ()).throw(
        RuntimeError("groq down"))))
    working = FakeClient(_Completions(chunks=["backup ok"]))
    brain._PROVIDERS = [_provider("Groq", failing), _provider("OR", working)]

    text, used = brain.llm_chat_stream([{"role": "user", "content": "hi"}])
    assert text == "backup ok"
    assert used == "OR"


def test_stream_keeps_partial_text_on_midstream_failure():
    class MidFailCompletions(_Completions):
        def create(self, **kwargs):
            yield _StreamEvent("partial ")
            raise RuntimeError("connection reset")

    failing = FakeClient(MidFailCompletions())
    brain._PROVIDERS = [_provider("Groq", failing)]
    text, used = brain.llm_chat_stream([{"role": "user", "content": "hi"}])
    assert text == "partial"
    assert "(partial)" in used


def test_stream_no_providers():
    text, info = brain.llm_chat_stream([{"role": "user", "content": "hi"}])
    assert text is None


def test_ask_nova_stream_returns_error_string_when_all_fail():
    failing = FakeClient(_Completions(
        fn=lambda kw: (_ for _ in ()).throw(RuntimeError("nope"))))
    brain._PROVIDERS = [_provider("Groq", failing)]
    reply = brain.ask_nova_stream("hello")
    assert isinstance(reply, str) and "couldn't process" in reply.lower()


# --------------------------------------------------------------------------
# llm_json
# --------------------------------------------------------------------------
def test_llm_json_parses_clean_object():
    client = FakeClient(_Completions(chunks=['{"action": "chat"}']))
    brain._PROVIDERS = [_provider("Groq", client)]
    result = brain.llm_json("sys", "usr")
    assert result == {"action": "chat"}


def test_llm_json_tolerates_fenced_json():
    raw = 'Sure! Here you go:\n```json\n{"a": 1}\n```'
    client = FakeClient(_Completions(chunks=[raw]))
    brain._PROVIDERS = [_provider("Groq", client)]
    assert brain.llm_json("sys", "usr") == {"a": 1}


def test_llm_json_returns_none_on_garbage():
    client = FakeClient(_Completions(chunks=["no json here at all"]))
    brain._PROVIDERS = [_provider("Groq", client)]
    assert brain.llm_json("sys", "usr") is None


def test_llm_json_returns_none_without_providers():
    assert brain.llm_json("sys", "usr") is None