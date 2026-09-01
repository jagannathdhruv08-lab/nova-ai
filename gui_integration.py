"""
gui_integration.py — drop-in patches for the existing gui.py (2,449 lines).

How to apply (do this AFTER you have already replaced the `print(user_message)`
line at gui.py:1296 per the previous patch file):

  1. Add the imports below to the very top of gui.py (after `import os`).
  2. Add the three helper functions (confirm_destructive, forget_everything,
     privacy_mode_toggle) anywhere after the existing helper functions.
  3. Modify `send_message` as shown in the SEND_MESSAGE_PATCH block.
  4. Add the privacy-mode toggle to the sidebar or top bar (see the
     SETTINGS_UI_PATCH block).
  5. Add a "Forget me" button in your existing Settings window (see the
     SETTINGS_UI_PATCH block).

That's it — no other file needs to change. The agent module is loaded
lazily so the app still runs even if agent.py is missing.
"""

# ===========================================================================
# 1. EXTRA IMPORTS — add near the top of gui.py, after `import os`
# ===========================================================================
import logging

log = logging.getLogger("nova.gui_integration")

try:
    import agent  # type: ignore
    _AGENT_AVAILABLE = True
except Exception:
    agent = None
    _AGENT_AVAILABLE = False

try:
    from brain import _strip_emojis, route_to_agent
    _BRAIN_AVAILABLE = True
except Exception:
    route_to_agent = None
    _BRAIN_AVAILABLE = False

from settings import save_settings as _save_app_settings


# ===========================================================================
# 2. CONFIRMATION DIALOG — used for shutdown, restart, agent destructive ops
# ===========================================================================
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


# ===========================================================================
# 3. PRIVACY MODE — when ON, the agent refuses ALL actions and the LLM
#    still answers chat, but no system action is executed.
# ===========================================================================
def _is_privacy_mode_on() -> bool:
    return bool(app_settings.get("privacy_mode", False))


def set_privacy_mode(enabled: bool):
    app_settings["privacy_mode"] = bool(enabled)
    _save_app_settings(app_settings)
    state = "ON" if enabled else "OFF"
    add_nova_bubble(f"🔒 Privacy mode {state}. "
                    f"System actions are {'blocked' if enabled else 'allowed'}.")


def toggle_privacy_mode():
    set_privacy_mode(not _is_privacy_mode_on())


# ===========================================================================
# 4. FORGET ME — wipe all local data after explicit double confirmation
# ===========================================================================
def forget_everything():
    if not confirm_destructive(
        "Delete ALL Nova data on this computer?\n\n"
        "This will remove:\n"
        "  • saved memory (name, color, custom facts)\n"
        "  • chat history (home + coach)\n"
        "  • journal and notes\n"
        "  • nutrition profile\n"
        "  • focus / streak data\n"
        "  • license\n\n"
        "This action CANNOT be undone."
    ):
        return "Cancelled."

    if not confirm_destructive(
        "Are you absolutely sure? Type yes by clicking Confirm one more time."
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
        _save_app_settings({"theme": "Dark", "language": "English",
                            "voice_enabled": True, "privacy_mode": False})
    except Exception as exc:
        log.warning("settings reset failed: %s", exc)

    add_nova_bubble("🧹 Sab data delete ho gaya. App restart kar lo.")


# ===========================================================================
# 5. SEND_MESSAGE_PATCH — REPLACE the existing send_message() with this.
#    Find the existing function (around line 1291) and swap it out.
# ===========================================================================
def send_message():
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

    try:
        # 1) Deterministic router (the patched commands.execute_command
        #    handles its own confirm_destructive for shutdown / restart).
        needs_destructive_confirm = any(
            t in clean_message.lower() for t in ("shutdown pc", "restart pc")
        )
        destructive_ok = (
            confirm_destructive(clean_message) if needs_destructive_confirm else False
        )
        response = execute_command(clean_message, confirm_destructive=destructive_ok)

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
                elif _BRAIN_AVAILABLE and _AGENT_AVAILABLE and any(
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
                    context_prompt = build_recent_context() + f"User ka naya message: {clean_message}"
                    response = ask_nova(context_prompt)

        if not isinstance(response, str) or response.strip() == "":
            response = "Sorry, something went wrong. Please try again."
    except Exception as e:
        log.error("send_message error: %s: %s", type(e).__name__, e)
        response = "Sorry, something went wrong. Please try again."

    lower_message = clean_message.lower()
    if "stop speaking" in lower_message:
        set_voice_enabled(False)
    elif "start speaking" in lower_message:
        set_voice_enabled(True)

    styled_response = add_emojis(response)
    typewriter_into_bubble(thinking_bubble, styled_response)
    persist_message("nova", styled_response, thinking_time_str)
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


# ===========================================================================
# 6. SETTINGS_UI_PATCH — add a Privacy toggle and a Forget-me button
#    inside the existing open_settings() / open_settings_window() function.
#    If you don't have a settings window yet, drop this whole block into
#    a new helper that opens a CTkToplevel.
# ===========================================================================
def open_settings_window():
    win = ctk.CTkToplevel(app)
    win.title("Settings")
    win.geometry("420x520")
    win.configure(fg_color=BG_COLOR)
    bring_window_to_front(win)

    ctk.CTkLabel(win, text="Settings", font=("Arial", 22, "bold")).pack(pady=(20, 10))

    # ---- Theme ----
    ctk.CTkLabel(win, text="Theme", anchor="w", font=("Arial", 13)).pack(fill="x", padx=24, pady=(8, 2))
    theme_var = ctk.StringVar(value=app_settings.get("theme", "Dark"))
    ctk.CTkSegmentedButton(
        win, values=["Dark", "Light"], variable=theme_var,
        command=lambda v: apply_theme(v),
    ).pack(fill="x", padx=24)

    # ---- Language ----
    ctk.CTkLabel(win, text="Language", anchor="w", font=("Arial", 13)).pack(fill="x", padx=24, pady=(14, 2))
    lang_var = ctk.StringVar(value=app_settings.get("language", "English"))
    ctk.CTkSegmentedButton(
        win, values=["English", "Hindi", "Hinglish"], variable=lang_var,
        command=lambda v: save_language(v),
    ).pack(fill="x", padx=24)

    # ---- Voice ----
    voice_var = ctk.BooleanVar(value=app_settings.get("voice_enabled", True))
    ctk.CTkCheckBox(
        win, text="Voice replies", variable=voice_var,
        command=lambda: set_voice_enabled(voice_var.get()),
    ).pack(anchor="w", padx=24, pady=(16, 4))

    # ---- Privacy mode ----
    privacy_var = ctk.BooleanVar(value=_is_privacy_mode_on())
    ctk.CTkCheckBox(
        win,
        text="🔒 Privacy mode (block all system / file actions)",
        variable=privacy_var,
        command=lambda: set_privacy_mode(privacy_var.get()),
    ).pack(anchor="w", padx=24, pady=(10, 4))
    ctk.CTkLabel(
        win,
        text="When ON, Nova still chats but will not touch files, "
             "folders, or launch apps. Useful when sharing your screen.",
        font=("Arial", 10), text_color=TEXT_MUTED, wraplength=360, justify="left",
    ).pack(anchor="w", padx=36, pady=(0, 8))

    # ---- Forget me ----
    ctk.CTkButton(
        win, text="🧹 Forget me (delete all Nova data)",
        fg_color=DANGER, hover_color=DANGER_HOVER,
        command=forget_everything,
    ).pack(fill="x", padx=24, pady=(24, 8))

    ctk.CTkButton(
        win, text="Close", command=win.destroy,
        fg_color=CARD_COLOR, hover_color=CARD_COLOR_SOFT,
    ).pack(fill="x", padx=24, pady=(0, 18))


# ===========================================================================
# 7. SIDEBAR TOGGLE — quick access to privacy mode from the main window.
#    Drop this anywhere after the sidebar is built.
# ===========================================================================
def add_privacy_chip(sidebar):
    chip = ctk.CTkButton(
        sidebar, text="🔒 Privacy: OFF", height=30, font=("Arial", 11),
        fg_color=CARD_COLOR, hover_color=ACCENT_SOFT,
        command=toggle_privacy_mode,
    )
    chip.pack(fill="x", padx=14, pady=(0, 8))

    def _refresh_chip():
        chip.configure(
            text="🔒 Privacy: ON" if _is_privacy_mode_on() else "🔒 Privacy: OFF",
            fg_color=ACCENT_SOFT if _is_privacy_mode_on() else CARD_COLOR,
        )

    chip.configure(command=lambda: (toggle_privacy_mode(), _refresh_chip()))
    _refresh_chip()
