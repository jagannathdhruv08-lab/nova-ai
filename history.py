import json
import os
from pathlib import Path
from datetime import datetime

# ==========================================
# CHAT HISTORY FEATURE
# ==========================================
#
# Yeh file kya karti hai:
#   - Har conversation history.json mein save hoti hai
#   - Date aur time bhi save hota hai
#   - "show history" command se last 5 baatein dikha sakta hai
#   - "clear history" se sab delete ho jaata hai
#
# Koi extra library install nahi karni — Python mein sab kuch pehle se hai!
# ==========================================

HISTORY_FILE = Path(__file__).with_name("history.json")


# ==========================================
# FILE SETUP
# ==========================================

def _load_history():
    """
    history.json padhta hai.
    Agar file nahi hai toh khali list return karta hai.
    """
    if not os.path.exists(HISTORY_FILE):
        return []

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_history(history):
    """history.json mein save karta hai."""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4, ensure_ascii=False)


# ==========================================
# SAVE ONE MESSAGE
# ==========================================

def save_message(user_text, nova_reply):
    """
    Ek conversation entry save karta hai.
    gui.py ke send_message() se call karo.

    Example:
        save_message("open youtube", "Opening YouTube")
    """
    history = _load_history()

    entry = {
        "time": datetime.now().strftime("%d %b %Y, %I:%M %p"),  # e.g. "23 Jun 2026, 04:30 PM"
        "you": user_text,
        "nova": nova_reply
    }

    history.append(entry)

    # Sirf last 150 conversations rakhte hain — file zyada badi nahi hogi
    if len(history) > 150:
        history = history[-150:]

    _save_history(history)


# ==========================================
# SHOW LAST FEW MESSAGES
# ==========================================

def get_recent_history(count=5):
    """
    Last N conversations return karta hai as a readable string.
    Nova bol sakti hai ya chat box mein dikha sakte ho.
    """
    history = _load_history()

    if not history:
        return "Koi history nahi mili abhi tak."

    # Last 'count' entries lo
    recent = history[-count:]

    lines = ["Yeh rahi last conversations:\n"]

    for entry in recent:
        lines.append(f"  [{entry['time']}]")
        lines.append(f"  You: {entry['you']}")
        lines.append(f"  Nova: {entry['nova']}")
        lines.append("")

    return "\n".join(lines)


# ==========================================
# CLEAR HISTORY
# ==========================================

def clear_history():
    """Saari history delete karta hai."""
    _save_history([])
    return "Chat history clear ho gayi."


# ==========================================
# COMMAND HANDLER
# ==========================================

def handle_history_command(command):
    """
    commands.py se call hoga.
    Supported commands:
      "show history"
      "clear history"
    """
    if "clear history" in command:
        return clear_history()

    if "show history" in command:
        return get_recent_history(count=5)

    return None
