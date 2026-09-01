# ==========================================
# NOVA CLIPBOARD MANAGER — Copy History + Quick Access
# ==========================================
import os
import json
import time

HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".nova", "clipboard_history.json")
MAX_HISTORY = 20


def _load_history():
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_history(history):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def get_clipboard():
    """Get the current clipboard content."""
    try:
        import pyperclip
        text = pyperclip.paste()
        return {
            "success": True,
            "feature": "clipboard_manager",
            "clipboard": text,
            "char_count": len(text),
            "message": f"📋 Clipboard: '{text[:60]}{'...' if len(text) > 60 else ''}'",
        }
    except Exception as e:
        return {
            "success": False,
            "feature": "clipboard_manager",
            "error": str(e),
            "message": f"Clipboard read failed: {str(e)}",
        }


def set_clipboard(text):
    """Set the clipboard content and save to history."""
    try:
        import pyperclip
        pyperclip.copy(str(text))

        # Save to history
        history = _load_history()
        entry = {
            "text": str(text),
            "copied_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        history.insert(0, entry)
        history = history[:MAX_HISTORY]
        _save_history(history)

        return {
            "success": True,
            "feature": "clipboard_manager",
            "message": f"📋 Copied: '{str(text)[:40]}{'...' if len(str(text)) > 40 else ''}'",
        }
    except Exception as e:
        return {
            "success": False,
            "feature": "clipboard_manager",
            "error": str(e),
            "message": f"Clipboard write failed: {str(e)}",
        }


def get_clipboard_history():
    """Get recent clipboard history."""
    history = _load_history()
    if not history:
        return {
            "success": True,
            "feature": "clipboard_manager",
            "history": [],
            "message": "📭 Clipboard history is empty",
        }
    return {
        "success": True,
        "feature": "clipboard_manager",
        "history": history,
        "count": len(history),
        "message": f"📚 {len(history)} clipboard item(s) in history",
    }


__version__ = "1.0.0"
__all__ = ["get_clipboard", "set_clipboard", "get_clipboard_history"]
