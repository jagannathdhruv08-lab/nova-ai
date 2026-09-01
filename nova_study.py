# ==========================================
# NOVA AI - STUDY WORKFLOW DATA MODULE
# ------------------------------------------
# Self-contained persistence for the PCM + Merchant Navy study workflow:
#   * subject palette + active subject
#   * error journal (with root cause + weak-topic tally)
#   * mock test tracker
#   * daily study schedule
#   * subject session log (minutes per subject)
# Pure data + helpers; no Tkinter. Safe to import from commands.py or gui.py.
# ==========================================

import json
import os
import sys
from datetime import date, timedelta

# Resolve a stable write location (mirrors memory.py / nova_storage).
if getattr(sys, "frozen", False):
    _DATA_DIR = os.path.dirname(sys.executable)
else:
    _DATA_DIR = os.path.dirname(os.path.abspath(__file__))
STUDY_FILE = os.path.join(_DATA_DIR, "nova_study_data.json")

# ---------------------------------------------------------------------------
# Subject palette (keys used everywhere else in Nova).
# ---------------------------------------------------------------------------
SUBJECTS = {
    "physics":   {"name": "Physics",       "color": "#185FA5", "icon": "🪐"},
    "chemistry": {"name": "Chemistry",     "color": "#D85A30", "icon": "🧪"},
    "maths":     {"name": "Maths",         "color": "#7C4AB7", "icon": "📐"},
    "english":   {"name": "English",       "color": "#3B6D11", "icon": "📖"},
    "mn":        {"name": "Merchant Navy", "color": "#0F6E56", "icon": "⚓"},
}


def subject_key(name: str) -> str:
    """Best-effort map from a user-typed subject name to a valid key."""
    n = (name or "").strip().lower()
    if n in SUBJECTS:
        return n
    # tolerate a few aliases
    aliases = {
        "phy": "physics", "physical": "physics",
        "chem": "chemistry", "organic": "chemistry",
        "math": "maths", "mathematics": "maths",
        "eng": "english",
        "merchant navy": "mn", "merchant navy prep": "mn", "navy": "mn",
    }
    return aliases.get(n, n if n in SUBJECTS else "general")


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------
def _default_data():
    return {
        "active_subject": "physics",
        "errors": [],          # {subject, topic, error, root_cause, date}
        "mock_tests": [],      # {name, score_pct, subject_scores: {...}, date}
        "sessions": [],        # {subject, minutes, date}
        "weekly_targets": {"hours": 40, "fitness_hrs": 6, "mn_hrs": 6},
    }


def _load():
    data = _default_data()
    try:
        if os.path.exists(STUDY_FILE):
            with open(STUDY_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            for k, v in _default_data().items():
                data.setdefault(k, v)
            if isinstance(loaded, dict):
                data.update(loaded)
    except Exception as exc:
        print("nova_study load failed:", exc)
    return data


def _save():
    try:
        with open(STUDY_FILE, "w", encoding="utf-8") as f:
            json.dump(_STUDY_DATA, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        print("nova_study save failed:", exc)


_STUDY_DATA = _load()


# ---------------------------------------------------------------------------
# Active subject
# ---------------------------------------------------------------------------
def set_active_subject(key: str) -> str:
    key = subject_key(key)
    if key in SUBJECTS:
        _STUDY_DATA["active_subject"] = key
        _save()
        return key
    return "general"


def get_active_subject() -> str:
    return _STUDY_DATA.get("active_subject", "physics")


def subject_color(key: str) -> str:
    return SUBJECTS.get(subject_key(key), {}).get("color", "#4f8cff")


# ---------------------------------------------------------------------------
# Error journal
# ---------------------------------------------------------------------------
def log_error(subject, topic, error, root_cause=""):
    """Add an error-journal entry and bump the weak-topic tally."""
    key = subject_key(subject)
    entry = {
        "subject": key,
        "topic": (topic or "").strip(),
        "error": (error or "").strip(),
        "root_cause": (root_cause or "").strip(),
        "date": str(date.today()),
    }
    _STUDY_DATA.setdefault("errors", []).append(entry)
    _STUDY_DATA["errors"] = _STUDY_DATA["errors"][-500:]
    _save()
    return entry


def list_error_journal(limit=20):
    errors = _STUDY_DATA.get("errors", [])
    return errors[-limit:][::-1]  # newest first


def weak_topics_list(limit=8):
    """Return (topic, subject, count) sorted by how often an error repeated."""
    counts = {}
    for e in _STUDY_DATA.get("errors", []):
        topic = (e.get("topic") or "untitled").strip()
        counts[topic] = counts.get(topic, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    subj_of = {}
    for e in _STUDY_DATA.get("errors", []):
        t = (e.get("topic") or "untitled").strip()
        if t not in subj_of:
            subj_of[t] = e.get("subject", "general")
    return [
        (topic, subj_of.get(topic, "general"), count)
        for topic, count in ranked[:limit]
    ]


def weekly_error_summary():
    """Top mistake patterns from the last 7 days."""
    week_ago = date.today() - timedelta(days=7)
    recent = [
        e for e in _STUDY_DATA.get("errors", [])
        if _parse_date(e.get("date")) >= week_ago
    ]
    if not recent:
        return {"count": 0, "top": []}
    counts = {}
    for e in recent:
        topic = (e.get("topic") or "untitled").strip()
        counts[topic] = counts.get(topic, 0) + 1
    top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:3]
    return {"count": len(recent), "top": top}


def _parse_date(s):
    try:
        return date.fromisoformat(str(s))
    except Exception:
        return date.today() - timedelta(days=999)


# ---------------------------------------------------------------------------
# Mock test tracker
# ---------------------------------------------------------------------------
def log_mock_score(score_pct, subject_scores=None, name=None):
    subject_scores = dict(subject_scores or {})
    entry = {
        "name": name or f"Mock #{len(_STUDY_DATA.get('mock_tests', [])) + 1}",
        "score_pct": float(score_pct),
        "subject_scores": subject_scores,
        "date": str(date.today()),
    }
    _STUDY_DATA.setdefault("mock_tests", []).append(entry)
    _save()
    return entry


def list_mock_tests():
    return list(_STUDY_DATA.get("mock_tests", []))


# ---------------------------------------------------------------------------
# Sessions (subject study timer)
# ---------------------------------------------------------------------------
def record_session(subject, minutes):
    key = subject_key(subject)
    _STUDY_DATA.setdefault("sessions", []).append({
        "subject": key,
        "minutes": int(minutes or 0),
        "date": str(date.today()),
    })
    _STUDY_DATA["sessions"] = _STUDY_DATA["sessions"][-2000:]
    _save()
    return key


def sessions_today():
    today = str(date.today())
    return [s for s in _STUDY_DATA.get("sessions", []) if s.get("date") == today]


def minutes_by_subject_today():
    out = {k: 0 for k in SUBJECTS}
    for s in sessions_today():
        out[s.get("subject")] = out.get(s.get("subject"), 0) + s.get("minutes", 0)
    return out


def total_focus_minutes_today():
    return sum(s.get("minutes", 0) for s in sessions_today())


# ---------------------------------------------------------------------------
# Weekly progress (rolling 7 days)
# ---------------------------------------------------------------------------
def weekly_progress():
    week_ago = date.today() - timedelta(days=7)
    mins = {k: 0 for k in SUBJECTS}
    total = 0
    mn = 0
    for s in _STUDY_DATA.get("sessions", []):
        if _parse_date(s.get("date")) >= week_ago:
            mins[s.get("subject")] = mins.get(s.get("subject"), 0) + s.get("minutes", 0)
            total += s.get("minutes", 0)
            if s.get("subject") == "mn":
                mn += s.get("minutes", 0)
    return {
        "hours": round(total / 60, 1),
        "mn_hours": round(mn / 60, 1),
        "hours_by_subject": {k: round(v / 60, 1) for k, v in mins.items()},
        "mock_count": len(_STUDY_DATA.get("mock_tests", [])),
        "error_count_week": weekly_error_summary()["count"],
    }


# ---------------------------------------------------------------------------
# Daily study schedule
# ---------------------------------------------------------------------------
def get_daily_schedule():
    """Return a list of (time, subject_key, description) for today."""
    return [
        ("06:30", "physics", "Mechanics: solve 3 motion problems"),
        ("08:30", "general", "Jog / physical exercise"),
        ("09:00", "chemistry", "Organic: reaction mechanisms"),
        ("11:00", "maths", "Algebra: practice drills"),
        ("13:00", "general", "Lunch break"),
        ("15:00", "english", "Vocabulary + reading drill"),
        ("17:00", "mn", "Navigation: charts & bearings"),
        ("20:00", "mn", "Merchant Navy theory / interview prep"),
    ]
