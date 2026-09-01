# ==========================================
# NOVA DAILY — daily tracking, planning and self-upgrade
# ==========================================
# On each NEW day Nova:
#   1. Records yesterday's performance (tasks done, goals done) into a
#      permanent daily_log so it can track streaks / trends over days.
#   2. Regenerates today's routine goals & tasks (reuses nova_routine).
#   3. Builds a short "Aaj ka plan" using the LLM (grounded in yesterday's
#      numbers + the user's saved memories), so Nova actively plans the day.
#   4. "Upgrades" goals/tasks — if yesterday was fully completed, Nova adds
#      a bonus challenge for today so the plan keeps getting harder as you
#      improve. All in one fast, non-blocking daily pass.
# ==========================================

from datetime import date

from nova_storage import dashboard_data, save_dashboard_data
from nova_routine import sync_routine_for_today
from memory import memory_facts_block

try:
    from brain import ask_nova
    _BRAIN_OK = True
except Exception:
    _BRAIN_OK = False


def _safe_today_str():
    return str(date.today())


def _snapshot_today_stats():
    """Which of today's goals/tasks are complete right now + nutrition."""
    tasks = dashboard_data.get("tasks", [])
    goals = dashboard_data.get("goals", [])
    return {
        "tasks_done": sum(1 for t in tasks if t.get("done")),
        "tasks_total": len(tasks),
        "goals_done": sum(1 for g in goals if g.get("done")),
        "goals_total": len(goals),
        "date": _safe_date_str(),
    }


def _safe_date_str():
    try:
        from nova_nutrition import _get_today_key  # may not exist
        return str(date.today())
    except Exception:
        return str(date.today())


def _record_yesterday():
    """Store yesterday's completion (measured from the still-old dashboard
    data, before today's routine re-sync overwrites it) into a permanent log."""
    tasks = dashboard_data.get("tasks", [])
    goals = dashboard_data.get("goals", [])
    entry = {
        "date": dashboard_data.get("routine_synced_date") or "unknown",
        "tasks_done": sum(1 for t in tasks if t.get("done")),
        "tasks_total": len(tasks),
        "goals_done": sum(1 for g in goals if g.get("done")),
        "goals_total": len(goals),
    }
    log = dashboard_data.setdefault("daily_log", [])
    # Avoid duplicating the same day if this ever runs twice.
    if not any(r.get("date") == entry["date"] for r in log):
        log.append(entry)
    dashboard_data["daily_log"] = log[-365:]
    save_dashboard_data()
    return entry


def _has_full_completion(prev):
    """True when yesterday's routine was fully ticked off."""
    t = prev.get("tasks_total", 0)
    g = prev.get("goals_total", 0)
    td = prev.get("tasks_done", 0)
    gd = prev.get("goals_done", 0)
    return t > 0 and td == t and g > 0 and gd == g


def _upgrade_for_today(prev_entry):
    """Add a bonus challenge goal today if yesterday was fully completed —
    so the plan naturally gets harder as the user improves."""
    if not _has_full_completion(prev_entry):
        return
    goals = dashboard_data.get("goals", [])
    # Don't stack a second bonus if one already exists from earlier.
    if any(g.get("bonus_upgrade") for g in goals):
        return
    bonus = {
        "text": "Bonus upgrade: 1 extra revision / Deep Work block (20-30 min)",
        "done": False,
        "routine": True,
        "bonus_upgrade": True,
    }
    dashboard_data.setdefault("goals", []).append(bonus)


def _make_plan(prev_entry):
    """Ask the LLM for a short, realistic 'today plan' grounded in
    yesterday's performance + saved memories. Falls back to a deterministic
    plan if the LLM is unavailable / rate-limited (keeps the app fast)."""
    mem = memory_facts_block()
    worth = f"{prev_entry.get('tasks_done', 0)}/{prev_entry.get('tasks_total', 0)}"
    prompt = (
        "Tum Nova ho - user ka daily study/fitness coach for Merchant Navy prep. "
        f"Kal ka performance: {worth} tasks, {prev_entry.get('goals_done',0)}/{prev_entry.get('goals_total',0)} goals. "
        f"{mem or ''}"
        "Ek Chhota (2-3 line) 'Aaj ka plan' banao - Hinglish mein, positive, actionable: "
        "pehle kya karna hai, main priority subah kya, shaam ko kya. Lecture mat dena, bas plan."
    )
    if _BRAIN_OK:
        try:
            result = ask_nova(prompt)
            if isinstance(result, str) and result.strip():
                return result.strip()
        except Exception:
            pass
    # Deterministic fallback — always works offline, no lag.
    return (
        "Aaj ka plan (auto): subah pehle routine (wake-up, run, breakfast) pochh karo, "
        "phir apne bache pending goals fix karo. Ek study block pe deep focus rakho, "
        "aur raat ko aaj ki progress review karo. 🎯"
    )


def run_daily(report_only=False):
    """Top-level daily routine call. Once per day:
    - logs yesterday
    - regenerates today's routine tasks/goals
    - builds today's plan + applies (bonus) upgrades
    Returns the short human message (for a chat bubble) or None if already done.
    """
    today = _safe_date_str()
    if dashboard_data.get("daily_date") == today and not report_only:
        return None  # already handled today

    # 1) Snapshot yesterday (dashboard still holds it before today's re-sync).
    prev = _record_yesterday()

    # 2) Regenerate today's routine goals/tasks.
    try:
        sync_routine_for_today(force=True)
    except Exception:
        pass

    # 3) Build today's plan + apply bonus upgrade.
    plan_text = _make_plan(prev)
    dashboard_data["daily_plan"] = {"date": today, "plan": plan_text}
    dashboard_data["daily_date"] = today

    # 4) Apply bonus upgrade for today (if yesterday was fully completed).
    _upgrade_for_today(prev)

    save_dashboard_data()

    return f"📅 Aaj ka plan ready:\n{plan_text}"