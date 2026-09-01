# ==========================================
# NOVA AI - DOCTOR (self-diagnostic health check)
# One command ("doctor" / "health check") that inspects Nova's own
# health: Python version, .env API keys (names only, NEVER values),
# required/optional packages, OCR, internet, data-file integrity,
# write access and git repo state.
#
# Design rules:
#   1. run_doctor() NEVER raises - a broken check becomes a "fail"
#      result, not an exception.
#   2. Every check returns {"name", "status", "detail"} where status
#      is one of "ok" / "warn" / "fail".
#   3. Package presence is probed with importlib.util.find_spec()
#      (no module side effects, fast). Secret VALUES are never read
#      into the report - only "is this key set?".
#   4. Internet being down is a "warn", not a "fail" - Nova has a
#      real offline fast-path.
# ==========================================

import importlib.util
import json
import os
import platform
import socket
import sys
import tempfile

# .env lives next to the source files (not the CWD, which changes
# depending on how Nova is launched) - same convention as nova_vision.py.
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

# Keys Nova knows about. Only NAMES are ever reported.
KNOWN_API_KEYS = (
    "GROQ_API_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
    "NEWS_API_KEY",
    "WEATHER_API_KEY",
)

# Packages Nova needs to boot at all (fail when missing).
REQUIRED_PACKAGES = (
    "PIL",            # pillow - images
    "requests",       # weather / news / generic HTTP
    "dotenv",         # python-dotenv - .env loading
    "openai",         # OpenAI-compatible client (Groq chain)
    "httpx",          # async HTTP used by openai client
    "customtkinter",  # the GUI itself
    "pygame",         # TTS audio playback
    "edge_tts",       # text-to-speech
    "speech_recognition",  # mic listening (PyPI package: SpeechRecognition)
    "cryptography",   # secure_store encrypted memory
)

# Nice-to-have packages - features degrade gracefully without them.
OPTIONAL_PACKAGES = (
    ("google.genai", "pip install google-genai"),   # vision / meal analysis
    ("pytesseract", "pip install pytesseract + Tesseract-OCR"),  # OCR
    ("cv2", "pip install opencv-python"),           # camera features
    ("pypdf", "pip install pypdf"),                 # PDF learning / previews
    ("sounddevice", "pip install sounddevice"),     # mic level meter
    ("keyboard", "pip install keyboard"),           # hotkey summon
    ("psutil", "pip install psutil"),               # system stats
    ("pystray", "pip install pystray"),             # system-tray launcher
    ("plyer", "pip install plyer"),                 # desktop notifications
)

# Runtime JSON data files Nova reads/writes (checked for corruption).
DATA_FILE_NAMES = (
    "memory.json",
    "history.json",
    "settings.json",
    "nova_dashboard_data.json",
    "nova_coach_data.json",
    "nova_nutrition_data.json",
    "nova_srs_cards.json",
    "nova_exams.json",
    "nova_knowledge.json",
    "nova_study_log.json",
)

VALID_STATUSES = ("ok", "warn", "fail")

_STATUS_GLYPH = {"ok": "[ OK ]", "warn": "[WARN]", "fail": "[FAIL]"}

def _result(name, status, detail=""):
    return {"name": name, "status": status, "detail": detail}


# ---------------------------------------------------------------------------
# 1. Individual checks
# ---------------------------------------------------------------------------

def _python_check():
    version = sys.version_info
    text = f"Python {version.major}.{version.minor}.{version.micro} ({platform.system()})"
    if version >= (3, 9):
        return _result("Python version", "ok", text)
    return _result("Python version", "fail", text + " - Nova needs 3.9+")


def _read_env_dict():
    """Naive KEY=VALUE parser (same tolerance as api_key_setup.py)."""
    values = {}
    if not os.path.exists(ENV_PATH):
        return values
    try:
        with open(ENV_PATH, "r", encoding="utf-8", errors="ignore") as file:
            for line in file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip("'\"")
    except Exception:
        return values
    return values


def _env_keys_check():
    if not os.path.exists(ENV_PATH):
        return _result(
            "Environment (.env)", "warn",
            f"{ENV_PATH} not found - run api_key_setup.py to create it",
        )
    values = _read_env_dict()
    configured = [k for k in KNOWN_API_KEYS if values.get(k)]
    missing = [k for k in KNOWN_API_KEYS if not values.get(k)]
    if configured and not missing:
        return _result(
            "Environment (.env)", "ok",
            f"all {len(configured)} known keys are set (values never shown)",
        )
    if configured:
        return _result(
            "Environment (.env)", "warn",
            f"set: {', '.join(configured)}; missing: {', '.join(missing)}",
        )
    return _result(
        "Environment (.env)", "fail",
        f"file exists but none of the known keys are set: {', '.join(KNOWN_API_KEYS)}",
    )


def _imports_check():
    missing = []
    for spec in REQUIRED_PACKAGES:
        try:
            if importlib.util.find_spec(spec) is None:
                missing.append(spec)
        except Exception:  # broken package metadata - treat as missing
            missing.append(spec)
    if missing:
        return _result(
            "Core packages", "fail",
            "missing: " + ", ".join(missing) + " (pip install -r requirements.txt)",
        )
    optional_missing = []
    for spec, hint in OPTIONAL_PACKAGES:
        try:
            if importlib.util.find_spec(spec) is None:
                optional_missing.append(f"{spec} ({hint})")
        except Exception:
            optional_missing.append(f"{spec} ({hint})")
    if optional_missing:
        return _result(
            "Core packages", "warn",
            "all required present; optional missing: " + ", ".join(optional_missing),
        )
    return _result(
        "Core packages", "ok",
        f"all {len(REQUIRED_PACKAGES)} required + {len(OPTIONAL_PACKAGES)} optional present",
    )


def _ocr_check():
    if importlib.util.find_spec("pytesseract") is None:
        return _result(
            "OCR (Tesseract)", "warn",
            "pytesseract not installed - screenshots fall back to Gemini vision",
        )
    try:
        import pytesseract  # type: ignore
        version = str(pytesseract.get_tesseract_version())
    except Exception as exc:
        return _result(
            "OCR (Tesseract)", "warn",
            f"Tesseract binary not usable ({type(exc).__name__}) - install "
            "Tesseract-OCR and add it to PATH",
        )
    return _result("OCR (Tesseract)", "ok", f"Tesseract {version}")


def _internet_check():
    """Cheap TCP probe of Nova's brain endpoint. Down == warn (offline
    fast-path exists), never fail."""
    try:
        with socket.create_connection(("api.groq.com", 443), timeout=2.5):
            return _result("Internet", "ok", "api.groq.com reachable")
    except Exception:
        return _result(
            "Internet", "warn",
            "offline - Nova will use its offline fast-path",
        )

def _data_file_paths():
    """Resolve runtime data files where nova_storage actually puts them."""
    paths = []
    try:
        from nova_storage import writable_data_path  # type: ignore
        for name in DATA_FILE_NAMES:
            try:
                paths.append(writable_data_path(name))
            except Exception:
                paths.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), name))
    except Exception:
        base = os.path.dirname(os.path.abspath(__file__))
        paths = [os.path.join(base, name) for name in DATA_FILE_NAMES]
    return paths


def _load_json_lenient(path):
    """Parse *path* as JSON - plaintext first, then secure_store's
    encrypted-at-rest format (memory.json carries a NOVAENC1: prefix).
    Returns the parsed object, or None when unreadable either way."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as file:
            return json.load(file)
    except Exception:
        pass
    try:
        import secure_store  # type: ignore
        data = secure_store.load_json_encrypted(str(path))
        return data if isinstance(data, (dict, list)) else None
    except Exception:
        return None


def _data_files_check():
    corrupt = []
    existing = 0
    for path in _data_file_paths():
        if not os.path.exists(path):
            continue  # first-run: file not created yet is fine
        existing += 1
        if _load_json_lenient(path) is None:
            corrupt.append(os.path.basename(path))
    if corrupt:
        return _result(
            "Data files", "fail",
            "CORRUPT or UNREADABLE (plaintext JSON and encrypted-at-rest "
            "both failed): " + ", ".join(corrupt) + " - restore from backups/",
        )
    return _result(
        "Data files", "ok",
        f"{existing}/{len(DATA_FILE_NAMES)} files present, all parse cleanly",
    )


def _write_access_check():
    base = os.path.dirname(os.path.abspath(__file__))
    try:
        handle = tempfile.NamedTemporaryFile(
            prefix="nova_doctor_", suffix=".tmp", dir=base, delete=False
        )
        handle.close()
        os.remove(handle.name)
    except Exception as exc:
        return _result(
            "Write access", "fail",
            f"cannot write in {base} ({type(exc).__name__}: {exc})",
        )
    return _result("Write access", "ok", f"{base} is writable")


def _git_check():
    git_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".git")
    head = os.path.join(git_dir, "HEAD")
    if not os.path.isdir(git_dir) or not os.path.exists(head):
        return _result("Git repo", "warn", "no git repo - no version history / backups")
    return _result("Git repo", "ok", "repository initialised, HEAD present")


def _mic_check():
    try:
        import sounddevice  # type: ignore
        devices = sounddevice.query_devices()
        inputs = sum(1 for d in devices if d.get("max_input_channels", 0) > 0)
    except Exception as exc:
        return _result(
            "Microphone", "warn",
            f"sounddevice unavailable ({type(exc).__name__}) - voice input disabled",
        )
    if inputs <= 0:
        return _result(
            "Microphone", "warn", "no input devices found - voice input disabled"
        )
    return _result("Microphone", "ok", f"{inputs} input device(s) available")

# ---------------------------------------------------------------------------
# 2. Report assembly
# ---------------------------------------------------------------------------

def run_doctor(include_mic=True):
    """Run every check and return the list of result dicts. Never raises."""
    checks = [
        _python_check,
        _env_keys_check,
        _imports_check,
        _ocr_check,
        _internet_check,
        _data_files_check,
        _write_access_check,
        _git_check,
    ]
    if include_mic:
        checks.append(_mic_check)

    results = []
    for check in checks:
        try:
            res = check()
        except Exception as exc:  # a broken check is a fail, never a crash
            res = _result(
                getattr(check, "__name__", "unknown"), "fail",
                f"check itself crashed: {type(exc).__name__}: {exc}",
            )
        if res.get("status") not in VALID_STATUSES:
            res["status"] = "fail"
        results.append(res)
    return results


def summarize(results):
    counts = {"ok": 0, "warn": 0, "fail": 0}
    for res in results:
        counts[res["status"]] = counts.get(res["status"], 0) + 1
    return counts


def format_report(results):
    """Aligned ASCII report (ASCII so Windows cp1252 consoles never choke)."""
    width = max((len(r["name"]) for r in results), default=0)
    lines = ["Nova Doctor - self check:", ""]
    for res in results:
        glyph = _STATUS_GLYPH[res["status"]]
        name = res["name"].ljust(width)
        lines.append(f" {glyph} {name}  {res['detail']}".rstrip())
    counts = summarize(results)
    lines.append("")
    lines.append(
        f"Summary: {counts['ok']} ok, {counts['warn']} warn, {counts['fail']} fail"
    )
    if counts["fail"]:
        lines.append("Verdict:  needs attention (fix the FAIL items above)")
    elif counts["warn"]:
        lines.append("Verdict:  healthy (warnings are optional features)")
    else:
        lines.append("Verdict:  all clear")
    return "\n".join(lines)


def handle_doctor_command(command=None):
    """Entry point for commands.py - returns the full report as a string."""
    return format_report(run_doctor())


if __name__ == "__main__":
    print(format_report(run_doctor()))



