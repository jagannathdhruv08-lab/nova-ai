# ==========================================
# NOVA APP LAUNCHER — Launch Apps + Open Websites
# ==========================================
import os
import webbrowser
import subprocess

# Map of common app names to launch commands
KNOWN_APPS = {
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "paint": ["mspaint.exe"],
    "cmd": ["cmd.exe"],
    "command prompt": ["cmd.exe"],
    "explorer": ["explorer.exe"],
    "file explorer": ["explorer.exe"],
    "task manager": ["taskmgr.exe"],
    "control panel": ["control.exe"],
    "settings": ["start", "ms-settings:"],
    "word": ["start", "winword.exe"],
    "excel": ["start", "excel.exe"],
    "powerpoint": ["start", "powerpnt.exe"],
    "chrome": ["start", "chrome.exe"],
    "browser": ["start", "chrome.exe"],
    "firefox": ["start", "firefox.exe"],
    "edge": ["start", "msedge.exe"],
    "vscode": ["start", "code.exe"],
    "code": ["start", "code.exe"],
    "pycharm": ["start", "pycharm64.exe"],
    "spotify": ["start", "spotify.exe"],
    "youtube": ["start", "youtube.com"],
    "python": ["start", "python.exe"],
}


def launch_app(app_name):
    """Launch a known application by name."""
    if not app_name:
        return {
            "success": False, "feature": "app_launcher",
            "message": "App name required. Try: notepad, calculator, chrome, vscode...",
            "available": list(KNOWN_APPS.keys()),
        }

    query = app_name.lower().strip()
    # Fuzzy match
    matched = None
    for name in KNOWN_APPS:
        if query in name or name in query:
            matched = name
            break
    if not matched:
        return {
            "success": False, "feature": "app_launcher",
            "message": f"❌ '{app_name}' nahi mila. Available: {', '.join(list(KNOWN_APPS)[:10])}...",
            "available": list(KNOWN_APPS.keys()),
        }

    command = KNOWN_APPS[matched]
    try:
        # Launch without a shell (list-form, matching agent.py's "NO shell=True"
        # design rule). "start" is a cmd.exe builtin, so `cmd /c start` is used
        # for those entries; plain .exe paths run directly.
        prog = command[0].lower()
        if prog == "start":
            process = subprocess.Popen(["cmd", "/c", "start"] + command[1:],
                                       shell=False)
        else:
            process = subprocess.Popen(command, shell=False)
        return {
            "success": True, "feature": "app_launcher",
            "app": matched,
            "command": command,
            "message": f"🚀 Launched: {matched}",
        }
    except Exception as e:
        return {
            "success": False, "feature": "app_launcher",
            "error": str(e),
            "message": f"Failed to launch {matched}: {str(e)}",
        }


def open_website(url):
    """Open a website in the default browser."""
    if not url:
        return {
            "success": False, "feature": "app_launcher",
            "message": "URL required. Try: youtube.com, google.com...",
        }

    if not url.startswith("http"):
        url = "https://" + url

    try:
        webbrowser.open(url)
        return {
            "success": True, "feature": "app_launcher",
            "url": url,
            "message": f"🌐 Opening: {url}",
        }
    except Exception as e:
        return {
            "success": False, "feature": "app_launcher",
            "error": str(e),
            "message": f"Failed to open {url}",
        }


def get_known_apps():
    """List all launchable apps."""
    return {
        "success": True,
        "feature": "app_launcher",
        "apps": sorted(KNOWN_APPS.keys()),
        "message": f"🗂 {len(KNOWN_APPS)} apps can be launched",
    }


__version__ = "1.0.0"
__all__ = ["launch_app", "open_website", "get_known_apps"]
