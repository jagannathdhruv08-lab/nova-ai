"""Reliably capture the Nova AI main window.

Run:  .venv\\Scripts\\python.exe capture_nova.py
- Kills old Nova instances, relaunches fresh
- Moves the window fully on-screen and forces it topmost (so nothing
  overlaps it), then captures exactly its rect.
"""
import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

user32 = ctypes.windll.user32
HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOMOVE, SWP_NOSIZE = 0x0002, 0x0001

hits = []

@ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
def cb(hwnd, _):
    n = user32.GetWindowTextLengthW(hwnd)
    if n:
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if user32.IsWindowVisible(hwnd):
            r = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            hits.append((buf.value, hwnd, (r.left, r.top, r.right, r.bottom)))
    return True

def enum():
    hits.clear()
    user32.EnumWindows(cb, 0)
    return list(hits)

def find_main():
    best = None
    for title, hwnd, (l, t, r, b) in enum():
        if title == "Nova AI" and (r - l) >= 900:
            area = (r - l) * (b - t)
            if best is None or area > best[0]:
                best = (area, hwnd, (l, t, r, b))
    return best[1:] if best else None

# 1. Fresh start: kill previous source-run instances
subprocess.run(["taskkill", "/F", "/FI", "WINDOWTITLE eq Nova AI"],
               capture_output=True)
print("launching Nova fresh...")
proc = subprocess.Popen([sys.executable, "main.py"],
                        stdout=open("assets/nova_startup.log", "w"),
                        stderr=subprocess.STDOUT)

# 2. Wait for the main window
hwnd = bbox = None
deadline = time.time() + 90
while time.time() < deadline:
    time.sleep(1)
    if proc.poll() is not None:
        print("Nova exited early, code", proc.returncode)
        break
    hwnd, bbox = find_main() if find_main() else (None, None)
    if hwnd:
        break
if not hwnd:
    print("FAILED - visible windows:", enum())
    proc.kill()
    sys.exit(1)
print("main window:", bbox)

# 3. Move fully on-screen (screen is ~1366x768) + force topmost so
#    nothing can be captured in place of Nova.
SW = user32.GetSystemMetrics(0)
SH = user32.GetSystemMetrics(1)
w = min(bbox[2] - bbox[0], SW - 6)
h = min(bbox[3] - bbox[1], SH - 50)  # leave room for taskbar
user32.MoveWindow(hwnd, 0, 0, w, h, True)
user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
user32.SetForegroundWindow(hwnd)
time.sleep(3)

# 4. Capture its (updated) rect
r = wt.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(r))
from PIL import ImageGrab
shot = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom), all_screens=True)
shot.save("assets/screenshot_home.png")
print("SAVED -> assets/screenshot_home.png", shot.size)

# 5. Drop topmost again (be a good citizen)
user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)




