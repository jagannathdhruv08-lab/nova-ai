"""Regression tests for the Sep-2026 provider fixes:

1. agent.empty_recycle_bin is implemented on Windows via SHEmptyRecycleBinW
   (with the already-empty E_UNEXPECTED case mapped to a friendly message,
   and confirmation still required because the action is destructive).
2. nova_vision.ask_gemini_vision walks the WHOLE fallback chain on ANY
   failure (including 503 "high demand"), not only model-not-found errors.

Everything is stubbed - no real API call and no real recycle-bin is touched.
"""
import ctypes

import pytest

import agent
import nova_vision


# ---------------------------------------------------------------------------
# Shared state resets
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_agent_rate_state():
    agent._ACTION_TIMES.clear()
    agent._DESTRUCTIVE_TIMES.clear()
    yield
    agent._ACTION_TIMES.clear()
    agent._DESTRUCTIVE_TIMES.clear()


# ---------------------------------------------------------------------------
# 1. agent.empty_recycle_bin
# ---------------------------------------------------------------------------

class _FakeShell32:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def SHEmptyRecycleBinW(self, hwnd, root, flags):
        self.calls.append((hwnd, root, flags))
        return self.result


class _FakeWindll:
    def __init__(self, shell32):
        self.shell32 = shell32


def _handle(shell, monkeypatch, confirm=lambda m: True):
    monkeypatch.setattr(agent.os, "name", "nt", raising=False)
    monkeypatch.setattr(ctypes, "windll", _FakeWindll(shell))
    return agent.handle(
        {"action": "empty_recycle_bin", "args": {}, "confidence": 0.9},
        confirm_callback=confirm)


def test_empty_recycle_bin_success(monkeypatch):
    shell = _FakeShell32(0)
    assert _handle(shell, monkeypatch) == "Recycle bin emptied."
    assert shell.calls and shell.calls[0][2] == 0x0007  # SHERB flags


def test_empty_recycle_bin_already_empty(monkeypatch):
    # 0x8000FFFF (E_UNEXPECTED) is what Windows returns for an empty bin.
    assert "already empty" in _handle(_FakeShell32(-2147418113), monkeypatch)


def test_empty_recycle_bin_failure_reports_code(monkeypatch):
    out = _handle(_FakeShell32(-2147024894), monkeypatch)
    assert "failed" in out


def test_empty_recycle_bin_requires_confirmation(monkeypatch):
    shell = _FakeShell32(0)
    out = _handle(shell, monkeypatch, confirm=None)
    assert out == "Cancelled."          # destructive => must confirm first
    assert shell.calls == []            # and must not touch the bin


# ---------------------------------------------------------------------------
# 2. nova_vision.ask_gemini_vision fallback chain
# ---------------------------------------------------------------------------

class _FakeModels:
    """generate_content raises/returns the queued behaviors in order."""

    def __init__(self, behaviors):
        self.behaviors = list(behaviors)
        self.tried_models = []

    def generate_content(self, model=None, contents=None):
        self.tried_models.append(model)
        behavior = self.behaviors.pop(0)
        if isinstance(behavior, Exception):
            raise behavior
        return behavior


class _FakeClient:
    def __init__(self, behaviors):
        self.models = _FakeModels(behaviors)


class _FakeResponse:
    def __init__(self, text):
        self.text = text


def _with_client(monkeypatch, behaviors):
    client = _FakeClient(behaviors)
    monkeypatch.setattr(nova_vision, "get_gemini_client", lambda: client)
    return client


def test_vision_fallback_survives_high_demand_503(monkeypatch):
    # Primary 503s ("high demand") -> the chain must STILL try the next model,
    # which answers. (The old code broke out of the loop on non-404 errors.)
    client = _with_client(monkeypatch, [
        RuntimeError("503 UNAVAILABLE 'This model is currently experiencing "
                     "high demand. Spikes in demand are usually temporary.'"),
        _FakeResponse("OK"),
    ])
    out = nova_vision.ask_gemini_vision(object(), "ping")
    assert out == "OK"
    assert len(client.models.tried_models) == 2


def test_vision_fallback_skips_retired_models(monkeypatch):
    client = _with_client(monkeypatch, [
        RuntimeError("404 model not_found"),
        RuntimeError("404 ... no longer available ..."),
        _FakeResponse("recovered"),
    ])
    assert nova_vision.ask_gemini_vision(object(), "ping") == "recovered"
    assert len(client.models.tried_models) == 3


def test_vision_reports_error_when_every_model_fails(monkeypatch):
    _with_client(monkeypatch, [
        RuntimeError("503 high demand"),
        RuntimeError("503 high demand again"),
        RuntimeError("503 still overloaded"),
    ])
    assert nova_vision.ask_gemini_vision(object(), "ping") is None
    assert "503" in (nova_vision.get_last_gemini_error() or "")
