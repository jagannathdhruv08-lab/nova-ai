import os
import json
import time
from datetime import datetime

REMINDER_FILE = os.path.join(os.path.expanduser("~"), ".nova", "reminders.json")

def _ensure_reminder_file():
    """Ensure the reminder file exists and return the list of reminders."""
    os.makedirs(os.path.dirname(REMINDER_FILE), exist_ok=True)
    if not os.path.exists(REMINDER_FILE):
        with open(REMINDER_FILE, "w") as f:
            json.dump([], f)
    return _load_reminders()

def _load_reminders():
    """Load all reminders from file."""
    try:
        with open(REMINDER_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def _save_reminders(reminders):
    """Save reminders to file."""
    os.makedirs(os.path.dirname(REMINDER_FILE), exist_ok=True)
    with open(REMINDER_FILE, "w") as f:
        json.dump(reminders, f, indent=2)

def set_reminder(task, time_str):
    """Set a new reminder with a task description and time.

    Args:
        task: Description of what to remember
        time_str: When to remind (e.g., '2024-01-15 14:30' or 'in 30 minutes')

    Returns dict with success status and reminder details.
    """
    try:
        reminders = _load_reminders()

        # Parse the time string into a timestamp
        parsed_time = None
        try:
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
            parsed_time = dt.timestamp()
        except ValueError:
            # Try "in X minutes" format
            if "minute" in time_str.lower():
                mins = int(time_str.split()[1])
                parsed_time = time.time() + (mins * 60)
            elif "hour" in time_str.lower():
                hours = int(time_str.split()[1])
                parsed_time = time.time() + (hours * 3600)
            else:
                # Default to 1 hour from now
                parsed_time = time.time() + 3600

        reminder = {
            "id": len(reminders) + 1,
            "task": task,
            "time_str": time_str,
            "timestamp": parsed_time,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "completed": False,
        }
        reminders.append(reminder)
        _save_reminders(reminders)

        return {
            "success": True,
            "feature": "smart_reminder",
            "reminder_id": reminder["id"],
            "task": task,
            "time_str": time_str,
            "message": "✅ Reminder set successfully!"
        }
    except Exception as e:
        return {
            "success": False,
            "feature": "smart_reminder",
            "error": str(e),
            "message": "Failed to set reminder"
        }

def check_reminders(check_all=True):
    """Check for any reminders.

    Args:
        check_all: If True, return all reminders. If False, return only due ones.

    Returns dict with reminder information.
    """
    try:
        reminders = _load_reminders()
        current_time = time.time()

        if check_all:
            # Return all reminders
            active = [r for r in reminders if not r.get("completed")]
            completed = [r for r in reminders if r.get("completed")]

            if not active:
                return {
                    "success": True,
                    "feature": "smart_reminder",
                    "total_reminders": len(reminders),
                    "active_count": 0,
                    "completed_count": len(completed),
                    "reminders": [],
                    "message": "📭 No active reminders. You're all caught up!"
                }

            upcoming = []
            for r in active:
                time_diff = r.get("timestamp", 0) - current_time
                if time_diff < 0:
                    status = "⏰ DUE NOW"
                elif time_diff < 3600:
                    status = f"⏳ Due in {int(time_diff // 60)} min"
                elif time_diff < 86400:
                    status = f"🕐 Due in {int(time_diff // 3600)} hr"
                else:
                    days = int(time_diff // 86400)
                    status = f"📅 Due in {days} days"

                upcoming.append({
                    "id": r["id"],
                    "task": r["task"],
                    "time_str": r["time_str"],
                    "created_at": r.get("created_at", ""),
                    "status": status,
                })

            return {
                "success": True,
                "feature": "smart_reminder",
                "total_reminders": len(reminders),
                "active_count": len(active),
                "completed_count": len(completed),
                "reminders": upcoming,
                "message": f"🔔 You have {len(active)} active reminder(s)"
            }
        else:
            # Return only due reminders
            due = [r for r in reminders
                   if not r.get("completed") and r.get("timestamp", 0) <= current_time]

            if not due:
                return {
                    "success": True,
                    "feature": "smart_reminder",
                    "due_count": 0,
                    "reminders": [],
                    "message": "✅ No reminders are due right now"
                }

            due_list = [{"id": r["id"], "task": r["task"], "time_str": r["time_str"]}
                        for r in due]

            return {
                "success": True,
                "feature": "smart_reminder",
                "due_count": len(due),
                "reminders": due_list,
                "message": f"⏰ {len(due)} reminder(s) are due now!"
            }
    except Exception as e:
        return {
            "success": False,
            "feature": "smart_reminder",
            "error": str(e),
            "message": "Failed to check reminders"
        }


__version__ = "1.1.0"
__all__ = ["check_reminders", "set_reminder"]