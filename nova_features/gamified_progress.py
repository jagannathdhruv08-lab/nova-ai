import os
import json
import re
import time
from datetime import date, timedelta

DATA_FILE = os.path.join(os.path.expanduser("~"), ".nova", "progress.json")

# XP needed to reach each level (cumulative)
LEVEL_THRESHOLDS = {
    1: 0, 2: 100, 3: 250, 4: 450, 5: 700,
    6: 1000, 7: 1400, 8: 1900, 9: 2500, 10: 3200,
}

ACHIEVEMENTS = [
    {"id": "first_chat", "icon": "💬", "title": "First Steps",
     "desc": "Start your first chat with Nova", "check": "chat_count >= 1"},
    {"id": "quiz_first", "icon": "🎯", "title": "Quiz Rookie",
     "desc": "Complete your first quiz", "check": "quizzes_completed >= 1"},
    {"id": "quiz_five", "icon": "🧠", "title": "Quiz Whiz",
     "desc": "Complete 5 quizzes", "check": "quizzes_completed >= 5"},
    {"id": "streak_3", "icon": "🔥", "title": "On Fire",
     "desc": "Reach a 3-day streak", "check": "best_streak >= 3"},
    {"id": "streak_7", "icon": "⚡", "title": "Unstoppable",
     "desc": "Reach a 7-day streak", "check": "best_streak >= 7"},
    {"id": "level_5", "icon": "🌟", "title": "Rising Star",
     "desc": "Reach Level 5", "check": "level >= 5"},
    {"id": "level_10", "icon": "👑", "title": "Nova Legend",
     "desc": "Reach Level 10", "check": "level >= 10"},
    {"id": "reminders_5", "icon": "⏰", "title": "Time Keeper",
     "desc": "Set 5 reminders", "check": "reminders_set >= 5"},
    {"id": "focus_60", "icon": "💪", "title": "Deep Focus",
     "desc": "Log 60 mins of focus", "check": "focus_minutes >= 60"},
    {"id": "export_first", "icon": "💾", "title": "Data Saver",
     "desc": "Export your Nova data", "check": "exports >= 1"},
]


def _default_data():
    return {
        "xp": 0, "level": 1, "chat_count": 0, "quizzes_completed": 0,
        "best_streak": 0, "current_streak": 0, "last_active": None,
        "reminders_set": 0, "focus_minutes": 0, "exports": 0,
        "unlocked_achievements": [], "joined": time.strftime("%Y-%m-%d"),
    }


def _load_data():
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            defaults = _default_data()
            defaults.update(data)
            return defaults
    except (FileNotFoundError, json.JSONDecodeError):
        return _default_data()


def _save_data(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _xp_for_level(level):
    return LEVEL_THRESHOLDS.get(level, level * 400)


_ACH_OP_MAP = {
    ">=": lambda v, n: v >= n,
    ">": lambda v, n: v > n,
    "<=": lambda v, n: v <= n,
    "<": lambda v, n: v < n,
    "==": lambda v, n: v == n,
}

# Fields the achievements are allowed to read. Using a whitelist means an
# unexpected/legacy check can never recover arbitrary names via eval().
_ACH_READABLE_FIELDS = {
    "level", "chat_count", "quizzes_completed", "best_streak",
    "reminders_set", "focus_minutes", "exports",
}

_ACH_EXPR_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(>=|<=|>|<|==)\s*(\d+(?:\.\d+)?)\s*$")


def _safe_achievement_check(check_expr, data):
    """Evaluate an achievement predicate WITHOUT eval().

    Strongly mirrors the old ``eval(ach["check"])`` behaviour but only
    recognises the exact ``field  op  number`` shape used by the hardcoded
    ACHIEVEMENTS list. Anything else fails closed (returns False) instead
    of being evaluated as code.
    """
    m = _ACH_EXPR_RE.match(str(check_expr or ""))
    if not m:
        return False
    field, op, num_str = m.group(1), m.group(2), m.group(3)
    if field not in _ACH_READABLE_FIELDS:
        return False
    value = data.get(field)
    if not isinstance(value, (int, float)):
        return False
    try:
        return _ACH_OP_MAP[op](value, float(num_str))
    except Exception:
        return False


def _update_level(data):
    level = 1
    for lvl in sorted(LEVEL_THRESHOLDS.keys()):
        if data["xp"] >= LEVEL_THRESHOLDS[lvl]:
            level = lvl
    data["level"] = level


def _check_achievements(data):
    newly_unlocked = []
    for ach in ACHIEVEMENTS:
        if ach["id"] in data["unlocked_achievements"]:
            continue
        try:
            if _safe_achievement_check(ach["check"], data):
                data["unlocked_achievements"].append(ach["id"])
                newly_unlocked.append(ach)
        except Exception:
            continue
    return newly_unlocked


def _update_streak(data):
    today = date.today().isoformat()
    if data.get("last_active") == today:
        return
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    if data.get("last_active") == yesterday:
        data["current_streak"] = data.get("current_streak", 0) + 1
    else:
        data["current_streak"] = 1
    data["best_streak"] = max(data.get("best_streak", 0), data["current_streak"])
    data["last_active"] = today


def update_progress(task_completed=False, goal_met=False):
    data = _load_data()
    _update_streak(data)
    xp_gain = 0
    if task_completed:
        xp_gain += 10
        data["focus_minutes"] = data.get("focus_minutes", 0) + 5
    if goal_met:
        xp_gain += 25
    if xp_gain == 0:
        data["chat_count"] = data.get("chat_count", 0) + 1
        xp_gain = 5
    data["xp"] += xp_gain
    old_level = data["level"]
    _update_level(data)
    newly = _check_achievements(data)
    _save_data(data)
    return {
        "success": True, "feature": "gamified_progress",
        "xp": data["xp"], "level": data["level"], "xp_gained": xp_gain,
        "leveled_up": data["level"] > old_level,
        "new_achievements": [{"icon": a["icon"], "title": a["title"]} for a in newly],
        "message": f"+{xp_gain} XP earned",
    }

def get_progress_status():
    data = _load_data()
    _update_streak(data)
    _save_data(data)
    level = data["level"]
    current_xp = data["xp"]
    threshold = _xp_for_level(level + 1)
    level_start = _xp_for_level(level)
    xp_into_level = current_xp - level_start
    xp_needed = threshold - level_start
    progress_pct = min(100, round((xp_into_level / xp_needed) * 100)) if xp_needed else 100
    return {
        "success": True, "feature": "gamified_progress",
        "level": level, "xp": current_xp,
        "xp_into_level": xp_into_level, "xp_needed": xp_needed,
        "progress_percent": progress_pct,
        "current_streak": data["current_streak"], "best_streak": data["best_streak"],
        "quizzes_completed": data["quizzes_completed"], "chat_count": data["chat_count"],
        "focus_minutes": data["focus_minutes"],
        "unlocked_count": len(data["unlocked_achievements"]),
        "message": f"Level {level} • {xp_into_level}/{xp_needed} XP • {progress_pct}% to next • {data['current_streak']}-day streak",
    }


def get_achievements_info():
    data = _load_data()
    _check_achievements(data)
    _save_data(data)
    unlocked_ids = set(data["unlocked_achievements"])
    locked, unlocked = [], []
    for ach in ACHIEVEMENTS:
        entry = {"id": ach["id"], "icon": ach["icon"], "title": ach["title"],
                 "desc": ach["desc"], "unlocked": ach["id"] in unlocked_ids}
        (unlocked if entry["unlocked"] else locked).append(entry)
    return {
        "success": True, "feature": "gamified_progress",
        "total": len(ACHIEVEMENTS), "unlocked_count": len(unlocked),
        "locked_count": len(locked), "unlocked": unlocked, "locked": locked,
        "message": f"{len(unlocked)}/{len(ACHIEVEMENTS)} achievements unlocked",
    }


def _record_quiz_completed():
    data = _load_data()
    data["quizzes_completed"] = data.get("quizzes_completed", 0) + 1
    data["xp"] += 15
    _update_level(data)
    _check_achievements(data)
    _save_data(data)


def _record_reminder_set():
    data = _load_data()
    data["reminders_set"] = data.get("reminders_set", 0) + 1
    data["xp"] += 5
    _update_level(data)
    _check_achievements(data)
    _save_data(data)


def _record_export():
    data = _load_data()
    data["exports"] = data.get("exports", 0) + 1
    data["xp"] += 5
    _update_level(data)
    _check_achievements(data)
    _save_data(data)


__version__ = "2.0.0"
__all__ = ["update_progress", "get_progress_status", "get_achievements_info",
           "_record_quiz_completed", "_record_reminder_set", "_record_export"]

