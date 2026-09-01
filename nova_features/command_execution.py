# ==========================================
# NOVA FEATURES - SAFE COMMAND EXECUTION (real implementation)
# ------------------------------------------
# A small, audited, rate-limited registry of READ-ONLY / reversible
# system commands. Design rules copied from agent.py (DO NOT BREAK):
#
#   1. NO os.system. NO shell=True. Nothing arbitrary is executed -
#      only named handlers in SAFE_COMMANDS below may run.
#   2. Every call is appended to an append-only audit log.
#   3. Per-minute rate limit: 20 actions/min.
#   4. If anything throws, the user gets a generic message and the
#      error type is logged - never a stack trace in the chat bubble.
#
# Deliberately NOT provided: shell escape, registry edits, service
# control, process killing, file writes (agent.py owns file actions).
# ==========================================

import json
import logging
import shutil
import socket
import time
from collections import deque
from datetime import datetime

log = logging.getLogger("nova.command_execution")

__version__ = "2.0.0"

# ---------------------------------------------------------------------------
# Audit log + rate limiting (mirrors agent.py, separate namespace)
# ---------------------------------------------------------------------------
def _user_data_dir():
    import os
    import sys
    from pathlib import Path
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    p = base / "Nova"
    p.mkdir(parents=True, exist_ok=True)
    return p


AUDIT_LOG = _user_data_dir() / "command_audit.log"

_RATE_MAX_ACTIONS = 20          # actions per window
_RATE_WINDOW_S = 60
_action_times = deque()


def _check_rate():
    """Return True when this action is allowed under the rate limit."""
    now = time.monotonic()
    while _action_times and now - _action_times[0] > _RATE_WINDOW_S:
        _action_times.popleft()
    if len(_action_times) >= _RATE_MAX_ACTIONS:
        return False
    _action_times.append(now)
    return True


def audit(action, detail=""):
    """Append-only audit entry; never raises."""
    try:
        entry = {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "detail": str(detail)[:300],
        }
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        log.debug("audit write failed", exc_info=True)

# ---------------------------------------------------------------------------
# Handlers - every one is read-only or trivially reversible
# ---------------------------------------------------------------------------
def _battery(args):
    import psutil
    batt = psutil.sensors_battery()
    if batt is None:
        return {"message": "Battery nahi mili - desktop PC lagta hai. 🔌"}
    plug = "charging ⚡" if batt.power_plugged else "on battery 🔋"
    return {"message": f"Battery: {round(batt.percent)}% ({plug})",
            "percent": round(batt.percent), "plugged": bool(batt.power_plugged)}


def _cpu_usage(args):
    import psutil
    per_core = psutil.cpu_percent(interval=0.4, percpu=True)
    overall = round(sum(per_core) / max(len(per_core), 1), 1)
    return {"message": f"CPU: {overall}% overall ({len(per_core)} cores)",
            "overall": overall, "cores": per_core}


def _memory_usage(args):
    import psutil
    mem = psutil.virtual_memory()
    used_gb = mem.used / (1024 ** 3)
    total_gb = mem.total / (1024 ** 3)
    return {"message": f"RAM: {used_gb:.1f}/{total_gb:.1f} GB "
                       f"({mem.percent:.0f}% used)",
            "percent": mem.percent}


def _disk_usage(args):
    usage = shutil.disk_usage(str(_user_data_dir().anchor or "C:\\"))
    free_gb = usage.free / (1024 ** 3)
    total_gb = usage.total / (1024 ** 3)
    pct = usage.used / max(usage.total, 1) * 100
    emoji = "🟢" if pct < 80 else ("🟡" if pct < 92 else "🔴")
    return {"message": f"Disk {emoji}: {free_gb:.0f} GB free of {total_gb:.0f} GB",
            "free_gb": round(free_gb, 1), "total_gb": round(total_gb, 1)}


def _top_processes(args):
    import psutil
    procs = []
    for p in psutil.process_iter(["name", "cpu_percent"]):
        try:
            procs.append((p.info["name"] or "?", p.info["cpu_percent"] or 0.0))
        except Exception:
            continue
    procs.sort(key=lambda x: x[1], reverse=True)
    lines = [f"{name[:24]:24} {cpu:5.1f}%" for name, cpu in procs[:5]]
    return {"message": "Top CPU processes:\n" + "\n".join(lines)}


def _network_status(args):
    online = False
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2).close()
        online = True
    except Exception:
        pass
    counters = None
    try:
        import psutil
        c = psutil.net_io_counters()
        counters = {"sent_mb": round(c.bytes_sent / 1048576, 1),
                    "recv_mb": round(c.bytes_recv / 1048576, 1)}
    except Exception:
        pass
    state = "ONLINE 🌐" if online else "OFFLINE 📴"
    msg = f"Network: {state}"
    if counters:
        msg += f" (session: ⬆ {counters['sent_mb']} MB, ⬇ {counters['recv_mb']} MB)"
    out = {"message": msg, "online": online}
    if counters:
        out.update(counters)
    return out

def _volume_step(key_name, label):
    """Media-key volume via the already-installed keyboard lib."""
    try:
        import keyboard
        keyboard.send(key_name)
        return {"message": f"Volume {label} 🔊", "key": key_name}
    except Exception as exc:
        log.warning("volume via keyboard lib failed: %s", exc)
        return {"error": "Volume keys unavailable (keyboard lib blocked?)."}


def _volume_up(args):
    return _volume_step("volume up", "badha diya")


def _volume_down(args):
    return _volume_step("volume down", "kam kar diya")


def _volume_mute(args):
    return _volume_step("volume mute", "mute")


def _open_folder(args):
    """Open one of the user's known shell folders (read-only action)."""
    import os
    import subprocess
    folder_key = str((args or {}).get("folder", "")).strip().lower()
    mapping = {
        "downloads": "Downloads", "documents": "Documents", "docs": "Documents",
        "pictures": "Pictures", "desktop": "Desktop", "music": "Music",
        "videos": "Videos",
    }
    folder = mapping.get(folder_key)
    if not folder:
        known = ", ".join(sorted(set(mapping.values())))
        return {"error": f"Kaunsa folder? Known: {known}"}
    path = os.path.join(os.path.expanduser("~"), folder)
    if not os.path.isdir(path):
        return {"error": f"Folder not found: {path}"}
    subprocess.Popen(["explorer", path])   # list form, no shell
    return {"message": f"Opening {folder} folder 📂", "path": path}


SAFE_COMMANDS = {
    "battery_status": (_battery, "Battery percent + charging state"),
    "cpu_usage": (_cpu_usage, "CPU load per core"),
    "memory_usage": (_memory_usage, "RAM usage"),
    "disk_usage": (_disk_usage, "Free disk space"),
    "top_processes": (_top_processes, "Top 5 CPU-consuming processes"),
    "network_status": (_network_status, "Online/offline + data counters"),
    "volume_up": (_volume_up, "Volume up (media key)"),
    "volume_down": (_volume_down, "Volume down (media key)"),
    "volume_mute": (_volume_mute, "Mute/unmute (media key)"),
    "open_folder": (_open_folder, "Open Downloads/Documents/Pictures/... (args: folder)"),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def execute_safe_command(cmd, args=None):
    """Run a whitelisted command by name.

    *cmd* must be an exact key of SAFE_COMMANDS - free-form text is
    intentionally rejected so this module can never become a shell.
    Returns a dict with success/message; every attempt is audited.
    """
    name = str(cmd or "").strip().lower()
    if not name:
        return {"success": False, "message": "Command name required.",
                "available": sorted(SAFE_COMMANDS.keys())}

    if name not in SAFE_COMMANDS:
        audit("rejected_unknown", name)
        available = ", ".join(sorted(SAFE_COMMANDS.keys()))
        return {
            "success": False,
            "message": f"❌ '{name}' safe commands list mein nahi hai.\n"
                       f"Available: {available}",
        }

    if not _check_rate():
        audit("rate_limited", name)
        return {"success": False,
                "message": "⏳ Rate limit: max 20 commands/minute. Thoda ruk jao."}

    handler, _desc = SAFE_COMMANDS[name]
    try:
        result = handler(args or {})
        ok = "error" not in result
        audit(name, result.get("message", result.get("error", "")))
        result.setdefault("command", name)
        result["success"] = bool(ok)
        return result
    except Exception as exc:
        log.error("safe command %s failed: %s", name, exc)
        audit(name, f"error:{type(exc).__name__}")
        return {"success": False, "command": name,
                "message": f"❌ Command failed ({type(exc).__name__})."}


def get_available_commands():
    """Catalog of the whitelist - shown by the features panel."""
    lines = ["🛡️ Nova Safe Commands (audited + rate-limited):\n"]
    for name, (_fn, desc) in sorted(SAFE_COMMANDS.items()):
        lines.append(f"• {name} — {desc}")
    lines.append(
        "\nNote: koi bhi arbitrary/shell command allowed NAHI hai - sirf "
        "ye whitelist. File actions ke liye agent.py use hota hai."
    )
    return {
        "success": True,
        "feature": "command_execution",
        "commands": {n: d for n, (_f, d) in SAFE_COMMANDS.items()},
        "count": len(SAFE_COMMANDS),
        "message": "\n".join(lines),
    }


__all__ = ["execute_safe_command", "get_available_commands",
           "SAFE_COMMANDS", "audit"]