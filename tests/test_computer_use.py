"""Tests for nova_features/computer_use.py - semantic (name/place) control.

All tests are offline: parsing is pure string logic, and mouse/keyboard/
screen actions are monkeypatched so nothing real is clicked."""
import json
import sys
import types

import pytest

from nova_features import computer_use as cu


@pytest.fixture(autouse=True)
def reset_rate_state():
    cu._action_times.clear()
    yield
    cu._action_times.clear()


# ---------------------------------------------------------------------------
# Place vocabulary (pure math)
# ---------------------------------------------------------------------------
def test_zone_corners_and_center():
    assert cu.resolve_zone("top left corner") == cu._ZONES["top left corner"]
    assert cu.resolve_zone("bottom right corner")[0] > 0.9
    assert cu.resolve_zone("center") == (0.5, 0.5)
    assert cu.resolve_zone("taskbar")[1] > 0.95


def test_zone_filler_words_and_longest_match_wins():
    assert cu.resolve_zone("from the top left corner") == \
        cu._ZONES["top left corner"]
    assert cu.resolve_zone("top left corner area") == \
        cu._ZONES["top left corner"]
    assert cu.resolve_zone("kuch bhi random") is None
    assert cu.resolve_zone("") is None
    assert cu.resolve_zone(None) is None


def test_is_zone_phrase():
    assert cu.is_zone_phrase("top right corner")
    assert not cu.is_zone_phrase("search bar")


# ---------------------------------------------------------------------------
# Parser - name/place commands in, everything else out
# ---------------------------------------------------------------------------
def test_parse_describe():
    assert cu.parse_command("screen dekho") == ("describe", {})
    assert cu.parse_command("screen kya dikh raha hai") == ("describe", {})
    assert cu.parse_command("kya dikh raha hai") == ("describe", {})


def test_parse_go_home():
    assert cu.parse_command("come back on home screen") == ("go_home", {})
    assert cu.parse_command("wapas home screen pe jao") == ("go_home", {})
    assert cu.parse_command("show desktop") == ("go_home", {})
    # "home page kholo" has no go/come-back verb -> not computer use
    assert cu.parse_command("home page kholo") is None


def test_parse_click():
    action, kw = cu.parse_command("click on search bar")
    assert action == "click" and kw["target"] == "search bar"
    action, kw = cu.parse_command("search bar pe click karo")
    assert action == "click" and kw["target"] == "search bar"
    assert cu.parse_command("double click on profile")[1]["clicks"] == 2
    assert cu.parse_command("right click on desktop")[1]["button"] == "right"
    # normal chat must NOT be captured
    assert cu.parse_command("click kaise karta hai?") is None
    assert cu.parse_command("open youtube") is None

def test_parse_type():
    action, kw = cu.parse_command("type hello in search bar")
    assert (action, kw["text"], kw["into"]) == ("type", "hello", "search bar")
    action, kw = cu.parse_command("search bar me nova likho")
    assert (kw["text"], kw["into"]) == ("nova", "search bar")
    action, kw = cu.parse_command("write something in this search bar")
    assert kw["text"] == "something" and kw["into"] == "search bar"
    # questions are chat, not typing
    assert cu.parse_command("type karne me kitna time lagta hai") is None
    assert cu.parse_command("essay likho") is None


def test_parse_press_scroll_verify_and_reject_chat():
    assert cu.parse_command("press enter") == ("press_key", {"name": "enter"})
    assert cu.parse_command("escape dabao") == \
        ("press_key", {"name": "escape"})
    assert cu.parse_command("scroll up")[0] == "scroll"
    assert cu.parse_command("niche scroll karo") == \
        ("scroll", {"direction": "down"})
    assert cu.parse_command("verify ki search bar hai")[0] == "verify"
    assert cu.parse_command("hello nova") is None
    assert cu.parse_command("") is None


# ---------------------------------------------------------------------------
# Resolver - zone -> OCR -> vision pipeline (injected, no real screen)
# ---------------------------------------------------------------------------
def test_resolve_target_zone(monkeypatch):
    monkeypatch.setattr(cu, "_screen_size", lambda: (1000, 500))
    res = cu.resolve_target("top left corner", use_vision=False)
    assert res["how"] == "zone"
    assert res["point"] == (0.06 * 1000, 0.08 * 500)


def test_resolve_target_ocr(monkeypatch):
    class FakeImg:
        pass
    lines = [{"text": "Search", "box": (400, 100, 500, 130)}]
    monkeypatch.setattr(cu, "_ocr_lines", lambda img: lines)
    res = cu.resolve_target("search bar", img=FakeImg(), use_vision=False)
    assert res["how"] == "ocr" and res["point"] == (450.0, 115.0)


def test_resolve_target_last_paragraph(monkeypatch):
    class FakeImg:
        pass
    lines = [
        {"text": "first line", "box": (10, 10, 100, 30)},
        {"text": "middle line", "box": (10, 50, 100, 70)},
        {"text": "end line", "box": (10, 90, 100, 110)},
    ]
    monkeypatch.setattr(cu, "_ocr_lines", lambda img: lines)
    res = cu.resolve_target("last paragraph", img=FakeImg(), use_vision=False)
    assert res["point"] == (55.0, 100.0)


def test_resolve_target_vision_fallback(monkeypatch):
    monkeypatch.setattr(cu, "_screen_size", lambda: (1000, 500))
    monkeypatch.setattr(cu, "_grab", lambda region=None: object())
    monkeypatch.setattr(cu, "_resolve_by_vision",
                        lambda t: {"point": (100, 200), "how": "vision",
                                   "label": t})
    res = cu.resolve_target("mystery button", use_vision=True)
    assert res["how"] == "vision"

# ---------------------------------------------------------------------------
# Actions - all input monkeypatched, rate limit + audit real
# ---------------------------------------------------------------------------
def test_click_action(monkeypatch):
    moves = []
    monkeypatch.setattr(cu, "resolve_target",
                        lambda t: {"point": (10, 20), "how": "zone",
                                   "label": t})
    monkeypatch.setattr(cu, "_move_mouse", lambda x, y: moves.append((x, y)))
    monkeypatch.setattr(cu, "_mouse_click", lambda button="left": None)
    msg = cu.click("top left corner")
    assert msg.startswith("✅") and moves == [(10, 20)]


def test_click_unknown_target_is_friendly(monkeypatch):
    monkeypatch.setattr(cu, "resolve_target", lambda t: None)
    msg = cu.click("kuch nahi")
    assert msg.startswith("❌") and "nahi mila" in msg


def test_click_not_windows(monkeypatch):
    monkeypatch.setattr(cu.os, "name", "linux")
    assert "Windows" in cu.click("center")


def test_type_text(monkeypatch):
    typed = []
    monkeypatch.setattr(cu, "_type_chars", lambda t: typed.append(t) or True)
    monkeypatch.setattr(cu, "click",
                        lambda t, button="left", clicks=1: "✅ clicked")
    msg = cu.type_text("hello", into="search bar")
    assert typed == ["hello"] and "Type ho gaya" in msg
    assert cu.type_text("x" * 501).startswith("❌")
    assert cu.type_text("   ").startswith("Kya")


def test_type_text_into_failure_cancels(monkeypatch):
    monkeypatch.setattr(cu, "click",
                        lambda t, button="left", clicks=1: "❌ nahi mila")
    assert "cancel" in cu.type_text("hello", into="search bar")


def test_press_key_validation(monkeypatch):
    monkeypatch.setattr(cu, "_press_physical_key", lambda k: None)
    assert cu.press_key("enter").startswith("⌨️")
    msg = cu.press_key("f13")
    assert msg.startswith("❌") and "Known keys" in msg


def test_rate_limit_blocks(monkeypatch):
    monkeypatch.setattr(cu, "_RATE_MAX_ACTIONS", 2)
    monkeypatch.setattr(cu, "resolve_target",
                        lambda t: {"point": (5, 5), "how": "zone",
                                   "label": t})
    monkeypatch.setattr(cu, "_move_mouse", lambda x, y: None)
    monkeypatch.setattr(cu, "_mouse_click", lambda button="left": None)
    assert cu.click("center").startswith("✅")
    assert cu.click("center").startswith("✅")
    assert "Rate limit" in cu.click("center")


def test_audit_log_written(tmp_path, monkeypatch):
    audit_file = tmp_path / "cu_audit.log"
    monkeypatch.setattr(cu, "AUDIT_LOG", audit_file)
    monkeypatch.setattr(cu, "resolve_target", lambda t: None)
    cu.click("nothing-here")
    entry = json.loads(audit_file.read_text(encoding="utf-8").splitlines()[0])
    assert entry["action"] == "rejected_unknown_target"


# ---------------------------------------------------------------------------
# Dispatcher + vision JSON parsing + home
# ---------------------------------------------------------------------------
def test_execute_command_dispatch(monkeypatch):
    monkeypatch.setitem(cu._ACTIONS, "describe", lambda: "desc-reply")
    assert cu.execute_command("screen dekho") == "desc-reply"
    assert cu.execute_command("normal chat message") is None


def test_execute_command_action_error_is_friendly(monkeypatch):
    def boom(target, button="left", clicks=1):
        raise RuntimeError("mouse exploded")
    monkeypatch.setitem(cu._ACTIONS, "click", boom)
    msg = cu.execute_command("click on x")
    assert msg.startswith("❌") and "mouse exploded" not in msg


def test_vision_percentage_parsing(monkeypatch):
    monkeypatch.setattr(cu, "_grab", lambda region=None: object())
    monkeypatch.setattr(cu, "_gemini", lambda: (
        lambda img, prompt:
            '{"found": true, "left": 40, "top": 40, "right": 60, '
            '"bottom": 60, "label": "OK"}'))
    monkeypatch.setattr(cu, "_screen_size", lambda: (1000, 500))
    res = cu._resolve_by_vision("ok button")
    assert res["point"] == (500.0, 250.0) and res["how"] == "vision"


def test_vision_rejects_out_of_range_box(monkeypatch):
    monkeypatch.setattr(cu, "_grab", lambda region=None: object())
    monkeypatch.setattr(cu, "_gemini", lambda: (
        lambda img, prompt:
            '{"found": true, "left": 40, "top": 400, "right": 60, '
            '"bottom": 60}'))
    assert cu._resolve_by_vision("ok button") is None


def test_go_home_presses_windows_d(monkeypatch):
    pressed = []
    fake_kb = types.ModuleType("keyboard")
    fake_kb.press_and_release = lambda k: pressed.append(k)
    monkeypatch.setitem(sys.modules, "keyboard", fake_kb)
    monkeypatch.setattr(cu, "_verify_vision", lambda q: True)
    msg = cu.go_home()
    assert pressed == ["windows+d"]
    assert "Home screen" in msg and "verified" in msg


def test_capabilities_catalog():
    caps = cu.get_capabilities()
    assert caps["feature"] and len(caps["controls"]) >= 5
    assert "no raw coordinates" in caps["safety"]


