# ==========================================
# NOVA AI - BACKGROUND HOTKEY LAUNCHER
# ==========================================
#
# This is a SEPARATE small program from Nova itself. Nova's own hotkey
# (set up in hotkey.py) only works while Nova is already open — it can't
# listen for key presses while it's closed.
#
# This launcher solves that: it's a tiny background process (with a
# system tray icon) that listens for a GLOBAL hotkey at all times and
# launches Nova.exe if it isn't already running. Run this at Windows
# startup and you can summon Nova from anywhere with a keypress.
#
# REQUIREMENTS:
#   pip install keyboard psutil pystray pillow
#
# USAGE:
#   python launcher.py                  -> runs the background listener
#   python launcher.py --install-autostart   -> makes it run automatically
#                                               every time Windows starts
#   python launcher.py --uninstall-autostart -> removes it from startup
# ==========================================

import os
import sys
import threading
import subprocess
import re

# Simple file log so you can always tell the launcher is alive. Every time
# Nova Launcher starts / launches Nova / fails, it writes a line here:
#   <project>\nova_launcher.log   (open it with Notepad to see recent activity)
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nova_launcher.log")

def _log(msg):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as _lf:
            _lf.write(msg + "\n")
    except Exception:
        pass

try:
    import keyboard
except ImportError:
    print("Missing dependency: pip install keyboard")
    sys.exit(1)

try:
    import psutil
except ImportError:
    print("Missing dependency: pip install psutil")
    sys.exit(1)

try:
    import pystray  # type: ignore
    from PIL import Image, ImageDraw  # type: ignore
except ImportError:
    pystray = None
    Image = None
    ImageDraw = None

# ==========================================
# CONFIG
# ==========================================

HOTKEY = "ctrl+windows+alt"     # change this to whatever combo you prefer
APP_EXE_NAME = "Nova.exe"      # the process name to check for / launch

LAUNCHER_FOLDER = os.path.dirname(os.path.abspath(__file__))
# Assumes the standard PyInstaller layout: launcher.py sits next to the
# "dist" folder that build.py produces. Two layouts are supported:
#   onedir  -> dist/Nova/Nova.exe   (recommended, fast startup)
#   onefile -> dist/Nova.exe
APP_EXE_PATH = None
for _candidate in (
    os.path.join(LAUNCHER_FOLDER, "dist", "Nova", APP_EXE_NAME),  # onedir
    os.path.join(LAUNCHER_FOLDER, "dist", APP_EXE_NAME),          # onefile
):
    if os.path.exists(_candidate):
        APP_EXE_PATH = _candidate
        break
if APP_EXE_PATH is None:
    APP_EXE_PATH = os.path.join(LAUNCHER_FOLDER, "dist", APP_EXE_NAME)  # fallback


# ==========================================
# CORE LOGIC
# ==========================================

def is_nova_running():
    for proc in psutil.process_iter(["name"]):
        try:
            if proc.info["name"] and proc.info["name"].lower() == APP_EXE_NAME.lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def normalize_hotkey_name(key_name):
    name = (key_name or "").strip().lower()
    if name in {"win", "windows", "left windows", "right windows"}:
        return "windows"
    if name in {"left alt", "right alt"}:
        return "alt"
    if name in {"left ctrl", "right ctrl"}:
        return "ctrl"
    return name


def should_trigger_combo(pressed_keys, combo_keys):
    normalized_pressed = {normalize_hotkey_name(key) for key in pressed_keys}
    normalized_combo = {normalize_hotkey_name(key) for key in combo_keys}
    return normalized_combo.issubset(normalized_pressed)


def launch_nova():
    if is_nova_running():
        print("Nova is already running — nothing to do.")
        _log("Hotkey pressed — Nova is already running, so nothing launched.")
        return

    if not os.path.exists(APP_EXE_PATH):
        print(f"Couldn't find {APP_EXE_PATH}.")
        _log(f"Hotkey pressed — but {APP_EXE_PATH} not found. Run build.py first.")
        print("Update APP_EXE_PATH at the top of launcher.py to match where your build lives.")
        return

    subprocess.Popen([APP_EXE_PATH], cwd=os.path.dirname(APP_EXE_PATH))
    _log(f"Hotkey pressed — launched {APP_EXE_PATH}")
    print("Nova launched.")


# ==========================================
# TRAY ICON (optional, but nice — shows the
# launcher is alive and gives a manual exit)
# ==========================================

def _build_tray_icon_image():
    img = Image.new("RGB", (64, 64), color="#0d1117")
    draw = ImageDraw.Draw(img)
    draw.ellipse((12, 12, 52, 52), fill="#238636")
    return img


def start_tray_icon():
    if pystray is None:
        print("pystray/Pillow not installed — running without a tray icon.")
        print("Install with: pip install pystray pillow")
        return

    def on_open(icon, item):
        launch_nova()

    def on_exit(icon, item):
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem(f"Open Nova ({HOTKEY})", on_open),
        pystray.MenuItem("Exit Launcher", on_exit),
    )

    icon = pystray.Icon("nova_launcher", _build_tray_icon_image(), "Nova Launcher", menu)
    icon.run()


# ==========================================
# WINDOWS AUTOSTART (optional)
# ==========================================

def install_autostart():
    if os.name != "nt":
        print("Autostart install is only supported on Windows.")
        return

    import winreg

    python_exe = sys.executable
    script_path = os.path.abspath(__file__)
    # pythonw.exe (no console window) if available, else the current interpreter
    pythonw = os.path.join(os.path.dirname(python_exe), "pythonw.exe")
    runner = pythonw if os.path.exists(pythonw) else python_exe

    command = f'"{runner}" "{script_path}"'

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "NovaLauncher", 0, winreg.REG_SZ, command)

    print("Installed: Nova Launcher will now start automatically with Windows.")


def uninstall_autostart():
    if os.name != "nt":
        print("Autostart is only supported on Windows.")
        return

    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, "NovaLauncher")
        print("Removed Nova Launcher from Windows startup.")
    except FileNotFoundError:
        print("Nova Launcher wasn't set to autostart — nothing to remove.")


# ==========================================
# MAIN
# ==========================================

def main():
    if "--install-autostart" in sys.argv:
        install_autostart()
        return

    if "--uninstall-autostart" in sys.argv:
        uninstall_autostart()
        return

    print(f"Nova Launcher running in the background.")
    print(f"Press {HOTKEY} anywhere to open Nova.")
    print("Right-click the tray icon to exit (or quit Nova from Task Manager).")
    _log(f"Launcher started. Hotkey={HOTKEY}  exe={APP_EXE_PATH or 'NOT FOUND'}")

    if not APP_EXE_PATH or not os.path.exists(APP_EXE_PATH):
        print("\nWARNING: Nova.exe not found yet. Build it first with:  python build.py")
        print("  (then re-run this launcher, or it will auto-launch Nova once built)")

    try:
        keyboard.add_hotkey(HOTKEY, launch_nova)
        print(f"Hotkey registered: {HOTKEY}")
        _log(f"Hotkey registered: {HOTKEY}")
    except Exception as exc:
        print(f"Hotkey registration failed: {exc}")
        _log(f"Hotkey registration FAILED: {exc}")
        print("Try using a simpler combo such as ctrl+alt+z")
        # Fall back to a reliable combo that never fights the Windows key.
        try:
            keyboard.add_hotkey("ctrl+alt+z", launch_nova)
            print("Fallback hotkey registered: ctrl+alt+z")
            _log("Fallback hotkey registered: ctrl+alt+z")
        except Exception as exc2:
            print(f"Fallback registration also failed: {exc2}")
            return

    if pystray is not None:
        threading.Thread(target=start_tray_icon, daemon=True).start()
    else:
        print("(No tray icon — pystray not installed. pip install pystray pillow to see one.)")

    keyboard.wait()  # blocks forever, listening for the hotkey


if __name__ == "__main__":
    main()
