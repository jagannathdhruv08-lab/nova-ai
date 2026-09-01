# ==========================================
# NOVA AI - MERCHANT NAVY DAILY ROUTINE
# Turns the fixed study/fitness/routine plan into REAL goals & tasks
# that regenerate every day automatically, with alarms at the right
# times (using the same reminder engine gui.py already has for
# Goals/Tasks - no new alarm system needed, just new data feeding it).
#
# How it plugs in:
#   - DAILY_ROUTINE items (clock-based) become entries in
#     dashboard_data["tasks"], each with a "remind_at" timestamp for
#     today. gui.py's existing check_reminders() loop already scans
#     tasks for remind_at and fires a notification + speaks it - so
#     alarms "just work" once these tasks exist, no extra code needed
#     in gui.py for the alarm part.
#   - WEEKLY_SUBJECTS (today's focus subjects) and DAILY_HABITS
#     (run/practice/vocab targets with no fixed clock time) become
#     checklist entries in dashboard_data["goals"].
#   - Everything this module adds is tagged {"routine": True} so it
#     can tell its own entries apart from things you added by hand,
#     and cleanly replace yesterday's routine with today's without
#     touching anything you typed in yourself.
# ==========================================

from datetime import date

from nova_storage import dashboard_data, save_dashboard_data

# ==========================================
# THE ROUTINE DATA (from your study plan)
# ==========================================

# Fixed daily clock schedule - (time "HH:MM" 24hr, activity). These
# get an alarm/reminder at that exact time every day.
DAILY_ROUTINE = [
    ("05:30", "Wake up, drink 500ml water"),
    ("05:40", "Stretching + Running (20-30 min)"),
    ("06:10", "Push-ups, Squats, Plank, Pull-up practice"),
    ("06:40", "Bath & high-protein breakfast"),
    ("17:00", "Physics study block"),
    ("18:30", "Mathematics study block"),
    ("19:45", "Dinner"),
    ("20:15", "Chemistry study block"),
    ("21:00", "English Grammar + Speaking practice"),
    ("21:30", "Merchant Navy preparation (30-45 min)"),
    ("22:15", "Sleep"),
]

# Which subjects/focus areas to highlight each weekday (from the
# Weekly Study Plan table). No fixed alarm time - shown as today's
# goals/checklist instead.
WEEKLY_SUBJECTS = {
    "Monday": ["Physics focus", "Merchant Navy English"],
    "Tuesday": ["Mathematics focus", "Reasoning practice"],
    "Wednesday": ["Chemistry focus", "Navigation basics"],
    "Thursday": ["Physics focus", "Interview speaking practice"],
    "Friday": ["Mathematics focus", "Current affairs"],
    "Saturday": ["Full revision", "Mock test"],
    "Sunday": ["Weekly revision", "Swimming", "Fitness assessment"],
}

# Recurring daily targets that aren't tied to a specific clock time -
# shown as goals/checkboxes every day regardless of weekday.
DAILY_HABITS = [
    "Run 2-3 km",
    "20-30 Maths practice questions",
    "Learn 5 new English words",
    "Read 1 English news article",
]

# Month-by-month Merchant Navy topics - informational only for now
# (not auto-injected daily; exposed here in case you want a monthly
# reminder added later).
MONTHLY_MERCHANT_NAVY = {
    1: ["Merchant Navy structure", "Deck Department", "Ship types", "Ship parts", "Maritime English"],
    2: ["Navigation basics", "Safety equipment", "Flags", "Compass"],
    3: ["IMU-CET aptitude", "Interview questions", "Sponsorship preparation"],
}


def _today_weekday_name():
    return date.today().strftime("%A")


def _clear_previous_routine_entries():
    """Remove yesterday's auto-generated routine items, but never
    touch anything the user typed in themselves."""
    dashboard_data["tasks"] = [t for t in dashboard_data.get("tasks", []) if not t.get("routine")]
    dashboard_data["goals"] = [g for g in dashboard_data.get("goals", []) if not g.get("routine")]


def sync_routine_for_today(force=False):
    """Regenerates today's routine tasks/goals if it hasn't been done
    yet today. Safe to call often (e.g. every reminder-check tick) -
    it only does real work once per day. Returns True if it actually
    (re)generated anything, False if today was already synced."""
    today_str = str(date.today())
    if not force and dashboard_data.get("routine_synced_date") == today_str:
        return False

    _clear_previous_routine_entries()

    for time_str, activity in DAILY_ROUTINE:
        dashboard_data["tasks"].append({
            "text": activity,
            "done": False,
            "remind_at": f"{today_str} {time_str}",
            "notified": False,
            "routine": True,
        })

    weekday = _today_weekday_name()
    for subject in WEEKLY_SUBJECTS.get(weekday, []):
        dashboard_data["goals"].append({"text": subject, "done": False, "routine": True})

    for habit in DAILY_HABITS:
        dashboard_data["goals"].append({"text": habit, "done": False, "routine": True})

    dashboard_data["routine_synced_date"] = today_str
    save_dashboard_data()
    return True
