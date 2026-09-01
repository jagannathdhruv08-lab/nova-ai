# ==========================================
# NOVA DAILY RECAP — Summary of Today's Activity
# ==========================================
import os
import json
import time
from datetime import date, datetime


def _try_load_progress():
    """Load gamified progress data."""
    try:
        path = os.path.join(os.path.expanduser("~"), ".nova", "progress.json")
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _try_load_reminders():
    """Load reminders data."""
    try:
        path = os.path.join(os.path.expanduser("~"), ".nova", "reminders.json")
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return []


def get_daily_recap():
    """Generate a summary report of today's Nova activity."""
    progress = _try_load_progress()
    reminders = _try_load_reminders()
    today = date.today().isoformat()

    # Gather stats
    stats = {
        "date": today,
        "weekday": datetime.now().strftime("%A"),
        "xp": progress.get("xp", 0),
        "level": progress.get("level", 1),
        "current_streak": progress.get("current_streak", 0),
        "best_streak": progress.get("best_streak", 0),
        "chat_count": progress.get("chat_count", 0),
        "quizzes_completed": progress.get("quizzes_completed", 0),
        "focus_minutes": progress.get("focus_minutes", 0),
        "reminders_set": progress.get("reminders_set", 0),
        "achievements_unlocked": len(progress.get("unlocked_achievements", [])),
    }

    active_reminders = sum(1 for r in reminders if not r.get("completed"))

    # Build a friendly summary message
    lines = []
    lines.append(f"📅 Daily Recap — {datetime.now().strftime('%A, %d %B %Y')}")
    lines.append(f"   • Level {stats['level']} • {stats['xp']} XP")
    lines.append(f"   • Streak: {stats['current_streak']} day(s) (best: {stats['best_streak']})")
    lines.append(f"   • Chats: {stats['chat_count']}")
    lines.append(f"   • Quizzes completed: {stats['quizzes_completed']}")
    lines.append(f"   • Focus minutes: {stats['focus_minutes']}")
    lines.append(f"   • Achievements unlocked: {stats['achievements_unlocked']}")
    lines.append(f"   • Active reminders: {active_reminders}")

    # Motivation
    if stats["focus_minutes"] >= 60:
        lines.append("🏆 Great focus today! Keep it up!")
    elif stats["focus_minutes"] >= 30:
        lines.append("👍 Solid effort — try for 60 minutes of focus tomorrow!")
    elif stats["level"] > 1 or stats["xp"] > 0:
        lines.append("💪 Good progress! Every session counts.")
    else:
        lines.append("🚀 Start your day — chat with Nova or try a quiz!")

    return {
        "success": True,
        "feature": "daily_recap",
        "stats": stats,
        "active_reminders": active_reminders,
        "message": "\n".join(lines),
        "generated_at": time.strftime("%H:%M:%S"),
    }


__version__ = "1.0.0"
__all__ = ["get_daily_recap"]