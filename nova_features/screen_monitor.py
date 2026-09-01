def _get_active_window_info():
    """Get info about the currently active window (process + window title)."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return {}

        # Get window title
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        window_title = buffer.value

        # Get process id and name
        lpdw_process_id = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(lpdw_process_id))
        process_id = lpdw_process_id.value

        import psutil
        try:
            proc = psutil.Process(process_id)
            return {
                "process_name": proc.name(),
                "process_pid": process_id,
                "window_title": window_title,
            }
        except Exception:
            return {"process_pid": process_id, "window_title": window_title}
    except Exception:
        pass
    return {}


def _count_running_apps():
    """Count how many visible windows/apps are running."""
    try:
        import ctypes
        user32 = ctypes.windll.user32

        def _enum_windows_proc(hwnd, lParam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    lParam[0] += 1
            return True

        count = [0]
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(WNDENUMPROC(_enum_windows_proc), count)
        return count[0]
    except Exception:
        return 0


def _detect_activity_snapshot():
    """Create a snapshot signature of current screen state (for change detection)."""
    import time
    active = _get_active_window_info()
    apps = _count_running_apps()
    hour = time.localtime().tm_hour
    return {
        "active_title": active.get("window_title", "unknown"),
        "active_app": active.get("process_name", "unknown"),
        "running_apps": apps,
        "hour": hour,
    }

def _get_screen_size():
    """Get screen resolution without pyautogui (which has a PIL compat issue)."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    except Exception:
        return 1280, 720


def get_screen_status():
    """Capture current screen information: resolution, active window, running apps."""
    try:
        import time
        screen_width, screen_height = _get_screen_size()
        active_window = _get_active_window_info()
        running_apps = _count_running_apps()
        hour = time.localtime().tm_hour

        if 5 <= hour < 12:
            period = "🌅 Morning"
        elif 12 <= hour < 17:
            period = "☀️ Afternoon"
        elif 17 <= hour < 21:
            period = "🌇 Evening"
        else:
            period = "🌙 Night"

        window_title = active_window.get('window_title', 'unknown')
        app_name = active_window.get('process_name', 'unknown')

        return {
            "success": True,
            "feature": "screen_monitor",
            "screen_width": screen_width,
            "screen_height": screen_height,
            "resolution": f"{screen_width}x{screen_height}",
            "active_window": active_window,
            "running_apps": running_apps,
            "time_period": period,
            "timestamp": time.strftime("%H:%M:%S"),
            "message": f"App: {app_name} • Window: '{window_title}' • {running_apps} apps running • {period}",
        }
    except Exception as e:
        return {
            "success": False,
            "feature": "screen_monitor",
            "error": str(e),
            "message": "Failed to capture screen status",
        }


def capture_and_analyze():
    """Take a screenshot and analyze basic features of the current screen."""
    try:
        from PIL import ImageGrab
        import time

        screen_width, screen_height = _get_screen_size()
        screenshot = ImageGrab.grab()
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

        img_width, img_height = screenshot.size
        pixel_count = img_width * img_height

        # Sample pixels for color/brightness
        center_pixel = screenshot.getpixel((img_width // 2, img_height // 2))

        def brightness(px):
            return sum(px) / 3 if isinstance(px, tuple) else px

        avg_brightness = brightness(center_pixel)
        if avg_brightness > 200:
            theme = "light"
        elif avg_brightness < 100:
            theme = "dark"
        else:
            theme = "medium"

        active_window = _get_active_window_info()
        running_apps = _count_running_apps()

        return {
            "success": True,
            "feature": "screen_monitor",
            "screen_resolution": f"{screen_width}x{screen_height}",
            "screenshot_size": f"{img_width}x{img_height}",
            "pixel_count": pixel_count,
            "avg_brightness": round(avg_brightness, 1),
            "detected_theme": theme,
            "active_window": active_window,
            "running_apps": running_apps,
            "timestamp": timestamp,
            "message": f"Screen: {screen_width}x{screen_height} • theme={theme} • app={active_window.get('process_name', 'unknown')} • {running_apps} apps",
        }
    except Exception as e:
        return {
            "success": False,
            "feature": "screen_monitor",
            "error": str(e),
            "message": "Failed to capture and analyze screen",
        }

__version__ = "1.1.0"
__all__ = ["capture_and_analyze", "get_screen_status"]