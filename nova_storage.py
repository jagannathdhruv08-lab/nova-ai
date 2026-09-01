# ==========================================
# NOVA AI - STORAGE
# Everything about reading/writing Nova's saved data: goals, tasks,
# notes, journal, focus tracking, chat history. Also holds file-path
# helpers and the static command-guide reference data. No Tkinter or
# live-widget dependencies here on purpose - this file can be tested
# or reused completely independently of the GUI.
# ==========================================

import os
import sys
import json
import time
from datetime import date

# ==========================================
# RESOURCE PATH HELPERS (for PyInstaller)
# ==========================================

def resource_path(relative_path):
    """For READ-ONLY bundled assets (images, icons) that ship inside
    the app. Do NOT use this for anything Nova needs to write and
    keep between runs - see writable_data_path() below."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def writable_data_path(relative_path):
    """Where to store files Nova needs to WRITE and keep between runs
    (goals, tasks, chat history, notes...). resource_path() above is
    fine for read-only bundled assets, but it is NOT safe for saved
    data: when Nova is built into a onefile .exe, sys._MEIPASS points
    at a fresh temp folder that Windows deletes when the app closes -
    so anything saved there (like your goals/tasks) was being wiped
    on every restart. This instead always resolves to a stable folder
    next to the .exe (or next to this file when run as a plain
    script), regardless of the current working directory."""
    if hasattr(sys, "_MEIPASS"):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, relative_path)


# ==========================================
# DASHBOARD DATA (goals / tasks / notes / journal / focus / chat history)
# ==========================================

# NOTE: this was previously wired to resource_path(), which is the
# bug that made goals/tasks reset on every restart when Nova was
# packaged as a onefile .exe (see writable_data_path's docstring).
# Fixed here to use the stable, writable path.
DATA_PATH = writable_data_path("nova_dashboard_data.json")


def load_dashboard_data():
    default = {
        "goals": [
            {"text": "Study 6 hours", "done": False},
            {"text": "Go for a walk (1 hour)", "done": False},
            {"text": "Learn something new", "done": False},
            {"text": "Work on Nova AI", "done": False},
        ],
        "tasks": [],
        "notes": [],
        "journal": [],
        "focus_minutes_today": 0,
        "focus_goal_minutes": 360,
        "focus_date": str(date.today()),
        "streak_days": [],
        "status": "Focus Mode",
        "quote": "Discipline today, freedom tomorrow.",
        "chat_history": [],
        "assistant_mode": "General",
        "current_thread_id": "main",
        "chat_threads": {
            "main": {
                "title": "Main Chat",
                "created_at": time.strftime("%Y-%m-%d %H:%M"),
                "messages": [],
            }
        },
        "prompt_library": [
            {"title": "Explain Simply", "prompt": "Explain this topic in simple steps: ", "enabled": True},
            {"title": "Study Plan", "prompt": "Create a focused study plan for: ", "enabled": True},
            {"title": "Summarize", "prompt": "Summarize this clearly: ", "enabled": True},
            {"title": "Improve Writing", "prompt": "Improve this writing professionally: ", "enabled": True},
            {"title": "News Query", "prompt": "Give me news about this place/topic/date: ", "enabled": True},
        ],
        "notifications": [],
        "activity_log": [],
        "onboarding_complete": False,
        "profile": {"name": "Dhruv"},
        "daily_schedule": [
            {"time": "06:00", "title": "Wake up and freshen up"},
            {"time": "07:00", "title": "Study block"},
            {"time": "13:00", "title": "Meal and reset"},
            {"time": "16:00", "title": "Practice / revision"},
            {"time": "21:00", "title": "Daily review"},
        ],
    }
    if os.path.exists(DATA_PATH):
        try:
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key, value in default.items():
                data.setdefault(key, value)
            return data
        except Exception as exc:
            print("dashboard data load failed:", exc)
    return default


def save_dashboard_data():
    try:
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(dashboard_data, f, indent=2)
    except Exception as exc:
        print("dashboard data save failed:", exc)


MAX_CHAT_HISTORY = 300


def persist_message(sender, text, time_str=None):
    """Append one chat message to the persisted history and save it.
    sender is 'nova' or 'user'."""
    message = {
        "sender": sender,
        "text": text,
        "time": time_str or time.strftime("%I:%M %p"),
    }
    dashboard_data.setdefault("chat_history", []).append(message)
    dashboard_data["chat_history"] = dashboard_data["chat_history"][-MAX_CHAT_HISTORY:]

    thread_id = dashboard_data.get("current_thread_id", "main")
    threads = dashboard_data.setdefault("chat_threads", {})
    thread = threads.setdefault(thread_id, {
        "title": "Main Chat" if thread_id == "main" else "New Chat",
        "created_at": time.strftime("%Y-%m-%d %H:%M"),
        "messages": [],
    })
    thread.setdefault("messages", []).append(message)
    thread["messages"] = thread["messages"][-MAX_CHAT_HISTORY:]
    save_dashboard_data()


# Loaded once at import time - every other Nova file that does
# `from nova_storage import dashboard_data` gets a reference to this
# SAME dict object, so in-place edits (dashboard_data["goals"].append(...))
# are visible everywhere without needing to re-import.
dashboard_data = load_dashboard_data()

if not dashboard_data.get("chat_threads"):
    dashboard_data["chat_threads"] = {
        "main": {
            "title": "Main Chat",
            "created_at": time.strftime("%Y-%m-%d %H:%M"),
            "messages": dashboard_data.get("chat_history", []),
        }
    }
dashboard_data.setdefault("current_thread_id", "main")
dashboard_data.setdefault("assistant_mode", "General")
_main_thread = dashboard_data.setdefault("chat_threads", {}).setdefault("main", {
    "title": "Main Chat",
    "created_at": time.strftime("%Y-%m-%d %H:%M"),
    "messages": [],
})
if not _main_thread.get("messages") and dashboard_data.get("chat_history"):
    _main_thread["messages"] = dashboard_data.get("chat_history", [])

_today_str = str(date.today())
if dashboard_data["focus_date"] != _today_str:
    dashboard_data["focus_date"] = _today_str
    dashboard_data["focus_minutes_today"] = 0
if _today_str not in dashboard_data["streak_days"]:
    dashboard_data["streak_days"].append(_today_str)
    dashboard_data["streak_days"] = dashboard_data["streak_days"][-60:]
save_dashboard_data()

# ==========================================
# COMMAND GUIDE DATA (static reference data for the command popup,
# the top-bar search, and the sidebar quick-command grid)
# ==========================================

command_groups = [
    ("Open Apps", [
        ("YouTube", "open youtube"),
        ("Google", "open google"),
        ("Chrome", "open chrome"),
        ("WhatsApp", "open whatsapp"),
        ("WhatsApp Web", "open whatsapp web"),
        ("YouTube short", "open yt"),
    ]),
    ("News", [
        ("News", "today's news"),
        ("Aaj ki news", "aaj ki news"),
        ("Briefing", "news briefing"),
        ("Daily briefing", "daily briefing"),
        ("News Hindi", "news sunao"),
        ("News Hindi 2", "news batao"),
    ]),
    ("Music", [
        ("Play song", "run shape of you"),
        ("Happy songs", "happy"),
        ("Sad songs", "sad"),
        ("Romantic songs", "romantic"),
        ("Motivational", "motivational"),
        ("English vibe", "english vibe"),
        ("Calm music", "angry"),
    ]),
    ("System", [
        ("Brightness up", "increase brightness"),
        ("Brightness down", "decrease brightness"),
        ("Shutdown", "shutdown pc"),
        ("Restart", "restart pc"),
        ("Screenshot", "take screenshot"),
        ("Battery", "battery"),
        ("Current time", "what is the time"),
    ]),
    ("Nova", [
        ("Stop voice", "stop speaking"),
        ("Start voice", "start speaking"),
        ("Thanks", "thank you"),
    ]),
    ("Memory", [
        ("Save name", "remember my name is Dhruv"),
        ("Ask name", "what is my name"),
        ("Save color", "remember my favorite color is blue"),
        ("Ask color", "what is my favorite color"),
        ("Save fact", "remember birthday is 12 may"),
    ]),
    ("History", [
        ("Show history", "show history"),
        ("Clear history", "clear history"),
    ]),
]
