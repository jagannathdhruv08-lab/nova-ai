# ==========================================
# NOVA ANALYTICS - study analytics aggregator
# ------------------------------------------
# Combines three existing data sources into one picture of study health:
#   1. Focus sessions   -> own log file (record_study_session), plus
#                          today's minutes from nova_storage dashboard
#   2. SRS reviews      -> nova_srs_cards.json review history
#   3. Exams            -> nova_exams.json urgency
#
# Everything returns plain dicts / chat-friendly strings so the GUI,
# intents, coach prompts and the Telegram bridge can all reuse it.
# ==========================================

import json
import logging
import os
from datetime import date, datetime, timedelta

from nova_storage import writable_data_path

log = logging.getLogger("nova.analytics")

__version__ = "1.0.0"

ANALYTICS_FILE = writable_data_path("nova_study_log.json")


def _load_log():
    try:
        if os.path.exists(ANALYTICS_FILE):
            with open(ANALYTICS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("sessions", [])
                return data
    except Exception as exc:
        log.error("analytics load failed: %s", exc)
    return {"sessions": []}


def _save_log(data):
    try:
        with open(ANALYTICS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        return True
    except Exception as exc:
        log.error("analytics save failed: %s", exc)
        return False


def record_study_session(subject, minutes, source="focus"):
    """Log one completed study session (subject-tagged)."""
    subject = str(subject or "general").strip().lower()[:40]
    try:
        minutes = max(1, min(600, int(minutes)))
    except (TypeError, ValueError):
        return {"success": False, "message": "Minutes invalid."}
    data = _load_log()
    now = datetime.now()
    data["sessions"].append({
        "subject": subject,
        "minutes": minutes,
        "source": str(source)[:20],
        "date": now.date().isoformat(),
        "hour": now.hour,
    })
    data["sessions"] = data["sessions"][-5000:]
    _save_log(data)
    return {
        "success": True,
        "message": f"📖 Logged {minutes} min of '{subject}'.",
    }


def sessions_last_days(days=7):
    """Sessions within the last *days* days (inclusive of today)."""
    cutoff = (date.today() - timedelta(days=days - 1)).isoformat()
    return [s for s in _load_log()["sessions"] if s.get("date", "") >= cutoff]


def minutes_by_subject(days=None, subject=None):
    """{subject: total_minutes}, optionally windowed."""
    sessions = (_load_log()["sessions"] if days is None
                else sessions_last_days(days))
    totals = {}
    for s in sessions:
        if subject and s.get("subject") != subject:
            continue
        key = s.get("subject", "general")
        totals[key] = totals.get(key, 0) + int(s.get("minutes", 0))
    return totals


def daily_minutes_last_week():
    """[{date, minutes}] for the last 7 days - ready for charting."""
    today = date.today()
    per_day = {}
    for s in _load_log()["sessions"]:
        key = s.get("date", "")
        per_day[key] = per_day.get(key, 0) + int(s.get("minutes", 0))
    out = []
    for offset in range(6, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        out.append({"date": day, "minutes": per_day.get(day, 0)})
    return out


def best_study_hour():
    """Hour-of-day (0-23) with most logged minutes; None without data."""
    hours = {}
    for s in _load_log()["sessions"]:
        hour = s.get("hour")
        if isinstance(hour, int) and 0 <= hour <= 23:
            hours[hour] = hours.get(hour, 0) + int(s.get("minutes", 0))
    if not hours:
        return None
    return max(hours, key=hours.get)

def _dashboard_today_focus():
    try:
        import nova_storage
        return int(nova_storage.dashboard_data.get("focus_minutes_today", 0))
    except Exception:
        return 0


def _streak_length():
    try:
        import nova_storage
        days = set(nova_storage.dashboard_data.get("streak_days", []))
        streak = 0
        day = date.today()
        while day.isoformat() in days:
            streak += 1
            day -= timedelta(days=1)
        return streak
    except Exception:
        return 0


def overview(days=7):
    """Aggregate snapshot dict combining all sources."""
    try:
        import nova_srs
        stats = nova_srs.srs_stats()
        cutoff = (date.today() - timedelta(days=days - 1)).isoformat()
        reviews_recent = sum(
            1 for r in nova_srs._load().get("reviews", [])
            if r.get("date", "") >= cutoff)
    except Exception:
        stats = {"total": 0, "due_today": 0, "learned": 0,
                 "avg_ease": 0, "subjects": {}}
        reviews_recent = 0

    try:
        import nova_exams
        next_exam = next(iter(nova_exams.exams_with_days()), None)
    except Exception:
        next_exam = None

    week_total = sum(s.get("minutes", 0) for s in sessions_last_days(days))
    return {
        "week_minutes": week_total,
        "week_hours": round(week_total / 60, 1),
        "today_dashboard_minutes": _dashboard_today_focus(),
        "streak_days": _streak_length(),
        "minutes_by_subject": minutes_by_subject(days=days),
        "daily_minutes": daily_minutes_last_week(),
        "best_hour": best_study_hour(),
        "cards": stats,
        "reviews_last_week": reviews_recent,
        "next_exam": next_exam,
    }


def analytics_report(days=7):
    """Hinglish chat-friendly analytics summary."""
    snap = overview(days=days)
    lines = [f"📊 Study report (last {days} days):\n"]

    hours = snap["week_hours"]
    lines.append(f"⏱️ Total focus: {snap['week_minutes']} min (~{hours} hrs)")
    lines.append(f"🔥 Streak: {snap['streak_days']} day(s)")
    lines.append(f"Aaj ka focus: {snap['today_dashboard_minutes']} min")

    subjects = snap["minutes_by_subject"]
    if subjects:
        top = sorted(subjects.items(), key=lambda kv: kv[1], reverse=True)
        lines.append("\n📚 Subject-wise:")
        for subj, mins in top[:5]:
            bar = "█" * max(1, min(10, mins // 30))
            lines.append(f"• {subj}: {mins} min {bar}")
    else:
        lines.append("\n📚 Abhi koi session log nahi hua - focus timer use karo!")

    cards = snap["cards"]
    if cards["total"]:
        lines.append(f"\n🃏 Flashcards: {cards['total']} total | "
                     f"{cards['due_today']} due today | {cards['learned']} learned")
    if snap["best_hour"] is not None:
        h = snap["best_hour"]
        ampm = "AM" if h < 12 else "PM"
        h12 = h if 1 <= h <= 12 else (h - 12 or 12)
        lines.append(f"⏰ Best study hour so far: {h12} {ampm}")

    nxt = snap.get("next_exam")
    if nxt and 0 <= nxt["days_left"] <= 90:
        lines.append(f"\n🎯 Next exam: {nxt['name']} — {nxt['days_left']} din baaki!")

    return "\n".join(lines)


__all__ = ["record_study_session", "sessions_last_days", "minutes_by_subject",
           "daily_minutes_last_week", "best_study_hour", "overview",
           "analytics_report", "ANALYTICS_FILE"]