# ==========================================
# NOVA AI - DASHBOARD GUI (v5)
# Split into 4 files for maintainability:
#   nova_theme.py   - color constants
#   nova_storage.py - goals/tasks/notes/chat-history persistence + static command data
#   nova_vision.py  - Gemini vision + OCR + screen capture
#   gui.py (this file) - the actual UI: sidebar, chat, windows, wiring
# ==========================================

from commands import execute_command, smart_execute, set_study_callbacks
from voice import (
    speak, listen, detect_emotion, mute_voice, unmute_voice,
    get_last_listen_error, microphone_status,
)
from PIL import Image, ImageTk, ImageDraw, ImageGrab
import os

try:
    import agent
    _AGENT_AVAILABLE = True
except Exception:
    agent = None
    _AGENT_AVAILABLE = False

from brain import route_to_agent
from settings import save_settings as _save_app_settings
import logging
log = logging.getLogger("nova.gui")

try:
    import emoji_render
    EMOJI_RENDER_OK = True
except Exception as _emoji_exc:
    emoji_render = None
    EMOJI_RENDER_OK = False
    print("emoji_render import failed:", _emoji_exc)

try:
    import cv2  # type: ignore  # optional dependency (opencv-python) for camera features
except Exception:
    cv2 = None

from nova_theme import (
    BG_COLOR, SIDEBAR_COLOR, TOPBAR_COLOR, CARD_COLOR, CARD_COLOR_SOFT,
    ACCENT, ACCENT_HOVER, ACCENT_SOFT, TEXT_MAIN, TEXT_MUTED,
    DANGER, DANGER_HOVER, SUCCESS, BORDER_COLOR,
)
from nova_storage import (
    resource_path, writable_data_path, dashboard_data, save_dashboard_data,
    persist_message, command_groups,
)
from nova_vision import (
    pytesseract, google_genai, GEMINI_API_KEY, GEMINI_MODEL,
    ask_gemini_vision, check_gemini_status, get_last_gemini_error,
    check_ocr_status, extract_text_from_image, capture_screen_image,
)
from nova_gui_helpers import completion_text, is_supported_image, read_file_preview
from nova_routine import sync_routine_for_today
from nova_daily import run_daily
import nova_study
from nova_nutrition import analyze_meal_photo, get_profile, set_profile, get_today_summary_text
from nova_coach import (
    coach_data, reset_for_new_day_if_needed, add_coach_message, build_coach_prompt,
    should_generate_rating_now, generate_daily_rating,
)

try:
    from photo_detector import detect_ai_image
except Exception as exc:
    detect_ai_image = None
    print("photo_detector import failed:", exc)

from brain import ask_nova, _strip_emojis
from hotkey import setup_hotkey
from history import save_message
from license import activate_license, get_license_status, is_license_valid
from memory import delete_memory, get_saved_facts, remember, memory_facts_block
from nova_knowledge import (
    ingest_text, ingest_file, ingest_folder, knowledge_stats,
    list_sources, clear_knowledge, knowledge_context,
)
from settings import load_settings, save_settings, update_setting

# ==========================================
# NOVA FEATURES (lazy-loaded, safe imports)
# ==========================================
try:
    from nova_features.smart_reminder import check_reminders, set_reminder
    REMINDer_AVAILABLE = True
except ImportError:
    REMINDer_AVAILABLE = False
    check_reminders = lambda: {"message": "Reminder feature not initialized", "status": "unavailable"}
    set_reminder = lambda task, time: {"message": "Reminder feature not initialized", "success": False}

try:
    from nova_features.screen_monitor import capture_and_analyze, get_screen_status
    SCREEN_Monitor_AVAILABLE = True
except ImportError:
    SCREEN_Monitor_AVAILABLE = False
    capture_and_analyze = lambda: {"message": "Screen monitor feature not initialized", "success": False, "feature": "screen_monitor"}
    get_screen_status = lambda: {"message": "Screen monitor feature not initialized", "feature": "screen_monitor"}

try:
    from nova_features.command_execution import execute_safe_command, get_available_commands
    COMMAND_EXECUTION_AVAILABLE = True
except ImportError:
    COMMAND_EXECUTION_AVAILABLE = False
    execute_safe_command = lambda cmd: {"message": "Command execution feature not initialized", "success": False, "feature": "command_execution"}
    get_available_commands = lambda: {"message": "Command execution feature not initialized", "feature": "command_execution"}

try:
    from nova_features.data_export_import import export_all_data, import_all_data
    DATA_EXPORT_IMPORT_AVAILABLE = True
except ImportError:
    DATA_EXPORT_IMPORT_AVAILABLE = False
    export_all_data = lambda: {"message": "Data export/import feature not initialized", "success": False, "feature": "data_export_import"}
    import_all_data = lambda data: {"message": "Data export/import feature not initialized", "feature": "data_export_import"}

try:
    from nova_features.multi_language import translate_to_hindi, detect_language
    MULTI_LANGUAGE_AVAILABLE = True
except ImportError:
    MULTI_LANGUAGE_AVAILABLE = False
    translate_to_hindi = lambda text: {"message": "Multi-language feature not initialized", "success": False, "feature": "multi_language"}
    detect_language = lambda text: {"message": "Multi-language feature not initialized", "feature": "multi_language"}

try:
    from nova_features.mini_quizzes import start_quiz, check_answer, get_quiz_category_options
    MINI_QUIZZES_AVAILABLE = True
except ImportError:
    MINI_QUIZZES_AVAILABLE = False
    start_quiz = lambda category="general": {"message": "Mini quizzes feature not initialized", "feature": "mini_quizzes"}
    check_answer = lambda *args: {"message": "Mini quizzes feature not initialized", "feature": "mini_quizzes"}
    get_quiz_category_options = lambda: {"message": "Mini quizzes feature not initialized", "feature": "mini_quizzes"}

try:
    from nova_features.context_suggestions import analyze_screen_and_suggest, get_suggestion_feedback
    CONTEXT_SUGGESTIONS_AVAILABLE = True
except ImportError:
    CONTEXT_SUGGESTIONS_AVAILABLE = False
    analyze_screen_and_suggest = lambda: {"message": "Context suggestions feature not initialized", "success": False, "feature": "context_suggestions"}
    get_suggestion_feedback = lambda action: {"message": "Context suggestions feature not initialized", "feature": "context_suggestions"}

try:
    from nova_features.gamified_progress import update_progress, get_progress_status, get_achievements_info
    GAMIFIED_PROGRESS_AVAILABLE = True
except ImportError:
    GAMIFIED_PROGRESS_AVAILABLE = False
    update_progress = lambda *args: {"message": "Gamified progress feature not initialized", "feature": "gamified_progress"}
    get_progress_status = lambda: {"message": "Gamified progress feature not initialized", "feature": "gamified_progress"}
    get_achievements_info = lambda: {"message": "Gamified progress feature not initialized", "feature": "gamified_progress"}

try:
    from nova_features.offline_first import check_offline_status, get_offline_response, store_user_fact
    OFFLINE_FIRST_AVAILABLE = True
except ImportError:
    OFFLINE_FIRST_AVAILABLE = False
    check_offline_status = lambda: {"message": "Offline mode feature not initialized", "feature": "offline_first"}
    get_offline_response = lambda cat: {"message": "Offline mode feature not initialized", "feature": "offline_first"}
    store_user_fact = lambda k, v: {"message": "Offline mode feature not initialized", "feature": "offline_first"}

try:
    from nova_features.enhanced_translation import translate_english_to_hindi, translate_hinglish_to_english, detect_and_translate, get_supported_languages
    ENHANCED_TRANSLATION_AVAILABLE = True
except ImportError:
    ENHANCED_TRANSLATION_AVAILABLE = False
    translate_english_to_hindi = lambda text: {"message": "Enhanced translation feature not initialized", "success": False, "feature": "enhanced_translation"}
    translate_hinglish_to_english = lambda text: {"message": "Enhanced translation feature not initialized", "success": False, "feature": "enhanced_translation"}
    detect_and_translate = lambda text: {"message": "Enhanced translation feature not initialized", "feature": "enhanced_translation"}
    get_supported_languages = lambda: {"message": "Enhanced translation feature not initialized", "feature": "enhanced_translation"}

# ===== NEW FEATURES (v2) =====
try:
    from nova_features.voice_assistant import listen_once, speak_text
    VOICE_ASSISTANT_AVAILABLE = True
except ImportError:
    VOICE_ASSISTANT_AVAILABLE = False
    listen_once = lambda timeout=5: {"message": "Voice input not initialized", "feature": "voice_assistant"}
    speak_text = lambda text: {"message": "Voice output not initialized", "feature": "voice_assistant"}

try:
    from nova_features.focus_timer import start_focus_session, start_break, get_timer_status, stop_timer
    FOCUS_TIMER_AVAILABLE = True
except ImportError:
    FOCUS_TIMER_AVAILABLE = False
    start_focus_session = lambda minutes=25: {"message": "Focus timer not initialized", "feature": "focus_timer"}
    start_break = lambda minutes=5: {"message": "Focus timer not initialized", "feature": "focus_timer"}
    get_timer_status = lambda: {"message": "Focus timer not initialized", "feature": "focus_timer"}
    stop_timer = lambda: {"message": "Focus timer not initialized", "feature": "focus_timer"}

try:
    from nova_features.system_health import get_system_health, get_top_processes
    SYSTEM_HEALTH_AVAILABLE = True
except ImportError:
    SYSTEM_HEALTH_AVAILABLE = False
    get_system_health = lambda: {"message": "System health not initialized", "feature": "system_health"}
    get_top_processes = lambda n=5: {"message": "System health not initialized", "feature": "system_health"}

try:
    from nova_features.screen_ocr import capture_screen_text, capture_and_save
    SCREEN_OCR_AVAILABLE = True
except ImportError:
    SCREEN_OCR_AVAILABLE = False
    capture_screen_text = lambda region=None: {"message": "Screen OCR not initialized", "feature": "screen_ocr"}
    capture_and_save = lambda: {"message": "Screen OCR not initialized", "feature": "screen_ocr"}

try:
    from nova_features.clipboard_manager import get_clipboard, set_clipboard, get_clipboard_history
    CLIPBOARD_MANAGER_AVAILABLE = True
except ImportError:
    CLIPBOARD_MANAGER_AVAILABLE = False
    get_clipboard = lambda: {"message": "Clipboard manager not initialized", "feature": "clipboard_manager"}
    set_clipboard = lambda text: {"message": "Clipboard manager not initialized", "feature": "clipboard_manager"}
    get_clipboard_history = lambda: {"message": "Clipboard manager not initialized", "feature": "clipboard_manager"}

try:
    from nova_features.app_launcher import launch_app, open_website, get_known_apps
    APP_LAUNCHER_AVAILABLE = True
except ImportError:
    APP_LAUNCHER_AVAILABLE = False
    launch_app = lambda app_name: {"message": "App launcher not initialized", "feature": "app_launcher"}
    open_website = lambda url: {"message": "App launcher not initialized", "feature": "app_launcher"}
    get_known_apps = lambda: {"message": "App launcher not initialized", "feature": "app_launcher"}

try:
    from nova_features.daily_recap import get_daily_recap
    DAILY_RECAP_AVAILABLE = True
except ImportError:
    DAILY_RECAP_AVAILABLE = False
    get_daily_recap = lambda: {"message": "Daily recap not initialized", "feature": "daily_recap"}

# === NOVA TOP-25 FEATURES: Browser Control | Alarm Scheduler | Email Notifications ===
try:
    from nova_features.browser_control import open_new_tab, search as browser_search, open_multi_tabs
    BROWSER_CONTROL_AVAILABLE = True
except ImportError:
    BROWSER_CONTROL_AVAILABLE = False
    open_new_tab = lambda url="": {"success": False, "feature": "browser_control", "message": "Browser module not available"}
    browser_search = lambda q, e="google": {"success": False, "feature": "browser_control", "message": "Browser module not available"}
    open_multi_tabs = lambda urls: {"success": False, "feature": "browser_control", "message": "Browser module not available"}

try:
    from nova_features.alarm_scheduler import set_alarm, get_alarms, snooze_alarm, disable_alarm
    ALARM_SCHEDULER_AVAILABLE = True
except ImportError:
    ALARM_SCHEDULER_AVAILABLE = False
    set_alarm = lambda label, t, r=None: {"success": False, "feature": "alarm_scheduler", "message": "Alarm module not available"}
    get_alarms = lambda: {"success": False, "feature": "alarm_scheduler", "message": "Alarm module not available"}
    snooze_alarm = lambda aid, m=5: {"success": False, "feature": "alarm_scheduler", "message": "Alarm module not available"}
    disable_alarm = lambda aid: {"success": False, "feature": "alarm_scheduler", "message": "Alarm module not available"}

try:
    from nova_features.email_notifications import (send_email_notification, send_reminder_email,
        get_email_status, save_email_config)
    EMAIL_NOTIFICATIONS_AVAILABLE = True
except ImportError:
    EMAIL_NOTIFICATIONS_AVAILABLE = False
    send_reminder_email = lambda text, recip, sender=None: {"success": False, "feature": "email_notifications", "message": "Email module not available"}
    get_email_status = lambda: {"success": False, "feature": "email_notifications", "message": "Email module not available"}

import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import threading
import random
import time
from datetime import date, timedelta, datetime

try:
    import plyer
    # plyer 2.x exposes facades as Proxy ATTRIBUTES on the plyer package
    # (plyer.notification), NOT as real submodules. The old
    # importlib.import_module("plyer.notification") raised
    # ModuleNotFoundError even with plyer installed, so reminders always
    # fell back to the in-app popup and never showed native toasts.
    plyer_notification = getattr(plyer, "notification", None)
except Exception:
    plyer_notification = None

# ==========================================
# APP SETTINGS (unchanged storage, settings.py)
# ==========================================

app_settings = load_settings()

ctk.set_appearance_mode(app_settings.get("theme", "Dark"))
ctk.set_default_color_theme("blue")

app = ctk.CTk()
app.title("Nova AI")
app.geometry("1400x840")
app.minsize(1120, 680)


def set_app_icon(window):
    icon_path = resource_path("assets/nova_icon.ico")
    if not os.path.exists(icon_path):
        icon_path = resource_path("assets/nova_icon .ico")  # legacy filename fallback
    if os.path.exists(icon_path):
        try:
            window.iconbitmap(icon_path)
            window.iconbitmap(default=icon_path)
        except Exception as exc:
            print("Icon load failed:", exc)


set_app_icon(app)

app.configure(fg_color=BG_COLOR)

# ==========================================
# LIGHTWEIGHT TOOLTIPS
# So icon-only buttons (mic, waveform, grid, paperclip, globe, sparkle,
# bell, chevron...) are self-explanatory on hover.
# ==========================================

class _ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, event=None):
        if self.tip is not None or not self.text:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        try:
            self.tip.wm_attributes("-topmost", True)
        except Exception:
            pass
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self.tip, text=self.text, bg="#1b1b30", fg="white", font=("Arial", 10),
            padx=8, pady=4, bd=0
        ).pack()

    def _hide(self, event=None):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


def add_tooltip(widget, text):
    _ToolTip(widget, text)


def bring_window_to_front(window):
    """Every new popup (license, settings, camera, etc.) was opening
    BEHIND the main window on some systems - this forces it to the
    front and gives it focus. The topmost flag is toggled off again
    right after so it doesn't stay stuck pinned above every other
    window forever, just long enough to grab attention on open."""
    try:
        window.lift()
        window.attributes("-topmost", True)
        window.after(100, lambda: window.attributes("-topmost", False))
        window.after(120, lambda: window.focus_force())
    except Exception as exc:
        print("bring_window_to_front failed:", exc)

# ==========================================
# IMAGE HELPERS (circular avatars + plain art, with safe fallbacks)
# ==========================================

def load_circle_image(path, size, fallback_letter="?", fallback_bg=ACCENT):
    try:
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        img = Image.open(path).convert("RGBA").resize((size, size))
    except Exception:
        img = Image.new("RGBA", (size, size), fallback_bg)
        draw = ImageDraw.Draw(img)
        draw.ellipse((0, 0, size, size), fill=fallback_bg)
        try:
            draw.text((size * 0.34, size * 0.2), fallback_letter, fill="white")
        except Exception:
            pass

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size))
    out.paste(img, (0, 0), mask)
    return ctk.CTkImage(light_image=out, dark_image=out, size=(size, size))


def load_plain_image(path, size, fallback_color=CARD_COLOR):
    try:
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        img = Image.open(path).convert("RGBA").resize((size, size))
    except Exception:
        img = Image.new("RGBA", (size, size), fallback_color)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))


# Sizes reduced from v3 - the previous hero logo (260px) alone pushed the
# chat area off-screen on normal laptop resolutions. These are the sizes
# that actually leave room for everything below them.
nova_hero_img = load_plain_image(resource_path("assets/nova_hero.png"), 140, fallback_color=BG_COLOR)
nova_orbit_img = load_plain_image(resource_path("assets/nova_orbit.png"), 100, fallback_color=BG_COLOR)
nova_avatar_img = load_circle_image(resource_path("assets/nova_avatar.png"), 34, fallback_letter="N", fallback_bg=ACCENT)
profile_avatar_img = load_circle_image(resource_path("assets/profile_avatar.jpeg"), 34, fallback_letter="D", fallback_bg="#3a3a55")
profile_avatar_img_top = load_circle_image(resource_path("assets/profile_avatar.jpeg"), 38, fallback_letter="D", fallback_bg="#3a3a55")

# Legacy animated face images - still used, but only inside the voice
# listening popup now (the mockup's home screen uses the logo instead).
face_open = Image.open(resource_path("assets/ai_face_open.png"))
face_open = face_open.resize((150, 150))
face_open = ImageTk.PhotoImage(face_open)

face_blink = Image.open(resource_path("assets/ai_face_blink.png"))
face_blink = face_blink.resize((150, 150))
face_blink = ImageTk.PhotoImage(face_blink)

face_talk = Image.open(resource_path("assets/ai_face_talk.png"))
face_talk = face_talk.resize((150, 150))
face_talk = ImageTk.PhotoImage(face_talk)

# ==========================================
# REMINDERS / NOTIFICATIONS (for Goals & Tasks)
# ==========================================

def send_notification(title, message):
    """Show a system notification (via plyer) or fall back to an
    in-app popup if plyer isn't installed. Also speaks the reminder
    aloud if voice replies are on."""
    add_notification_item(title, message)
    log_activity("Notification", f"{title}: {message}")
    notified_natively = False
    if plyer_notification is not None:
        try:
            plyer_notification.notify(title=title, message=message, app_name="Nova AI", timeout=8)
            notified_natively = True
        except Exception as exc:
            print("plyer notify failed:", exc)

    if not notified_natively:
        popup = ctk.CTkToplevel(app)
        popup.title(title)
        popup.geometry("320x150")
        popup.configure(fg_color=BG_COLOR)
        bring_window_to_front(popup)
        ctk.CTkLabel(popup, text=title, font=("Arial", 16, "bold")).pack(pady=(18, 4), padx=16)
        ctk.CTkLabel(popup, text=message, font=("Arial", 12), text_color=TEXT_MUTED, wraplength=280, justify="left").pack(pady=(0, 12), padx=16)
        ctk.CTkButton(popup, text="OK", fg_color=ACCENT, hover_color=ACCENT_HOVER, command=popup.destroy).pack(pady=(0, 14))

    if app_settings.get("voice_enabled", True):
        try:
            threading.Thread(target=lambda: speak(clean_text(f"Reminder: {message}")), daemon=True).start()
        except Exception as exc:
            print("reminder speak failed:", exc)


# Global guard so we only spawn the (once-a-day) plan-LM thread once.
_daily_run_started = False


def check_reminders():
    """Runs every 30 seconds. Fires a notification for any goal/task
    whose reminder time has arrived and hasn't fired yet. Also
    re-syncs the daily Merchant Navy routine if the date has rolled
    over (so leaving Nova open past midnight regenerates tomorrow's
    schedule without needing a restart)."""
    # NEW: once per day, run Nova's daily tracker/planner in the
    # background (logs yesterday, regenerates routine, builds today's
    # plan + optional bonus upgrade) without blocking the UI.
    global _daily_run_started
    _today_daily = str(date.today())
    if dashboard_data.get("daily_date") != _today_daily and not _daily_run_started:
        _daily_run_started = True

        def _daily_worker():
            try:
                msg = run_daily()
                if msg:
                    if "add_nova_bubble" in globals():
                        app.after(0, lambda: add_nova_bubble(msg))
            finally:
                global _daily_run_started
                _daily_run_started = False

        threading.Thread(target=_daily_worker, daemon=True).start()

    if sync_routine_for_today():
        for _refresh_fn_name in ("render_goals", "render_tasks", "refresh_goals_preview"):
            _refresh_fn = globals().get(_refresh_fn_name)
            if _refresh_fn is not None:
                try:
                    _refresh_fn()
                except Exception:
                    pass
        if "add_nova_bubble" in globals():
            try:
                add_nova_bubble("\U0001F4C6 Aaj ka routine (tasks/goals) auto-generate ho gaya.")
            except Exception:
                pass

    # Coach chat: 9 PM daily rating (once per day)
    if should_generate_rating_now():
        rating_text = generate_daily_rating()
        for _bubble_fn_name in ("add_coach_nova_bubble", "add_nova_bubble"):
            _bubble_fn = globals().get(_bubble_fn_name)
            if _bubble_fn is not None:
                try:
                    _bubble_fn(rating_text)
                except Exception:
                    pass

    # Coach chat: midnight reset (clears the chat, keeps the ratings log)
    if reset_for_new_day_if_needed():
        _coach_scroll = globals().get("coach_chat_scroll")
        _add_coach_bubble = globals().get("add_coach_nova_bubble")
        if _coach_scroll is not None and _add_coach_bubble is not None:
            try:
                for widget in _coach_scroll.winfo_children():
                    widget.destroy()
                _add_coach_bubble(
                    "Naya din shuru! Kal ki baatcheet clear ho gayi hai (rating history safe hai). "
                    "Aaj ke goals/tasks/nutrition ke baare me pucho.",
                    save=False,
                )
            except Exception:
                pass

    now = datetime.now()
    changed = False
    for key in ("goals", "tasks"):
        for item in dashboard_data.get(key, []):
            remind_at = item.get("remind_at")
            if not remind_at or item.get("done") or item.get("notified"):
                continue
            try:
                due = datetime.strptime(remind_at, "%Y-%m-%d %H:%M")
            except ValueError:
                continue
            if now >= due:
                label = "Goal" if key == "goals" else "Task"
                send_notification(f"Nova Reminder - {label}", item["text"])
                if "add_nova_bubble" in globals():
                    try:
                        add_nova_bubble(f"\u23F0 Reminder: {item['text']}")
                    except Exception:
                        pass
                item["notified"] = True
                changed = True
    if changed:
        save_dashboard_data()
    app.after(30000, check_reminders)

# ==========================================
# GLOBAL VARIABLES
# ==========================================

listening_window = None
wave_canvas = None
wave_bars = []
popup_face_label = None
status_label = None
license_label = None
speak_button = None
search_hint_label = None
profile_status_label = None
focus_running = False
focus_ring_canvas = None
focus_toggle_button = None
quick_focus_button = None
streak_canvas = None
memory_preview_frame = None
nav_buttons = {}
current_page_key = "home"
screen_watch_active = False
screen_watch_thread = None
camera_window = None
camera_active = False
camera_label = None
camera_capture = None
camera_question_entry = None
screen_watch_button = None
camera_button = None
listening_status_label = None
attached_file_context = None
mode_menu = None
assistant_status_label = None

# ==========================================
# UI HELPERS
# ==========================================

FONT_FAMILY = "Segoe UI"
# Font that supports coloured emoji glyphs on Windows (used for chat bubbles).
CHAT_FONT_FAMILY = "Segoe UI Emoji"
PANEL_RADIUS = 8
TILE_RADIUS = 8


def make_section_title(parent, title, subtitle=None):
    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.pack(fill="x", pady=(4, 14))
    ctk.CTkLabel(
        block, text=title, font=(FONT_FAMILY, 24, "bold"),
        text_color=TEXT_MAIN, anchor="w"
    ).pack(fill="x")
    if subtitle:
        ctk.CTkLabel(
            block, text=subtitle, font=(FONT_FAMILY, 12),
            text_color=TEXT_MUTED, anchor="w", justify="left", wraplength=720
        ).pack(fill="x", pady=(3, 0))
    return block


def make_metric_card(parent, label, value, detail, accent_color=ACCENT):
    card = ctk.CTkFrame(parent, fg_color=CARD_COLOR_SOFT, corner_radius=TILE_RADIUS)
    ctk.CTkLabel(
        card, text=label.upper(), font=(FONT_FAMILY, 10, "bold"),
        text_color=TEXT_MUTED, anchor="w"
    ).pack(fill="x", padx=12, pady=(12, 0))
    ctk.CTkLabel(
        card, text=value, font=(FONT_FAMILY, 21, "bold"),
        text_color=accent_color, anchor="w"
    ).pack(fill="x", padx=12, pady=(2, 0))
    ctk.CTkLabel(
        card, text=detail, font=(FONT_FAMILY, 11),
        text_color=TEXT_MUTED, anchor="w", wraplength=170
    ).pack(fill="x", padx=12, pady=(2, 12))
    return card


def make_tool_card(parent, title, subtitle, command, row, column):
    card = ctk.CTkFrame(parent, fg_color=CARD_COLOR, corner_radius=TILE_RADIUS)
    card.grid(row=row, column=column, padx=6, pady=6, sticky="nsew")
    card.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(
        card, text=title, font=(FONT_FAMILY, 14, "bold"),
        text_color=TEXT_MAIN, anchor="w"
    ).grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 2))
    ctk.CTkLabel(
        card, text=subtitle, font=(FONT_FAMILY, 11),
        text_color=TEXT_MUTED, anchor="w", justify="left", wraplength=190
    ).grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 12))
    ctk.CTkButton(
        card, text="Open", height=30, fg_color=ACCENT_SOFT,
        hover_color=ACCENT, text_color=TEXT_MAIN, command=command
    ).grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 14))
    return card


def current_streak_count():
    count = 0
    d = date.today()
    while str(d) in dashboard_data["streak_days"]:
        count += 1
        d -= timedelta(days=1)
    return count


def log_activity(title, detail=""):
    dashboard_data.setdefault("activity_log", []).append({
        "time": time.strftime("%Y-%m-%d %H:%M"),
        "title": title,
        "detail": detail,
    })
    dashboard_data["activity_log"] = dashboard_data["activity_log"][-120:]
    save_dashboard_data()


def add_notification_item(title, detail=""):
    dashboard_data.setdefault("notifications", []).append({
        "time": time.strftime("%Y-%m-%d %H:%M"),
        "title": title,
        "detail": detail,
        "read": False,
    })
    dashboard_data["notifications"] = dashboard_data["notifications"][-80:]
    save_dashboard_data()


def set_assistant_mode(mode):
    dashboard_data["assistant_mode"] = mode
    save_dashboard_data()
    if assistant_status_label is not None:
        assistant_status_label.configure(text=f"{mode} Mode")
    # Also refresh the right-sidebar status card so it doesn't stay stale.
    try:
        refresh_assistant_status()
    except Exception:
        pass
    log_activity("Mode changed", mode)


def get_current_thread():
    threads = dashboard_data.setdefault("chat_threads", {})
    thread_id = dashboard_data.get("current_thread_id", "main")
    return threads.setdefault(thread_id, {
        "title": "Main Chat" if thread_id == "main" else "New Chat",
        "created_at": time.strftime("%Y-%m-%d %H:%M"),
        "messages": [],
    })


def make_thread(title=None):
    thread_id = f"thread_{int(time.time())}_{random.randint(100, 999)}"
    dashboard_data.setdefault("chat_threads", {})[thread_id] = {
        "title": title or f"Chat {len(dashboard_data.get('chat_threads', {})) + 1}",
        "created_at": time.strftime("%Y-%m-%d %H:%M"),
        "messages": [],
    }
    dashboard_data["current_thread_id"] = thread_id
    save_dashboard_data()
    log_activity("New chat thread", dashboard_data["chat_threads"][thread_id]["title"])
    return thread_id


def rebuild_home_chat():
    if "chat_scroll" not in globals():
        return
    for widget in chat_scroll.winfo_children():
        widget.destroy()
    messages = get_current_thread().get("messages", [])
    if not messages:
        add_nova_bubble(random.choice(greetings), save=False)
        return
    for entry in messages:
        if entry.get("sender") == "user":
            add_user_bubble(entry.get("text", ""), time_str=entry.get("time"), save=False)
        else:
            add_nova_bubble(entry.get("text", ""), time_str=entry.get("time"), save=False)


# ==========================================
# SETTINGS HELPERS (theme / language / voice) - unchanged logic
# ==========================================

def apply_theme(choice):
    mode = "light" if str(choice).lower() == "light" else "dark"
    ctk.set_appearance_mode(mode)
    app_settings["theme"] = choice
    save_settings(app_settings)


def save_language(choice):
    app_settings["language"] = choice
    update_setting("language", choice)


def update_voice_ui():
    if status_label is not None:
        voice_text = "Voice On" if app_settings.get("voice_enabled", True) else "Voice Off"
        license_text = "Licensed" if is_license_valid() else "No License"
        status_label.configure(text=f"{voice_text}  |  {license_text}")

    if license_label is not None:
        license_label.configure(text=get_license_status())

    if speak_button is not None:
        if app_settings.get("voice_enabled", True):
            speak_button.configure(fg_color=ACCENT_SOFT, text_color=ACCENT)
        else:
            speak_button.configure(fg_color=ACCENT_SOFT, text_color=DANGER)


def set_voice_enabled(enabled, save=True):
    enabled = bool(enabled)
    app_settings["voice_enabled"] = enabled
    if save:
        save_settings(app_settings)
    if enabled:
        unmute_voice()
    else:
        mute_voice()
    update_voice_ui()
    return enabled


def toggle_voice(setting=None):
    if setting is None:
        enabled = not app_settings.get("voice_enabled", True)
    else:
        enabled = setting.get() == 1
    return set_voice_enabled(enabled)


def refresh_status():
    update_voice_ui()


def paste_command_example(example):
    message_entry.delete(0, "end")
    message_entry.insert(0, example)
    message_entry.focus()


def run_command_example(example):
    paste_command_example(example)
    send_message()


def send_prefilled(text):
    """Fill the chat box with a prompt and jump to Home so the user can send it."""
    show_page("home")
    message_entry.delete(0, "end")
    message_entry.insert(0, text)
    message_entry.focus()


# ==========================================
# CONFIRMATION DIALOG — used for shutdown, restart, agent destructive ops
# (Integrated from gui_integration.py — these were missing and caused
#  NameError crashes in send_message() whenever a destructive command
#  or privacy-mode check ran.)
# ==========================================

def confirm_destructive(message):
    """
    Pop a modal that asks the user to confirm a destructive action.
    Returns True only if the user clicks the red Confirm button.
    Default focus is on Cancel, so a stray Enter key cancels.
    """
    win = ctk.CTkToplevel(app)
    win.title("Confirm")
    win.geometry("420x200")
    win.configure(fg_color=BG_COLOR)
    win.transient(app)
    win.grab_set()
    bring_window_to_front(win)

    ctk.CTkLabel(
        win,
        text=message,
        font=("Arial", 14),
        wraplength=380,
        justify="left",
    ).pack(padx=20, pady=(22, 14), fill="x")

    result = {"ok": False}

    def _ok():
        result["ok"] = True
        win.destroy()

    def _cancel():
        result["ok"] = False
        win.destroy()

    row = ctk.CTkFrame(win, fg_color="transparent")
    row.pack(fill="x", padx=20, pady=(0, 18))
    cancel_btn = ctk.CTkButton(
        row, text="Cancel", fg_color=CARD_COLOR, hover_color=CARD_COLOR_SOFT,
        command=_cancel, width=160, height=40,
    )
    cancel_btn.pack(side="left", padx=(0, 8))
    confirm_btn = ctk.CTkButton(
        row, text="Confirm", fg_color=DANGER, hover_color=DANGER_HOVER,
        command=_ok, width=160, height=40,
    )
    confirm_btn.pack(side="right")
    cancel_btn.focus_set()  # default focus on Cancel
    win.bind("<Return>", lambda e: _cancel())
    win.bind("<Escape>", lambda e: _cancel())
    win.protocol("WM_DELETE_WINDOW", _cancel)
    app.wait_window(win)
    return result["ok"]


def _format_result_for_display(result, indent=0):
    """Convert a feature result dict into nicely formatted text lines."""
    lines = []
    if isinstance(result, dict):
        for key, value in result.items():
            if key in ("success", "feature") and indent == 0:
                continue
            if isinstance(value, (dict,)):
                lines.append(f"{'  ' * indent}▸ {key.replace('_', ' ').title()}:")
                lines.extend(_format_result_for_display(value, indent + 1))
            elif isinstance(value, (list, tuple)):
                lines.append(f"{'  ' * indent}▸ {key.replace('_', ' ').title()}:")
                for item in value:
                    if isinstance(item, dict):
                        # Render list-item dict on one line
                        parts = []
                        for k, v in item.items():
                            if k == "unlocked":
                                parts.append("✅ Unlocked" if v else "🔒 Locked")
                            elif k in ("icon",):
                                parts.append(f"{v}")
                            elif k == "title":
                                parts.append(f"{v}")
                            else:
                                parts.append(f"{k.replace('_', ' ').title()}: {v}")
                        lines.append(f"{'  ' * (indent + 1)}• {' — '.join(parts)}")
                    else:
                        lines.append(f"{'  ' * (indent + 1)}• {item}")
            elif key == "message" and value:
                lines.append(f"\n{'  ' * indent}{value}")
            else:
                lines.append(f"{'  ' * indent}▸ {key.replace('_', ' ').title()}: {value}")
    else:
        lines.append(str(result))
    return lines


def show_popup(title, result, result_type="generic"):
    """Show feature result in a styled popup window."""
    popup = ctk.CTkToplevel(app)
    popup.title(f"Nova — {title}")
    popup.geometry("560x440")
    popup.configure(fg_color=BG_COLOR)
    popup.transient(app)
    try:
        bring_window_to_front(popup)
    except Exception:
        pass

    # Header
    header = ctk.CTkFrame(popup, fg_color=ACCENT_SOFT, corner_radius=0, height=56)
    header.pack(fill="x")
    header.pack_propagate(False)
    ctk.CTkLabel(header, text=f"  {title}", font=("Arial", 18, "bold"),
                 text_color="#eaeaea", anchor="w").pack(side="left", padx=18)

    # Body (scrollable)
    body = ctk.CTkFrame(popup, fg_color=BG_COLOR)
    body.pack(fill="both", expand=True, padx=14, pady=14)

    text_widget = tk.Text(
        body, wrap="word", bg="#16213e", fg="#eaeaea", relief="flat",
        font=("Consolas", 11), padx=14, pady=12, bd=0, highlightthickness=0,
    )
    scrollbar = tk.Scrollbar(body, command=text_widget.yview, bg="#0f3460")
    text_widget.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    text_widget.pack(fill="both", expand=True)

    # Render result
    if isinstance(result, dict):
        lines = _format_result_for_display(result)
        text_widget.insert("1.0", "\n".join(lines))
    elif isinstance(result, (list, tuple)):
        for i, item in enumerate(result, 1):
            text_widget.insert("end", f"{i}. {item}\n")
    else:
        text_widget.insert("1.0", str(result))

    text_widget.config(state="disabled")

    # Footer with close button
    footer = ctk.CTkFrame(popup, fg_color="transparent")
    footer.pack(fill="x", padx=14, pady=(0, 14))
    ctk.CTkButton(
        footer, text="Close", command=popup.destroy,
        fg_color=ACCENT, hover_color=ACCENT_SOFT,
        font=("Arial", 13, "bold"), height=36, width=120,
    ).pack(side="right")

    popup.after(300, lambda: popup.focus_set())


def open_app_launcher():
    """Open an interactive app launcher window where user types an app name to launch."""
    win = ctk.CTkToplevel(app)
    win.title("Nova — App Launcher")
    win.geometry("460x380")
    win.configure(fg_color=BG_COLOR)
    win.transient(app)
    try:
        bring_window_to_front(win)
    except Exception:
        pass

    # Header
    header = ctk.CTkFrame(win, fg_color=ACCENT_SOFT, corner_radius=0, height=52)
    header.pack(fill="x")
    header.pack_propagate(False)
    ctk.CTkLabel(header, text="  🚀 App Launcher", font=("Arial", 17, "bold"),
                 text_color="#eaeaea", anchor="w").pack(side="left", padx=18)

    # Help text
    ctk.CTkLabel(
        win, text="App ka naam likho (notepad, chrome, excel...)",
        font=("Arial", 12), text_color=TEXT_MUTED, anchor="w",
    ).pack(fill="x", padx=18, pady=(14, 4))

    # Input row
    input_row = ctk.CTkFrame(win, fg_color="transparent")
    input_row.pack(fill="x", padx=18)
    entry = ctk.CTkEntry(input_row, placeholder_text="e.g. notepad, chrome, vscode, word",
                         height=40, font=("Arial", 13))
    entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

    def _do_launch():
        app_name = entry.get().strip()
        if not app_name:
            result_label.configure(text="⚠️ App name likho!", text_color="#f85149")
            return
        result = launch_app(app_name)
        if result.get("success"):
            result_label.configure(text=result.get("message", ""), text_color="#3fb950")
        else:
            result_label.configure(text=result.get("message", "Nahi mila"), text_color="#f85149")

    launch_btn = ctk.CTkButton(input_row, text="Launch", command=_do_launch,
                               fg_color=ACCENT, hover_color=ACCENT_SOFT,
                               font=("Arial", 13, "bold"), height=40, width=80)
    launch_btn.pack(side="right")
    entry.bind("<Return>", lambda e: _do_launch())

    # Result label
    result_label = ctk.CTkLabel(win, text="", font=("Arial", 12), text_color="#3fb950",
                                anchor="w", wraplength=420)
    result_label.pack(fill="x", padx=18, pady=(6, 0))

    # Available apps list (scrollable)
    ctk.CTkLabel(win, text="Available Apps:", font=("Arial", 12, "bold"),
                 text_color="#eaeaea", anchor="w").pack(fill="x", padx=18, pady=(10, 4))

    list_frame = ctk.CTkFrame(win, fg_color=CARD_COLOR)
    list_frame.pack(fill="both", expand=True, padx=14, pady=(0, 8))

    apps_info = get_known_apps()
    apps = apps_info.get("apps", [])

    # Show apps as clickable buttons in a grid
    import math
    cols = 3
    for i, name in enumerate(apps):
        row = i // cols
        col = i % cols
        btn = ctk.CTkButton(
            list_frame, text=name, height=30, font=("Arial", 11),
            fg_color=CARD_COLOR_SOFT, hover_color=ACCENT_SOFT,
            command=lambda n=name: (entry.delete(0, "end"), entry.insert(0, n), _do_launch()),
        )
        btn.grid(row=row, column=col, padx=4, pady=3, sticky="ew")
        list_frame.grid_columnconfigure(col, weight=1)

    ctk.CTkButton(win, text="Close", command=win.destroy,
                  fg_color=CARD_COLOR, hover_color=CARD_COLOR_SOFT,
                  font=("Arial", 12), height=32, width=100).pack(pady=(0, 12))

    entry.focus_set()


def open_live_monitor():
    """Open a STANDALONE live monitor window that keeps tracking the active window
    even when user switches to other apps. Not tied to Nova's window.
    """
    win = ctk.CTkToplevel(app)
    win.title("Nova — Live Monitor")
    win.geometry("520x460")
    win.configure(fg_color=BG_COLOR)
    # Independent window — stays open even when Nova loses focus.
    try:
        win.attributes("-topmost", True)
        win.attributes("-topmost", False)
    except Exception:
        pass

    header = ctk.CTkFrame(win, fg_color=ACCENT_SOFT, corner_radius=0, height=50)
    header.pack(fill="x")
    header.pack_propagate(False)
    ctk.CTkLabel(header, text="  📡 Live Screen Monitor", font=("Arial", 16, "bold"),
                 text_color="#eaeaea", anchor="w").pack(side="left", padx=16)

    status_frame = ctk.CTkFrame(win, fg_color=CARD_COLOR, corner_radius=10)
    status_frame.pack(fill="x", padx=14, pady=(14, 8))
    status_label = ctk.CTkLabel(status_frame, text="Detecting...", font=("Arial", 13),
                                text_color="#eaeaea", justify="left", anchor="w", wraplength=460)
    status_label.pack(fill="x", padx=12, pady=10)

    sugg_label_title = ctk.CTkLabel(win, text="💡 Suggestion", font=("Arial", 13, "bold"),
                                    text_color="#eaeaea", anchor="w")
    sugg_label_title.pack(fill="x", padx=16, pady=(6, 2))
    sugg_frame = ctk.CTkFrame(win, fg_color=CARD_COLOR, corner_radius=10)
    sugg_frame.pack(fill="x", padx=14)
    sugg_label = ctk.CTkLabel(sugg_frame, text="Analyzing...", font=("Arial", 12),
                              text_color=TEXT_MUTED, justify="left", anchor="w", wraplength=460)
    sugg_label.pack(fill="x", padx=12, pady=8)

    ctk.CTkLabel(win, text="🕘 Window History", font=("Arial", 13, "bold"),
                 text_color="#eaeaea", anchor="w").pack(fill="x", padx=16, pady=(8, 2))
    log_frame = ctk.CTkFrame(win, fg_color=CARD_COLOR, corner_radius=10)
    log_frame.pack(fill="both", expand=True, padx=14, pady=(0, 8))
    log_text = tk.Text(log_frame, wrap="word", bg="#1c212c", fg="#a5adbd",
                       relief="flat", font=("Consolas", 10), height=7, bd=0,
                       highlightthickness=0, padx=10, pady=8)
    log_text.pack(fill="both", expand=True)
    log_text.insert("1.0", "Switch to different apps to see them appear here...\n")
    log_text.config(state="disabled")

    footer = ctk.CTkFrame(win, fg_color="transparent")
    footer.pack(fill="x", padx=14, pady=(0, 12))
    ctk.CTkLabel(footer, text="Updates every 2s", font=("Arial", 10),
                 text_color=TEXT_MUTED).pack(side="left")
    ctk.CTkButton(footer, text="Close", command=win.destroy, fg_color=DANGER,
                  hover_color=DANGER_HOVER, font=("Arial", 12), height=34, width=100).pack(side="right")

    seen_windows = {}

    def _append_log(text):
        log_text.config(state="normal")
        log_text.insert("end", text + "\n")
        log_text.see("end")
        log_text.config(state="disabled")

    def refresh():
        if not win.winfo_exists():
            return
        try:
            status = get_screen_status()
            status_label.configure(text=status.get("message", "No data"))
            app_name = status.get("active_window", {}).get("process_name", "unknown")
            win_title = status.get("active_window", {}).get("window_title", "")
            key = f"{app_name} • {win_title}"
            if key not in seen_windows:
                seen_windows[key] = True
                from datetime import datetime
                ts = datetime.now().strftime("%H:%M:%S")
                _append_log(f"[{ts}] → {key}")
            sug = analyze_screen_and_suggest()
            sug_list = sug.get("suggestions", [])
            if sug_list:
                first = sug_list[0]
                sugg_label.configure(text=f"{first.get('title')}\n{first.get('description')}", text_color="#eaeaea")
            else:
                sugg_label.configure(text="No suggestion", text_color=TEXT_MUTED)
        except Exception as e:
            status_label.configure(text=f"Error: {e}")
        win.after(2000, refresh)

    win.after(1000, refresh)


# NOVA TOP-25 FEATURES — Browser Control, Alarm, Email dialogs
# ==========================================

def open_browser_control():
    """Dialog to open a website URL in a new tab or search the web."""
    d = ctk.CTkToplevel(app)
    d.title("Nova — Browser Control")
    d.geometry("460x180")
    d.configure(fg_color=BG_COLOR)
    d.transient(app)
    d.grab_set()
    ctk.CTkLabel(d, text="  🌐 Open Website / Search the Web",
                 font=("Arial", 15, "bold"), text_color="#eaeaea", anchor="w").pack(anchor="w", padx=14, pady=(14, 4))
    url_entry = ctk.CTkEntry(d, placeholder_text="URL like google.com  OR  search term", font=("Arial", 12), width=400)
    url_entry.pack(pady=10)

    def _go():
        q = url_entry.get().strip()
        if not q:
            return
        if q.startswith("http") or "." in q:
            res = open_new_tab(q)
        else:
            res = browser_search(q, "google")
        show_popup("Browser", res)
        d.destroy()

    btns = ctk.CTkFrame(d, fg_color="transparent")
    btns.pack(pady=8)
    ctk.CTkButton(btns, text="🔍 Go", command=_go, fg_color=ACCENT, width=90).pack(side="left", padx=6)
    ctk.CTkButton(btns, text="Close", command=d.destroy, fg_color=DANGER, hover_color=DANGER_HOVER, width=80).pack(side="left", padx=6)
    url_entry.focus_set()






def open_alarm_manager():
    """Dialog to set an alarm with label, time and repeat option."""
    d = ctk.CTkToplevel(app)
    d.title("Nova — Alarm Scheduler")
    d.geometry("460x240")
    d.configure(fg_color=BG_COLOR)
    d.transient(app)
    d.grab_set()
    ctk.CTkLabel(d, text="  ⏰ Set New Alarm", font=("Arial", 15, "bold"),
                 text_color="#eaeaea", anchor="w").pack(anchor="w", padx=14, pady=(14, 4))
    label_entry = ctk.CTkEntry(d, placeholder_text="Label (e.g. Wake up, Meeting)", font=("Arial", 12), width=400)
    label_entry.pack(pady=5)
    time_entry = ctk.CTkEntry(d, placeholder_text="Time: 24h HH:MM (e.g. 07:30)", font=("Arial", 12), width=400)
    time_entry.pack(pady=5)
    repeat_var = ctk.StringVar(value="daily")
    rep = ctk.CTkComboBox(d, values=["Once", "daily", "weekdays", "weekends"],
                          variable=repeat_var, width=220, font=("Arial", 11))
    rep.set("daily")
    rep.pack(pady=4)

    def _set():
        lbl = label_entry.get().strip() or "Alarm"
        t = time_entry.get().strip()
        rep_map = {"Once": None, "daily": "daily", "weekdays": "weekdays", "weekends": "weekends"}
        res = set_alarm(lbl, t, rep_map.get(repeat_var.get()))
        show_popup("Alarm", res)
        d.destroy()

    btns = ctk.CTkFrame(d, fg_color="transparent")
    btns.pack(pady=10)
    ctk.CTkButton(btns, text="💾 Set Alarm", command=_set, fg_color=SUCCESS, width=100).pack(side="left", padx=6)
    ctk.CTkButton(btns, text="📋 List", command=lambda: show_popup("All Alarms", get_alarms()),
                  fg_color=ACCENT, width=70).pack(side="left", padx=6)
    ctk.CTkButton(btns, text="Close", command=d.destroy, fg_color=DANGER, hover_color=DANGER_HOVER, width=70).pack(side="left", padx=6)
    label_entry.focus_set()


def open_email_manager():
    """Dialog to save email SMTP config & send a test reminder email."""
    d = ctk.CTkToplevel(app)
    d.title("Nova — Email Notifications")
    d.geometry("480x340")
    d.configure(fg_color=BG_COLOR)
    d.transient(app)
    d.grab_set()
    ctk.CTkLabel(d, text="  📧 Email Notification Center", font=("Arial", 15, "bold"),
                 text_color="#eaeaea", anchor="w").pack(anchor="w", padx=14, pady=(14, 4))

    status = get_email_status()
    ctk.CTkLabel(d, text=f"Status: {status.get('message')}", font=("Arial", 11),
                 text_color=("#4ade80" if status.get("configured") else "#f59e0b")).pack(pady=4)

    email_entry = ctk.CTkEntry(d, placeholder_text="Your email (you@gmail.com)", width=430, font=("Arial", 11))
    email_entry.pack(pady=4)
    pass_entry = ctk.CTkEntry(d, placeholder_text="Password / App-password", show="•", width=430, font=("Arial", 11))
    pass_entry.pack(pady=4)
    host_entry = ctk.CTkEntry(d, placeholder_text="SMTP host (smtp.gmail.com)", width=430, font=("Arial", 11))
    host_entry.insert(0, "smtp.gmail.com")
    host_entry.pack(pady=4)

    def _save():
        em = email_entry.get().strip()
        pw = pass_entry.get().strip()
        ho = host_entry.get().strip() or "smtp.gmail.com"
        if not em or not pw:
            show_popup("Email", {"message": "⚠️ Email & password required"})
            return
        res = save_email_config(em, pw, ho, 587, em.split("@")[1].split(".")[0])
        show_popup("Email Config", res)
        d.destroy()

    def _test():
        recip = email_entry.get().strip() or "test@example.com"
        res = send_reminder_email("Nova email notifications working! ✅", recip)
        show_popup("Email Test", res)

    btns = ctk.CTkFrame(d, fg_color="transparent")
    btns.pack(pady=10)
    ctk.CTkButton(btns, text="💾 Save", command=_save, fg_color=SUCCESS, width=95).pack(side="left", padx=6)
    ctk.CTkButton(btns, text="📤 Test Mail", command=_test, fg_color=ACCENT, width=105).pack(side="left", padx=6)
    ctk.CTkButton(btns, text="Close", command=d.destroy, fg_color=DANGER, hover_color=DANGER_HOVER, width=75).pack(side="left", padx=6)


# ==========================================

def _is_privacy_mode_on() -> bool:
    return bool(app_settings.get("privacy_mode", False))


def set_privacy_mode(enabled: bool):
    app_settings["privacy_mode"] = bool(enabled)
    save_settings(app_settings)
    state = "ON" if enabled else "OFF"
    add_nova_bubble(f"\U0001F512 Privacy mode {state}. "
                    f"System actions are {'blocked' if enabled else 'allowed'}.")


def toggle_privacy_mode():
    set_privacy_mode(not _is_privacy_mode_on())


def add_privacy_chip(parent):
    """Quick-access privacy mode toggle button for the sidebar."""
    chip = ctk.CTkButton(
        parent, text="\U0001F512 Privacy: OFF", height=30, font=("Arial", 11),
        fg_color=CARD_COLOR, hover_color=ACCENT_SOFT,
        command=toggle_privacy_mode,
    )
    chip.pack(fill="x", padx=14, pady=(0, 8))

    def _refresh_chip():
        chip.configure(
            text="\U0001F512 Privacy: ON" if _is_privacy_mode_on() else "\U0001F512 Privacy: OFF",
            fg_color=ACCENT_SOFT if _is_privacy_mode_on() else CARD_COLOR,
        )

    chip.configure(command=lambda: (toggle_privacy_mode(), _refresh_chip()))
    _refresh_chip()


# ==========================================
# FORGET ME — wipe all local data after explicit double confirmation
# ==========================================

def forget_everything():
    if not confirm_destructive(
        "Delete ALL Nova data on this computer?\n\n"
        "This will remove:\n"
        "  \U0001F4BE saved memory (name, color, custom facts)\n"
        "  \U0001F4AC chat history (home + coach)\n"
        "  \U0001F4DD journal and notes\n"
        "  \U0001F37D nutrition profile\n"
        "  \U0001F525 focus / streak data\n"
        "  \U0001F511 license\n\n"
        "This action CANNOT be undone."
    ):
        return "Cancelled."

    if not confirm_destructive(
        "Are you absolutely sure? Click Confirm one more time to proceed."
    ):
        return "Cancelled."

    from pathlib import Path

    # 1) memory
    try:
        from memory import clear_memory
        clear_memory()
    except Exception as exc:
        log.warning("clear_memory failed: %s", exc)

    # 2) dashboard data
    try:
        dashboard_data["chat_history"] = []
        dashboard_data["goals"] = []
        dashboard_data["tasks"] = []
        dashboard_data["notes"] = []
        dashboard_data["journal"] = []
        dashboard_data["streak_days"] = []
        dashboard_data["focus_minutes_today"] = 0
        dashboard_data["focus_goal_minutes"] = 120
        dashboard_data["profile"] = {}
        save_dashboard_data()
    except Exception as exc:
        log.warning("dashboard_data reset failed: %s", exc)

    # 3) history.json
    try:
        for candidate in (Path("history.json"),
                          Path.home() / ".nova" / "history.json"):
            if candidate.exists():
                candidate.unlink()
    except Exception as exc:
        log.warning("history.json delete failed: %s", exc)

    # 4) license
    try:
        for candidate in (Path("license.json"),
                          Path.home() / ".nova" / "license.json"):
            if candidate.exists():
                candidate.unlink()
    except Exception as exc:
        log.warning("license.json delete failed: %s", exc)

    # 5) settings — keep theme but clear everything else
    try:
        save_settings({"theme": "Dark", "language": "English",
                       "voice_enabled": True, "privacy_mode": False})
    except Exception as exc:
        log.warning("settings reset failed: %s", exc)

    add_nova_bubble("\U0001F9F9 Sab data delete ho gaya. App restart kar lo.")


# ==========================================
# LICENSE WINDOW (unchanged)
# ==========================================

def open_license_window(required=False):
    license_window = ctk.CTkToplevel(app)
    license_window.title("Nova License")
    license_window.geometry("520x360")
    license_window.resizable(False, False)
    license_window.configure(fg_color=BG_COLOR)

    license_window.transient(app)
    license_window.grab_set()
    bring_window_to_front(license_window)

    if required:
        license_window.protocol("WM_DELETE_WINDOW", app.destroy)

    title = ctk.CTkLabel(license_window, text="License Activation", font=("Arial", 26, "bold"))
    title.pack(pady=(24, 8))

    global license_label
    license_label = ctk.CTkLabel(
        license_window, text=get_license_status(), font=("Arial", 13),
        text_color="#f7022b", wraplength=440
    )
    license_label.pack(padx=24, pady=(0, 18))

    key_entry = ctk.CTkEntry(license_window, placeholder_text="Enter license key", height=42, font=("Arial", 14))
    key_entry.pack(fill="x", padx=28, pady=8)

    owner_entry = ctk.CTkEntry(license_window, placeholder_text="Owner name", height=42, font=("Arial", 14))
    owner_entry.pack(fill="x", padx=28, pady=8)

    result_label = ctk.CTkLabel(license_window, text="", font=("Arial", 13), text_color="#8b949e")
    result_label.pack(pady=(8, 0))

    def submit_license():
        success, message = activate_license(key_entry.get().strip(), owner=owner_entry.get().strip())
        result_label.configure(text=message, text_color="#3fb950" if success else "#f85149")
        refresh_status()
        if success and required:
            license_window.destroy()
            app.deiconify()

    activate_button = ctk.CTkButton(
        license_window, text="Activate", height=40, fg_color=ACCENT, hover_color=ACCENT_HOVER,
        command=submit_license
    )
    activate_button.pack(fill="x", padx=28, pady=18)

# ==========================================
# MEMORY MANAGER WINDOW (unchanged logic, refreshes the home preview too)
# ==========================================

def open_memory_manager():
    memory_window = ctk.CTkToplevel(app)
    memory_window.title("Nova Memory")
    memory_window.geometry("620x520")
    memory_window.transient(app)
    memory_window.configure(fg_color=BG_COLOR)
    bring_window_to_front(memory_window)

    title = ctk.CTkLabel(memory_window, text="Saved Memory", font=("Arial", 26, "bold"))
    title.pack(pady=(22, 8))

    subtitle = ctk.CTkLabel(
        memory_window, text="Nova saves only facts you explicitly say with \"remember\".",
        font=("Arial", 13), text_color="#8b949e"
    )
    subtitle.pack(pady=(0, 12))

    form = ctk.CTkFrame(memory_window, fg_color=CARD_COLOR, corner_radius=10)
    form.pack(fill="x", padx=22, pady=(0, 12))

    key_entry = ctk.CTkEntry(form, placeholder_text="memory key", height=38)
    key_entry.pack(side="left", fill="x", expand=True, padx=(12, 6), pady=12)

    value_entry = ctk.CTkEntry(form, placeholder_text="memory value", height=38)
    value_entry.pack(side="left", fill="x", expand=True, padx=6, pady=12)

    list_frame = ctk.CTkScrollableFrame(memory_window, fg_color="#0d1117", corner_radius=10)
    list_frame.pack(fill="both", expand=True, padx=22, pady=(0, 22))

    def render_memory():
        for widget in list_frame.winfo_children():
            widget.destroy()

        facts = get_saved_facts()
        if not facts:
            empty = ctk.CTkLabel(list_frame, text="No saved memory yet.", text_color="#8b949e")
            empty.pack(pady=18)
        else:
            for key, value in facts.items():
                row = ctk.CTkFrame(list_frame, fg_color="#21262d", corner_radius=8)
                row.pack(fill="x", padx=8, pady=6)

                text = ctk.CTkLabel(row, text=f"{key}: {value}", anchor="w", justify="left", wraplength=390)
                text.pack(side="left", fill="x", expand=True, padx=12, pady=10)

                edit_button = ctk.CTkButton(
                    row, text="Edit", width=62, command=lambda k=key, v=value: load_memory_for_edit(k, v)
                )
                edit_button.pack(side="left", padx=(4, 4), pady=8)

                delete_button = ctk.CTkButton(
                    row, text="Delete", width=72, fg_color=DANGER, hover_color=DANGER_HOVER,
                    command=lambda k=key: remove_memory(k)
                )
                delete_button.pack(side="right", padx=(4, 10), pady=8)

        refresh_memory_preview()

    def load_memory_for_edit(key, value):
        key_entry.delete(0, "end")
        key_entry.insert(0, key)
        value_entry.delete(0, "end")
        value_entry.insert(0, value)

    def save_memory_item():
        key = key_entry.get().strip().lower().replace(" ", "_")
        value = value_entry.get().strip()
        if not key or not value:
            return
        remember(key, value)
        key_entry.delete(0, "end")
        value_entry.delete(0, "end")
        render_memory()

    def remove_memory(key):
        delete_memory(key)
        render_memory()

    save_button = ctk.CTkButton(form, text="Save", width=74, fg_color=ACCENT, hover_color=ACCENT_HOVER, command=save_memory_item)
    save_button.pack(side="right", padx=(6, 12), pady=12)

    render_memory()

def open_knowledge_trainer():
    """Pop-out window that lets the user train Nova on their own data."""
    kt = ctk.CTkToplevel(app)
    kt.title("Train Nova - Personal Knowledge")
    kt.geometry("720x640")
    kt.transient(app)
    kt.configure(fg_color=BG_COLOR)
    bring_window_to_front(kt)

    title = ctk.CTkLabel(kt, text="Train Nova", font=("Arial", 26, "bold"))
    title.pack(pady=(22, 6))

    subtitle = ctk.CTkLabel(
        kt, text="Teach Nova from your paragraphs, photos (OCR/vision), and PDFs.",
        font=("Arial", 13), text_color="#8b949e",
    )
    subtitle.pack(pady=(0, 14))

    stats_label = ctk.CTkLabel(
        kt, text="", font=("Arial", 13), text_color="#8b949e",
    )
    stats_label.pack(pady=(0, 10))

    # --- paragraph input ---
    para_box = ctk.CTkTextbox(kt, height=120, font=(FONT_FAMILY, 13),
                              wrap="word", fg_color=CARD_COLOR)
    para_box.pack(fill="x", padx=22, pady=4)
    _PARA_HINT = "Paste a paragraph or notes here, then click 'Learn Paragraph'."
    para_box.insert("1.0", _PARA_HINT)

    # --- action row ---
    btn_row = ctk.CTkFrame(kt, fg_color="transparent")
    btn_row.pack(fill="x", padx=22, pady=8)

    def _learn_paragraph():
        text = para_box.get("1.0", "end-1c").strip()
        if not text or text == _PARA_HINT:
            add_nova_bubble("Type or paste something to learn first.", save=False)
            return
        import nova_knowledge as _nk
        count = _nk.ingest_text("pasted paragraph", text)
        if count:
            add_nova_bubble(f"Learned {count} chunk(s) from your paragraph.",
                            save=False)
            para_box.delete("1.0", "end")
            para_box.insert("1.0", _PARA_HINT)
        else:
            add_nova_bubble("Hmm, that had no text I could save.", save=False)
        _refresh_sources()

    def _learn_file():
        path = filedialog.askopenfilename(
            title="Select a file to teach Nova",
            filetypes=[
                ("Documents & Images", "*.pdf *.txt *.md *.csv *.json *.py "
                 "*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tiff"),
                ("PDF", "*.pdf"),
                ("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tiff"),
                ("Text", "*.txt *.md *.csv *.json *.py"),
            ],
        )
        if not path:
            return
        import nova_knowledge as _nk
        add_nova_bubble(
            f"Learning from **{os.path.basename(path)}**...", save=False)
        kt.update()

        def _do():
            count, src, err = _nk.ingest_file(path)
            kt.after(0, lambda: _on_file_done(count, src, err))
        threading.Thread(target=_do, daemon=True).start()

    def _on_file_done(count, src, err):
        if count:
            add_nova_bubble(f"Learned {count} chunk(s) from **{src}**.", save=False)
        else:
            add_nova_bubble(f"Could not learn from file: {err or 'no text'}",
                            save=False)
        _refresh_sources()

    def _learn_folder():
        path = filedialog.askdirectory(title="Select a folder to teach Nova")
        if not path:
            return
        import nova_knowledge as _nk
        add_nova_bubble(f"Scanning folder **{path}**...", save=False)
        kt.update()

        def _do():
            total, files, errs = _nk.ingest_folder(path)
            kt.after(0, lambda: _on_folder_done(total, files, errs, path))
        threading.Thread(target=_do, daemon=True).start()

    def _on_folder_done(total, files, errs, path):
        if files:
            msg = f"Learned {total} chunk(s) from {files} file(s) in '{path}'."
        else:
            msg = f"No learnable files in '{path}'."
        if errs:
            msg += "\nSkipped: " + "; ".join(errs[:3])
        add_nova_bubble(msg, save=False)
        _refresh_sources()

    def _clear_all():
        if not messagebox.askyesno(
                "Clear Knowledge",
                "Delete ALL trained knowledge? This cannot be undone."):
            return
        import nova_knowledge as _nk
        _nk.clear_knowledge()
        add_nova_bubble("All trained knowledge cleared.", save=False)
        _refresh_sources()

    ctk.CTkButton(btn_row, text="Learn Paragraph", width=130,
                  fg_color=ACCENT, hover_color=ACCENT_HOVER,
                  command=_learn_paragraph).pack(side="left")
    ctk.CTkButton(btn_row, text="Learn from File", width=120,
                  command=_learn_file).pack(side="left", padx=10)
    ctk.CTkButton(btn_row, text="Learn from Folder", width=130,
                  command=_learn_folder).pack(side="left", padx=10)
    ctk.CTkButton(btn_row, text="Clear All Knowledge", width=150,
                  fg_color=DANGER, hover_color=DANGER_HOVER,
                  command=_clear_all).pack(side="right")

    # --- learned-sources list ---
    list_frame = ctk.CTkScrollableFrame(kt, fg_color="#0d1117", corner_radius=10)
    list_frame.pack(fill="both", expand=True, padx=22, pady=(6, 22))

    def _remove_source(name):
        import nova_knowledge as _nk
        _nk._KB["sources"].pop(name, None)
        _nk._KB["chunks"] = [c for c in _nk._KB["chunks"]
                             if c.get("source") != name]
        _nk._save()
        _refresh_sources()

    def _refresh_sources():
        for w in list_frame.winfo_children():
            w.destroy()
        import nova_knowledge as _nk
        stats = _nk.knowledge_stats()
        stats_label.configure(
            text=f"{stats['sources']} source(s)  |  {stats['chunks']} chunk(s)"
                 f"  |  ~{stats['chars']} chars"
        )
        sources = _nk.list_sources()
        if not sources:
            empty = ctk.CTkLabel(
                list_frame,
                text="No knowledge trained yet. Teach Nova above to get started.",
                text_color="#8b949e")
            empty.pack(pady=24)
            return
        for src, info in sources:
            row = ctk.CTkFrame(list_frame, fg_color="#21262d", corner_radius=8)
            row.pack(fill="x", padx=8, pady=6)
            lbl = ctk.CTkLabel(
                row, text=f"{src}\n{info['chunks']} chunks, "
                          f"{info.get('chars', 0)} chars",
                anchor="w", justify="left", wraplength=380,
            )
            lbl.pack(side="left", fill="x", expand=True, padx=12, pady=10)
            del_btn = ctk.CTkButton(row, text="Remove", width=72,
                                    fg_color=DANGER, hover_color=DANGER_HOVER,
                                    command=lambda s=src: _remove_source(s))
            del_btn.pack(side="right", padx=(4, 10), pady=8)

    _refresh_sources()


# ==========================================
# COMMAND GUIDE WINDOW (unchanged content from old left panel)
# ==========================================

def open_command_guide():
    guide_window = ctk.CTkToplevel(app)
    guide_window.title("Nova Commands")
    guide_window.geometry("420x560")
    guide_window.transient(app)
    guide_window.configure(fg_color=BG_COLOR)
    bring_window_to_front(guide_window)

    title = ctk.CTkLabel(guide_window, text="Quick Commands", font=("Arial", 22, "bold"))
    title.pack(pady=(20, 4))

    subtitle = ctk.CTkLabel(guide_window, text="Tap a command to run it instantly.", font=("Arial", 12), text_color=TEXT_MUTED)
    subtitle.pack(pady=(0, 10))

    scroll = ctk.CTkScrollableFrame(guide_window, fg_color="#0d1117", corner_radius=10)
    scroll.pack(fill="both", expand=True, padx=18, pady=(0, 18))

    for group_name, examples in command_groups:
        group_label = ctk.CTkLabel(scroll, text=group_name, font=("Arial", 13, "bold"), text_color=ACCENT, anchor="w")
        group_label.pack(fill="x", padx=8, pady=(12, 3))

        for label, example in examples:
            row = ctk.CTkFrame(scroll, fg_color="#21262d", corner_radius=6)
            row.pack(fill="x", padx=6, pady=3)

            row_label = ctk.CTkLabel(row, text=f"{label}: {example}", anchor="w", wraplength=250)
            row_label.pack(side="left", fill="x", expand=True, padx=8, pady=6)

            run_button = ctk.CTkButton(
                row, text="Run", width=48, height=24, font=("Arial", 11),
                fg_color=ACCENT, hover_color=ACCENT_HOVER,
                command=lambda text=example: (guide_window.destroy(), run_command_example(text))
            )
            run_button.pack(side="right", padx=(2, 6), pady=6)

# ==========================================
# SETTINGS WINDOW (unchanged logic, opened from the sidebar)
# ==========================================

def open_settings():
    global app_settings
    settings_window = ctk.CTkToplevel(app)
    settings_window.title("Nova Settings")
    settings_window.geometry("620x680")
    settings_window.transient(app)
    # allow resizing so users on small screens can expand/contract; use a scrollable body
    settings_window.resizable(True, True)
    settings_window.configure(fg_color=BG_COLOR)
    bring_window_to_front(settings_window)

    title = ctk.CTkLabel(settings_window, text="Nova Settings", font=("Arial", 28, "bold"), text_color="white")
    title.pack(pady=(22, 8))

    subtitle = ctk.CTkLabel(
        settings_window, text="Control account, voice, privacy, appearance, memory, prompts, and assistant behavior.",
        font=("Arial", 14), text_color="#8b949e"
    )
    subtitle.pack(pady=(0, 18))

    # Use a scrollable frame for the settings body so content doesn't get clipped on small windows
    settings_body = ctk.CTkScrollableFrame(settings_window, fg_color=CARD_COLOR, corner_radius=12)
    settings_body.pack(fill="both", expand=True, padx=24, pady=(0, 24))

    appearance_label = ctk.CTkLabel(settings_body, text="Appearance", font=("Arial", 18, "bold"), anchor="w")
    appearance_label.pack(fill="x", padx=18, pady=(18, 8))

    language_label = ctk.CTkLabel(settings_body, text="Language", anchor="w")
    language_label.pack(fill="x", padx=18, pady=(10, 0))

    language = ctk.CTkOptionMenu(settings_body, values=["English", "Hindi", "Hinglish"], command=save_language)
    language.set(app_settings.get("language", "English"))
    language.pack(fill="x", padx=18, pady=8)

    mode_label = ctk.CTkLabel(settings_body, text="Theme", anchor="w")
    mode_label.pack(fill="x", padx=18, pady=(10, 0))

    mode = ctk.CTkOptionMenu(settings_body, values=["Dark", "Light"], command=apply_theme)
    mode.set(app_settings.get("theme", "Dark"))
    mode.pack(fill="x", padx=18, pady=8)

    accent_label = ctk.CTkLabel(settings_body, text="Professional Theme Preset", anchor="w")
    accent_label.pack(fill="x", padx=18, pady=(10, 0))
    accent = ctk.CTkOptionMenu(
        settings_body,
        values=["Graphite Blue", "Midnight", "Minimal Light", "Ocean"],
        command=lambda value: (app_settings.__setitem__("theme_preset", value), save_settings(app_settings))
    )
    accent.set(app_settings.get("theme_preset", "Graphite Blue"))
    accent.pack(fill="x", padx=18, pady=8)

    ai_label = ctk.CTkLabel(settings_body, text="Assistant", font=("Arial", 18, "bold"), anchor="w")
    ai_label.pack(fill="x", padx=18, pady=(20, 8))

    ai_mode = ctk.CTkOptionMenu(
        settings_body,
        values=["General", "Study", "Coding", "Coach", "Vision", "Deep Thinking"],
        command=set_assistant_mode
    )
    ai_mode.set(dashboard_data.get("assistant_mode", "General"))
    ai_mode.pack(fill="x", padx=18, pady=8)

    privacy_switch = ctk.CTkSwitch(settings_body, text="Privacy mode blocks file / OS actions", command=toggle_privacy_mode)
    if _is_privacy_mode_on():
        privacy_switch.select()
    privacy_switch.pack(fill="x", padx=18, pady=8)

    voice_label = ctk.CTkLabel(settings_body, text="Voice", font=("Arial", 18, "bold"), anchor="w")
    voice_label.pack(fill="x", padx=18, pady=(20, 8))

    voice_switch = ctk.CTkSwitch(settings_body, text="Voice replies", command=lambda: toggle_voice(voice_switch))
    if app_settings.get("voice_enabled", True):
        voice_switch.select()
    else:
        voice_switch.deselect()
    voice_switch.pack(fill="x", padx=18, pady=8)

    tools_label = ctk.CTkLabel(settings_body, text="Tools", font=("Arial", 18, "bold"), anchor="w")
    tools_label.pack(fill="x", padx=18, pady=(20, 8))

    memory_button = ctk.CTkButton(settings_body, text="Open Memory Manager", height=38, fg_color="#1f6feb", command=open_memory_manager)
    memory_button.pack(fill="x", padx=18, pady=6)

    license_button = ctk.CTkButton(settings_body, text="Open License Activation", height=38, fg_color="#8957e5", command=open_license_window)
    license_button.pack(fill="x", padx=18, pady=6)

    commands_button = ctk.CTkButton(settings_body, text="Open Command Guide", height=38, fg_color=ACCENT, hover_color=ACCENT_HOVER, command=open_command_guide)
    commands_button.pack(fill="x", padx=18, pady=6)

    prompt_button = ctk.CTkButton(settings_body, text="Edit Prompt Library", height=38, fg_color=CARD_COLOR_SOFT, hover_color=ACCENT_SOFT, command=open_prompt_library)
    prompt_button.pack(fill="x", padx=18, pady=6)

    threads_button = ctk.CTkButton(settings_body, text="Manage Chat Threads", height=38, fg_color=CARD_COLOR_SOFT, hover_color=ACCENT_SOFT, command=open_threads_window)
    threads_button.pack(fill="x", padx=18, pady=6)

    onboarding_button = ctk.CTkButton(
        settings_body, text="Run Onboarding Again", height=38, fg_color=CARD_COLOR_SOFT,
        hover_color=ACCENT_SOFT,
        command=lambda: (dashboard_data.__setitem__("onboarding_complete", False), save_dashboard_data(), open_onboarding())
    )
    onboarding_button.pack(fill="x", padx=18, pady=6)

    # ----------------------------------
    # Allowed Folders section
    # ----------------------------------
    allowed_label = ctk.CTkLabel(settings_body, text="Allowed Folders", font=("Arial", 18, "bold"), anchor="w")
    allowed_label.pack(fill="x", padx=18, pady=(18, 8))

    allowed_frame = ctk.CTkFrame(settings_body, fg_color="#0d1117", corner_radius=8)
    allowed_frame.pack(fill="x", padx=18, pady=(0, 12))

    allowed_status_label = ctk.CTkLabel(allowed_frame, text="", font=("Arial", 11), text_color="#8b949e", anchor="w")
    allowed_status_label.pack(fill="x", padx=10, pady=(8, 6))

    list_container = ctk.CTkFrame(allowed_frame, fg_color="transparent")
    list_container.pack(fill="x", padx=8, pady=(0, 8))

    allowed_listbox = tk.Listbox(
        list_container,
        height=6,
        bg="#0d1117",
        fg="white",
        selectbackground=ACCENT,
        selectforeground="white",
        highlightthickness=0,
        bd=0,
        font=("Arial", 11),
    )
    allowed_listbox.pack(side="left", fill="x", expand=True)

    allowed_scrollbar = tk.Scrollbar(list_container, orient="vertical", command=allowed_listbox.yview)
    allowed_scrollbar.pack(side="right", fill="y")
    allowed_listbox.configure(yscrollcommand=allowed_scrollbar.set)

    button_row = ctk.CTkFrame(allowed_frame, fg_color="transparent")
    button_row.pack(fill="x", padx=8, pady=(0, 8))

    add_folder_btn = ctk.CTkButton(button_row, text="Add Folder", width=110, height=36, fg_color=ACCENT, hover_color=ACCENT_HOVER)
    add_folder_btn.pack(side="left")

    remove_folder_btn = ctk.CTkButton(button_row, text="Remove Selected", width=140, height=36, fg_color=DANGER, hover_color=DANGER_HOVER)
    remove_folder_btn.pack(side="right")

    def render_allowed_folders():
        allowed_listbox.delete(0, tk.END)
        folders = app_settings.get("allowed_folders", []) or []
        for path in folders:
            allowed_listbox.insert(tk.END, path)

        if not folders:
            allowed_status_label.configure(text="No allowed folders yet.")
        else:
            allowed_status_label.configure(text=f"{len(folders)} folder(s) allowed")

    def add_allowed_folder():
        try:
            settings_window.lift()
            settings_window.attributes("-topmost", True)
            settings_window.after(100, lambda: settings_window.attributes("-topmost", False))
            folder = filedialog.askdirectory(title="Select folder to allow")
        except Exception:
            folder = None
        if not folder:
            return
        folders = app_settings.get("allowed_folders", []) or []
        normalized_folder = os.path.normpath(folder)
        if any(os.path.normpath(path) == normalized_folder for path in folders):
            allowed_status_label.configure(text="That folder is already allowed.")
            return
        new_list = folders + [normalized_folder]
        update_setting("allowed_folders", new_list)
        app_settings["allowed_folders"] = new_list
        render_allowed_folders()
        allowed_status_label.configure(text=f"Added: {normalized_folder}")

    def remove_allowed_folder():
        selection = allowed_listbox.curselection()
        if not selection:
            allowed_status_label.configure(text="Select a folder to remove first.")
            return
        selected_path = allowed_listbox.get(selection[0])
        folders = app_settings.get("allowed_folders", []) or []
        new_list = [path for path in folders if os.path.normpath(path) != os.path.normpath(selected_path)]
        update_setting("allowed_folders", new_list)
        app_settings["allowed_folders"] = new_list
        render_allowed_folders()
        allowed_status_label.configure(text=f"Removed: {selected_path}")

    add_folder_btn.configure(command=add_allowed_folder)
    remove_folder_btn.configure(command=remove_allowed_folder)
    render_allowed_folders()

    # ----------------------------------
    # Explicit Save button — so the user always has a clear, final "save"
    # action and doesn't have to re-enter settings. Persists everything
    # (theme, language, voice, privacy, allowed folders) in one click.
    # ----------------------------------
    save_row = ctk.CTkFrame(settings_body, fg_color="transparent")
    save_row.pack(fill="x", padx=18, pady=(18, 24))

    settings_saved_label = ctk.CTkLabel(save_row, text="", font=("Arial", 11), text_color=SUCCESS)

    def save_all_settings():
        global app_settings
        save_settings(app_settings)
        settings_saved_label.configure(text="\u2713 All settings saved")

    ctk.CTkButton(
        save_row, text="\U0001F4BE Save Settings", height=40,
        fg_color=SUCCESS, hover_color="#3aa856", command=save_all_settings,
    ).pack(side="top", fill="x", pady=(0, 6))
    settings_saved_label.pack(side="top")

# ==========================================
# ROOT LAYOUT (sidebar | center | right panel)
# ==========================================

app.grid_columnconfigure(0, weight=0)
app.grid_columnconfigure(1, weight=1)
app.grid_columnconfigure(2, weight=0)
app.grid_rowconfigure(0, weight=1)

# Sidebar is now a SCROLLABLE frame - if the nav list + bottom cluster +
# orbit graphic + premium/quote cards add up to more than the window's
# height, it scrolls instead of getting clipped by the window edge.
sidebar = ctk.CTkScrollableFrame(app, width=246, fg_color=SIDEBAR_COLOR, corner_radius=0)
sidebar.grid(row=0, column=0, sticky="ns")

center_container = ctk.CTkFrame(app, fg_color=BG_COLOR, corner_radius=0)
center_container.grid(row=0, column=1, sticky="nsew")
center_container.grid_rowconfigure(1, weight=1)
center_container.grid_columnconfigure(0, weight=1)

right_panel = ctk.CTkScrollableFrame(app, width=304, fg_color=BG_COLOR, corner_radius=0)
right_panel.grid(row=0, column=2, sticky="ns")

# ==========================================
# SIDEBAR CONTENT
# ==========================================

logo_label = ctk.CTkLabel(sidebar, text="NOVA", font=(FONT_FAMILY, 26, "bold"), text_color=TEXT_MAIN)
logo_label.pack(pady=(22, 0))

logo_sub = ctk.CTkLabel(sidebar, text="PERSONAL OPERATING DESK", font=(FONT_FAMILY, 10), text_color=ACCENT)
logo_sub.pack(pady=(0, 14))

status_label = ctk.CTkLabel(
    sidebar, text="Voice On  |  No License", font=(FONT_FAMILY, 11, "bold"),
    text_color=SUCCESS, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS, padx=10, pady=6
)
status_label.pack(pady=(0, 14))

nav_scroll = ctk.CTkFrame(sidebar, fg_color="transparent")
nav_scroll.pack(fill="x", padx=14)


def set_active_nav(key):
    global current_page_key
    current_page_key = key
    for k, btn in nav_buttons.items():
        if k == key:
            btn.configure(fg_color=ACCENT_SOFT, text_color=TEXT_MAIN)
        else:
            btn.configure(fg_color="transparent", text_color=TEXT_MUTED)


def show_page(key):
    for k, frame in pages.items():
        if k == key:
            frame.tkraise()
    if key == "activity" and "render_activity" in globals():
        render_activity()
    if key == "routine" and "render_routine" in globals():
        render_routine()
    set_active_nav(key)


def make_nav_button(parent, icon, label, key, command):
    btn = ctk.CTkButton(
        parent, text=f"  {icon}   {label}", anchor="w", height=42,
        fg_color="transparent", hover_color=CARD_COLOR_SOFT, text_color=TEXT_MUTED,
        font=(FONT_FAMILY, 14), corner_radius=PANEL_RADIUS, command=command
    )
    btn.pack(fill="x", pady=3)
    if key:
        nav_buttons[key] = btn
    return btn


nav_items = [
    ("\U0001F3E0", "Home", "home", lambda: show_page("home")),
    ("\U0001F4AC", "Chat", "home", lambda: show_page("home")),
    ("\U0001F9E0", "Memory", None, open_memory_manager),
    ("\U0001FAE0", "Train Nova", None, open_knowledge_trainer),
    ("\U0001F3AF", "Goals", "goals", lambda: show_page("goals")),
    ("\u2705", "Tasks", "tasks", lambda: show_page("tasks")),
    ("\U0001F393", "Study Hub", "study", lambda: show_page("study")),
    ("\U0001F4F0", "Briefing", "briefing", lambda: show_page("briefing")),
    ("\U0001F4C6", "Routine", "routine", lambda: show_page("routine")),
    ("\U0001F4DD", "Notes", "notes", lambda: show_page("notes")),
    ("\U0001F9F0", "AI Tools", "tools", lambda: show_page("tools")),
    ("\U0001F4DA", "Prompts", "prompts", lambda: show_page("prompts")),
    ("\U0001F4C8", "Activity", "activity", lambda: show_page("activity")),
    ("\u2712", "Journal", "journal", lambda: show_page("journal")),
    ("\u2699", "Settings", None, open_settings),
]

for icon, label, key, cmd in nav_items:
    make_nav_button(nav_scroll, icon, label, key, cmd)

add_privacy_chip(sidebar)

# ---- sidebar bottom cluster: mic / voice toggle / command grid ----

sidebar_bottom = ctk.CTkFrame(sidebar, fg_color="transparent")
sidebar_bottom.pack(fill="x", padx=14, pady=(10, 6))

mic_button = ctk.CTkButton(
    sidebar_bottom, text="\U0001F3A4", width=42, height=42, font=("Arial", 16),
    fg_color=CARD_COLOR, hover_color=ACCENT_SOFT, command=lambda: open_listening_window()
)
mic_button.pack(side="left", padx=4)
add_tooltip(mic_button, "Start voice listening")

speak_button = ctk.CTkButton(
    sidebar_bottom, text="\u3030", width=42, height=42, font=("Arial", 16),
    fg_color=ACCENT_SOFT, hover_color=ACCENT, text_color=ACCENT, command=toggle_voice
)
speak_button.pack(side="left", padx=4)
add_tooltip(speak_button, "Turn Nova's spoken replies on/off")

grid_button = ctk.CTkButton(
    sidebar_bottom, text="\u25A6", width=42, height=42, font=("Arial", 16),
    fg_color=CARD_COLOR, hover_color=ACCENT_SOFT, command=open_command_guide
)
grid_button.pack(side="left", padx=4)
add_tooltip(grid_button, "Open the quick command list")

sidebar_bottom_2 = ctk.CTkFrame(sidebar, fg_color="transparent")
sidebar_bottom_2.pack(fill="x", padx=14, pady=(0, 6))

screen_watch_button = ctk.CTkButton(
    sidebar_bottom_2, text="\U0001F441", width=42, height=42, font=("Arial", 16),
    fg_color=CARD_COLOR, hover_color=ACCENT_SOFT, command=lambda: toggle_screen_watch()
)
screen_watch_button.pack(side="left", padx=4)
add_tooltip(screen_watch_button, "Screen Watch: continuous listening, no wake word needed (mic button stays normal)")

camera_button = ctk.CTkButton(
    sidebar_bottom_2, text="\U0001F4F7", width=42, height=42, font=("Arial", 16),
    fg_color=CARD_COLOR, hover_color=ACCENT_SOFT, command=lambda: toggle_camera()
)
camera_button.pack(side="left", padx=4)
add_tooltip(camera_button, "Open camera preview (capture a frame and ask Nova about it)")

# ---- orbit graphic (decorative, matches mockup) ----

orbit_label = ctk.CTkLabel(sidebar, image=nova_orbit_img, text="")
orbit_label.pack(pady=(4, 6))

# ---- premium card (decorative) ----

premium_card = ctk.CTkFrame(sidebar, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
premium_card.pack(fill="x", padx=14, pady=(6, 6))

premium_title = ctk.CTkLabel(premium_card, text="\U0001F451 NOVA Premium", font=(FONT_FAMILY, 13, "bold"), anchor="w")
premium_title.pack(fill="x", padx=12, pady=(12, 2))

premium_body = ctk.CTkLabel(
    premium_card, text="Unlock all features and\nsupercharge your productivity.",
    font=(FONT_FAMILY, 11), text_color=TEXT_MUTED, justify="left", anchor="w"
)
premium_body.pack(fill="x", padx=12, pady=(0, 10))

premium_button = ctk.CTkButton(
    premium_card, text="Upgrade Now  \u203A", height=32, fg_color=ACCENT, hover_color=ACCENT_HOVER,
    command=lambda: open_license_window()
)
premium_button.pack(fill="x", padx=12, pady=(0, 12))
add_tooltip(premium_button, "Opens the license activation window")

# ---- quote card ----

quote_card = ctk.CTkFrame(sidebar, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
quote_card.pack(fill="x", padx=14, pady=(0, 16))

quote_text = ctk.CTkLabel(
    quote_card, text=f"\u201c{dashboard_data['quote']}\u201d", font=("Arial", 12, "italic"),
    text_color=TEXT_MAIN, wraplength=170, justify="left", anchor="w"
)
quote_text.pack(fill="x", padx=12, pady=(12, 4))

quote_author = ctk.CTkLabel(quote_card, text="\u2014 Dhruv", font=("Arial", 11), text_color=ACCENT, anchor="w")
quote_author.pack(fill="x", padx=12, pady=(0, 12))

# ==========================================
# TOP BAR
# ==========================================

top_bar = ctk.CTkFrame(center_container, height=64, fg_color=TOPBAR_COLOR, corner_radius=PANEL_RADIUS)
top_bar.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))

search_entry = ctk.CTkEntry(
    top_bar, placeholder_text="\U0001F50D  Search commands here, or Ctrl+K for palette",
    width=380, height=36, font=(FONT_FAMILY, 13), fg_color=BG_COLOR,
    border_color=BORDER_COLOR
)
search_entry.pack(side="left", padx=16, pady=14)

mode_menu = ctk.CTkOptionMenu(
    top_bar,
    values=["General", "Study", "Coding", "Coach", "Vision", "Deep Thinking"],
    width=145, height=32, fg_color=CARD_COLOR, button_color=ACCENT_SOFT,
    button_hover_color=ACCENT, command=set_assistant_mode
)
mode_menu.set(dashboard_data.get("assistant_mode", "General"))
mode_menu.pack(side="left", padx=(0, 10), pady=14)

palette_button = ctk.CTkButton(
    top_bar, text="Palette", width=82, height=32,
    fg_color=CARD_COLOR, hover_color=CARD_COLOR_SOFT,
    font=(FONT_FAMILY, 11), command=lambda: open_command_palette()
)
palette_button.pack(side="left", padx=(0, 8), pady=14)
add_tooltip(palette_button, "Open command palette")


def run_search(event=None):
    global search_hint_label
    query = search_entry.get().strip().lower()
    if not query:
        return
    match = None
    for group_name, examples in command_groups:
        for label, example in examples:
            if query in label.lower() or query in example.lower():
                match = (label, example)
                break
        if match:
            break
    if search_hint_label is not None:
        search_hint_label.destroy()
        search_hint_label = None
    if match:
        search_hint_label = ctk.CTkLabel(
            top_bar, text=f"\u21B3 {match[0]}: tap to run", font=("Arial", 11), text_color=ACCENT,
            cursor="hand2"
        )
        search_hint_label.bind("<Button-1>", lambda e, ex=match[1]: run_command_example(ex))
    else:
        search_hint_label = ctk.CTkLabel(top_bar, text="No matching command", font=("Arial", 11), text_color=TEXT_MUTED)
    search_hint_label.pack(side="left", padx=(0, 10))
    app.after(4000, lambda: search_hint_label.destroy() if search_hint_label else None)


search_entry.bind("<Return>", run_search)
app.bind("<Control-k>", lambda e: open_command_palette(e))
app.bind("<Control-Shift-P>", lambda e: open_command_palette(e))


def open_history():
    show_page("home")
    result = execute_command("show history")
    if isinstance(result, str) and result.strip():
        add_nova_bubble(result)


def clear_chat_history():
    get_current_thread()["messages"] = []
    save_dashboard_data()
    show_page("home")
    rebuild_home_chat()
    log_activity("Thread cleared", get_current_thread().get("title", "Current chat"))


def open_notification_center():
    win = ctk.CTkToplevel(app)
    win.title("Notification Center")
    win.geometry("460x560")
    win.configure(fg_color=BG_COLOR)
    win.transient(app)
    bring_window_to_front(win)
    make_section_title(win, "Notifications", "Reminders, failed actions, and Nova status updates.")

    body = ctk.CTkScrollableFrame(win, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
    body.pack(fill="both", expand=True, padx=18, pady=(0, 18))

    items = dashboard_data.get("notifications", [])
    if not items:
        ctk.CTkLabel(body, text="No notifications yet.", text_color=TEXT_MUTED).pack(pady=20)
    for item in reversed(items[-40:]):
        row = ctk.CTkFrame(body, fg_color=CARD_COLOR_SOFT, corner_radius=PANEL_RADIUS)
        row.pack(fill="x", padx=8, pady=6)
        ctk.CTkLabel(row, text=item.get("title", "Notification"), font=(FONT_FAMILY, 13, "bold"), anchor="w").pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(row, text=item.get("detail", ""), font=(FONT_FAMILY, 11), text_color=TEXT_MUTED, wraplength=390, justify="left", anchor="w").pack(fill="x", padx=10)
        ctk.CTkLabel(row, text=item.get("time", ""), font=(FONT_FAMILY, 10), text_color=TEXT_MUTED, anchor="w").pack(fill="x", padx=10, pady=(0, 8))

    for item in items:
        item["read"] = True
    save_dashboard_data()


def open_threads_window():
    win = ctk.CTkToplevel(app)
    win.title("Chat Threads")
    win.geometry("460x560")
    win.configure(fg_color=BG_COLOR)
    win.transient(app)
    bring_window_to_front(win)
    make_section_title(win, "Chat Threads", "Create and switch between separate conversations.")

    name_entry = ctk.CTkEntry(win, placeholder_text="New thread name...", height=36)
    name_entry.pack(fill="x", padx=18, pady=(0, 8))

    list_frame = ctk.CTkScrollableFrame(win, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
    list_frame.pack(fill="both", expand=True, padx=18, pady=(0, 18))

    def switch_thread(thread_id):
        dashboard_data["current_thread_id"] = thread_id
        save_dashboard_data()
        win.destroy()
        show_page("home")
        rebuild_home_chat()

    def delete_thread(thread_id):
        threads = dashboard_data.get("chat_threads", {})
        if thread_id not in threads:
            return
        # Keep at least the main chat; if deleting the active one, fall back to main.
        if thread_id == "main":
            add_nova_bubble("Main Chat delete nahi ho sakta — wo default conversation hai.")
            return
        if not messagebox.askyesno(
            "Delete Chat", f"'{threads[thread_id].get('title', 'Chat')}' ko hamesha ke liye delete karein?"
        ):
            return
        del threads[thread_id]
        if dashboard_data.get("current_thread_id") == thread_id:
            dashboard_data["current_thread_id"] = "main"
        save_dashboard_data()
        log_activity("Deleted chat thread", threads.get("main", {}).get("title", "Main Chat"))
        # Refresh the thread list inside this window.
        for widget in list_frame.winfo_children():
            widget.destroy()
        _render_thread_list()

    def create_thread():
        make_thread(name_entry.get().strip() or None)
        win.destroy()
        show_page("home")
        rebuild_home_chat()

    def _render_thread_list():
        for thread_id, thread in dashboard_data.get("chat_threads", {}).items():
            row = ctk.CTkFrame(list_frame, fg_color=CARD_COLOR_SOFT, corner_radius=PANEL_RADIUS)
            row.pack(fill="x", padx=8, pady=5)
            active = "  Active" if thread_id == dashboard_data.get("current_thread_id") else ""
            ctk.CTkLabel(row, text=f"{thread.get('title', 'Chat')}{active}", font=(FONT_FAMILY, 13, "bold"), anchor="w").pack(
                side="left", fill="x", expand=True, padx=10, pady=10
            )
            ctk.CTkButton(row, text="Open", width=60, height=28,
                          command=lambda tid=thread_id: switch_thread(tid)).pack(side="right", padx=4, pady=8)
            # Delete icon (🗑 = U+1F5D1) so any thread can be removed from the list.
            ctk.CTkButton(
                row, text="\U0001F5D1", width=54, height=28, fg_color=DANGER, hover_color=DANGER_HOVER,
                command=lambda tid=thread_id: delete_thread(tid),
            ).pack(side="right", padx=(0, 6), pady=8)

    ctk.CTkButton(win, text="Create Thread", fg_color=ACCENT, hover_color=ACCENT_HOVER, command=create_thread).pack(fill="x", padx=18, pady=(0, 10))
    _render_thread_list()


def open_prompt_library():
    win = ctk.CTkToplevel(app)
    win.title("Prompt Library")
    win.geometry("560x620")
    win.configure(fg_color=BG_COLOR)
    win.transient(app)
    bring_window_to_front(win)
    make_section_title(win, "Prompt Library", "Edit which prompt commands Nova should keep available.")

    form = ctk.CTkFrame(win, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
    form.pack(fill="x", padx=18, pady=(0, 10))
    title_entry = ctk.CTkEntry(form, placeholder_text="Prompt title", height=34)
    title_entry.pack(fill="x", padx=12, pady=(12, 6))
    prompt_entry = ctk.CTkEntry(form, placeholder_text="Prompt text / command", height=34)
    prompt_entry.pack(fill="x", padx=12, pady=(0, 8))

    list_frame = ctk.CTkScrollableFrame(win, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
    list_frame.pack(fill="both", expand=True, padx=18, pady=(0, 18))

    def render():
        for widget in list_frame.winfo_children():
            widget.destroy()
        for idx, item in enumerate(dashboard_data.setdefault("prompt_library", [])):
            row = ctk.CTkFrame(list_frame, fg_color=CARD_COLOR_SOFT, corner_radius=PANEL_RADIUS)
            row.pack(fill="x", padx=8, pady=5)
            enabled = tk.BooleanVar(value=item.get("enabled", True))

            def toggle(i=idx, var=enabled):
                dashboard_data["prompt_library"][i]["enabled"] = var.get()
                save_dashboard_data()

            ctk.CTkCheckBox(row, text=item.get("title", "Prompt"), variable=enabled, command=toggle, font=(FONT_FAMILY, 12, "bold")).pack(fill="x", padx=10, pady=(8, 0))
            ctk.CTkLabel(row, text=item.get("prompt", ""), text_color=TEXT_MUTED, wraplength=440, justify="left", anchor="w").pack(fill="x", padx=10)
            btns = ctk.CTkFrame(row, fg_color="transparent")
            btns.pack(fill="x", padx=10, pady=(4, 8))
            ctk.CTkButton(btns, text="Use", width=60, height=26, command=lambda p=item.get("prompt", ""): (win.destroy(), send_prefilled(p))).pack(side="left")
            ctk.CTkButton(btns, text="Edit", width=60, height=26, fg_color=CARD_COLOR, command=lambda it=item: (title_entry.delete(0, "end"), title_entry.insert(0, it.get("title", "")), prompt_entry.delete(0, "end"), prompt_entry.insert(0, it.get("prompt", "")))).pack(side="left", padx=6)
            ctk.CTkButton(btns, text="Delete", width=70, height=26, fg_color=DANGER, hover_color=DANGER_HOVER, command=lambda i=idx: (dashboard_data["prompt_library"].pop(i), save_dashboard_data(), render())).pack(side="right")

    def save_prompt():
        title = title_entry.get().strip()
        prompt = prompt_entry.get().strip()
        if not title or not prompt:
            return
        library = dashboard_data.setdefault("prompt_library", [])
        for item in library:
            if item.get("title", "").lower() == title.lower():
                item["prompt"] = prompt
                item["enabled"] = True
                break
        else:
            library.append({"title": title, "prompt": prompt, "enabled": True})
        save_dashboard_data()
        title_entry.delete(0, "end")
        prompt_entry.delete(0, "end")
        render()

    ctk.CTkButton(form, text="Save Prompt", fg_color=ACCENT, hover_color=ACCENT_HOVER, command=save_prompt).pack(fill="x", padx=12, pady=(0, 12))
    render()


def open_profile_menu(event=None):
    win = ctk.CTkToplevel(app)
    win.title("Profile")
    win.geometry("340x430")
    win.configure(fg_color=BG_COLOR)
    win.transient(app)
    bring_window_to_front(win)
    make_section_title(win, dashboard_data.get("profile", {}).get("name", "Dhruv"), "Profile, privacy, export, and quick settings.")

    actions = [
        ("Toggle Focus / Available", toggle_profile_status),
        ("Chat Threads", open_threads_window),
        ("Chat History", open_history),
        ("Prompt Library", open_prompt_library),
        ("Notification Center", open_notification_center),
        ("Settings", open_settings),
    ("Memory Manager", open_memory_manager),
        ("License", open_license_window),
    ]
    for label, cmd in actions:
        ctk.CTkButton(win, text=label, height=36, fg_color=CARD_COLOR, hover_color=CARD_COLOR_SOFT, command=cmd).pack(fill="x", padx=18, pady=5)


def open_command_palette(event=None):
    win = ctk.CTkToplevel(app)
    win.title("Command Palette")
    win.geometry("620x560")
    win.configure(fg_color=BG_COLOR)
    win.transient(app)
    bring_window_to_front(win)
    search = ctk.CTkEntry(win, placeholder_text="Search commands, pages, prompts...", height=42, font=(FONT_FAMILY, 14))
    search.pack(fill="x", padx=18, pady=18)
    results = ctk.CTkScrollableFrame(win, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
    results.pack(fill="both", expand=True, padx=18, pady=(0, 18))

    entries = [
        ("Home", "Open Home", lambda: show_page("home")),
        ("Daily Briefing", "Open Daily Briefing", lambda: show_page("briefing")),
        ("Calendar", "Open Routine Timeline", lambda: show_page("routine")),
        ("AI Tools", "Open AI Tools", lambda: show_page("tools")),
        ("Settings", "Open Settings", open_settings),
        ("Threads", "Open Chat Threads", open_threads_window),
        ("Prompts", "Open Prompt Library", open_prompt_library),
    ]
    for group_name, examples in command_groups:
        for label, example in examples:
            entries.append((label, example, lambda ex=example: run_command_example(ex)))
    for item in dashboard_data.get("prompt_library", []):
        if item.get("enabled", True):
            entries.append((item.get("title", "Prompt"), item.get("prompt", ""), lambda p=item.get("prompt", ""): send_prefilled(p)))

    def render(_event=None):
        query = search.get().strip().lower()
        for widget in results.winfo_children():
            widget.destroy()
        for title, detail, cmd in entries:
            if query and query not in title.lower() and query not in detail.lower():
                continue
            row = ctk.CTkFrame(results, fg_color=CARD_COLOR_SOFT, corner_radius=PANEL_RADIUS)
            row.pack(fill="x", padx=8, pady=4)
            ctk.CTkLabel(row, text=title, font=(FONT_FAMILY, 13, "bold"), anchor="w").pack(side="left", fill="x", expand=True, padx=10, pady=8)
            ctk.CTkButton(row, text="Run", width=58, height=28, command=lambda c=cmd: (win.destroy(), c())).pack(side="right", padx=8, pady=7)

    search.bind("<KeyRelease>", render)
    render()
    search.focus()


def open_onboarding():
    if dashboard_data.get("onboarding_complete"):
        return
    win = ctk.CTkToplevel(app)
    win.title("Welcome to Nova")
    win.geometry("460x520")
    win.configure(fg_color=BG_COLOR)
    win.transient(app)
    bring_window_to_front(win)
    make_section_title(win, "Set Up Nova", "A quick professional setup for name, mode, language, and focus goal.")
    name_entry = ctk.CTkEntry(win, placeholder_text="Your name", height=36)
    name_entry.insert(0, dashboard_data.get("profile", {}).get("name", "Dhruv"))
    name_entry.pack(fill="x", padx=22, pady=8)
    mode_select = ctk.CTkOptionMenu(win, values=["General", "Study", "Coding", "Coach", "Vision", "Deep Thinking"])
    mode_select.set(dashboard_data.get("assistant_mode", "General"))
    mode_select.pack(fill="x", padx=22, pady=8)
    focus_entry = ctk.CTkEntry(win, placeholder_text="Daily focus goal minutes", height=36)
    focus_entry.insert(0, str(dashboard_data.get("focus_goal_minutes", 360)))
    focus_entry.pack(fill="x", padx=22, pady=8)

    def finish():
        dashboard_data.setdefault("profile", {})["name"] = name_entry.get().strip() or "Dhruv"
        dashboard_data["assistant_mode"] = mode_select.get()
        try:
            dashboard_data["focus_goal_minutes"] = max(1, int(focus_entry.get().strip()))
        except ValueError:
            pass
        dashboard_data["onboarding_complete"] = True
        save_dashboard_data()
        set_assistant_mode(dashboard_data["assistant_mode"])
        win.destroy()

    ctk.CTkButton(win, text="Finish Setup", fg_color=ACCENT, hover_color=ACCENT_HOVER, command=finish).pack(fill="x", padx=22, pady=18)


bell_button = ctk.CTkButton(
    top_bar, text="\U0001F514", width=36, height=36, fg_color="transparent", hover_color=CARD_COLOR,
    font=("Arial", 15), command=open_notification_center
)
bell_button.pack(side="right", padx=(0, 14), pady=14)
add_tooltip(bell_button, "Open notification center")

new_chat_button = ctk.CTkButton(
    top_bar, text="\U0001F5C2", width=36, height=36, fg_color="transparent", hover_color=CARD_COLOR,
    font=("Arial", 15), command=open_threads_window
)
new_chat_button.pack(side="right", padx=(0, 4), pady=14)
add_tooltip(new_chat_button, "Open chat threads")

clear_thread_button = ctk.CTkButton(
    top_bar, text="\U0001F5D1", width=36, height=36, fg_color="transparent", hover_color=CARD_COLOR,
    font=("Arial", 15), command=clear_chat_history
)
clear_thread_button.pack(side="right", padx=(0, 4), pady=14)
add_tooltip(clear_thread_button, "Clear current chat thread")

notif_dot = tk.Canvas(top_bar, width=9, height=9, bg=TOPBAR_COLOR, highlightthickness=0)
notif_dot.create_oval(0, 0, 9, 9, fill=ACCENT, outline="")
notif_dot.place(in_=bell_button, relx=0.78, rely=0.12, anchor="center")

profile_container = ctk.CTkFrame(top_bar, fg_color="transparent")
profile_container.pack(side="right", padx=(0, 8), pady=10)

profile_avatar_label = ctk.CTkLabel(profile_container, image=profile_avatar_img_top, text="")
profile_avatar_label.pack(side="left", padx=(0, 8))

profile_status_dot = tk.Canvas(profile_container, width=11, height=11, bg=TOPBAR_COLOR, highlightthickness=0)
profile_status_dot.create_oval(1, 1, 10, 10, fill=SUCCESS, outline=TOPBAR_COLOR, width=2)
profile_status_dot.place(in_=profile_avatar_label, relx=0.86, rely=0.86, anchor="center")

profile_text_col = ctk.CTkFrame(profile_container, fg_color="transparent")
profile_text_col.pack(side="left")

profile_name = ctk.CTkLabel(profile_text_col, text=dashboard_data.get("profile", {}).get("name", "Dhruv"), font=("Arial", 13, "bold"), anchor="e")
profile_name.pack(anchor="e")

assistant_status_label = ctk.CTkLabel(profile_text_col, text=f"{dashboard_data.get('assistant_mode', 'General')} Mode", font=("Arial", 10), text_color=TEXT_MUTED, anchor="e")
assistant_status_label.pack(anchor="e")

profile_status_label = ctk.CTkLabel(profile_text_col, text=dashboard_data["status"], font=("Arial", 10), text_color=TEXT_MUTED, anchor="e")
profile_status_label.pack(anchor="e")

chevron_label = ctk.CTkLabel(profile_container, text="\u2304", font=("Arial", 13), text_color=TEXT_MUTED)
chevron_label.pack(side="left", padx=(6, 0))


def toggle_profile_status(event=None):
    dashboard_data["status"] = "Available" if dashboard_data["status"] == "Focus Mode" else "Focus Mode"
    save_dashboard_data()
    profile_status_label.configure(text=dashboard_data["status"])


for w in (profile_container, profile_avatar_label, profile_name, profile_status_label, chevron_label):
    w.bind("<Button-1>", open_profile_menu)
add_tooltip(chevron_label, "Open profile menu")

license_top_button = ctk.CTkButton(
    top_bar, text="License", width=80, height=30, fg_color=ACCENT_SOFT, hover_color=ACCENT,
    font=(FONT_FAMILY, 11), command=open_license_window
)
license_top_button.pack(side="right", padx=(0, 10), pady=14)

# ==========================================
# PAGE CONTAINER (swappable pages)
# ==========================================

page_container = ctk.CTkFrame(center_container, fg_color="transparent")
page_container.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
page_container.grid_rowconfigure(0, weight=1)
page_container.grid_columnconfigure(0, weight=1)

pages = {}


def register_page(key):
    frame = ctk.CTkFrame(page_container, fg_color="transparent")
    frame.grid(row=0, column=0, sticky="nsew")
    pages[key] = frame
    return frame

# ---------------- HOME PAGE ----------------
# FIX: hero + quick actions + chat bubbles now live in ONE scrollable
# frame (home_scroll), exactly like the mockup - so the chat is never
# squeezed into a sliver by a tall hero section. Only the message input
# bar is pinned outside of it, at the bottom.

home_page = register_page("home")
home_page.grid_rowconfigure(0, weight=1)
home_page.grid_columnconfigure(0, weight=1)

home_scroll = ctk.CTkScrollableFrame(home_page, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
home_scroll.grid(row=0, column=0, sticky="nsew", pady=(4, 8))

# chat bubbles are appended straight into home_scroll - see add_nova_bubble / add_user_bubble below
chat_scroll = home_scroll

hero_frame = ctk.CTkFrame(home_scroll, fg_color="transparent")
hero_frame.pack(fill="x", pady=(8, 10), padx=8)

hero_logo_label = ctk.CTkLabel(hero_frame, image=nova_hero_img, text="")
hero_logo_label.pack(pady=(2, 6))

greetings = [
    "Ready for another session Dhruv? \U0001F680",
    "Systems online \u26A1",
    "Good to see you again \U0001F44B",
    "Nova AI initialized successfully \U0001F9E0",
    "Let's build something amazing today \u2728",
    "Your AI assistant is ready \U0001F916",
]

hero_title = ctk.CTkLabel(hero_frame, text="Hey Dhruv,", font=(FONT_FAMILY, 24, "bold"))
hero_title.pack()

hero_subtitle = ctk.CTkLabel(hero_frame, text="Your command center is ready.", font=(FONT_FAMILY, 23, "bold"), text_color=ACCENT)
hero_subtitle.pack()

hero_line = ctk.CTkLabel(
    hero_frame, text="Chat, voice, memory, study planning, focus, vision, nutrition, and system tools in one place.",
    font=(FONT_FAMILY, 13), text_color=TEXT_MUTED, justify="center", wraplength=680
)
hero_line.pack(pady=(4, 14))

home_metrics_frame = ctk.CTkFrame(hero_frame, fg_color="transparent")
home_metrics_frame.pack(fill="x", padx=18, pady=(0, 10))
for c in range(4):
    home_metrics_frame.grid_columnconfigure(c, weight=1)

facts_count = len(get_saved_facts())
today_focus = dashboard_data.get("focus_minutes_today", 0)
focus_goal = dashboard_data.get("focus_goal_minutes", 1)
make_metric_card(
    home_metrics_frame, "Goals", completion_text(dashboard_data.get("goals", [])),
    "today completed"
).grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
make_metric_card(
    home_metrics_frame, "Tasks", completion_text(dashboard_data.get("tasks", [])),
    "active checklist"
).grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
make_metric_card(
    home_metrics_frame, "Focus", f"{today_focus}/{focus_goal}",
    "minutes logged", accent_color=SUCCESS
).grid(row=0, column=2, padx=5, pady=5, sticky="nsew")
make_metric_card(
    home_metrics_frame, "Memory", str(facts_count),
    "saved facts"
).grid(row=0, column=3, padx=5, pady=5, sticky="nsew")

quick_actions_frame = ctk.CTkFrame(hero_frame, fg_color="transparent")
quick_actions_frame.pack(pady=(0, 6))

quick_actions = [
    ("\U0001F4D6 Study with me", "Study with me"),
    ("\U0001F4C5 Plan my day", "Plan my day"),
    ("\u2753 Solve doubts", "Solve my doubts"),
    ("\u270F\uFE0F Write something", "Write something about "),
    ("\u2661 Give me advice", "Give me advice on "),
    ("\u2605 Motivate me", "Motivate me"),
]

for i, (label, prompt) in enumerate(quick_actions):
    b = ctk.CTkButton(
        quick_actions_frame, text=label, height=36, fg_color=CARD_COLOR_SOFT, hover_color=ACCENT_SOFT,
        text_color=TEXT_MAIN, font=(FONT_FAMILY, 12), corner_radius=PANEL_RADIUS,
        command=lambda p=prompt: send_prefilled(p)
    )
    b.grid(row=i // 3, column=i % 3, padx=5, pady=5, sticky="ew")

for c in range(3):
    quick_actions_frame.grid_columnconfigure(c, weight=1)


def scroll_chat_to_bottom():
    chat_scroll.update_idletasks()
    try:
        chat_scroll._parent_canvas.yview_moveto(1.0)
    except Exception:
        pass


def _bubble_current_text(bubble, fallback=""):
    """Return the LIVE text currently shown in a chat bubble.

    Nova bubbles are created once (often with a "Thinking..." placeholder),
    then typewriter_into_bubble() streams the REAL response into the SAME
    widget. A closure that captured early text (like "Thinking...") goes
    stale, so Copy/Save/Speak must read the widget's current text instead.
    """
    try:
        # Colour-emoji bubble (tk.Text based) — store the original string.
        if hasattr(bubble, "get_text"):
            t = bubble.get_text()
            if t:
                return t
        # Plain CTkLabel fallback.
        t = getattr(bubble, "cget", lambda _k: "" )("text") or ""
        return t or fallback
    except Exception:
        return fallback


def add_nova_bubble(text, time_str=None, save=True):
    time_str = time_str or time.strftime("%I:%M %p")
    row = ctk.CTkFrame(chat_scroll, fg_color="transparent")
    row.pack(fill="x", padx=8, pady=6)

    inner = ctk.CTkFrame(row, fg_color="transparent")
    inner.pack(side="left", anchor="w")

    avatar = ctk.CTkLabel(inner, image=nova_avatar_img, text="")
    avatar.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 10), pady=(2, 0))

    name = ctk.CTkLabel(inner, text=f"Nova   {time_str}", font=("Arial", 11, "bold"), text_color=TEXT_MUTED, anchor="w")
    name.grid(row=0, column=1, sticky="w")

    if EMOJI_RENDER_OK:
        bubble = emoji_render.EmojiBubble(
            inner, bg_color=CARD_COLOR_SOFT, text_color=TEXT_MAIN,
            corner_radius=PANEL_RADIUS, wraplength=520, font_family=FONT_FAMILY,
        )
        bubble.set_text(text)
    else:
        bubble = ctk.CTkLabel(
            inner, text=text, font=(CHAT_FONT_FAMILY, 13), text_color=TEXT_MAIN, fg_color=CARD_COLOR_SOFT,
            corner_radius=PANEL_RADIUS, justify="left", anchor="w", wraplength=520, padx=14, pady=10
        )
    bubble.grid(row=1, column=1, sticky="w", pady=(4, 0))

    actions = ctk.CTkFrame(inner, fg_color="transparent")
    actions.grid(row=2, column=1, sticky="w", pady=(3, 0))

    def current_text():
        return _bubble_current_text(bubble, text)

    def copy_text():
        app.clipboard_clear()
        app.clipboard_append(current_text())
        log_activity("Copied response", current_text()[:60])

    def save_to_notes():
        dashboard_data.setdefault("notes", []).append({
            "text": current_text(),
            "time": time.strftime("%b %d, %I:%M %p"),
        })
        save_dashboard_data()
        add_notification_item("Saved to Notes", current_text()[:90])

    ctk.CTkButton(actions, text="Copy", width=46, height=22, font=(FONT_FAMILY, 10), fg_color="transparent", text_color=TEXT_MUTED, hover_color=CARD_COLOR_SOFT, command=copy_text).pack(side="left")
    ctk.CTkButton(actions, text="Save", width=44, height=22, font=(FONT_FAMILY, 10), fg_color="transparent", text_color=TEXT_MUTED, hover_color=CARD_COLOR_SOFT, command=save_to_notes).pack(side="left", padx=2)
    ctk.CTkButton(actions, text="Speak", width=50, height=22, font=(FONT_FAMILY, 10), fg_color="transparent", text_color=TEXT_MUTED, hover_color=CARD_COLOR_SOFT, command=lambda: threading.Thread(target=lambda: speak(clean_text(current_text())), daemon=True).start()).pack(side="left")

    scroll_chat_to_bottom()
    if save:
        persist_message("nova", text, time_str)
    return bubble


def add_user_bubble(text, time_str=None, save=True):
    time_str = time_str or time.strftime("%I:%M %p")
    row = ctk.CTkFrame(chat_scroll, fg_color="transparent")
    row.pack(fill="x", padx=8, pady=6)

    inner = ctk.CTkFrame(row, fg_color="transparent")
    inner.pack(side="right", anchor="e")

    avatar = ctk.CTkLabel(inner, image=profile_avatar_img, text="")
    avatar.grid(row=0, column=1, rowspan=2, sticky="n", padx=(10, 0), pady=(2, 0))

    name = ctk.CTkLabel(inner, text=f"{time_str}   You", font=("Arial", 11, "bold"), text_color=TEXT_MUTED, anchor="e")
    name.grid(row=0, column=0, sticky="e")

    if EMOJI_RENDER_OK:
        bubble = emoji_render.EmojiBubble(
            inner, bg_color=ACCENT, text_color="white",
            corner_radius=PANEL_RADIUS, wraplength=460, font_family=FONT_FAMILY,
        )
        bubble.set_text(text)
    else:
        bubble = ctk.CTkLabel(
            inner, text=text, font=(CHAT_FONT_FAMILY, 13), text_color="white", fg_color=ACCENT,
            corner_radius=PANEL_RADIUS, justify="left", anchor="w", wraplength=460, padx=14, pady=10
        )
    bubble.grid(row=1, column=0, sticky="e", pady=(4, 0))

    actions = ctk.CTkFrame(inner, fg_color="transparent")
    actions.grid(row=2, column=0, sticky="e", pady=(3, 0))
    ctk.CTkButton(
        actions, text="Copy", width=46, height=22, font=(FONT_FAMILY, 10),
        fg_color="transparent", text_color=TEXT_MUTED, hover_color=CARD_COLOR_SOFT,
        command=lambda: (app.clipboard_clear(), app.clipboard_append(text))
    ).pack(side="right")

    scroll_chat_to_bottom()
    if save:
        persist_message("user", text, time_str)
    return bubble


def typewriter_into_bubble(bubble, text):
    # Colour-emoji bubble (tk.Text based) — streams char/emoji by emoji.
    if hasattr(bubble, "stream_text"):
        bubble.stream_text(text, after_step=scroll_chat_to_bottom)
        return
    bubble.configure(text="")
    partial = ""
    for ch in text:
        partial += ch
        bubble.configure(text=partial)
        bubble.update()
        scroll_chat_to_bottom()
        time.sleep(0.015)


def add_focus_chip_row():
    row = ctk.CTkFrame(chat_scroll, fg_color="transparent")
    row.pack(fill="x", padx=8, pady=(0, 10))

    inner = ctk.CTkFrame(row, fg_color="transparent")
    inner.pack(side="left", anchor="w", padx=(52, 0))

    chips = [
        ("Pomodoro\n25 min focus", 25),
        ("Deep Focus\n50 min focus", 50),
        ("Custom\nSet your time", None),
    ]
    for label, minutes in chips:
        b = ctk.CTkButton(
            inner, text=label, width=110, height=48, font=("Arial", 11),
            fg_color=CARD_COLOR_SOFT, hover_color=ACCENT_SOFT, text_color=TEXT_MAIN,
            command=lambda m=minutes: start_focus_session(m)
        )
        b.pack(side="left", padx=4)
    scroll_chat_to_bottom()


def session_complete(minutes):
    add_nova_bubble(f"Nice work! Your {minutes}-minute focus session is complete. \U0001F389")


def start_focus_session(minutes):
    global focus_running
    if minutes is None:
        popup = ctk.CTkToplevel(app)
        popup.title("Custom Focus")
        popup.geometry("300x160")
        popup.transient(app)
        popup.configure(fg_color=BG_COLOR)
        bring_window_to_front(popup)
        ctk.CTkLabel(popup, text="Minutes to focus:", font=("Arial", 13)).pack(pady=(20, 8))
        entry = ctk.CTkEntry(popup)
        entry.pack(pady=6, padx=20, fill="x")

        def confirm():
            try:
                m = int(entry.get().strip())
            except ValueError:
                return
            popup.destroy()
            start_focus_session(m)

        ctk.CTkButton(popup, text="Start", fg_color=ACCENT, hover_color=ACCENT_HOVER, command=confirm).pack(pady=14)
        return

    if not focus_running:
        toggle_focus_timer()
    add_nova_bubble(f"Started a {minutes}-minute focus session. I'll let you know when it's done!")
    app.after(minutes * 60000, lambda: session_complete(minutes))


_saved_history = get_current_thread().get("messages") or dashboard_data.get("chat_history", [])
if _saved_history:
    for _entry in _saved_history:
        if _entry.get("sender") == "user":
            add_user_bubble(_entry.get("text", ""), time_str=_entry.get("time"), save=False)
        else:
            add_nova_bubble(_entry.get("text", ""), time_str=_entry.get("time"), save=False)
else:
    startup_message = random.choice(greetings)
    add_nova_bubble(startup_message)


_gemini_ready, _gemini_message = check_gemini_status()
_gemini_icon = "\u2705" if _gemini_ready else "\u26A0\uFE0F"
add_nova_bubble(f"{_gemini_icon} {_gemini_message}", save=False)

_ocr_ready, _ocr_message = check_ocr_status()
_ocr_icon = "\u2705" if _ocr_ready else "\u26A0\uFE0F"
add_nova_bubble(f"{_ocr_icon} OCR fallback: {_ocr_message}", save=False)

bottom_frame = ctk.CTkFrame(home_page, height=70, fg_color=TOPBAR_COLOR, corner_radius=PANEL_RADIUS)
bottom_frame.grid(row=1, column=0, sticky="ew")


def attach_file():
    global attached_file_context
    path = filedialog.askopenfilename(
        filetypes=[
            ("Supported files", "*.txt *.md *.csv *.json *.py *.pdf *.png *.jpg *.jpeg *.webp *.bmp *.gif *.tiff"),
            ("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tiff"),
            ("Documents", "*.txt *.md *.csv *.json *.py *.pdf"),
            ("All files", "*.*"),
        ]
    )
    if path:
        filename = os.path.basename(path)
        if is_supported_image(path):
            attached_file_context = {"kind": "image", "name": filename, "path": path}
            message_entry.insert("end", f" [Image: {filename}]")
            add_nova_bubble(
                f"Image attached: {filename}. Ask me what to read, describe, or analyze in it.",
                save=False,
            )
            log_activity("Image attached", filename)
            return

        text, err = read_file_preview(path)
        if err:
            attached_file_context = None
            add_nova_bubble(f"File attach failed for {filename}: {err}", save=False)
            return
        attached_file_context = {"kind": "document", "name": filename,
                                 "path": path, "text": text or ""}
        message_entry.insert("end", f" [Attached: {filename}]")
        add_nova_bubble(f"Attached {filename}. Ask me to summarize, explain, or extract action points.", save=False)
        log_activity("File attached", filename)


def cycle_language():
    order = ["English", "Hindi", "Hinglish"]
    current = app_settings.get("language", "English")
    nxt = order[(order.index(current) + 1) % len(order)] if current in order else "English"
    save_language(nxt)
    add_nova_bubble(f"Language set to {nxt}.")


attach_button = ctk.CTkButton(bottom_frame, text="\U0001F4CE", width=32, height=32, fg_color="transparent", hover_color=CARD_COLOR_SOFT, font=("Arial", 14), command=attach_file)
attach_button.pack(side="left", padx=(12, 2), pady=13)
add_tooltip(attach_button, "Attach a file (adds its name to your message)")

globe_button = ctk.CTkButton(bottom_frame, text="\U0001F310", width=32, height=32, fg_color="transparent", hover_color=CARD_COLOR_SOFT, font=("Arial", 14), command=cycle_language)
globe_button.pack(side="left", padx=2, pady=13)
add_tooltip(globe_button, "Cycle language: English / Hindi / Hinglish")

sparkle_button = ctk.CTkButton(bottom_frame, text="\u2728", width=32, height=32, fg_color="transparent", hover_color=CARD_COLOR_SOFT, font=("Arial", 14), command=lambda: send_prefilled("Write something about "))
sparkle_button.pack(side="left", padx=(2, 8), pady=13)
add_tooltip(sparkle_button, "AI Writer - drafts something for you")

message_entry = ctk.CTkEntry(
    bottom_frame, placeholder_text="Message Nova or type a command...",
    height=42, font=(FONT_FAMILY, 14), fg_color=BG_COLOR, border_color=BORDER_COLOR
)
message_entry.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=13)

mic_inline_button = ctk.CTkButton(bottom_frame, text="\U0001F3A4", width=32, height=32, fg_color="transparent", hover_color=CARD_COLOR_SOFT, font=("Arial", 14), command=lambda: open_listening_window())
mic_inline_button.pack(side="left", padx=(0, 6), pady=13)
add_tooltip(mic_inline_button, "Start voice listening")

send_button = ctk.CTkButton(bottom_frame, text="\u27A4", width=44, height=42, command=lambda: send_message(), fg_color=ACCENT, hover_color=ACCENT_HOVER, font=("Arial", 16))
send_button.pack(side="right", padx=(0, 14), pady=13)
add_tooltip(send_button, "Send message")
message_entry.bind("<Return>", lambda e: send_message())


def talk_animation():
    global popup_face_label
    if popup_face_label is not None:
        popup_face_label.configure(image=face_talk)
        app.after(500, lambda: popup_face_label.configure(image=face_open) if popup_face_label else None)


def blink_animation():
    global popup_face_label
    if popup_face_label is not None:
        popup_face_label.configure(image=face_blink)
        app.after(200, lambda: popup_face_label.configure(image=face_open) if popup_face_label else None)
    app.after(random.randint(3000, 6000), blink_animation)


blink_animation()


def add_emojis(text):
    """Append a colorful, expressive emoji to *text* based on keywords.

    A rotating palette of vibrant emojis is used so the chat stays lively
    and engaging without repeating the exact same symbol every time.
    """
    if text is None:
        return ""
    text_lower = text.lower()

    # Colorful emoji palettes — each keyword maps to several vibrant options
    emoji_map = {
        "opening": ["🚀", "🎉", "✨", "🌟"],
        "youtube": ["🎬", "▶️", "🎥", "📺"],
        "google":   ["🔍", "🌐", "📶", "🔗"],
        "hello":    ["👋", "🌈", "👋🏻", "👋🏻‍♀️"],
        "music":    ["🎶", "🎵", "🎧", "🎤"],
        "happy":    ["😊", "🤗", "🌞", "🌼"],
        "sad":      ["😢", "😞", "💙", "🌧️"],
        "error":    ["⚠️", "🚨", "❌", "⚡"],
        "remember": ["🧠", "💭", "📝", "🎯"],
        "screenshot": ["📸", "📷", "🖼️", "📹"],
        "volume":   ["🔊", "🎙️", "📢", "🔈"],
        "battery":  ["🔋", "⚡", "🔌", "🔋"],
        "locking":  ["🔒", "🔐", "🛡️", "⛔"],
        "congratulations": ["🎊", "🎁", "🏆", "🥳"],
        "done":     ["✅", "🎉", "👍", "💯"],
        "waiting":  ["⏳", "⏰", "🕐", "🕒"],
        "thinking": ["🤔", "💭", "🧐", "🔍"],
        "yes":      ["🙂", "✔️", "👍", "🎉"],
        "no":       ["🙁", "✖️", "👎", "😔"],
        "good":     ["👍", "🌟", "💪", "🎉"],
        "bad":      ["😞", "👎", "💩", "🚫"],
        "save":     ["💾", "📁", "✅", "🔖"],
        "delete":   ["🗑️", "❌", "🚫", "🧹"],
        "copy":     ["📋", "✅", "📄", "🔗"],
        "help":     ["🆘", "❓", "💡", "🤝"],
        "question": ["❓", "🤔", "💭", "🎯"],
        "idea":     ["💡", "✨", "🌟", "🎯"],
        "time":     ["⏰", "🕒", "📅", "⏳"],
        "file":     ["📄", "📁", "📂", "📋"],
        "folder":   ["📁", "📂", "🗂️", "📁"],
        "search":   ["🔎", "🏃", "🕵️", "📍"],
        "chat":     ["💬", "👋", "🗨️", "✉️"],
        "study":    ["📚", "📖", "🎓", "🧠"],
        "ship":     ["🚢", "⛴️", "🛥️", "⚓"],
        "navy":     ["⛵", "🚢", "⚓", "🌊"],
        "ocean":    ["🌊", "🌊", "🐋", "🐠"],
    }

    for keyword, options in emoji_map.items():
        if keyword in text_lower:
            return text + " " + random.choice(options)

    return text + " ✨"


def clean_text(text):
    """Remove emojis AND special formatting symbols so TTS can read the text."""
    text = _strip_emojis(text)
    for symbol in ("*", "#"):
        text = text.replace(symbol, "")
    return text


def build_recent_context(max_messages=30):
    """Small helper: turns the last few persisted chat messages into a
    plain-text transcript so ask_nova() can answer with awareness of
    what was already discussed, instead of treating every message as
    a fresh, isolated question.

    Expanded from 8 to 30 messages so Nova remembers more of the recent
    conversation. Groq (openai/gpt-oss-20b) has a 131K-token window and
    ~1000 tokens/sec generation, so 30 short messages add almost nothing
    to reply latency — the app stays snappy (well under 10-20s).

    Also PREPENDS the user's saved memories (name, facts, preferences)
    so Nova reads them before every reply.
    """
    memory_block = memory_facts_block()
    history = dashboard_data.get("chat_history", [])[-max_messages:]
    if not history:
        return memory_block
    lines = []
    for entry in history:
        who = "You" if entry.get("sender") == "user" else "Nova"
        lines.append(f"{who}: {_strip_emojis(entry.get('text', ''))}")
    transcript = "Ab tak ki baatcheet:\n" + "\n".join(lines) + "\n\n"
    return memory_block + transcript


def send_message():
    global attached_file_context
    user_message = message_entry.get().strip()
    if user_message == "":
        return

    # Strip emojis so the LLM never "reads" them — display keeps them
    clean_message = _strip_emojis(user_message)

    styled_message = add_emojis(user_message)
    add_user_bubble(styled_message)
    message_entry.delete(0, "end")

    thinking_time_str = time.strftime("%I:%M %p")
    thinking_bubble = add_nova_bubble("Thinking...", time_str=thinking_time_str, save=False)
    app.update()

    # --- Non-blocking path for slow computer-use / AI-vision commands ----
    # Computer-use ("screen dekho", "click on search bar", "search bar me x
    # likho") hits OCR/Gemini/network and can take seconds; running it on
    # the Tk main thread would freeze Nova's UI. parse_command() is cheap
    # pure string logic, so we route on the UI thread and only offload the
    # slow execution, marshalling the result back via app.after(0, ...) —
    # the same safe pattern the codebase already uses elsewhere.
    _cu_hit = False
    try:
        from nova_features import computer_use as _cu_mod
        _cu_hit = _cu_mod.parse_command(clean_message) is not None
    except Exception:
        _cu_hit = False
    if _cu_hit:
        def _run_slow_command():
            try:
                res = execute_command(clean_message)
                if not isinstance(res, str) or not res.strip():
                    res = "Sorry, something went wrong. Please try again."
            except Exception as e:
                log.error("computer-use async error: %s: %s",
                          type(e).__name__, e)
                res = "Sorry, something went wrong. Please try again."
            app.after(0, lambda r=res: _finish_slow_response(
                r, thinking_bubble, thinking_time_str))
        threading.Thread(target=_run_slow_command, daemon=True).start()
        return

    if attached_file_context and attached_file_context.get("kind") == "image":
        image_name = attached_file_context.get("name", "attached image")
        image_path = attached_file_context.get("path")
        question = clean_message
        for marker in (f"[Image: {image_name}]", f"[Attached: {image_name}]"):
            question = question.replace(marker, "").strip()
        if not question:
            question = "Describe this image and read any visible text."

        try:
            pil_image = Image.open(image_path).convert("RGB")
            response = ask_gemini_vision(pil_image, question)
            if response is None:
                ocr_text = extract_text_from_image(pil_image)
                if ocr_text:
                    response = ask_nova(
                        f"User attached image: {image_name}\n"
                        f"Question: {question}\n"
                        f"OCR text from image:\n{ocr_text}\n\n"
                        "Answer using the OCR text. If visual details are needed, explain that Gemini Vision setup is required."
                    )
                else:
                    response = (
                        f"I received the image {image_name}, but I could not analyze it visually.\n"
                        f"Gemini Vision issue: {get_last_gemini_error() or 'not configured'}\n"
                        "OCR also did not find readable text in the image."
                    )
        except Exception as exc:
            response = f"I could not open/read the attached image {image_name}: {exc}"

        attached_file_context = None
        styled_response = add_emojis(response)
        typewriter_into_bubble(thinking_bubble, styled_response)
        persist_message("nova", styled_response, thinking_time_str)
        log_activity("Image chat", image_name)
        scroll_chat_to_bottom()
        talk_animation()

        emotion = detect_emotion(response)
        if app_settings.get("voice_enabled", True):
            threading.Thread(
                target=lambda: speak(clean_text(response), emotion=emotion),
                daemon=True,
            ).start()
        return

    try:
        # 1) Deterministic router (the patched commands.execute_command
        #    handles its own confirm_destructive for shutdown / restart).
        needs_destructive_confirm = any(
            t in clean_message.lower() for t in ("shutdown pc", "restart pc")
        )
        destructive_ok = (
            confirm_destructive(clean_message) if needs_destructive_confirm else False
        )
        response = execute_command(clean_message, confirm_destructive=destructive_ok, attached_file=attached_file_context)

        # 2) If the deterministic router says "not me", try the agent.
        if response == "Command not recognized":
            smart_response = smart_execute(clean_message, confirm_destructive=destructive_ok)
            if smart_response:
                response = smart_response
            else:
                # 3) Free-form LLM chat fallback.
                if _is_privacy_mode_on() and any(
                    kw in clean_message.lower() for kw in
                    ("file", "folder", "delete", "open ", "list", "search",
                     "rename", "move", "run ", "launch", "app")
                ):
                    response = ("🔒 Privacy mode is on — system actions are "
                                "blocked. Turn it off in Settings to allow "
                                "file / OS operations.")
                elif _AGENT_AVAILABLE and any(
                    kw in clean_message.lower() for kw in
                    ("file", "folder", "delete", "open ", "list my",
                     "search for", "rename", "move", "run ", "launch ",
                     "start the", "disk", "empty")
                ):
                    try:
                        response = route_to_agent(
                            clean_message, confirm_callback=confirm_destructive
                        )
                    except Exception as exc:
                        log.error("route_to_agent failed: %s", exc)
                        response = "Agent routing failed. Try again."
                else:
                    mode = dashboard_data.get("assistant_mode", "General")
                    mode_prefix = f"Assistant mode: {mode}. "
                    file_prefix = ""
                    if attached_file_context:
                        file_prefix = (
                            f"Attached file: {attached_file_context['name']}\n"
                            f"File content preview:\n{attached_file_context['text']}\n\n"
                        )
                    context_prompt = mode_prefix + file_prefix + build_recent_context() + f"User ka naya message: {clean_message}"
                    response = ask_nova(context_prompt)
                    attached_file_context = None

        if not isinstance(response, str) or response.strip() == "":
            response = "Sorry, something went wrong. Please try again."
    except Exception as e:
        log.error("send_message error: %s: %s", type(e).__name__, e)
        add_notification_item("Chat Error", f"{type(e).__name__}: {e}")
        log_activity("Chat error", f"{type(e).__name__}: {e}")
        response = "Sorry, something went wrong. Please try again."

    lower_message = clean_message.lower()
    if "stop speaking" in lower_message:
        set_voice_enabled(False)
    elif "start speaking" in lower_message:
        set_voice_enabled(True)

    styled_response = add_emojis(response)
    typewriter_into_bubble(thinking_bubble, styled_response)
    persist_message("nova", styled_response, thinking_time_str)
    log_activity("Chat message", clean_message[:90])
    attached_file_context = None
    scroll_chat_to_bottom()
    talk_animation()

    if clean_message.strip().lower() == "study with me":
        add_focus_chip_row()

    emotion = detect_emotion(response)
    if app_settings.get("voice_enabled", True):
        threading.Thread(
            target=lambda: speak(clean_text(response), emotion=emotion),
            daemon=True,
        ).start()

# ---------------- SCREEN WATCH (continuous listening) + CAMERA ----------------
def _finish_slow_response(response, thinking_bubble, thinking_time_str):
    """UI-thread tail for the async computer-use path (called via app.after).
    Replicates what the synchronous send_message tail does, but must run on
    the Tk main thread so it is safe to touch widgets."""
    styled_response = add_emojis(response)
    typewriter_into_bubble(thinking_bubble, styled_response)
    persist_message("nova", styled_response, thinking_time_str)
    log_activity("Chat message", "computer-use command (async)")
    scroll_chat_to_bottom()
    talk_animation()
    emotion = detect_emotion(response)
    if app_settings.get("voice_enabled", True):
        threading.Thread(
            target=lambda: speak(clean_text(response), emotion=emotion),
            daemon=True,
        ).start()


# These are NEW features. They do NOT touch the original mic button flow
# below (open_listening_window / listen_and_send) - that stays exactly
# as it was: press the mic, say one thing, it gets typed and sent.
#
# Screen Watch is a separate, opt-in mode: once turned on, Nova listens
# continuously in a background thread and treats everything you say as
# a question about your screen (no wake word needed). It screenshots
# the screen and asks Gemini vision (or OCR as a fallback) to answer.


def handle_vision_query(command_text, pil_image, source_label="Screen"):
    """Runs on the MAIN thread. Tries real Gemini vision first (it can
    actually see the image - objects, expressions, code, everything).
    Falls back to OCR-only text extraction if Gemini isn't configured
    or the call fails."""
    command_text = command_text.strip()
    if not command_text:
        return

    add_user_bubble(f"\U0001F441 ({source_label}) {add_emojis(command_text)}")
    thinking_time_str = time.strftime("%I:%M %p")
    thinking_bubble = add_nova_bubble(f"Looking at your {source_label.lower()}...", time_str=thinking_time_str, save=False)
    app.update()

    if pil_image is None:
        response = f"Main {source_label.lower()} capture nahi kar paaya is system par."
    else:
        response = ask_gemini_vision(pil_image, command_text)
        if response is None:
            # fall back to OCR + text-only brain
            screen_text = extract_text_from_image(pil_image)
            if pytesseract is None and google_genai is None:
                response = "Na Gemini configure hai, na OCR install hai. Ek setup karo - Gemini free hai (README dekho), ya `pip install pytesseract` + Tesseract-OCR install karo."
            elif screen_text:
                try:
                    prompt = (
                        f"User ne bola: \"{command_text}\".\n\n"
                        f"Unki {source_label.lower()} par ye text dikh raha hai (OCR se nikala, formatting perfect nahi hogi):\n"
                        f"---\n{screen_text}\n---\n\nIsko dekh kar user ki request ka jawab do."
                    )
                    response = ask_nova(prompt)
                    if not isinstance(response, str) or not response.strip():
                        response = "Sorry, kuch samajh nahi paya. Dobara try karo."
                except Exception as exc:
                    print("handle_vision_query OCR-fallback error:", exc)
                    response = "Analyze karte waqt error aa gaya."
            else:
                response = (
                    f"{source_label} capture ho gaya, lekin na Gemini se jawab mila na OCR ko koi text mila.\n"
                    f"Gemini ki asli wajah: {get_last_gemini_error() or 'pata nahi'}\n"
                    f"Agar photo/face/scene samjhana tha (sirf text nahi), Gemini setup zaroori hai - OCR sirf text padh sakta hai."
                )

    styled_response = add_emojis(response)
    typewriter_into_bubble(thinking_bubble, styled_response)
    persist_message("nova", styled_response, thinking_time_str)
    scroll_chat_to_bottom()
    talk_animation()

    emotion = detect_emotion(response)
    if app_settings.get("voice_enabled", True):
        threading.Thread(target=lambda: speak(clean_text(response), emotion=emotion), daemon=True).start()


def run_screen_watch_loop():
    """Background thread: keeps calling listen() continuously. No wake
    word anymore - whatever you say while Screen Watch is ON gets
    treated as a command about your screen."""
    global screen_watch_active
    failure_count = 0
    while screen_watch_active:
        try:
            heard = listen()
        except Exception as exc:
            print("screen watch listen() failed:", exc)
            heard = None

        if not screen_watch_active:
            break

        if not heard or not heard.strip():
            failure_count += 1
            if failure_count >= 3:
                screen_watch_active = False

                def _stop_with_error():
                    if screen_watch_button is not None:
                        screen_watch_button.configure(fg_color=CARD_COLOR, text_color=TEXT_MAIN)
                    detail = get_last_listen_error() or "No voice input was detected."
                    add_nova_bubble(f"\U0001F441 Screen Watch stopped because voice listening failed.\n{detail}")

                app.after(0, _stop_with_error)
                break
            time.sleep(0.5)
            continue

        failure_count = 0
        command_text = heard.strip()

        def _run(c=command_text):
            screenshot = capture_screen_image()
            handle_vision_query(c, screenshot, source_label="Screen")

        app.after(0, _run)


def toggle_screen_watch():
    global screen_watch_active, screen_watch_thread
    screen_watch_active = not screen_watch_active

    if screen_watch_active:
        screen_watch_button.configure(fg_color=ACCENT, text_color="white")
        add_nova_bubble("\U0001F441 Screen Watch ON - ab jo bhi bologe, seedha screen ke baare me sawaal maana jayega (koi wake word nahi chahiye).")
        screen_watch_thread = threading.Thread(target=run_screen_watch_loop, daemon=True)
        screen_watch_thread.start()
    else:
        screen_watch_button.configure(fg_color=CARD_COLOR, text_color=TEXT_MAIN)
        add_nova_bubble("\U0001F441 Screen Watch OFF.")


# ---------------- CAMERA ----------------


def camera_update_frame():
    global camera_active
    if not camera_active or camera_capture is None or camera_label is None:
        return
    ok, frame = camera_capture.read()
    if ok:
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb).resize((420, 315))
        photo = ImageTk.PhotoImage(img)
        camera_label.configure(image=photo)
        camera_label.image = photo
    if camera_window is not None:
        camera_window.after(33, camera_update_frame)


def camera_capture_and_ask():
    if camera_capture is None:
        return
    ok, frame = camera_capture.read()
    if not ok:
        add_nova_bubble("Camera se frame capture nahi ho paaya.")
        return
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pil_frame = Image.fromarray(frame_rgb)

    question = camera_question_entry.get().strip() if camera_question_entry is not None else ""
    if not question:
        question = "Camera me abhi ye dikh raha hai, describe karo - log, expressions, cheezein, sab kuch."

    show_page("home")
    handle_vision_query(question, pil_frame, source_label="Camera")

    if camera_question_entry is not None:
        camera_question_entry.delete(0, "end")


def camera_log_meal():
    if camera_capture is None:
        return
    ok, frame = camera_capture.read()
    if not ok:
        add_nova_bubble("Camera se frame capture nahi ho paaya.")
        return
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pil_frame = Image.fromarray(frame_rgb)

    note = camera_question_entry.get().strip() if camera_question_entry is not None else ""

    show_page("home")
    add_user_bubble(f"\U0001F37D (Meal) {add_emojis(note) if note else 'Thali ka photo, analyze karo'}")
    thinking_time_str = time.strftime("%I:%M %p")
    thinking_bubble = add_nova_bubble("Thali analyze kar raha hoon...", time_str=thinking_time_str, save=False)
    app.update()

    result = analyze_meal_photo(pil_frame, note=note)
    if result is None:
        result = f"Meal analyze nahi ho paaya. Wajah: {get_last_gemini_error() or 'Gemini configure nahi hai - pehle setup karo.'}"

    styled_result = add_emojis(result)
    typewriter_into_bubble(thinking_bubble, styled_result)
    persist_message("nova", styled_result, thinking_time_str)
    scroll_chat_to_bottom()
    talk_animation()

    emotion = detect_emotion(result)
    if app_settings.get("voice_enabled", True):
        threading.Thread(target=lambda: speak(clean_text(result), emotion=emotion), daemon=True).start()

    if camera_question_entry is not None:
        camera_question_entry.delete(0, "end")


def close_camera_window():
    global camera_window, camera_active, camera_capture, camera_question_entry
    camera_active = False
    if camera_capture is not None:
        try:
            camera_capture.release()
        except Exception:
            pass
        camera_capture = None
    if camera_window is not None:
        camera_window.destroy()
        camera_window = None
    camera_question_entry = None
    if camera_button is not None:
        camera_button.configure(fg_color=CARD_COLOR, text_color=TEXT_MAIN)


def open_camera_window():
    global camera_window, camera_active, camera_capture, camera_label, camera_question_entry

    if cv2 is None:
        add_nova_bubble("Camera feature ke liye `opencv-python` install nahi hai. Terminal me `pip install opencv-python` chala do.")
        return

    if camera_window is not None:
        return

    camera_capture = cv2.VideoCapture(0)
    if not camera_capture.isOpened():
        add_nova_bubble("Camera nahi mila / access nahi mil paaya. Kisi aur app me camera use to nahi ho raha?")
        camera_capture = None
        return

    camera_active = True
    if camera_button is not None:
        camera_button.configure(fg_color=ACCENT, text_color="white")

    camera_window = ctk.CTkToplevel(app)
    camera_window.title("Nova Camera")
    camera_window.geometry("460x560")
    camera_window.transient(app)
    camera_window.configure(fg_color=BG_COLOR)
    camera_window.protocol("WM_DELETE_WINDOW", close_camera_window)
    bring_window_to_front(camera_window)

    camera_label = tk.Label(camera_window, bg=BG_COLOR, bd=0)
    camera_label.pack(pady=16)

    ctk.CTkLabel(camera_window, text="Is photo ke baare me kya poochna hai? (khaali chhod do to general description milegi)", font=("Arial", 11), text_color=TEXT_MUTED, wraplength=400, justify="left").pack(padx=16, pady=(0, 6), fill="x")

    camera_question_entry = ctk.CTkEntry(camera_window, placeholder_text="e.g. Ye kya cheez hai? / Main kaisa lag raha hoon?", height=38)
    camera_question_entry.pack(padx=16, pady=(0, 10), fill="x")
    camera_question_entry.bind("<Return>", lambda e: camera_capture_and_ask())

    btn_row = ctk.CTkFrame(camera_window, fg_color="transparent")
    btn_row.pack(pady=10)

    capture_btn = ctk.CTkButton(btn_row, text="\U0001F4F8 Capture & Ask Nova", fg_color=ACCENT, hover_color=ACCENT_HOVER, command=camera_capture_and_ask)
    capture_btn.pack(side="left", padx=6)

    meal_btn = ctk.CTkButton(btn_row, text="\U0001F37D Log Meal", fg_color=SUCCESS, hover_color="#2fa863", command=camera_log_meal)
    meal_btn.pack(side="left", padx=6)

    close_btn = ctk.CTkButton(btn_row, text="Close", fg_color=DANGER, hover_color=DANGER_HOVER, command=close_camera_window)
    close_btn.pack(side="left", padx=6)

    camera_update_frame()


def toggle_camera():
    if camera_window is None:
        open_camera_window()
    else:
        close_camera_window()

# ---------------- LISTENING (VOICE) WINDOW ----------------


def animate_waves():
    global listening_window
    if listening_window is None:
        return
    for bar in wave_bars:
        height = random.randint(20, 100)
        x1, y1, x2, y2 = wave_canvas.coords(bar)
        wave_canvas.coords(bar, x1, 120 - height, x2, 120)
    listening_window.after(120, animate_waves)


def close_listening_window():
    global listening_window, popup_face_label, listening_status_label
    if listening_window is not None:
        listening_window.destroy()
        listening_window = None
    popup_face_label = None
    listening_status_label = None


def listen_and_send():
    def _set_status(text):
        if listening_status_label is not None:
            listening_status_label.configure(text=text)

    try:
        app.after(0, lambda: _set_status("Listening... speak now"))
        command = listen()
    except Exception as exc:
        print("listen_and_send error:", exc)
        command = ""
    error_text = get_last_listen_error()
    app.after(0, close_listening_window)
    if command:
        def _send_heard(c=command):
            message_entry.delete(0, "end")
            message_entry.insert(0, c)
            send_message()
        app.after(0, _send_heard)
    else:
        def _show_voice_error():
            detail = error_text or "I could not hear anything. Try again once the mic is selected and allowed."
            add_nova_bubble(f"Voice listening did not capture a command.\n{detail}", save=False)
        app.after(0, _show_voice_error)


def open_listening_window():
    global listening_window, wave_canvas, wave_bars, popup_face_label, listening_status_label
    if listening_window is not None:
        return

    mic_status_text = microphone_status()
    listening_window = ctk.CTkToplevel(app)
    listening_window.title("Nova Listening")
    listening_window.geometry("500x500")
    listening_window.transient(app)
    listening_window.configure(fg_color="#0d1117")
    bring_window_to_front(listening_window)

    popup_face_label = tk.Label(listening_window, image=face_open, bg="#0d1117", bd=0)
    popup_face_label.pack(pady=20)

    listening_status_label = ctk.CTkLabel(
        listening_window, text="Preparing microphone...",
        font=(FONT_FAMILY, 13), text_color=TEXT_MAIN
    )
    listening_status_label.pack(pady=(0, 4))

    ctk.CTkLabel(
        listening_window, text=mic_status_text,
        font=(FONT_FAMILY, 10), text_color=TEXT_MUTED,
        wraplength=430, justify="center"
    ).pack(pady=(0, 8), padx=20)

    wave_canvas = tk.Canvas(listening_window, width=300, height=120, bg="#0d1117", highlightthickness=0)
    wave_canvas.pack(pady=12)

    wave_bars.clear()
    x = 20
    for i in range(15):
        bar = wave_canvas.create_rectangle(x, 60, x + 10, 120, fill="#00ffff", outline="")
        wave_bars.append(bar)
        x += 18

    hangup_button = ctk.CTkButton(
        listening_window, text="Hang Up", fg_color="red", hover_color="#aa0000", width=180, height=45,
        command=close_listening_window
    )
    hangup_button.pack(pady=30)

    animate_waves()
    threading.Thread(target=listen_and_send, daemon=True).start()

# ---------------- GOALS / TASKS PAGES (checklist, persisted) ----------------


def build_checklist_page(frame, data_key, title_text, subtitle_text):
    make_section_title(frame, title_text, subtitle_text)

    add_row = ctk.CTkFrame(frame, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
    add_row.pack(fill="x", pady=(0, 12))

    entry = ctk.CTkEntry(
        add_row, placeholder_text="Add a new item...", height=38,
        fg_color=BG_COLOR, border_color=BORDER_COLOR
    )
    entry.pack(side="left", fill="x", expand=True, padx=(12, 6), pady=10)

    pending_reminder = {"value": None}

    def open_reminder_picker():
        popup = ctk.CTkToplevel(app)
        popup.title("Set Reminder")
        popup.geometry("300x230")
        popup.transient(app)
        popup.configure(fg_color=BG_COLOR)
        bring_window_to_front(popup)

        ctk.CTkLabel(popup, text="Remind me on:", font=("Arial", 13)).pack(pady=(20, 6))
        date_entry = ctk.CTkEntry(popup, placeholder_text="YYYY-MM-DD")
        date_entry.pack(padx=20, pady=6, fill="x")
        time_entry = ctk.CTkEntry(popup, placeholder_text="HH:MM (24-hour)")
        time_entry.pack(padx=20, pady=6, fill="x")
        error_label = ctk.CTkLabel(popup, text="", text_color=DANGER, font=("Arial", 10), wraplength=260)
        error_label.pack(pady=(4, 0))

        def confirm():
            d = date_entry.get().strip()
            t = time_entry.get().strip()
            if not d or not t:
                error_label.configure(text="Date aur time dono bharo.")
                return
            try:
                datetime.strptime(f"{d} {t}", "%Y-%m-%d %H:%M")
            except ValueError:
                error_label.configure(text="Format galat hai - YYYY-MM-DD aur HH:MM (24hr) use karo.")
                return
            pending_reminder["value"] = f"{d} {t}"
            remind_button.configure(text=f"\u23F0 {t}")
            popup.destroy()

        def clear_reminder():
            pending_reminder["value"] = None
            remind_button.configure(text="\u23F0")
            popup.destroy()

        btn_row = ctk.CTkFrame(popup, fg_color="transparent")
        btn_row.pack(pady=14, fill="x", padx=20)
        ctk.CTkButton(btn_row, text="Clear", width=80, fg_color=CARD_COLOR, hover_color=CARD_COLOR_SOFT, command=clear_reminder).pack(side="left")
        ctk.CTkButton(btn_row, text="Save", fg_color=ACCENT, hover_color=ACCENT_HOVER, command=confirm).pack(side="right")

    remind_button = ctk.CTkButton(
        add_row, text="\u23F0", width=36, height=38, fg_color=CARD_COLOR_SOFT, hover_color=ACCENT_SOFT,
        command=open_reminder_picker
    )
    remind_button.pack(side="left", padx=(0, 6), pady=10)
    add_tooltip(remind_button, "Set an optional reminder date/time for this item")

    toolbar = ctk.CTkFrame(frame, fg_color="transparent")
    toolbar.pack(fill="x", pady=(0, 8))
    summary_label = ctk.CTkLabel(
        toolbar, text="", font=(FONT_FAMILY, 12, "bold"),
        text_color=TEXT_MUTED, anchor="w"
    )
    summary_label.pack(side="left")
    filter_mode = tk.StringVar(value="All")
    filter_tabs = ctk.CTkSegmentedButton(
        toolbar, values=["All", "Open", "Done"], variable=filter_mode,
        command=lambda _value: render(), height=30,
        fg_color=CARD_COLOR, selected_color=ACCENT_SOFT,
        selected_hover_color=ACCENT, unselected_color=CARD_COLOR,
        unselected_hover_color=CARD_COLOR_SOFT
    )
    filter_tabs.pack(side="right")

    list_frame = ctk.CTkScrollableFrame(frame, fg_color="transparent")
    list_frame.pack(fill="both", expand=True)

    def render():
        for widget in list_frame.winfo_children():
            widget.destroy()
        items = dashboard_data[data_key]
        done_count = sum(1 for item in items if item.get("done"))
        summary_label.configure(text=f"{done_count} complete  /  {len(items)} total")
        selected = filter_mode.get()
        visible_items = [
            (idx, item) for idx, item in enumerate(items)
            if selected == "All"
            or (selected == "Open" and not item.get("done"))
            or (selected == "Done" and item.get("done"))
        ]
        if not visible_items:
            empty_text = "Nothing here yet." if not items else f"No {selected.lower()} items."
            empty = ctk.CTkLabel(list_frame, text=empty_text, text_color=TEXT_MUTED)
            empty.pack(pady=18)
            return
        for idx, item in visible_items:
            row = ctk.CTkFrame(list_frame, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
            row.pack(fill="x", pady=4)

            var = tk.BooleanVar(value=item.get("done", False))

            def on_toggle(i=idx, v=var):
                dashboard_data[data_key][i]["done"] = v.get()
                save_dashboard_data()
                if data_key == "goals":
                    refresh_goals_preview()

            cb = ctk.CTkCheckBox(row, text=item["text"], variable=var, command=on_toggle, font=("Arial", 13))
            cb.pack(side="left", fill="x", expand=True, padx=10, pady=8)

            if item.get("remind_at"):
                reminder_tag = ctk.CTkLabel(
                    row, text=f"\u23F0 {item['remind_at']}", font=("Arial", 10), text_color=ACCENT
                )
                reminder_tag.pack(side="right", padx=(0, 8))

            del_btn = ctk.CTkButton(
                row, text="\u2715", width=30, height=26, fg_color=DANGER, hover_color=DANGER_HOVER,
                command=lambda i=idx: (dashboard_data[data_key].pop(i), save_dashboard_data(), render(), refresh_goals_preview())
            )
            del_btn.pack(side="right", padx=8, pady=6)

    def add_item():
        text = entry.get().strip()
        if not text:
            return
        dashboard_data[data_key].append({
            "text": text, "done": False,
            "remind_at": pending_reminder["value"], "notified": False,
        })
        save_dashboard_data()
        entry.delete(0, "end")
        pending_reminder["value"] = None
        remind_button.configure(text="\u23F0")
        render()
        refresh_goals_preview()

    entry.bind("<Return>", lambda e: add_item())
    add_button = ctk.CTkButton(add_row, text="Add", width=70, fg_color=ACCENT, hover_color=ACCENT_HOVER, command=add_item)
    add_button.pack(side="right", padx=(6, 12), pady=10)

    render()
    return render


goals_page = register_page("goals")
render_goals = build_checklist_page(goals_page, "goals", "Today's Goals", "Track the goals you want to hit today.")

tasks_page = register_page("tasks")
render_tasks = build_checklist_page(tasks_page, "tasks", "Tasks", "Your general to-do list.")

# ---------------- NOTES / JOURNAL PAGES (free text, persisted) ----------------


def build_notes_page(frame, data_key, title_text, subtitle_text):
    make_section_title(frame, title_text, subtitle_text)

    entry_box = ctk.CTkTextbox(
        frame, height=96, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS,
        border_color=BORDER_COLOR, border_width=1, font=(FONT_FAMILY, 13)
    )
    entry_box.pack(fill="x", pady=(0, 8))

    notes_toolbar = ctk.CTkFrame(frame, fg_color="transparent")
    notes_toolbar.pack(fill="x", pady=(0, 10))

    search_var = tk.StringVar()
    search_box = ctk.CTkEntry(
        notes_toolbar, textvariable=search_var, placeholder_text="Search saved entries...",
        height=34, fg_color=BG_COLOR, border_color=BORDER_COLOR
    )
    search_box.pack(side="left", fill="x", expand=True, padx=(0, 8))

    count_label = ctk.CTkLabel(notes_toolbar, text="", font=(FONT_FAMILY, 11), text_color=TEXT_MUTED)
    count_label.pack(side="right")

    list_frame = ctk.CTkScrollableFrame(frame, fg_color="transparent")
    list_frame.pack(fill="both", expand=True)

    def render():
        for widget in list_frame.winfo_children():
            widget.destroy()
        items = dashboard_data[data_key]
        query = search_var.get().strip().lower()
        visible_items = [
            (idx, item) for idx, item in enumerate(items)
            if not query or query in item.get("text", "").lower() or query in item.get("time", "").lower()
        ]
        count_label.configure(text=f"{len(visible_items)} shown / {len(items)} saved")
        if not visible_items:
            empty = ctk.CTkLabel(
                list_frame,
                text="Nothing saved yet." if not items else "No entries match your search.",
                text_color=TEXT_MUTED
            )
            empty.pack(pady=18)
            return
        for _idx, (real_idx, item) in enumerate(reversed(visible_items)):
            row = ctk.CTkFrame(list_frame, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
            row.pack(fill="x", pady=4)

            ts = ctk.CTkLabel(row, text=item.get("time", ""), font=("Arial", 10), text_color=TEXT_MUTED, anchor="w")
            ts.pack(fill="x", padx=12, pady=(8, 0))

            body = ctk.CTkLabel(row, text=item.get("text", ""), anchor="w", justify="left", wraplength=380, font=("Arial", 13))
            body.pack(fill="x", padx=12, pady=(0, 8))

            del_btn = ctk.CTkButton(
                row, text="Delete", width=64, height=24, fg_color=DANGER, hover_color=DANGER_HOVER,
                command=lambda i=real_idx: (dashboard_data[data_key].pop(i), save_dashboard_data(), render())
            )
            del_btn.pack(anchor="e", padx=10, pady=(0, 8))

    def add_entry():
        text = entry_box.get("1.0", "end").strip()
        if not text:
            return
        dashboard_data[data_key].append({"text": text, "time": time.strftime("%b %d, %I:%M %p")})
        save_dashboard_data()
        entry_box.delete("1.0", "end")
        render()

    search_box.bind("<KeyRelease>", lambda _e: render())

    save_btn = ctk.CTkButton(frame, text="Save Entry", height=36, fg_color=ACCENT, hover_color=ACCENT_HOVER, command=add_entry)
    save_btn.pack(fill="x", pady=(0, 12))

    render()
    return render


notes_page = register_page("notes")
build_notes_page(notes_page, "notes", "Notes", "Quick notes, saved locally.")

journal_page = register_page("journal")
build_notes_page(journal_page, "journal", "Journal", "A private daily journal.")

# ---------------- DAILY BRIEFING PAGE ----------------

briefing_page = register_page("briefing")
make_section_title(
    briefing_page,
    "Daily Briefing",
    "Ask for news by topic, date, place, or time. Example: news in Delhi on 12 August 2026 evening."
)

briefing_row = ctk.CTkFrame(briefing_page, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
briefing_row.pack(fill="x", pady=(0, 10))
briefing_entry = ctk.CTkEntry(
    briefing_row, placeholder_text="news about merchant navy in Mumbai on 2026-08-12 morning",
    height=38, fg_color=BG_COLOR, border_color=BORDER_COLOR
)
briefing_entry.pack(side="left", fill="x", expand=True, padx=12, pady=12)
briefing_output = ctk.CTkTextbox(briefing_page, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS, font=(FONT_FAMILY, 12))
briefing_output.pack(fill="both", expand=True)


def run_briefing_query(query=None):
    q = (query or briefing_entry.get().strip() or "today's news")
    result = execute_command(q)
    briefing_output.delete("1.0", "end")
    briefing_output.insert("1.0", result)
    log_activity("News briefing", q)


ctk.CTkButton(briefing_row, text="Get News", width=92, fg_color=ACCENT, hover_color=ACCENT_HOVER, command=run_briefing_query).pack(side="right", padx=(0, 12), pady=12)
briefing_entry.bind("<Return>", lambda _e: run_briefing_query())

briefing_quick = ctk.CTkFrame(briefing_page, fg_color="transparent")
briefing_quick.pack(fill="x", pady=(10, 0))
for label, query in [
    ("Today", "today's news"),
    ("Top India", "top headlines in India"),
    ("Strategic", "news about India strategic"),
    ("Cricket", "news about India cricket"),
]:
    ctk.CTkButton(
        briefing_quick, text=label, height=32, fg_color=CARD_COLOR,
        hover_color=CARD_COLOR_SOFT, command=lambda q=query: run_briefing_query(q)
    ).pack(side="left", padx=(0, 8))

# ---------------- ROUTINE / CALENDAR PAGE ----------------

routine_page = register_page("routine")
make_section_title(routine_page, "Routine Timeline", "Edit your day plan and use it like a simple calendar.")

routine_form = ctk.CTkFrame(routine_page, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
routine_form.pack(fill="x", pady=(0, 10))
routine_time_entry = ctk.CTkEntry(routine_form, placeholder_text="HH:MM", width=90, height=36)
routine_time_entry.pack(side="left", padx=(12, 6), pady=12)
routine_title_entry = ctk.CTkEntry(routine_form, placeholder_text="Routine item", height=36)
routine_title_entry.pack(side="left", fill="x", expand=True, padx=6, pady=12)
routine_list = ctk.CTkScrollableFrame(routine_page, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
routine_list.pack(fill="both", expand=True)


def render_routine():
    for widget in routine_list.winfo_children():
        widget.destroy()
    schedule = sorted(
        enumerate(dashboard_data.setdefault("daily_schedule", [])),
        key=lambda pair: pair[1].get("time", ""),
    )
    for original_idx, item in schedule:
        row = ctk.CTkFrame(routine_list, fg_color=CARD_COLOR_SOFT, corner_radius=PANEL_RADIUS)
        row.pack(fill="x", padx=8, pady=5)
        ctk.CTkLabel(row, text=item.get("time", ""), width=64, font=(FONT_FAMILY, 13, "bold"), text_color=ACCENT).pack(side="left", padx=10, pady=10)
        ctk.CTkLabel(row, text=item.get("title", ""), anchor="w", font=(FONT_FAMILY, 13)).pack(side="left", fill="x", expand=True, padx=6)
        ctk.CTkButton(row, text="Delete", width=66, height=28, fg_color=DANGER, hover_color=DANGER_HOVER, command=lambda i=original_idx: (dashboard_data["daily_schedule"].pop(i), save_dashboard_data(), render_routine())).pack(side="right", padx=8)


def add_routine_item():
    t = routine_time_entry.get().strip()
    title = routine_title_entry.get().strip()
    if not t or not title:
        return
    dashboard_data.setdefault("daily_schedule", []).append({"time": t, "title": title})
    save_dashboard_data()
    routine_time_entry.delete(0, "end")
    routine_title_entry.delete(0, "end")
    render_routine()


ctk.CTkButton(routine_form, text="Add", width=70, fg_color=ACCENT, hover_color=ACCENT_HOVER, command=add_routine_item).pack(side="right", padx=12, pady=12)
render_routine()

# ---------------- PROMPTS PAGE ----------------

prompts_page = register_page("prompts")
make_section_title(prompts_page, "Prompt Library", "Editable prompt commands. Disable/delete what you do not need.")
ctk.CTkButton(prompts_page, text="Open Prompt Editor", height=40, fg_color=ACCENT, hover_color=ACCENT_HOVER, command=open_prompt_library).pack(fill="x", pady=(0, 12))
prompt_preview = ctk.CTkScrollableFrame(prompts_page, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
prompt_preview.pack(fill="both", expand=True)
for item in dashboard_data.get("prompt_library", []):
    row = ctk.CTkFrame(prompt_preview, fg_color=CARD_COLOR_SOFT, corner_radius=PANEL_RADIUS)
    row.pack(fill="x", padx=8, pady=5)
    state = "On" if item.get("enabled", True) else "Off"
    ctk.CTkLabel(row, text=f"{item.get('title', 'Prompt')}  ({state})", font=(FONT_FAMILY, 13, "bold"), anchor="w").pack(fill="x", padx=10, pady=(8, 0))
    ctk.CTkLabel(row, text=item.get("prompt", ""), text_color=TEXT_MUTED, wraplength=620, justify="left", anchor="w").pack(fill="x", padx=10, pady=(0, 8))

# ---------------- ACTIVITY TIMELINE PAGE ----------------

activity_page = register_page("activity")
make_section_title(activity_page, "Activity Timeline", "Recent Nova actions, chats, tool launches, and notifications.")
activity_list = ctk.CTkScrollableFrame(activity_page, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
activity_list.pack(fill="both", expand=True)


def render_activity():
    for widget in activity_list.winfo_children():
        widget.destroy()
    items = dashboard_data.get("activity_log", [])
    if not items:
        ctk.CTkLabel(activity_list, text="No activity yet.", text_color=TEXT_MUTED).pack(pady=20)
        return
    for item in reversed(items[-80:]):
        row = ctk.CTkFrame(activity_list, fg_color=CARD_COLOR_SOFT, corner_radius=PANEL_RADIUS)
        row.pack(fill="x", padx=8, pady=5)
        ctk.CTkLabel(row, text=item.get("title", ""), font=(FONT_FAMILY, 13, "bold"), anchor="w").pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(row, text=item.get("detail", ""), text_color=TEXT_MUTED, wraplength=620, justify="left", anchor="w").pack(fill="x", padx=10)
        ctk.CTkLabel(row, text=item.get("time", ""), text_color=TEXT_MUTED, font=(FONT_FAMILY, 10), anchor="w").pack(fill="x", padx=10, pady=(0, 8))


render_activity()

# ---------------- STUDY HUB PAGE ----------------

study_page = register_page("study")
make_section_title(study_page, "Study Hub",
                   "Your PCM + Merchant Navy command centre. Pick a subject, start a timer, log errors, track mocks.")

# --- Subject colour palette (quick subject switching) ---
study_subject_row = ctk.CTkFrame(study_page, fg_color="transparent")
study_subject_row.pack(fill="x", padx=2, pady=(0, 6))
study_subject_buttons = {}


def _highlight_subject_buttons():
    active = nova_study.get_active_subject()
    for k, b in study_subject_buttons.items():
        col = nova_study.subject_color(k)
        if k == active:
            b.configure(fg_color=col, text_color="white")
        else:
            b.configure(fg_color=CARD_COLOR_SOFT, text_color=TEXT_MAIN)


def _pick_subject(key):
    nova_study.set_active_subject(key)
    _highlight_subject_buttons()
    render_study_dashboard()


for _idx, (_k, _info) in enumerate(nova_study.SUBJECTS.items()):
    _b = ctk.CTkButton(study_subject_row, text=f"{_info['icon']} {_info['name']}",
                       height=40, fg_color=CARD_COLOR_SOFT, hover_color=ACCENT_SOFT,
                       text_color=TEXT_MAIN, font=(FONT_FAMILY, 12),
                       corner_radius=PANEL_RADIUS, command=lambda k=_k: _pick_subject(k))
    _b.grid(row=0, column=_idx, padx=4, pady=2, sticky="ew")
    study_subject_row.grid_columnconfigure(_idx, weight=1)
    study_subject_buttons[_k] = _b

_highlight_subject_buttons()

study_scroll = ctk.CTkScrollableFrame(study_page, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
study_scroll.pack(fill="both", expand=True)


def _clear_widgets(container):
    for w in container.winfo_children():
        w.destroy()


def _study_panel(title, accent=ACCENT):
    card = ctk.CTkFrame(study_scroll, fg_color=CARD_COLOR_SOFT, corner_radius=PANEL_RADIUS)
    card.pack(fill="x", pady=(6, 0), padx=4)
    ctk.CTkLabel(card, text=title, font=(FONT_FAMILY, 14, "bold"),
                 text_color=accent, anchor="w").pack(fill="x", padx=12, pady=(10, 2))
    body = ctk.CTkFrame(card, fg_color="transparent")
    body.pack(fill="x", padx=12, pady=(2, 12))
    return body


def _cmd_chip(parent, text, command):
    ctk.CTkButton(parent, text=text, height=34, fg_color=ACCENT_SOFT, hover_color=ACCENT,
                  text_color=TEXT_MAIN, font=(FONT_FAMILY, 11),
                  corner_radius=PANEL_RADIUS, command=command).pack(side="left", padx=3, pady=3)


def exec_study_slash(text):
    """Run a study slash command directly from a Study Hub button and show the reply."""
    add_user_bubble(add_emojis(text))
    try:
        result = execute_command(text)
    except Exception as exc:
        result = f"Command error: {exc}"
    if not isinstance(result, str) or result.strip() == "" or result == "Command not recognized":
        result = ask_nova(text)
    reply = add_emojis(result)
    bubble = add_nova_bubble("Thinking...", time_str=time.strftime("%I:%M %p"), save=False)
    typewriter_into_bubble(bubble, reply)
    persist_message("nova", reply, time.strftime("%I:%M %p"))
    render_study_dashboard()
    refresh_study_card()


def _subject_dot(key):
    col = nova_study.subject_color(key)
    return f"{nova_study.SUBJECTS.get(key, {}).get('icon', '📘')} {nova_study.SUBJECTS.get(key, {}).get('name', key)}"


def render_study_dashboard():
    """Rebuild the Study Hub dashboard panels from the study data store."""
    _clear_widgets(study_scroll)

    active = nova_study.get_active_subject()
    active_info = nova_study.SUBJECTS.get(active, {})
    ctk.CTkLabel(
        study_scroll,
        text=f"{active_info.get('icon', '')}  {active_info.get('name', 'Study')} — Quick commands",
        font=(FONT_FAMILY, 15, "bold"), text_color=TEXT_MAIN, anchor="w"
    ).pack(fill="x", padx=6, pady=(8, 2))

    chips = ctk.CTkFrame(study_scroll, fg_color="transparent")
    chips.pack(fill="x", padx=4)
    for k in nova_study.SUBJECTS:
        _cmd_chip(chips, f"{k}", lambda kk=k: exec_study_slash(f"/{kk}"))
    _cmd_chip(chips, "🗓 Today's plan", lambda: exec_study_slash("/today-plan"))
    _cmd_chip(chips, "🎯 Weak topics", lambda: exec_study_slash("/weak-topics"))
    _cmd_chip(chips, "📔 Error journal", lambda: exec_study_slash("/error-journal"))
    _cmd_chip(chips, "⏱ Timer 50", lambda: exec_study_slash(f"/timer 50 {active}"))

    # ---- Today's Plan ----
    body = _study_panel("🗓 Today's study plan", accent=nova_study.subject_color("general"))
    for time, sub, desc in nova_study.get_daily_schedule():
        ctk.CTkLabel(
            body,
            text=f"**{time}**  {_subject_dot(sub)} — {desc}",
            font=(FONT_FAMILY, 12), text_color=TEXT_MAIN, anchor="w", justify="left",
            wraplength=760
        ).pack(fill="x", pady=1)

    # ---- Error Journal ----
    body = _study_panel("📔 Error journal — quick log")
    _cmd_chip(body, "Log error", lambda: send_prefilled(f"/log-error {active} | topic | what went wrong | root cause"))
    _cmd_chip(body, "View all", lambda: exec_study_slash("/error-journal"))
    recent_errors = nova_study.list_error_journal(4)
    if recent_errors:
        for e in recent_errors:
            ctk.CTkLabel(
                body,
                text=f"• {_subject_dot(e['subject'])} — *{e.get('topic','')}*: {e.get('error','')}",
                font=(FONT_FAMILY, 11), text_color=TEXT_MUTED, anchor="w", justify="left",
                wraplength=760
            ).pack(fill="x", pady=1)
    else:
        ctk.CTkLabel(body, text="No errors logged yet. Tap 'Log error' to add your first entry.",
                     font=(FONT_FAMILY, 11), text_color=TEXT_MUTED, anchor="w").pack(fill="x", pady=1)

    # ---- Weak Topics ----
    body = _study_panel("🎯 Weak topics — fix these first", accent=nova_study.subject_color("maths"))
    weak = nova_study.weak_topics_list(6)
    if weak:
        for topic, sub, count in weak:
            ctk.CTkLabel(
                body,
                text=f"• **{topic}** ({_subject_dot(sub)}) — repeated **{count}×**",
                font=(FONT_FAMILY, 11), text_color=TEXT_MAIN, anchor="w", justify="left",
                wraplength=760
            ).pack(fill="x", pady=1)
    else:
        ctk.CTkLabel(body, text="No weak topics tracked yet — use /log-error to build this list.",
                     font=(FONT_FAMILY, 11), text_color=TEXT_MUTED, anchor="w").pack(fill="x", pady=1)

    # ---- Mock Tests ----
    body = _study_panel("📊 Mock test tracker", accent=SUCCESS)
    _cmd_chip(body, "+ Log result", lambda: send_prefilled("/mock-score 80 | physics:75 | chemistry:82 | maths:85"))
    _cmd_chip(body, "Mocks", lambda: exec_study_slash("/mock-score"))
    mocks = nova_study.list_mock_tests()
    if mocks:
        for m in mocks[-5:][::-1]:
            ctk.CTkLabel(
                body,
                text=f"• **{m['name']}** — {m['score_pct']:.0f}%  ({m['date']})",
                font=(FONT_FAMILY, 11), text_color=TEXT_MAIN, anchor="w",
                wraplength=760
            ).pack(fill="x", pady=1)
    else:
        ctk.CTkLabel(body, text="No mocks logged yet. Target: **+5%** vs last mock.",
                     font=(FONT_FAMILY, 11), text_color=TEXT_MUTED, anchor="w").pack(fill="x", pady=1)

    # ---- Merchant Navy focus ----
    body = _study_panel("⚓ Merchant Navy focus", accent=nova_study.subject_color("mn"))
    mn_rows = [
        "🧭 Navigation — charts & GPS",
        "⚙️ Engineering — bridge simulator & safety",
        "🗣 Interview prep — mock Q&A",
        "🪢 Seamanship — knots progress",
    ]
    for r in mn_rows:
        ctk.CTkLabel(body, text=r, font=(FONT_FAMILY, 11), text_color=TEXT_MAIN,
                     anchor="w").pack(fill="x", pady=1)
    _cmd_chip(body, "⚓ Start MN session", lambda: exec_study_slash("/timer 50 mn"))
    _cmd_chip(body, "MN help", lambda: exec_study_slash("/mn"))

    # ---- Weekly progress ----
    body = _study_panel("📈 Weekly progress (rolling 7 days)", accent=ACCENT)
    prog = nova_study.weekly_progress()
    ctk.CTkLabel(
        body,
        text=f"**{prog['hours']}h** study  ·  **{prog['mn_hours']}h** MN  ·  "
             f"{prog['mock_count']} mock(s)  ·  {prog['error_count_week']} error(s) this week",
        font=(FONT_FAMILY, 12), text_color=TEXT_MAIN, anchor="w", justify="left",
        wraplength=760
    ).pack(fill="x", pady=2)
    for k, hours in prog["hours_by_subject"].items():
        col = nova_study.subject_color(k)
        ctk.CTkLabel(
            body,
            text=f"{_subject_dot(k)}: {hours}h",
            font=(FONT_FAMILY, 11), text_color=col, anchor="w"
        ).pack(fill="x", pady=0)

    # ---- ASK Nova (prompt starters) ----
    body = _study_panel("💬 Ask Nova")
    prompts = [
        ("Explainer", "Explain this topic to me: "),
        ("Quiz me", "Quiz me on "),
        ("MCQ practice", "Give me MCQs on "),
        ("Summarize", "Summarize this: "),
    ]
    for label, p in prompts:
        _cmd_chip(body, label, lambda pp=p: send_prefilled(pp))


render_study_dashboard()


# ---------------- AI TOOLS PAGE ----------------

tools_page = register_page("tools")

make_section_title(
    tools_page,
    "AI Tools",
    "Fast launchers for Nova's chat brain, vision tools, nutrition workflow, and local system utilities."
)

tools_workspace = ctk.CTkFrame(tools_page, fg_color="transparent")
tools_workspace.pack(fill="both", expand=True)
tools_workspace.grid_rowconfigure(0, weight=1)
tools_workspace.grid_columnconfigure(1, weight=1)

tools_sidebar = ctk.CTkFrame(tools_workspace, width=176, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
tools_sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 12), pady=(0, 4))
tools_sidebar.grid_propagate(False)

ctk.CTkLabel(
    tools_sidebar, text="Categories", font=(FONT_FAMILY, 13, "bold"),
    text_color=TEXT_MAIN, anchor="w"
).pack(fill="x", padx=12, pady=(14, 8))

tools_grid = ctk.CTkScrollableFrame(tools_workspace, fg_color="transparent")
tools_grid.grid(row=0, column=1, sticky="nsew", pady=(0, 4))
for c in range(3):
    tools_grid.grid_columnconfigure(c, weight=1)


def open_calculator():
    show_page("home")
    result = execute_command("open calculator")
    if isinstance(result, str) and result.strip():
        add_nova_bubble(result)


def open_nutrition_profile_window():
    profile = get_profile()

    win = ctk.CTkToplevel(app)
    win.title("Nutrition Profile")
    win.geometry("340x420")
    win.configure(fg_color=BG_COLOR)
    bring_window_to_front(win)

    ctk.CTkLabel(win, text="Your Body Profile", font=("Arial", 18, "bold")).pack(pady=(20, 4))
    ctk.CTkLabel(
        win, text="Ye info thali-photo analysis ko accurate banati hai.",
        font=("Arial", 11), text_color=TEXT_MUTED, wraplength=280
    ).pack(pady=(0, 14))

    def labeled_entry(label_text, current_value):
        ctk.CTkLabel(win, text=label_text, anchor="w", font=("Arial", 12)).pack(fill="x", padx=24)
        entry = ctk.CTkEntry(win, height=36)
        if current_value is not None:
            entry.insert(0, str(current_value))
        entry.pack(fill="x", padx=24, pady=(2, 10))
        return entry

    height_entry = labeled_entry("Height (cm)", profile.get("height_cm"))
    weight_entry = labeled_entry("Current weight (kg)", profile.get("weight_kg"))
    target_entry = labeled_entry("Target weight (kg)", profile.get("target_weight_kg"))
    protein_entry = labeled_entry("Daily protein target (g)", profile.get("daily_protein_target_g"))

    status_label_local = ctk.CTkLabel(win, text="", font=("Arial", 11), text_color=SUCCESS)
    status_label_local.pack(pady=(4, 0))

    def save_profile():
        def to_float(entry):
            val = entry.get().strip()
            try:
                return float(val) if val else None
            except ValueError:
                return None

        set_profile(
            height_cm=to_float(height_entry),
            weight_kg=to_float(weight_entry),
            target_weight_kg=to_float(target_entry),
            daily_protein_target_g=to_float(protein_entry),
        )
        status_label_local.configure(text="Saved!")
        add_nova_bubble("\U0001F37D Nutrition profile update ho gaya - ab meal analysis zyada accurate hoga.")

    ctk.CTkButton(win, text="Save", fg_color=ACCENT, hover_color=ACCENT_HOVER, command=save_profile).pack(pady=16, padx=24, fill="x")


def show_nutrition_summary():
    show_page("home")
    add_nova_bubble(get_today_summary_text())


def finish_image_detection(result, bubble, time_str):
    styled_result = add_emojis(result)
    typewriter_into_bubble(bubble, styled_result)
    persist_message("nova", styled_result, time_str)
    scroll_chat_to_bottom()
    talk_animation()

    emotion = detect_emotion(result)
    if app_settings.get("voice_enabled", True):
        threading.Thread(target=lambda: speak(clean_text(result), emotion=emotion), daemon=True).start()


def open_ai_image_detector():
    show_page("home")

    if detect_ai_image is None:
        add_nova_bubble(
            "AI Image Detector load nahi hua. Check karo:\n"
            "1. `photo_detector.py` gui.py wale hi folder me hai?\n"
            "2. `pip install openai python-dotenv` kiya?\n"
            "3. Usi folder me `.env` file hai jisme GROQ_API_KEY likha hai?"
        )
        return

    file_path = filedialog.askopenfilename(
        title="Select Image",
        filetypes=[("Images", "*.jpg *.jpeg *.png *.webp *.gif")]
    )
    if not file_path:
        return

    filename = os.path.basename(file_path)
    add_user_bubble(f"\U0001F5BC Check karo real hai ya AI-generated: {filename}")
    thinking_time_str = time.strftime("%I:%M %p")
    thinking_bubble = add_nova_bubble("Image analyze kar raha hoon...", time_str=thinking_time_str, save=False)
    app.update()

    def worker():
        try:
            result = detect_ai_image(file_path)
        except Exception as exc:
            result = f"Detection fail ho gaya: {exc}"
        app.after(0, lambda: finish_image_detection(result, thinking_bubble, thinking_time_str))

    threading.Thread(target=worker, daemon=True).start()


tool_actions = [
    ("System", "\U0001F9EE Calculator", "Open the local calculator for quick math.", open_calculator),
    ("Chat", "\U0001F310 Translator", "Prepare a translation prompt in chat.", lambda: send_prefilled("Translate this: ")),
    ("Chat", "\u270F\uFE0F AI Writer", "Draft paragraphs, captions, letters, and ideas.", lambda: send_prefilled("Write something about ")),
    ("Study", "\U0001F4C4 Summarizer", "Turn long notes into concise summaries.", lambda: send_prefilled("Summarize this: ")),
    ("Study", "\U0001F4A1 Explainer", "Break down hard topics in simple steps.", lambda: send_prefilled("Explain this topic: ")),
    ("System", "\U0001F5C2 Command Guide", "Browse every saved command example.", open_command_guide),
    ("Nutrition", "\U0001F37D Nutrition Profile", "Tune meal-photo analysis with your body profile.", open_nutrition_profile_window),
    ("Nutrition", "\U0001F4CA Today's Nutrition", "Review today's nutrition totals.", show_nutrition_summary),
    ("Study", "\U0001F3AF Coach Chat", "Open the focused study and nutrition coach.", lambda: show_page("coach")),
    ("Vision", "\U0001F5BC AI Image Detector", "Check whether an image appears AI-generated.", open_ai_image_detector),
    # === NOVA NEW FEATURES ===
    ("Study", "Quiz Time", "Take a mini-quiz!", lambda: send_prefilled("quiz")),
    ("Study", "Progress Tracker", "Check XP/levels/streaks.", lambda: show_popup("Progress", get_progress_status())),
    ("Study", "Translator", "Translate text to Hindi.", lambda: send_prefilled("Translate this: ")),
    ("Study", "Reminders", "Check all reminders.", lambda: show_popup("Reminders", check_reminders())),
    ("Study", "Screen Monitor", "LIVE: Track active window in real-time.", open_live_monitor),
    ("Study", "Offline Mode", "Check offline status.", lambda: show_popup("Offline", check_offline_status())),
    ("Study", "Achievements", "View unlocked achievements.", lambda: show_popup("Achievements", get_achievements_info())),
    ("Study", "Suggestions", "LIVE: Get smart suggestions as you switch apps.", open_live_monitor),
    ("Study", "Export Data", "Export all Nova data.", lambda: show_popup("Export", export_all_data())),
    ("Study", "Run Commands", "Run safe system commands.", lambda: show_popup("Commands", get_available_commands())),

    # === NOVA AI v2 FEATURES ===
    ("Nova AI", "System Health", "Check CPU, RAM, disk & battery.", lambda: show_popup("System Health", get_system_health())),
    ("Nova AI", "Focus Timer", "Start a 25-min Pomodoro focus session.", lambda: show_popup("Focus Timer", start_focus_session(25))),
    ("Nova AI", "App Launcher", "Launch apps by name (notepad, chrome).", open_app_launcher),
    ("Nova AI", "Screenshot OCR", "Capture screen and extract text.", lambda: show_popup("Screen OCR", capture_screen_text())),
    ("Nova AI", "Clipboard", "Read current clipboard & history.", lambda: show_popup("Clipboard", get_clipboard_history())),
    ("Nova AI", "Daily Recap", "Today's activity summary.", lambda: show_popup("Daily Recap", get_daily_recap())),
    ("Nova AI", "Voice Output", "Speak text aloud.", lambda: speak_text("Hello! Nova is here to help you.")),
    ("Nova AI", "Open Website", "Open a website in browser.", lambda: open_website("google.com")),

    ("Chat", "\U0001F4DA Prompt Library", "Edit the prompt commands you want Nova to keep.", open_prompt_library),
    ("Chat", "\U0001F5C2 Chat Threads", "Switch between separate conversations.", open_threads_window),
    ("System", "\U0001F514 Notifications", "Open Nova's notification center.", open_notification_center),
    ("System", "\U0001F4F0 Daily Briefing", "Ask news by place, date, time, or topic.", lambda: show_page("briefing")),
    ("System", "\U0001F4C6 Routine Timeline", "Edit your daily calendar-style routine.", lambda: show_page("routine")),
    ("System", "\U0001F4CE File Chat",                 "Attach a document and ask Nova about it.", attach_file),

    # === NOVA TOP-25 FEATURES: Browser Control | Alarm Scheduler | Email Notifications ===
    ("Nova AI", "🌐 Browser Control", "Open a URL or search the web in a new tab.", open_browser_control),
    ("Nova AI", "⏰ Alarm Scheduler", "Set recurring alarms with snooze support.", open_alarm_manager),
    ("Nova AI", "📧 Email Notifications", "Save email config & send reminder emails.", open_email_manager),
]

tool_category_buttons = {}
tool_categories = [
    ("All", "\u25A6", len(tool_actions)),
    ("Chat", "\U0001F4AC", sum(1 for item in tool_actions if item[0] == "Chat")),
    ("Study", "\U0001F393", sum(1 for item in tool_actions if item[0] == "Study")),
    ("Vision", "\U0001F441", sum(1 for item in tool_actions if item[0] == "Vision")),
    ("Nutrition", "\U0001F37D", sum(1 for item in tool_actions if item[0] == "Nutrition")),
    ("System", "\u2699", sum(1 for item in tool_actions if item[0] == "System")),
    ("Nova AI", "\U0001F916", sum(1 for item in tool_actions if item[0] == "Nova AI")),
]


def render_tools(category="All"):
    for widget in tools_grid.winfo_children():
        widget.destroy()

    for name, button in tool_category_buttons.items():
        active = name == category
        button.configure(
            fg_color=ACCENT_SOFT if active else "transparent",
            text_color=TEXT_MAIN if active else TEXT_MUTED,
        )

    visible_tools = [
        item for item in tool_actions
        if category == "All" or item[0] == category
    ]

    if not visible_tools:
        ctk.CTkLabel(
            tools_grid, text="No tools in this category yet.",
            font=(FONT_FAMILY, 13), text_color=TEXT_MUTED
        ).grid(row=0, column=0, padx=10, pady=20, sticky="w")
        return

    for i, (_category, label, subtitle, cmd) in enumerate(visible_tools):
        make_tool_card(tools_grid, label, subtitle, cmd, i // 3, i % 3)


for category, icon, count in tool_categories:
    btn = ctk.CTkButton(
        tools_sidebar, text=f"  {icon}  {category}  ({count})",
        height=38, anchor="w", fg_color="transparent",
        hover_color=CARD_COLOR_SOFT, text_color=TEXT_MUTED,
        font=(FONT_FAMILY, 12), corner_radius=PANEL_RADIUS,
        command=lambda name=category: render_tools(name)
    )
    btn.pack(fill="x", padx=10, pady=3)
    tool_category_buttons[category] = btn

ctk.CTkLabel(
    tools_sidebar,
    text="Tip: use this rail to keep tools focused while all old actions remain available.",
    font=(FONT_FAMILY, 10), text_color=TEXT_MUTED,
    wraplength=145, justify="left", anchor="w"
).pack(fill="x", padx=12, pady=(12, 10))

render_tools("All")

# ---------------- COACH CHAT PAGE ----------------
# A separate, topic-locked chat (studies/goals/tasks/nutrition only)
# with its own persisted history, a 9 PM auto-rating, and a midnight
# reset. Deliberately kept simpler than the Home chat (no hero, no
# quick-action grid) since it's meant to be a focused, single-purpose
# space.

coach_page = register_page("coach")
coach_page.grid_rowconfigure(1, weight=1)
coach_page.grid_columnconfigure(0, weight=1)

coach_header = ctk.CTkFrame(coach_page, fg_color="transparent")
coach_header.grid(row=0, column=0, sticky="ew", pady=(4, 8))

ctk.CTkLabel(coach_header, text="\U0001F3AF Coach Chat", font=("Arial", 20, "bold")).pack(anchor="w")
ctk.CTkLabel(
    coach_header, text="Sirf padhai, goals, tasks aur nutrition ke baare me baat karta hai. "
    "Raat 9 baje aaj ka rating milega, aur raat 12 baje ye chat reset ho jaati hai (naya din, nayi shuruaat).",
    font=("Arial", 11), text_color=TEXT_MUTED, wraplength=520, justify="left"
).pack(anchor="w", pady=(2, 0))

coach_chat_scroll = ctk.CTkScrollableFrame(coach_page, fg_color=CARD_COLOR, corner_radius=15)
coach_chat_scroll.grid(row=1, column=0, sticky="nsew", pady=(4, 8))


def scroll_coach_to_bottom():
    coach_chat_scroll.update_idletasks()
    try:
        coach_chat_scroll._parent_canvas.yview_moveto(1.0)
    except Exception:
        pass


def add_coach_nova_bubble(text, time_str=None, save=True):
    time_str = time_str or time.strftime("%I:%M %p")
    row = ctk.CTkFrame(coach_chat_scroll, fg_color="transparent")
    row.pack(fill="x", padx=8, pady=6)
    inner = ctk.CTkFrame(row, fg_color="transparent")
    inner.pack(side="left", anchor="w")
    ctk.CTkLabel(inner, image=nova_avatar_img, text="").grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 10))
    ctk.CTkLabel(inner, text=f"Coach   {time_str}", font=("Arial", 11, "bold"), text_color=TEXT_MUTED, anchor="w").grid(row=0, column=1, sticky="w")
    if EMOJI_RENDER_OK:
        bubble = emoji_render.EmojiBubble(
            inner, bg_color=CARD_COLOR_SOFT, text_color=TEXT_MAIN,
            corner_radius=12, wraplength=420, font_family=FONT_FAMILY,
        )
        bubble.set_text(text)
    else:
        bubble = ctk.CTkLabel(
            inner, text=text, font=(CHAT_FONT_FAMILY, 13), text_color=TEXT_MAIN, fg_color=CARD_COLOR_SOFT,
            corner_radius=12, justify="left", anchor="w", wraplength=420, padx=14, pady=10
        )
    bubble.grid(row=1, column=1, sticky="w", pady=(4, 0))
    scroll_coach_to_bottom()
    if save:
        add_coach_message("nova", text, time_str)
    return bubble


def add_coach_user_bubble(text, time_str=None, save=True):
    time_str = time_str or time.strftime("%I:%M %p")
    row = ctk.CTkFrame(coach_chat_scroll, fg_color="transparent")
    row.pack(fill="x", padx=8, pady=6)
    inner = ctk.CTkFrame(row, fg_color="transparent")
    inner.pack(side="right", anchor="e")
    ctk.CTkLabel(inner, image=profile_avatar_img, text="").grid(row=0, column=1, rowspan=2, sticky="n", padx=(10, 0))
    ctk.CTkLabel(inner, text=f"{time_str}   You", font=("Arial", 11, "bold"), text_color=TEXT_MUTED, anchor="e").grid(row=0, column=0, sticky="e")
    if EMOJI_RENDER_OK:
        bubble = emoji_render.EmojiBubble(
            inner, bg_color=ACCENT, text_color="white",
            corner_radius=12, wraplength=380, font_family=FONT_FAMILY,
        )
        bubble.set_text(text)
    else:
        bubble = ctk.CTkLabel(
            inner, text=text, font=(CHAT_FONT_FAMILY, 13), text_color="white", fg_color=ACCENT,
            corner_radius=12, justify="left", anchor="w", wraplength=380, padx=14, pady=10
        )
    bubble.grid(row=1, column=0, sticky="e", pady=(4, 0))
    scroll_coach_to_bottom()
    if save:
        add_coach_message("user", text, time_str)
    return bubble


def coach_typewriter(bubble, text):
    if hasattr(bubble, "stream_text"):
        bubble.stream_text(text, after_step=scroll_coach_to_bottom)
        return
    bubble.configure(text="")
    partial = ""
    for ch in text:
        partial += ch
        bubble.configure(text=partial)
        bubble.update()
        scroll_coach_to_bottom()
        time.sleep(0.015)


coach_bottom_frame = ctk.CTkFrame(coach_page, height=64, fg_color=CARD_COLOR, corner_radius=12)
coach_bottom_frame.grid(row=2, column=0, sticky="ew")

coach_message_entry = ctk.CTkEntry(coach_bottom_frame, placeholder_text="Padhai, goals, tasks, nutrition ke baare me pucho...", height=42, font=("Arial", 14))
coach_message_entry.pack(side="left", fill="x", expand=True, padx=(14, 8), pady=11)


def send_coach_message(event=None):
    user_message = coach_message_entry.get().strip()
    if not user_message:
        return
    clean_message = _strip_emojis(user_message)
    coach_message_entry.delete(0, "end")
    add_coach_user_bubble(add_emojis(user_message))

    thinking_time_str = time.strftime("%I:%M %p")
    thinking_bubble = add_coach_nova_bubble("Thinking...", time_str=thinking_time_str, save=False)
    app.update()

    try:
        prompt = build_coach_prompt(clean_message)
        response = ask_nova(prompt)
        if not isinstance(response, str) or not response.strip():
            response = "Sorry, samajh nahi paya. Dobara try karo."
    except Exception as exc:
        print("coach chat error:", exc)
        response = "Kuch error aa gaya. Dobara try karo."

    styled_response = add_emojis(response)
    coach_typewriter(thinking_bubble, styled_response)
    add_coach_message("nova", styled_response, thinking_time_str)
    scroll_coach_to_bottom()

    emotion = detect_emotion(response)
    if app_settings.get("voice_enabled", True):
        threading.Thread(target=lambda: speak(clean_text(response), emotion=emotion), daemon=True).start()


coach_send_button = ctk.CTkButton(coach_bottom_frame, text="\u27A4", width=44, height=42, command=send_coach_message, fg_color=ACCENT, hover_color=ACCENT_HOVER, font=("Arial", 16))
coach_send_button.pack(side="right", padx=14, pady=11)
coach_message_entry.bind("<Return>", send_coach_message)

# Replay today's coach history (if any) so the page isn't empty on launch
reset_for_new_day_if_needed()
for _entry in coach_data.get("chat_history", []):
    if _entry.get("sender") == "user":
        add_coach_user_bubble(_entry.get("text", ""), time_str=_entry.get("time"), save=False)
    else:
        add_coach_nova_bubble(_entry.get("text", ""), time_str=_entry.get("time"), save=False)
if not coach_data.get("chat_history"):
    add_coach_nova_bubble(
        "Hi! Main tumhara Study & Nutrition coach hoon. Padhai, goals, tasks, ya nutrition ke baare me kuch bhi pucho. "
        "Raat 9 baje main aaj ka performance rate karunga.",
        save=False,
    )

show_page("home")

# ==========================================
# RIGHT PANEL
# ==========================================

# ---- Today overview card ----

today_card = ctk.CTkFrame(right_panel, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
today_card.pack(fill="x", padx=14, pady=(16, 10))

ctk.CTkLabel(
    today_card, text="Today", font=(FONT_FAMILY, 14, "bold"),
    anchor="w"
).pack(fill="x", padx=12, pady=(12, 2))

ctk.CTkLabel(
    today_card, text=datetime.now().strftime("%A, %d %B"),
    font=(FONT_FAMILY, 11), text_color=TEXT_MUTED, anchor="w"
).pack(fill="x", padx=12, pady=(0, 10))

today_stats = ctk.CTkFrame(today_card, fg_color="transparent")
today_stats.pack(fill="x", padx=8, pady=(0, 10))
for c in range(2):
    today_stats.grid_columnconfigure(c, weight=1)

make_metric_card(
    today_stats, "Open", str(sum(1 for item in dashboard_data["tasks"] if not item.get("done"))),
    "tasks"
).grid(row=0, column=0, padx=4, sticky="nsew")
make_metric_card(
    today_stats, "Streak", f"{current_streak_count()}d",
    "focus run", accent_color=SUCCESS
).grid(row=0, column=1, padx=4, sticky="nsew")

ctk.CTkButton(
    today_card, text="Plan Today", height=34, fg_color=ACCENT,
    hover_color=ACCENT_HOVER, command=lambda: send_prefilled("Plan my day")
).pack(fill="x", padx=12, pady=(0, 12))

# ---- Assistant status card ----

status_card = ctk.CTkFrame(right_panel, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
status_card.pack(fill="x", padx=14, pady=(0, 10))
ctk.CTkLabel(status_card, text="Assistant Status", font=(FONT_FAMILY, 14, "bold"), anchor="w").pack(fill="x", padx=12, pady=(12, 6))

# Registry of status value labels so the card can be refreshed live (e.g. when
# the user changes Mode / Voice / Privacy), instead of staying stale until restart.
_status_value_labels = {}


def _status_line(parent, label, value, color=TEXT_MUTED):
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=12, pady=2)
    ctk.CTkLabel(row, text=label, font=(FONT_FAMILY, 11), text_color=TEXT_MUTED, anchor="w").pack(side="left")
    value_lbl = ctk.CTkLabel(row, text=value, font=(FONT_FAMILY, 11, "bold"), text_color=color, anchor="e")
    value_lbl.pack(side="right")
    _status_value_labels[label] = value_lbl  # store for later live updates


_status_line(status_card, "Mode", dashboard_data.get("assistant_mode", "General"), ACCENT)
_status_line(status_card, "Voice", "On" if app_settings.get("voice_enabled", True) else "Off", SUCCESS if app_settings.get("voice_enabled", True) else DANGER)
_status_line(status_card, "Privacy", "On" if _is_privacy_mode_on() else "Off", DANGER if _is_privacy_mode_on() else SUCCESS)
_status_line(status_card, "Vision", "Ready" if _gemini_ready else "Setup needed", SUCCESS if _gemini_ready else DANGER)
_status_line(status_card, "OCR", "Ready" if _ocr_ready else "Setup needed", SUCCESS if _ocr_ready else DANGER)
_status_line(status_card, "Memory", f"{len(get_saved_facts())} facts", TEXT_MAIN)


def refresh_assistant_status():
    """Live-update the right-sidebar status card so it reflects the current
    Mode / Voice / Privacy instantly (no app restart needed). Safe to call
    any time after startup."""
    if _status_value_labels.get("Mode") is not None:
        _status_value_labels["Mode"].configure(text=dashboard_data.get("assistant_mode", "General"))
    if _status_value_labels.get("Voice") is not None:
        _status_value_labels["Voice"].configure(
            text="On" if app_settings.get("voice_enabled", True) else "Off",
            text_color=SUCCESS if app_settings.get("voice_enabled", True) else DANGER,
        )
    if _status_value_labels.get("Privacy") is not None:
        _status_value_labels["Privacy"].configure(
            text="On" if _is_privacy_mode_on() else "Off",
            text_color=DANGER if _is_privacy_mode_on() else SUCCESS,
        )
    if _status_value_labels.get("Memory") is not None:
        _status_value_labels["Memory"].configure(text=f"{len(get_saved_facts())} facts")

# ---- Memory preview card ----

memory_card = ctk.CTkFrame(right_panel, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
memory_card.pack(fill="x", padx=14, pady=(0, 10))

memory_header = ctk.CTkFrame(memory_card, fg_color="transparent")
memory_header.pack(fill="x", padx=12, pady=(12, 4))

ctk.CTkLabel(memory_header, text="\U0001F4CB Memory", font=("Arial", 14, "bold")).pack(side="left")
_memory_view_all = ctk.CTkButton(
    memory_header, text="View all", width=50, height=22, font=("Arial", 10),
    fg_color="transparent", text_color=ACCENT, hover_color=CARD_COLOR_SOFT, command=open_memory_manager
)
_memory_view_all.pack(side="right")
add_tooltip(_memory_view_all, "Open the full memory manager")

memory_preview_frame = ctk.CTkFrame(memory_card, fg_color=CARD_COLOR_SOFT, corner_radius=PANEL_RADIUS)
memory_preview_frame.pack(fill="x", padx=12, pady=(4, 12))

memory_preview_label = ctk.CTkLabel(
    memory_preview_frame, text="No saved memory yet.", font=("Arial", 11),
    text_color=TEXT_MUTED, wraplength=220, justify="left", anchor="w"
)
memory_preview_label.pack(fill="x", padx=10, pady=10)


def refresh_memory_preview():
    facts = get_saved_facts()
    if not facts:
        memory_preview_label.configure(text="No saved memory yet.")
        return
    last_key = list(facts.keys())[-1]
    memory_preview_label.configure(text=f"{last_key}: {facts[last_key]}")


refresh_memory_preview()

# ---- Today's Goals card ----

goals_card = ctk.CTkFrame(right_panel, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
goals_card.pack(fill="x", padx=14, pady=(0, 10))

goals_header = ctk.CTkFrame(goals_card, fg_color="transparent")
goals_header.pack(fill="x", padx=12, pady=(12, 4))

ctk.CTkLabel(goals_header, text="\U0001F3AF Today's Goals", font=("Arial", 14, "bold")).pack(side="left")
ctk.CTkButton(
    goals_header, text="Edit", width=40, height=22, font=("Arial", 10),
    fg_color="transparent", text_color=ACCENT, hover_color=CARD_COLOR_SOFT, command=lambda: show_page("goals")
).pack(side="right")

goals_list_frame = ctk.CTkFrame(goals_card, fg_color="transparent")
goals_list_frame.pack(fill="x", padx=12, pady=(2, 6))

goals_progress_bar = ctk.CTkProgressBar(goals_card, width=220)
goals_progress_bar.pack(padx=12, pady=(4, 2))

goals_progress_label = ctk.CTkLabel(goals_card, text="0 / 0 Completed", font=("Arial", 11), text_color=TEXT_MUTED)
goals_progress_label.pack(padx=12, pady=(0, 12))


def refresh_goals_preview():
    for w in goals_list_frame.winfo_children():
        w.destroy()

    items = dashboard_data["goals"]
    done_count = sum(1 for g in items if g.get("done"))

    for item in items[:4]:
        row = ctk.CTkFrame(goals_list_frame, fg_color="transparent")
        row.pack(fill="x", pady=2)
        var = tk.BooleanVar(value=item.get("done", False))
        idx = items.index(item)

        def on_toggle(i=idx, v=var):
            dashboard_data["goals"][i]["done"] = v.get()
            save_dashboard_data()
            refresh_goals_preview()

        cb = ctk.CTkCheckBox(row, text=item["text"], variable=var, command=on_toggle, font=("Arial", 12))
        cb.pack(side="left", fill="x", expand=True)

    total = max(len(items), 1)
    goals_progress_bar.set(done_count / total)
    goals_progress_label.configure(text=f"{done_count} / {len(items)} Completed")


refresh_goals_preview()

# ---- Focus Streak card ----

streak_card = ctk.CTkFrame(right_panel, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
streak_card.pack(fill="x", padx=14, pady=(0, 10))

ctk.CTkLabel(streak_card, text="Focus Streak", font=("Arial", 14, "bold"), anchor="w").pack(fill="x", padx=12, pady=(12, 2))

streak_count_label = ctk.CTkLabel(streak_card, text="\U0001F525 0 days", font=("Arial", 20, "bold"), anchor="w")
streak_count_label.pack(fill="x", padx=12, pady=(0, 4))

streak_canvas = tk.Canvas(streak_card, width=240, height=95, bg=CARD_COLOR, highlightthickness=0)
streak_canvas.pack(padx=12, pady=(0, 12))


def compute_streak():
    return current_streak_count()


def draw_streak():
    streak_canvas.delete("all")
    today = date.today()
    bar_w = 20
    gap = 14
    x = 10
    for i in range(7):
        d = today - timedelta(days=6 - i)
        active = str(d) in dashboard_data["streak_days"]
        h = 55 if active else 12
        color = ACCENT if active else "#2a2a40"
        streak_canvas.create_rectangle(x, 65 - h, x + bar_w, 65, fill=color, outline="")
        streak_canvas.create_text(x + bar_w / 2, 78, text=d.strftime("%a")[0], fill=TEXT_MUTED, font=("Arial", 9))
        x += bar_w + gap
    streak_count_label.configure(text=f"\U0001F525 {compute_streak()} days")


draw_streak()

# ---- Today's Focus card ----

focus_card = ctk.CTkFrame(right_panel, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
focus_card.pack(fill="x", padx=14, pady=(0, 10))

ctk.CTkLabel(focus_card, text="Today's Focus", font=("Arial", 14, "bold"), anchor="w").pack(fill="x", padx=12, pady=(12, 4))

focus_ring_canvas = tk.Canvas(focus_card, width=160, height=160, bg=CARD_COLOR, highlightthickness=0)
focus_ring_canvas.pack(pady=(0, 8))


def draw_focus_ring():
    focus_ring_canvas.delete("all")
    size = 150
    goal = max(dashboard_data["focus_goal_minutes"], 1)
    mins = dashboard_data["focus_minutes_today"]
    percent = min(mins / goal, 1.0)

    focus_ring_canvas.create_oval(10, 10, size - 10, size - 10, outline="#2a2a40", width=12)
    extent = 359.9 * percent
    if extent > 0:
        focus_ring_canvas.create_arc(
            10, 10, size - 10, size - 10, start=90, extent=-extent,
            style="arc", outline=ACCENT, width=12
        )
    focus_ring_canvas.create_text(size / 2, size / 2 - 10, text=f"{int(percent * 100)}%", fill=TEXT_MAIN, font=("Arial", 22, "bold"))
    hh, mm = divmod(mins, 60)
    gh = goal // 60
    focus_ring_canvas.create_text(size / 2, size / 2 + 18, text=f"{hh}h {mm}m / {gh}h", fill=TEXT_MUTED, font=("Arial", 10))


draw_focus_ring()


def refresh_focus_ui():
    draw_focus_ring()
    draw_streak()


def focus_tick():
    global focus_running
    if not focus_running:
        return
    dashboard_data["focus_minutes_today"] += 1
    save_dashboard_data()
    # Also log one minute to the active subject session log (study data)
    try:
        nova_study.record_session(nova_study.get_active_subject(), 1)
        refresh_study_card()
    except Exception:
        pass
    refresh_focus_ui()
    app.after(60000, focus_tick)


def toggle_focus_timer():
    global focus_running
    focus_running = not focus_running
    label = "\u23F8 Pause Focus" if focus_running else "\u25B6 Start Focus"
    focus_toggle_button.configure(text=label)
    if quick_focus_button is not None:
        quick_focus_button.configure(text="\u23F8 Timer" if focus_running else "\u23F1 Timer")
    if focus_running:
        focus_tick()


focus_toggle_button = ctk.CTkButton(
    focus_card, text="\u25B6 Start Focus", height=34, fg_color=ACCENT, hover_color=ACCENT_HOVER,
    command=toggle_focus_timer
)
focus_toggle_button.pack(fill="x", padx=12, pady=(0, 12))
add_tooltip(focus_toggle_button, "Starts a running timer that fills the ring above")

# ---- Study Session (subject-aware) card ----------------------------------
study_session_card = ctk.CTkFrame(right_panel, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
study_session_card.pack(fill="x", padx=14, pady=(0, 10))

ctk.CTkLabel(study_session_card, text="Study Session", font=("Arial", 14, "bold"),
             anchor="w").pack(fill="x", padx=12, pady=(12, 4))

study_active_subject_label = ctk.CTkLabel(study_session_card, text="", font=("Arial", 16, "bold"),
                                          anchor="w", text_color=TEXT_MAIN)
study_active_subject_label.pack(fill="x", padx=12)

study_session_summary = ctk.CTkLabel(study_session_card, text="", font=("Arial", 11),
                                     text_color=TEXT_MUTED, anchor="w", justify="left",
                                     wraplength=250)
study_session_summary.pack(fill="x", padx=12, pady=(2, 6))

study_session_btns = ctk.CTkFrame(study_session_card, fg_color="transparent")
study_session_btns.pack(fill="x", padx=12, pady=(0, 4))


def _subject_timer_btn(subject_key, minutes, text):
    ctk.CTkButton(
        study_session_btns, text=text, height=30,
        fg_color=nova_study.subject_color(subject_key), hover_color=ACCENT_SOFT,
        text_color="white", font=("Arial", 11),
        corner_radius=PANEL_RADIUS,
        command=lambda: start_subject_timer(subject_key, minutes)
    ).pack(side="left", padx=3, pady=(0, 4), expand=True, fill="x")


_study_session_btn_row2 = ctk.CTkFrame(study_session_card, fg_color="transparent")
_study_session_btn_row2.pack(fill="x", padx=12, pady=(0, 12))

ctk.CTkButton(_study_session_btn_row2, text="☕ 5-min break", height=28,
              fg_color=CARD_COLOR_SOFT, hover_color=ACCENT_SOFT, text_color=TEXT_MAIN,
              font=("Arial", 10), corner_radius=PANEL_RADIUS,
              command=lambda: start_break(5)).pack(side="left", padx=3, expand=True, fill="x")


def refresh_study_card():
    """Live-refresh the right-panel Study Session card."""
    active = nova_study.get_active_subject()
    info = nova_study.SUBJECTS.get(active, {})
    study_active_subject_label.configure(
        text=f"{info.get('icon', '')}  {info.get('name', 'Study')}"
    )
    mins = nova_study.minutes_by_subject_today()
    total = nova_study.total_focus_minutes_today()
    parts = "  ·  ".join(
        f"{nova_study.SUBJECTS.get(k, {}).get('icon', '')} {v}m"
        for k, v in mins.items() if v > 0
    )
    study_session_summary.configure(text=f"Today: {total // 60}h {total % 60}m\n{parts}")


def start_subject_timer(subject_key, minutes):
    """Start a subject-aware focus session (reuses the existing focus timer)."""
    nova_study.set_active_subject(subject_key)
    _highlight_subject_buttons()
    render_study_dashboard()
    try:
        if minutes:
            start_focus_session(minutes)
    except Exception as exc:
        log.error("start_subject_timer failed: %s", exc)
    refresh_study_card()


# Build the per-subject timer buttons (uses default minutes per subject slot)
subject_timer_defaults = {"physics": 90, "chemistry": 90, "maths": 90,
                          "english": 45, "mn": 60}
for _sk, _info in nova_study.SUBJECTS.items():
    _subject_timer_btn(_sk, subject_timer_defaults.get(_sk, 50), f"{_info['icon']} {_info['name'][:1]}")

refresh_study_card()

# Wire the command-layer callbacks so slash commands (e.g. /timer, /log-error)
# trigger the live timer + dashboard refresh from anywhere in the app.
set_study_callbacks(
    timer_cb=start_subject_timer,
    refresh_cb=lambda: (render_study_dashboard(), _highlight_subject_buttons(), refresh_study_card()),
)



# ---- Quick Access grid ----

quick_card = ctk.CTkFrame(right_panel, fg_color=CARD_COLOR, corner_radius=PANEL_RADIUS)
quick_card.pack(fill="x", padx=14, pady=(0, 16))

ctk.CTkLabel(quick_card, text="Quick Access", font=("Arial", 14, "bold"), anchor="w").pack(fill="x", padx=12, pady=(12, 6))

quick_grid = ctk.CTkFrame(quick_card, fg_color="transparent")
quick_grid.pack(fill="x", padx=12, pady=(0, 12))
for c in range(3):
    quick_grid.grid_columnconfigure(c, weight=1)

quick_focus_button = None

quick_actions_panel = [
    ("\u23F1\nTimer", toggle_focus_timer, True, "Start/pause today's focus timer"),
    ("\U0001F4DD\nNotes", lambda: show_page("notes"), False, "Open the Notes page"),
    ("\u2705\nTasks", lambda: show_page("tasks"), False, "Open the Tasks page"),
    ("\U0001F9EE\nCalculator", open_calculator, False, "Opens your system calculator"),
    ("\U0001F310\nTranslator", lambda: send_prefilled("Translate this: "), False, "Prefills a translate prompt in chat"),
    ("\u270F\uFE0F\nAI Writer", lambda: send_prefilled("Write something about "), False, "Prefills a writing prompt in chat"),
]

for i, (label, cmd, is_timer, tip) in enumerate(quick_actions_panel):
    b = ctk.CTkButton(
        quick_grid, text=label, height=56, fg_color=CARD_COLOR_SOFT, hover_color=ACCENT_SOFT,
        text_color=TEXT_MAIN, font=("Arial", 11), command=cmd
    )
    b.grid(row=i // 3, column=i % 3, padx=4, pady=4, sticky="ew")
    add_tooltip(b, tip)
    if is_timer:
        quick_focus_button = b

# ==========================================
# APPLY STARTUP VOICE STATE + STATUS BAR
# ==========================================

set_voice_enabled(app_settings.get("voice_enabled", True), save=False)
refresh_status()

# ==========================================
# REQUIRE LICENSE ON STARTUP (HARD LOCK) - unchanged
# ==========================================

if not is_license_valid():
    app.withdraw()
    app.after(300, lambda: open_license_window(required=True))
else:
    app.after(600, open_onboarding)

# ==========================================
# STARTUP SELF-CHECK (silent when healthy)
# ~6s after boot, run the nova_doctor health check in a background
# thread (never blocks the UI). A healthy Nova says NOTHING; only
# FAIL results surface as a notification + chat bubble, with a hint
# that "doctor" shows the full report. UI updates are marshalled back
# through app.after(0, ...) - the same safe pattern used elsewhere.
# ==========================================

def _run_startup_doctor():
    def _worker():
        try:
            from nova_doctor import run_doctor
            results = run_doctor(include_mic=False)
        except Exception:
            log.exception("startup doctor failed")
            return
        failures = [r for r in results if r.get("status") == "fail"]
        if not failures:
            return  # healthy - stay quiet
        detail = "\n".join(
            f"\u2022 {r['name']}: {r['detail']}" for r in failures
        )

        def _report():
            try:
                short = detail[:180]
                add_notification_item("Nova self-check found problems", short)
                send_notification("Nova self-check", short)
                add_nova_bubble(
                    "\u26a0 Self-check found problems:\n" + detail +
                    "\nType 'doctor' for the full report.",
                    save=False,
                )
            except Exception:
                log.exception("startup doctor UI report failed")

        app.after(0, _report)

    threading.Thread(target=_worker, daemon=True, name="startup-doctor").start()


app.after(6000, _run_startup_doctor)

# ==========================================
# RUN APP
# ==========================================

check_reminders()
setup_hotkey(open_listening_window)
app.mainloop()
