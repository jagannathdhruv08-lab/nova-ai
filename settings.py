import json
from pathlib import Path



SETTINGS_FILE = Path(__file__).with_name("settings.json")

DEFAULT_SETTINGS = {
    "language": "English",
    "theme": "Dark",
    "voice_enabled": True,
    "privacy_mode": False,
    "allowed_folders": [],
}


def load_settings():
    if not SETTINGS_FILE.exists():
        return DEFAULT_SETTINGS.copy()

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return DEFAULT_SETTINGS.copy()

    settings = DEFAULT_SETTINGS.copy()
    if isinstance(data, dict):
        settings.update(data)
    return settings


def save_settings(settings):
    data = DEFAULT_SETTINGS.copy()
    data.update(settings)

    with open(SETTINGS_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

    return data


def update_setting(key, value):
    settings = load_settings()
    settings[key] = value
    return save_settings(settings)