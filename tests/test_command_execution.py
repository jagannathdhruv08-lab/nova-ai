"""Tests for nova_features/command_execution.py - the safe whitelist."""
import json

import pytest

from nova_features import command_execution as ce


@pytest.fixture(autouse=True)
def reset_rate_state():
    ce._action_times.clear()
    yield
    ce._action_times.clear()


def test_unknown_command_rejected():
    result = ce.execute_safe_command("format c:")
    assert result["success"] is False
    assert "Available" in result["message"]


def test_empty_command_rejected():
    assert ce.execute_safe_command("")["success"] is False


def test_whitelist_catalog_lists_all_commands():
    catalog = ce.get_available_commands()
    assert catalog["count"] == len(ce.SAFE_COMMANDS)
    for name in ("battery_status", "network_status", "open_folder"):
        assert name in catalog["commands"]


def test_open_folder_rejects_unknown_folder():
    result = ce.execute_safe_command("open_folder", {"folder": "system32"})
    assert result["success"] is False


def test_network_status_runs_and_reports_state():
    result = ce.execute_safe_command("network_status")
    # works online or off - must always answer with a message + success flag
    assert isinstance(result.get("online"), bool)
    assert "Network" in result["message"]


def test_rate_limit_blocks_after_threshold(monkeypatch):
    monkeypatch.setattr(ce, "_RATE_MAX_ACTIONS", 3)
    results = [ce.execute_safe_command("network_status") for _ in range(5)]
    assert all(r["success"] for r in results[:3])
    blocked = results[3]
    assert blocked["success"] is False
    assert "Rate limit" in blocked["message"]


def test_audit_log_written(tmp_path, monkeypatch):
    audit_file = tmp_path / "audit.log"
    monkeypatch.setattr(ce, "AUDIT_LOG", audit_file)
    ce.execute_safe_command("definitely_not_a_command")
    ce.execute_safe_command("network_status")

    lines = audit_file.read_text(encoding="utf-8").splitlines()
    entries = [json.loads(l) for l in lines if l.strip()]
    actions = [e["action"] for e in entries]
    assert "rejected_unknown" in actions
    assert any(a.startswith(("network_status")) or a == "network_status"
               for a in actions)


def test_handler_exception_becomes_generic_message(monkeypatch):
    def boom(args):
        raise RuntimeError("disk exploded")
    monkeypatch.setitem(ce.SAFE_COMMANDS,
                        "battery_status", (boom, "test handler"))
    result = ce.execute_safe_command("battery_status")
    assert result["success"] is False
    assert "RuntimeError" in result["message"]
    assert "disk exploded" not in result["message"]   # no leak of internals