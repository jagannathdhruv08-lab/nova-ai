"""Tests for emoji_render._split_markdown (pure logic - no Tk needed),
calendar_sync.py, and telegram_bridge.py handler safety."""
import pytest

import emoji_render


# ===========================================================================
# markdown-lite parsing
# ===========================================================================
def test_bold_inline():
    segs = emoji_render._split_markdown("this is **important** stuff")
    tags = {t for _s, t in segs if t}
    assert "bold" in tags
    joined = "".join(s for s, _t in segs)
    assert "important" in joined


def test_h2_header_stripped_of_bold_markers():
    segs = emoji_render._split_markdown("## **Real-world analogy**")
    text = "".join(s for s, _t in segs)
    assert "##" not in text
    assert "**" not in text
    assert "Real-world analogy" in text
    assert any(t == "h2" for _s, t in segs)


def test_fenced_code_block_gets_codeblock_tag():
    md = "look:\n```python\nx = 1\ny = 2\n```\ndone"
    segs = emoji_render._split_markdown(md)
    code_lines = [s for s, t in segs if t == "codeblock"]
    assert any("x = 1" in s for s in code_lines)
    assert any("y = 2" in s for s in code_lines)
    # fences themselves are removed
    plain = "".join(s for s, _t in segs)
    assert "```" not in plain
    # content outside block stays untagged-ish
    assert any(s.startswith("done") for s, _t in segs)


def test_bullet_lists_become_dots():
    segs = emoji_render._split_markdown("- apples\n* mangoes")
    text = "".join(s for s, _t in segs)
    assert "•" in text
    assert "\n- " not in text and "- apples" not in text


def test_separator_line_becomes_bar():
    segs = emoji_render._split_markdown("---")
    assert any("━" in s for s, _t in segs)


def test_plain_text_untouched():
    segs = emoji_render._split_markdown("hello world\nsecond line")
    text = "".join(s for s, _t in segs)
    assert "hello world" in text and "second line" in text


# ===========================================================================
# calendar_sync
# ===========================================================================
@pytest.fixture
def isolated_calendar(tmp_path, monkeypatch):
    import calendar_sync as cs
    import nova_exams
    monkeypatch.setattr(nova_exams, "EXAMS_FILE", str(tmp_path / "exams.json"))
    ics_path = tmp_path / "cal.ics"
    yield cs, nova_exams, ics_path


def test_export_and_reimport_roundtrip(isolated_calendar):
    from datetime import date, timedelta
    cs, ne, ics_path = isolated_calendar
    future = (date.today() + timedelta(days=10)).isoformat()
    ne.set_exam("IMU CET", future)

    report = cs.export_calendar(path=str(ics_path))
    assert report["success"] is True
    assert report["events"] >= 1

    raw = ics_path.read_text(encoding="utf-8")
    assert raw.startswith("BEGIN:VCALENDAR")
    assert "SUMMARY:📝 Exam: IMU CET" in raw
    assert "BEGIN:VALARM" in raw                      # reminder embedded

    parsed = cs.import_ics(str(ics_path))
    assert parsed["success"] is True
    summaries = [e["summary"] for e in parsed["events"]]
    assert any("IMU CET" in s for s in summaries)


def test_import_missing_file(isolated_calendar):
    cs, _ne, ics_path = isolated_calendar
    result = cs.import_ics(str(ics_path) + ".missing")
    assert result["success"] is False


# ===========================================================================
# telegram bridge - handler surface (no network)
# ===========================================================================
class _FakeBridge:
    """Expose TelegramBridge.handle() without touching the network."""
    def __init__(self):
        from telegram_bridge import TelegramBridge
        self.real = TelegramBridge.__new__(TelegramBridge)

    def handle(self, text):
        return self.real.handle(text)


def test_telegram_help_and_unknown_command_safe():
    bridge = _FakeBridge()
    reply = bridge.handle("/help")
    assert "/ask" in reply
    # unknown slash commands fall through to ask -> brain error string
    reply2 = bridge.handle("/totallyunknowncommand")
    assert isinstance(reply2, str)


def test_telegram_never_routes_to_agent(monkeypatch):
    """Remote messages must never reach agent.py file actions."""
    import builtins
    real_import = builtins.__import__

    def guard(name, *args, **kwargs):
        if name == "agent":
            raise AssertionError("telegram bridge must not import agent")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guard)
    bridge = _FakeBridge()
    # a file-delete-looking request goes to the brain (ask), NOT agent
    reply = bridge.handle("/ask delete my files please")
    assert isinstance(reply, str)