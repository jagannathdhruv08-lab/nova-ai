# ==========================================
# NOVA ALARM SCHEDULER — Recurring alarms with snooze
# ==========================================
import os
import json
import time
import threading
from datetime import datetime

ALARM_FILE = os.path.join(os.path.expanduser("~"), ".nova", "alarms.json")

_running = {}
_lock = threading.Lock()


def _load_alarms():
    try:
        with open(ALARM_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_alarms(alarms):
    os.makedirs(os.path.dirname(ALARM_FILE), exist_ok=True)
    with open(ALARM_FILE, "w") as f:
        json.dump(alarms, f, indent=2)


def set_alarm(label, time_str, repeat=None):
    """Set an alarm.

    Args:
        label: Alarm name (e.g., 'Wake up', 'Meeting')
        time_str: 'HH:MM' 24-hour time
        repeat: None (once), 'daily', 'weekdays', 'weekends'
    """
    try:
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        return {"success": False, "feature": "alarm_scheduler",
                "message": "⚠️ Invalid time. Use 24-hour format like '07:30'."}

    alarm = {
        "id": int(time.time()),
        "label": label,
        "time": time_str,
        "repeat": repeat,
        "enabled": True,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    alarms = _load_alarms()
    alarms.append(alarm)
    _save_alarms(alarms)
    _schedule(alarm)
    return {"success": True, "feature": "alarm_scheduler",
            "alarm": alarm, "message": f"⏰ Alarm '{label}' set for {time_str}"}


def _schedule(alarm):
    """Schedule an alarm to fire."""
    if not alarm.get("enabled"):
        return
    t = threading.Thread(target=_alarm_worker, args=(alarm,), daemon=True)
    _running[alarm["id"]] = t
    t.start()


def _should_fire_today(alarm, now):
    """Check whether alarm should fire today based on repeat rule."""
    rule = alarm.get("repeat")
    weekday = now.weekday()  # 0=Mon ... 6=Sun
    if rule is None:
        return True
    if rule == "daily":
        return True
    if rule == "weekdays":
        return weekday < 5
    if rule == "weekends":
        return weekday >= 5
    return True


def _alarm_worker(alarm):
    """Background worker that waits for the alarm time and rings."""
    try:
        while _running.get(alarm["id"]) is threading.current_thread():
            alarms = _load_alarms()
            current = next((a for a in alarms if a["id"] == alarm["id"]), None)
            if not current or not current.get("enabled"):
                break

            now = datetime.now()
            if _should_fire_today(alarm, now):
                target = datetime.strptime(alarm["time"], "%H:%M").time()
                if now.hour == target.hour and now.minute == target.minute and now.second < 5:
                    _ring(alarm)
                    if alarm.get("repeat") is None:
                        alarms = _load_alarms()
                        for a in alarms:
                            if a["id"] == alarm["id"]:
                                a["enabled"] = False
                        _save_alarms(alarms)
                        break
                    time.sleep(55)
            time.sleep(5)
    except Exception:
        pass


def _ring(alarm):
    """Ring the alarm sound + notify."""
    try:
        import winsound
        for _ in range(4):
            try:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                winsound.Beep(1200, 300)
            time.sleep(0.3)
    except Exception:
        pass


def get_alarms():
    """Get all alarms."""
    alarms = _load_alarms()
    active = [a for a in alarms if a.get("enabled")]
    if not alarms:
        return {"success": True, "feature": "alarm_scheduler",
                "alarms": [], "message": "📭 No alarms set. Use set_alarm('Wake up', '07:30')."}
    display = [{"id": a["id"], "label": a["label"], "time": a["time"],
                "repeat": a.get("repeat", "once"), "enabled": a.get("enabled")}
               for a in alarms]
    return {"success": True, "feature": "alarm_scheduler",
            "alarms": display, "active_count": len(active),
            "message": f"⏰ {len(active)} active alarm(s)"}


def snooze_alarm(alarm_id, minutes=5):
    """Snooze an active alarm."""
    alarms = _load_alarms()
    for a in alarms:
        if a["id"] == alarm_id:
            try:
                from datetime import timedelta
                now = datetime.now() + timedelta(minutes=minutes)
                a["time"] = now.strftime("%H:%M")
                _save_alarms(alarms)
                return {"success": True, "feature": "alarm_scheduler",
                        "message": f"😴 Snoozed '{a['label']}' for {minutes} min (now {a['time']})"}
            except Exception as e:
                return {"success": False, "feature": "alarm_scheduler",
                        "message": f"Error: {str(e)}"}
    return {"success": False, "feature": "alarm_scheduler", "message": "Alarm not found"}


def disable_alarm(alarm_id):
    """Disable an alarm."""
    alarms = _load_alarms()
    for a in alarms:
        if a["id"] == alarm_id:
            a["enabled"] = False
            _save_alarms(alarms)
            return {"success": True, "feature": "alarm_scheduler",
                    "message": f"🔕 Alarm '{a['label']}' disabled"}
    return {"success": False, "feature": "alarm_scheduler", "message": "Alarm not found"}


def _init_scheduler():
    for alarm in _load_alarms():
        if alarm.get("enabled"):
            _schedule(alarm)


_init_scheduler()


__version__ = "1.0.0"
__all__ = ["set_alarm", "get_alarms", "snooze_alarm", "disable_alarm"]
