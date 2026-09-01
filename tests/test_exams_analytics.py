"""Tests for nova_exams.py + nova_analytics.py (isolated storage)."""
from datetime import date, timedelta

import pytest

import nova_analytics
import nova_exams


@pytest.fixture(autouse=True)
def isolated_files(monkeypatch, tmp_path):
    monkeypatch.setattr(nova_exams, "EXAMS_FILE", str(tmp_path / "exams.json"))
    monkeypatch.setattr(nova_analytics, "ANALYTICS_FILE",
                        str(tmp_path / "study_log.json"))
    yield


# ---------------------------------------------------------------------------
# exams
# ---------------------------------------------------------------------------
def test_set_exam_future_date():
    future = (date.today() + timedelta(days=12)).isoformat()
    msg = nova_exams.set_exam("IMU CET", future)
    assert "IMU CET" in msg
    exams = nova_exams.exams_with_days()
    assert exams[0]["days_left"] == 12


def test_urgency_colours():
    assert nova_exams._urgency(3).startswith("🔴")
    assert nova_exams._urgency(20).startswith("🟡")
    assert nova_exams._urgency(90).startswith("🟢")


def test_set_exam_rejects_bad_date():
    msg = nova_exams.set_exam("Weird", "not-a-date")
    assert "samajh nahi" in msg or "format" in msg.lower()


def test_delete_exam():
    future = (date.today() + timedelta(days=5)).isoformat()
    nova_exams.set_exam("Physics test", future)
    removal = nova_exams.delete_exam("physics TEST")   # case-insensitive
    assert "removed" in removal.lower() or "🗑️" in removal
    assert nova_exams.exams_with_days() == []


def test_overview_text_sorted_soonest_first():
    d30 = (date.today() + timedelta(days=30)).isoformat()
    d2 = (date.today() + timedelta(days=2)).isoformat()
    nova_exams.set_exam("Later exam", d30)
    nova_exams.set_exam("Sooner exam", d2)
    text = nova_exams.exams_overview_text()
    assert text.index("Sooner exam") < text.index("Later exam")


def test_context_block_mentions_upcoming():
    future = (date.today() + timedelta(days=9)).isoformat()
    nova_exams.set_exam("IMU CET", future)
    block = nova_exams.exams_context_block()
    assert "IMU CET" in block and "9 days left" in block


def test_context_block_empty_without_exams():
    assert nova_exams.exams_context_block() == ""


# ---------------------------------------------------------------------------
# analytics
# ---------------------------------------------------------------------------
def _session(minutes, subject="physics", days_ago=0, hour=21):
    day = (date.today() - timedelta(days=days_ago)).isoformat()
    return {"subject": subject, "minutes": minutes,
            "source": "focus", "date": day, "hour": hour}


def test_record_session_clamps_minutes():
    # absurd values clamp into a sane range instead of failing
    ok = nova_analytics.record_study_session("maths", 99999)
    assert ok["success"] is True
    sessions = nova_analytics._load_log()["sessions"]
    assert sessions[-1]["minutes"] == 600
    bad = nova_analytics.record_study_session("maths", "not-a-number")
    assert bad["success"] is False


def test_minutes_by_subject_window():
    data = {"sessions": [
        _session(60, "physics", days_ago=1),
        _session(30, "physics", days_ago=0),
        _session(120, "chemistry", days_ago=10),   # outside 7-day window
    ]}
    nova_analytics._save_log(data)
    totals = nova_analytics.minutes_by_subject(days=7)
    assert totals["physics"] == 90
    assert "chemistry" not in totals


def test_daily_minutes_last_week_shape():
    nova_analytics._save_log({"sessions": [_session(25)]})
    daily = nova_analytics.daily_minutes_last_week()
    assert len(daily) == 7
    assert daily[-1]["date"] == date.today().isoformat()
    assert sum(d["minutes"] for d in daily) == 25


def test_best_study_hour():
    nova_analytics._save_log({"sessions": [
        _session(10, hour=6), _session(50, hour=6), _session(20, hour=22),
    ]})
    assert nova_analytics.best_study_hour() == 6


def test_report_contains_key_sections():
    nova_analytics._save_log({"sessions": [_session(90, "physics")]})
    report = nova_analytics.analytics_report()
    assert "Study report" in report
    assert "physics" in report