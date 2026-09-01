"""Tests for nova_srs.py - SM-2 scheduling + card lifecycle.

All card storage is redirected to tmp_path so real study data is safe.
"""
from datetime import date, timedelta

import pytest

import nova_srs


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch, tmp_path):
    monkeypatch.setattr(nova_srs, "SRS_FILE", str(tmp_path / "srs.json"))
    yield


def _fresh_card():
    return nova_srs.add_card("What is SM-2?", "A spaced repetition algorithm",
                             subject="testing")


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------
def test_add_and_get_card():
    card = _fresh_card()
    fetched = nova_srs.get_card(card["id"])
    assert fetched["front"] == "What is SM-2?"
    assert fetched["ease"] == 2.5
    assert fetched["repetitions"] == 0
    assert fetched["subject"] == "testing"


def test_new_card_is_due_today():
    card = _fresh_card()
    due = nova_srs.due_cards()
    assert any(c["id"] == card["id"] for c in due)


def test_delete_card():
    card = _fresh_card()
    assert nova_srs.delete_card(card["id"]) is True
    assert nova_srs.get_card(card["id"]) is None


def test_bulk_add_skips_empty_pairs():
    made = nova_srs.add_cards([("q1", "a1"), ("", "nope"), ("q3", "")])
    assert len(made) == 1


# ---------------------------------------------------------------------------
# SM-2 transitions
# ---------------------------------------------------------------------------
def test_lapse_resets_repetitions():
    card = _fresh_card()
    card["repetitions"] = 4
    card["interval_days"] = 15
    updated, interval = nova_srs.sm2_update(card, quality=2)
    assert updated["repetitions"] == 0
    assert updated["lapses"] == 1
    assert interval == 1


def test_first_graduation_one_day():
    card = _fresh_card()
    _, interval = nova_srs.sm2_update(card, quality=4)
    assert card["repetitions"] == 1
    assert interval == 1


def test_second_graduation_six_days():
    card = _fresh_card()
    nova_srs.sm2_update(card, quality=4)
    _, interval = nova_srs.sm2_update(card, quality=4)
    assert interval == 6


def test_interval_grows_by_ease_after_second():
    card = _fresh_card()
    nova_srs.sm2_update(card, quality=5)   # reps 1, ease up
    nova_srs.sm2_update(card, quality=5)   # reps 2, interval 6
    _, interval = nova_srs.sm2_update(card, quality=5)   # reps 3
    assert interval > 6
    expected_due = date.today() + timedelta(days=interval)
    assert card["due"] == expected_due.isoformat()


def test_ease_never_below_minimum():
    card = _fresh_card()
    for _ in range(10):
        nova_srs.sm2_update(card, quality=3)   # hardest passing grade
    assert card["ease"] >= nova_srs._EASE_MIN


def test_quality_clamped():
    card = _fresh_card()
    _, interval = nova_srs.sm2_update(card, quality=99)
    assert interval >= 1   # treated as max quality, no crash
    nova_srs.sm2_update(card, quality=-5)   # treated as lapse
    assert card["repetitions"] == 0


# ---------------------------------------------------------------------------
# review flow + stats
# ---------------------------------------------------------------------------
def test_review_card_logs_review():
    card = _fresh_card()
    updated, msg = nova_srs.review_card(card["id"], 5)
    assert updated["review_count"] == 1
    assert "next review" in msg.lower()
    reviews = nova_srs._load()["reviews"]
    assert reviews[-1]["quality"] == 5


def test_review_unknown_card():
    _, msg = nova_srs.review_card("deadbeef", 4)
    assert "not found" in msg.lower()


def test_grade_from_text_parsing():
    assert nova_srs.grade_from_text("grade abc123 4") == ("abc123", 4)
    assert nova_srs.grade_from_text("GRADE ABCDEF 5") == ("abcdef", 5)
    assert nova_srs.grade_from_text("grade zzz 9") is None
    assert nova_srs.grade_from_text("hello world") is None


def test_stats_counts():
    _fresh_card()
    stats = nova_srs.srs_stats()
    assert stats["total"] == 1
    assert stats["due_today"] == 1
    assert stats["subjects"].get("testing") == 1