import os
import json
import socket
import time
from datetime import datetime

FACTS_FILE = os.path.join(os.path.expanduser("~"), ".nova", "offline_facts.json")


def _is_actually_offline():
    """Try to reach a public DNS to check real internet connectivity."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2).close()
        return False
    except Exception:
        return True


def check_offline_status():
    """Check real internet connectivity."""
    offline = _is_actually_offline()
    return {
        "success": True,
        "feature": "offline_first",
        "offline": offline,
        "message": ("🌐 Nova is ONLINE - internet available"
                    if not offline else "📴 Nova is OFFLINE - no internet detected"),
        "check_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _load_facts():
    try:
        with open(FACTS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_facts(facts):
    os.makedirs(os.path.dirname(FACTS_FILE), exist_ok=True)
    with open(FACTS_FILE, "w") as f:
        json.dump(facts, f, indent=2)


def store_user_fact(key, value):
    """Store a fact that Nova remembers even when offline."""
    facts = _load_facts()
    facts[key] = {"value": value, "stored_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    _save_facts(facts)
    return {
        "success": True,
        "feature": "offline_first",
        "key": key, "value": value,
        "message": f"✅ Fact saved for offline use: '{key}'",
    }


def get_offline_response(category):
    """Return a cached/offline-available response for a category."""
    categories = {
        "greeting": "Namaste! Nova offline mode mein bhi aapke saath hai. 🙏",
        "motivation": "Aap acche kar rahe ho - aage badhte raho! 💪",
        "study": "Study tip: Focus timer use karo - 25 min padho, 5 min break lo. 📚",
        "health": "Remember to drink water and take short walks. 💧",
        "default": "Offline mode: Nova internet ke bina bhi basics help karta hai.",
    }
    response = categories.get(category, categories["default"])
    return {
        "success": True,
        "feature": "offline_first",
        "category": category,
        "response": response,
        "offline": True,
    }


__version__ = "2.0.0"
__all__ = ["check_offline_status", "get_offline_response", "store_user_fact"]
