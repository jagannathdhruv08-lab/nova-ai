# ==========================================
# NOVA FOCUS TIMER — Pomodoro-style focus sessions
# ==========================================
import time
import threading
from datetime import datetime

_timer_state = {
    "running": False,
    "mode": "idle",          # focus | break
    "total_seconds": 0,
    "remaining": 0,
    "started_at": None,
    "ends_at": None,
    "finished": False,
    "notified": False,
}


def _background_timer():
    """Background thread that ticks the timer down."""
    slept = 0
    try:
        import winsound
        while _timer_state["running"] and slept < _timer_state["total_seconds"]:
            time.sleep(1)
            slept += 1
            _timer_state["remaining"] = _timer_state["total_seconds"] - slept
        if slept >= _timer_state["total_seconds"]:
            _timer_state["finished"] = True
            _timer_state["running"] = False
            # Play completion beep
            for _ in range(3):
                winsound.Beep(1000, 300)
                time.sleep(0.2)
    except Exception:
        while _timer_state["running"] and slept < _timer_state["total_seconds"]:
            time.sleep(1)
            slept += 1
            _timer_state["remaining"] = _timer_state["total_seconds"] - slept
        if slept >= _timer_state["total_seconds"]:
            _timer_state["finished"] = True
            _timer_state["running"] = False


def start_focus_session(minutes=25):
    """Start a Pomodoro focus session."""
    if _timer_state["running"]:
        return {
            "success": False, "feature": "focus_timer",
            "message": "⏳ Timer already running! Stop it first.",
            **_timer_summary(),
        }

    _timer_state.update({
        "running": True,
        "mode": "focus",
        "total_seconds": int(minutes * 60),
        "remaining": int(minutes * 60),
        "started_at": time.strftime("%H:%M:%S"),
        "ends_at": None,
        "finished": False,
        "notified": False,
    })

    thread = threading.Thread(target=_background_timer, daemon=True)
    thread.start()

    return {
        "success": True, "feature": "focus_timer",
        "message": f"🎯 Focus session started — {minutes} minute(s). Work hard! 💪",
        "duration_minutes": minutes,
        **_timer_summary(),
    }


def start_break(minutes=5):
    """Start a break timer."""
    if _timer_state["running"]:
        return {
            "success": False, "feature": "focus_timer",
            "message": "⏳ Timer already running! Stop it first.",
            **_timer_summary(),
        }

    _timer_state.update({
        "running": True,
        "mode": "break",
        "total_seconds": int(minutes * 60),
        "remaining": int(minutes * 60),
        "started_at": time.strftime("%H:%M:%S"),
        "ends_at": None,
        "finished": False,
        "notified": False,
    })

    thread = threading.Thread(target=_background_timer, daemon=True)
    thread.start()

    return {
        "success": True, "feature": "focus_timer",
        "message": f"☕ Break started — {minutes} minute(s). Relax!",
        "duration_minutes": minutes,
        **_timer_summary(),
    }


def get_timer_status():
    """Get current focus timer status."""
    return {
        "success": True,
        "feature": "focus_timer",
        **_timer_summary(),
    }


def stop_timer():
    """Stop the current timer."""
    _timer_state["running"] = False
    return {
        "success": True, "feature": "focus_timer",
        "message": "⏹ Timer stopped.",
        **_timer_summary(),
    }


def _timer_summary():
    """Build summary dict of current timer state."""
    running = _timer_state["running"]
    remaining = _timer_state["remaining"]
    if running:
        mins = remaining // 60
        secs = remaining % 60
        time_str = f"{mins:02d}:{secs:02d}"
        if _timer_state["mode"] == "focus":
            state_label = "🎯 Focusing"
        else:
            state_label = "☕ Break"
    elif _timer_state["finished"]:
        time_str = "00:00"
        state_label = "✨ Finished!"
    else:
        time_str = "00:00"
        state_label = "⏸ Idle"

    return {
        "running": running,
        "mode": _timer_state["mode"],
        "remaining_seconds": remaining,
        "remaining_display": time_str,
        "state": state_label,
        "finished": _timer_state["finished"],
        "message": f"{state_label} • {time_str} left",
    }


__version__ = "1.0.0"
__all__ = ["start_focus_session", "start_break", "get_timer_status", "stop_timer"]