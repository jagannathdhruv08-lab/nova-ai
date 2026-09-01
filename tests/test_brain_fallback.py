"""Tests for brain.py multi-provider failover (Groq -> OpenRouter backup).

Fully hermetic: brain._PROVIDERS is replaced with fake clients so no test
ever touches the real network or the user's API quota.
"""
import pytest

import brain

# The autouse fixture below stubs brain._internet_ok to keep tests hermetic;
# the probe tests need the REAL implementation, so capture it at import time
# (before any fixture runs) and re-attach it inside those tests.
_REAL_INTERNET_OK = brain._internet_ok


# --------------------------------------------------------------------------
# fake OpenAI-style client:  client.chat.completions.create(**kwargs)
# --------------------------------------------------------------------------
class _Completions:
    def __init__(self, fn):
        self._fn = fn

    def create(self, **kwargs):
        return self._fn(kwargs)


class _Chat:
    def __init__(self, fn):
        self.completions = _Completions(fn)


class FakeClient:
    def __init__(self, fn):
        self.chat = _Chat(fn)


def _ok_client(text, seen=None):
    def fn(kwargs):
        if seen is not None:
            seen.append(kwargs)
        msg = type("M", (), {"content": text})()
        choice = type("C", (), {"message": msg})()
        return type("R", (), {"choices": [choice]})()
    return FakeClient(fn)


def _fail_client(exc_text="boom"):
    def fn(kwargs):
        raise RuntimeError(exc_text)
    return FakeClient(fn)


def _provider(name, client):
    return {
        "name": name,
        "client": client,
        "model": "test-model",
        "min_max_tokens": 0,
        "cooldown_until": 0.0,
    }


@pytest.fixture(autouse=True)
def clean_brain_state(monkeypatch):
    """Isolate provider chain + rate-limit + offline-probe state per test."""
    monkeypatch.setattr(brain, "_PROVIDERS", [])
    monkeypatch.setattr(brain, "_RATE_LIMITED_UNTIL", 0.0)
    monkeypatch.setattr(brain, "_RATE_LIMIT_MESSAGE", "")
    # Keep every test hermetic: no real socket probes, no lazy Ollama
    # attach, no keep-warm thread. Offline tests override _internet_ok
    # explicitly with their own fakes.
    monkeypatch.setattr(brain, "_internet_ok", lambda force=False: True)
    monkeypatch.setattr(brain, "_ensure_ollama_provider", lambda: False)
    monkeypatch.setattr(brain, "_start_keep_warm", lambda: None)
    monkeypatch.setattr(brain, "_keep_warm_started", False)
    monkeypatch.setattr(brain, "_internet_state", {"ok": None, "at": 0.0})
    yield


# --------------------------------------------------------------------------
# llm_chat
# --------------------------------------------------------------------------
def test_primary_failure_falls_back_to_backup():
    brain._PROVIDERS = [
        _provider("Groq", _fail_client("groq down")),
        _provider("OpenRouter", _ok_client("hello from backup")),
    ]
    text, used = brain.llm_chat([{"role": "user", "content": "hi"}])
    assert text == "hello from backup"
    assert used == "OpenRouter"


def test_primary_used_when_healthy():
    brain._PROVIDERS = [
        _provider("Groq", _ok_client("from groq")),
        _provider("OpenRouter", _ok_client("from backup")),
    ]
    text, used = brain.llm_chat([{"role": "user", "content": "hi"}])
    assert text == "from groq"
    assert used == "Groq"


def test_cooldown_reorders_next_request():
    order = []

    def groq_fn(kwargs):
        order.append("Groq")
        raise RuntimeError("temporary glitch")

    brain._PROVIDERS = [
        _provider("Groq", FakeClient(groq_fn)),
        _provider("OpenRouter", _ok_client("backup ok")),
    ]
    text1, used1 = brain.llm_chat([{"role": "user", "content": "a"}])
    assert used1 == "OpenRouter"

    # Groq is now on a 30s cooldown -> next call goes straight to backup.
    text2, used2 = brain.llm_chat([{"role": "user", "content": "b"}])
    assert used2 == "OpenRouter"
    assert order == ["Groq"]  # Groq was NOT retried on request #2
    assert text2 == "backup ok"


def test_empty_completion_counts_as_failure():
    brain._PROVIDERS = [
        _provider("Groq", _ok_client("")),  # empty -> treated as failure
        _provider("OpenRouter", _ok_client("rescued")),
    ]
    text, used = brain.llm_chat([{"role": "user", "content": "hi"}])
    assert text == "rescued" and used == "OpenRouter"


def test_all_providers_fail_returns_none_and_error():
    brain._PROVIDERS = [
        _provider("Groq", _fail_client("x")),
        _provider("OpenRouter", _fail_client("y")),
    ]
    text, info = brain.llm_chat([{"role": "user", "content": "hi"}])
    assert text is None
    assert "Groq" in info and "OpenRouter" in info


def test_rate_limit_error_puts_provider_on_long_cooldown():
    brain._PROVIDERS = [_provider("Groq", _fail_client("HTTP 429 rate limited"))]
    before = 10_000.0
    import brain as _b
    real = _b.time.monotonic
    _b.time.monotonic = lambda: before  # freeze clock for determinism
    try:
        text, info = brain.llm_chat([{"role": "user", "content": "hi"}])
    finally:
        _b.time.monotonic = real
    assert text is None
    cd = brain._PROVIDERS[0]["cooldown_until"] - before
    assert cd == pytest.approx(brain._RATE_LIMIT_COOLDOWN_S)


def test_response_format_retry_without_format():
    """Provider that rejects response_format gets one plain retry."""
    attempts = []

    def fn(kwargs):
        attempts.append(kwargs.get("response_format"))
        if kwargs.get("response_format") is not None:
            raise RuntimeError("response_format not supported")
        msg = type("M", (), {"content": '{"action":"chat"}'})()
        return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()

    brain._PROVIDERS = [_provider("OpenRouter", FakeClient(fn))]
    text, used = brain.llm_chat(
        [{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
    )
    assert attempts[0] == {"type": "json_object"}
    assert attempts[1] is None
    assert text == '{"action":"chat"}'


def test_min_max_tokens_headroom_applied():
    seen = []
    brain._PROVIDERS = [{
        "name": "OpenRouter",
        "client": _ok_client("ok", seen),
        "model": "test-model",
        "min_max_tokens": 600,
        "cooldown_until": 0.0,
    }]
    brain.llm_chat([{"role": "user", "content": "hi"}], max_tokens=200)
    assert seen[0]["max_tokens"] == 600  # bumped to reasoning headroom


# --------------------------------------------------------------------------
# ask_nova integration
# --------------------------------------------------------------------------
def test_ask_nova_survives_total_groq_outage(monkeypatch):
    monkeypatch.setattr(brain, "_retrieve_knowledge", lambda p: "")
    brain._PROVIDERS = [
        _provider("Groq", _fail_client("connection refused")),
        _provider("OpenRouter", _ok_client("Nova here - backup answered!")),
    ]
    reply = brain.ask_nova("are you alive?")
    assert isinstance(reply, str)
    assert reply == "Nova here - backup answered!"


def test_ask_nova_returns_message_when_everything_fails(monkeypatch):
    monkeypatch.setattr(brain, "_retrieve_knowledge", lambda p: "")
    brain._PROVIDERS = [
        _provider("Groq", _fail_client("down")),
        _provider("OpenRouter", _fail_client("down too")),
    ]
    reply = brain.ask_nova("hello")
    assert isinstance(reply, str) and reply.strip()
    assert "couldn't process" in reply.lower() or "sorry" in reply.lower()


def test_ask_nova_no_providers_hint_mentions_both_keys():
    brain._PROVIDERS = []
    reply = brain.ask_nova("hello")
    assert "GROQ_API_KEY" in reply and "OPENROUTER_API_KEY" in reply


def test_ask_nova_both_ratelimited_marks_global_limit(monkeypatch):
    monkeypatch.setattr(brain, "_retrieve_knowledge", lambda p: "")
    brain._PROVIDERS = [
        _provider("Groq", _fail_client("429 limit")),
        _provider("OpenRouter", _fail_client("429 limit")),
    ]
    first = brain.ask_nova("hello")
    second = brain.ask_nova("hello again")
    assert "rate limit" in first.lower()
    # global flag now short-circuits before touching any provider
    assert first == second


# --------------------------------------------------------------------------
# route_to_agent integration
# --------------------------------------------------------------------------
def test_route_to_agent_falls_back_and_parses(monkeypatch):
    class FakeAgent:
        ALLOWED_ACTIONS = {"chat"}

    import sys
    monkeypatch.setitem(sys.modules, "agent", FakeAgent())
    brain._PROVIDERS = [
        _provider("Groq", _fail_client("groq 429 rate limit")),
        _provider(
            "OpenRouter",
            _ok_client('{"action": "chat", "ask": "kya karna hai?"}'),
        ),
    ]
    reply = brain.route_to_agent("delete my notes file")
    assert reply == "kya karna hai?"


# --------------------------------------------------------------------------
# Offline fast-path (fix for 40s+ offline reply latency)
# --------------------------------------------------------------------------
def test_offline_skips_cloud_and_answers_locally(monkeypatch):
    monkeypatch.setattr(brain, "_internet_ok", lambda force=False: False)
    cloud_seen = []
    brain._PROVIDERS = [
        _provider("Groq", _ok_client("cloud hi", cloud_seen)),
        _provider("Ollama", _ok_client("local hello")),
    ]
    text, used = brain.llm_chat([{"role": "user", "content": "hello"}])
    assert text == "local hello"
    assert used == "Ollama"
    assert cloud_seen == []          # cloud client was never touched
    now = brain.time.monotonic()
    for prov in brain._PROVIDERS:
        if prov["name"] != "Ollama":
            assert prov["cooldown_until"] > now   # cloud marked on cooldown


def test_offline_fast_path_also_applies_to_stream(monkeypatch):
    monkeypatch.setattr(brain, "_internet_ok", lambda force=False: False)
    cloud_seen = []

    def groq_fn(kwargs):
        cloud_seen.append(kwargs)
        raise RuntimeError("should not be called")

    brain._PROVIDERS = [
        _provider("Groq", FakeClient(groq_fn)),
        _provider("Ollama", _ok_client("local stream hi")),
    ]
    brain.llm_chat_stream([{"role": "user", "content": "hello"}])
    assert cloud_seen == []          # offline fast-path skipped Groq


def test_offline_verdict_wrong_recovers_cloud(monkeypatch):
    # Cached probe says offline; forced re-probe (after local failed) says
    # online -> the cloud providers must be retried and answer.
    monkeypatch.setattr(brain, "_internet_ok",
                        lambda force=False: True if force else False)
    brain._PROVIDERS = [
        _provider("Ollama", _fail_client("connection refused")),
        _provider("Groq", _ok_client("cloud saved the day")),
    ]
    text, used = brain.llm_chat([{"role": "user", "content": "hello"}])
    assert text == "cloud saved the day"
    assert used == "Groq"


def test_ollama_success_starts_keep_warm(monkeypatch):
    warmed = []
    monkeypatch.setattr(brain, "_start_keep_warm", lambda: warmed.append(True))
    monkeypatch.setattr(brain, "_internet_ok", lambda force=False: False)
    brain._PROVIDERS = [_provider("Ollama", _ok_client("local hi"))]
    text, used = brain.llm_chat([{"role": "user", "content": "hello"}])
    assert used == "Ollama"
    assert warmed == [True]          # keep-warm kicked in exactly once


def test_internet_probe_negative_result_is_cached(monkeypatch):
    import socket as socket_mod
    monkeypatch.setattr(brain, "_internet_ok", _REAL_INTERNET_OK)
    attempts = []

    def failing_connect(address, timeout=None):
        attempts.append(address)
        raise OSError("network down")

    monkeypatch.setattr(socket_mod, "create_connection", failing_connect)
    assert brain._internet_ok(force=True) is False
    first = len(attempts)
    assert first == len(brain._INTERNET_PROBE_HOSTS)  # both hosts tried once
    assert brain._internet_ok() is False             # served from cache
    assert len(attempts) == first                    # no extra sockets opened


def test_internet_probe_positive_result_is_cached(monkeypatch):
    import socket as socket_mod
    monkeypatch.setattr(brain, "_internet_ok", _REAL_INTERNET_OK)
    attempts = []

    def ok_connect(address, timeout=None):
        attempts.append(address)
        return type("Sock", (), {"close": lambda self: None})()

    monkeypatch.setattr(socket_mod, "create_connection", ok_connect)
    assert brain._internet_ok() is True
    assert len(attempts) == 1             # first probe host succeeded
    assert brain._internet_ok() is True   # cached, no new probes
    assert len(attempts) == 1


def test_build_client_disables_retries_and_short_connect(monkeypatch):
    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(brain, "OpenAI", FakeOpenAI)
    client = brain._build_client("test-key", "https://example.invalid/v1")
    assert client is not None
    assert captured.get("max_retries") == 0
    timeout = captured.get("timeout")
    try:
        import httpx
        assert isinstance(timeout, httpx.Timeout)
        assert timeout.connect == brain._CONNECT_TIMEOUT_S
        assert timeout.read == brain._CLIENT_TIMEOUT_S
    except ImportError:
        # httpx unavailable (never the case with the openai package)
        assert timeout == brain._CLIENT_TIMEOUT_S


# --------------------------------------------------------------------------
# JSON extraction helper
# --------------------------------------------------------------------------
def test_extract_json_object_plain():
    assert brain._extract_json_object('{"action": "chat"}') == {"action": "chat"}


def test_extract_json_object_wrapped_in_prose():
    raw = 'Sure! Here is the JSON:\n{"action": "chat", "ask": "kya?"}\nDone.'
    assert brain._extract_json_object(raw)["ask"] == "kya?"


def test_extract_json_object_garbage_returns_none():
    assert brain._extract_json_object("not json at all") is None
    assert brain._extract_json_object("") is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
