# ==========================================
# NOVA COMPUTER USE - semantic (name/place) control of the PC screen
# ------------------------------------------
# Replaces the old LDPlayer/ADB emulator modules (removed). The user NEVER
# gives pixel coordinates - only names and places:
#     "search bar pe click karo", "top right corner pe click karo",
#     "type hello in search bar", "last paragraph pe click karo",
#     "home screen pe wapas jao", "screen dekho"
#
# Target resolution pipeline (first hit wins):
#   1. PLACE vocabulary  - corner/center/bar phrases -> normalized point
#   2. OCR text anchors  - pytesseract word boxes matched by name/synonym
#                          ("search bar" -> box containing "Search",
#                           "last paragraph" -> lowest text line)
#   3. Gemini vision     - free-form name -> bounding box as PERCENTAGES
#                          (internal only; the user still never sees pixels)
#
# Design rules (copied from command_execution.py / agent.py - DO NOT BREAK):
#   1. NO os.system. NO shell=True. NO subprocess at all - mouse goes
#      through ctypes, keys/typing through the `keyboard` package.
#   2. Every action is appended to an append-only audit log.
#   3. Per-minute rate limit on actions.
#   4. Friendly Hinglish errors; never a raw traceback in the chat bubble.
#   5. Typed text is length-capped (500); nothing is executed, only typed.
#   6. The natural-language parser must be TIGHT: when a phrase looks like
#      normal chat (questions, "type karne me kitna time..."), it returns
#      None so execute_command() falls through to the normal router.
# ==========================================

import difflib
import json
import logging
import os
import re
import time
from collections import deque
from datetime import datetime

log = logging.getLogger("nova.computer_use")

__version__ = "1.0.0"

# ---------------------------------------------------------------------------
# Audit log + rate limiting (mirrors command_execution.py, own namespace)
# ---------------------------------------------------------------------------
def _user_data_dir():
    from pathlib import Path
    import sys
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    p = base / "Nova"
    p.mkdir(parents=True, exist_ok=True)
    return p


AUDIT_LOG = _user_data_dir() / "computer_use_audit.log"

_RATE_MAX_ACTIONS = 30          # actions per window
_RATE_WINDOW_S = 60
_action_times = deque()

_RATE_MSG = "⏳ Rate limit: max 30 computer-use actions/minute. Thoda ruk jao."


def _check_rate():
    """Return True when this action is allowed under the rate limit."""
    now = time.monotonic()
    while _action_times and now - _action_times[0] > _RATE_WINDOW_S:
        _action_times.popleft()
    if len(_action_times) >= _RATE_MAX_ACTIONS:
        return False
    _action_times.append(now)
    return True


def audit(action, detail=""):
    """Append-only audit entry; never raises."""
    try:
        entry = {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "detail": str(detail)[:300],
        }
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        log.debug("audit write failed", exc_info=True)

# ---------------------------------------------------------------------------
# Screen / mouse / keyboard primitives (Windows; guarded + monkeypatchable)
# ---------------------------------------------------------------------------
def _screen_size():
    """True pixel size of the primary screen (DPI-aware)."""
    if os.name == "nt":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass
            w, h = int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
            if w > 0 and h > 0:
                return w, h
        except Exception:
            log.debug("ctypes screen size failed", exc_info=True)
    from PIL import ImageGrab
    return ImageGrab.grab().size


def _grab(region=None):
    """Full-screen (or region) screenshot as a PIL image."""
    from PIL import ImageGrab
    return ImageGrab.grab(bbox=region) if region else ImageGrab.grab()


def _move_mouse(x, y):
    if os.name != "nt":
        raise OSError("mouse control Windows-only")
    import ctypes
    ctypes.windll.user32.SetCursorPos(int(x), int(y))


_MOUSE_FLAGS = {
    "left": (0x0002, 0x0004),
    "right": (0x0008, 0x0010),
    "middle": (0x0020, 0x0040),
}


def _mouse_click(button="left"):
    if os.name != "nt":
        raise OSError("mouse control Windows-only")
    import ctypes
    down, up = _MOUSE_FLAGS.get(button, _MOUSE_FLAGS["left"])
    ctypes.windll.user32.mouse_event(down, 0, 0, 0, 0)
    time.sleep(0.02)
    ctypes.windll.user32.mouse_event(up, 0, 0, 0, 0)


def _mouse_wheel(direction, steps=3):
    if os.name != "nt":
        raise OSError("mouse control Windows-only")
    import ctypes
    delta = 120 * max(1, min(int(steps), 10))   # WHEEL_DELTA, clamped
    ctypes.windll.user32.mouse_event(
        0x0800, 0, 0, -delta if direction == "down" else delta, 0)


_KEY_ALIASES = {
    "esc": "esc", "escape": "esc", "enter": "enter", "return": "enter",
    "tab": "tab", "backspace": "backspace", "space": "space",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "delete": "delete", "del": "delete", "home": "home", "end": "end",
}


def _press_physical_key(name):
    """Press a single named key via the `keyboard` package (already a Nova dep)."""
    import keyboard
    keyboard.press_and_release(_KEY_ALIASES.get(name, name))


def _type_chars(text):
    """Type *text* into the currently focused control.
    Primary: `keyboard.write` (unicode-safe). Fallback: ctypes SendInput."""
    try:
        import keyboard
        keyboard.write(text, delay=0.01)
        return True
    except Exception:
        log.debug("keyboard.write failed; trying ctypes fallback", exc_info=True)
    if os.name != "nt":
        return False
    try:
        import ctypes
        PUL = ctypes.POINTER(ctypes.c_ulong)

        class _KBD(ctypes.Structure):
            _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                        ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                        ("dwExtraInfo", PUL)]

        class _U(ctypes.Union):
            _fields_ = [("ki", _KBD), ("pad", ctypes.c_ubyte * 32)]

        class _INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("u", _U)]

        def _send(scan, flags):
            inp = _INPUT(1, _U())
            inp.u.ki = _KBD(0, scan, flags, 0, None)
            ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

        for ch in text:
            if ch == "\n":
                _press_physical_key("enter")
                continue
            code = ord(ch)
            if code > 0xFFFF:
                continue
            _send(code, 0x0004)                    # KEYEVENTF_UNICODE
            _send(code, 0x0004 | 0x0002)           # + KEYEVENTF_KEYUP
        return True
    except Exception:
        log.exception("ctypes typing failed")
        return False

# ---------------------------------------------------------------------------
# PLACE vocabulary - normalized (0..1) points; pure math, fully testable
# ---------------------------------------------------------------------------
_ZONES = {
    "top left corner": (0.06, 0.08),
    "top right corner": (0.94, 0.08),
    "bottom left corner": (0.06, 0.90),
    "bottom right corner": (0.94, 0.90),
    "top corner": (0.50, 0.06),
    "top center": (0.50, 0.08),
    "top middle": (0.50, 0.25),
    "bottom center": (0.50, 0.88),
    "bottom middle": (0.50, 0.75),
    "top bar": (0.50, 0.04),
    "title bar": (0.50, 0.03),
    "bottom bar": (0.50, 0.95),
    "taskbar": (0.50, 0.985),
    "center": (0.50, 0.50),
    "middle": (0.50, 0.50),
    "left side": (0.12, 0.50),
    "right side": (0.88, 0.50),
    "left edge": (0.05, 0.50),
    "right edge": (0.95, 0.50),
    "top edge": (0.50, 0.03),
    "bottom edge": (0.50, 0.97),
    "top half": (0.50, 0.25),
    "bottom half": (0.50, 0.75),
    "top left": (0.20, 0.20),
    "top right": (0.80, 0.20),
    "bottom left": (0.20, 0.80),
    "bottom right": (0.80, 0.80),
}

_ZONE_HINTS = (
    "corner", "center", "centre", "middle", "side", "edge", "taskbar",
    "top bar", "bottom bar", "title bar", "half",
)


def resolve_zone(target):
    """Return a normalized (x, y) point for a place phrase, else None.

    Longest key wins so 'top left corner' beats 'top left'. Handles filler
    words like 'from/to/the' around the phrase."""
    t = (target or "").strip().lower().strip("?.,!").strip()
    if not t:
        return None
    t = re.sub(r"^(?:from|to|at|on|the|in)\s+", "", t)
    t = re.sub(r"\s+(?:wale|wala|part|area)$", "", t)
    for key in sorted(_ZONES, key=len, reverse=True):
        if key == t or re.search(r"\b" + re.escape(key) + r"\b", t):
            return _ZONES[key]
    return None


def is_zone_phrase(target):
    """Cheap check whether a phrase even smells like a place."""
    t = (target or "").lower()
    return any(h in t for h in _ZONE_HINTS)

# ---------------------------------------------------------------------------
# OCR text anchors - find elements BY NAME on screen
# ---------------------------------------------------------------------------
# Friendly name -> words we expect OCR to see for that element
_ELEMENT_SYNONYMS = {
    "search bar": ("search",),
    "search box": ("search",),
    "search": ("search",),
    "home button": ("home",),
    "home": ("home",),
    "start button": ("start",),
    "start": ("start",),
    "send button": ("send",),
    "send": ("send",),
    "ok button": ("ok", "okay", "yes"),
    "ok": ("ok", "okay", "yes"),
    "cancel button": ("cancel", "no"),
    "cancel": ("cancel", "no"),
    "close button": ("close", "cross"),
    "close": ("close", "cross"),
    "back button": ("back",),
    "back": ("back",),
    "settings": ("settings", "setting"),
    "menu": ("menu",),
    "submit button": ("submit", "go"),
    "submit": ("submit", "go"),
    "login button": ("log in", "sign in", "login", "sign-in"),
    "login": ("log in", "sign in", "login", "sign-in"),
    "next button": ("next",),
    "next": ("next",),
    "play button": ("play",),
    "play": ("play",),
    "like button": ("like",),
    "share button": ("share",),
    "profile": ("profile", "account"),
}


def _tesseract_ready():
    """Point pytesseract at the engine if present (same path nova_vision uses)."""
    try:
        import pytesseract
    except Exception:
        return None
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        import shutil
        exe = shutil.which("tesseract") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.isfile(exe):
            pytesseract.pytesseract.tesseract_cmd = exe
        else:
            return None
    return pytesseract


def _ocr_words(img):
    """Word boxes from pytesseract; [] when OCR is unavailable."""
    pyt = _tesseract_ready()
    if pyt is None or img is None:
        return []
    try:
        data = pyt.image_to_data(img, output_type=pyt.Output.DICT)
    except Exception:
        log.debug("image_to_data failed", exc_info=True)
        return []
    words = []
    for i in range(len(data.get("text", []))):
        w = (data["text"][i] or "").strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        if not w or conf < 0:
            continue
        words.append({
            "text": w,
            "x": int(data["left"][i]), "y": int(data["top"][i]),
            "w": int(data["width"][i]), "h": int(data["height"][i]),
            "block": int(data["block_num"][i]),
            "par": int(data["par_num"][i]),
            "line": int(data["line_num"][i]),
        })
    return words


def _ocr_lines(img):
    """Group OCR words into visual lines -> [{'text', 'box':(x0,y0,x1,y1)}],
    sorted top-to-bottom (then left-to-right)."""
    groups = {}
    for w in _ocr_words(img):
        groups.setdefault((w["block"], w["par"], w["line"]), []).append(w)
    lines = []
    for ws in groups.values():
        ws.sort(key=lambda w: w["x"])
        text = " ".join(w["text"] for w in ws)
        box = (min(w["x"] for w in ws), min(w["y"] for w in ws),
               max(w["x"] + w["w"] for w in ws), max(w["y"] + w["h"] for w in ws))
        lines.append({"text": text, "box": box})
    lines.sort(key=lambda l: (l["box"][1], l["box"][0]))
    return lines


def _box_center(box):
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def _match_line(target, lines):
    """Match a friendly name/place against OCR lines. Returns the line or None."""
    t = (target or "").strip().lower().strip("?.,!").strip()
    if not t or not lines:
        return None

    # "last paragraph" / "first line" style positional text anchors
    positional = re.search(r"para(?:graph)?|line|text|block|pura|paragraph", t)
    if positional:
        if re.search(r"\b(?:last|sabse\s*(?:niche|neeche)|neeche|niche|bottom|end)\b", t):
            return lines[-1]
        if re.search(r"\b(?:first|sabse\s*(?:upar|pehle)|top|shuru)\b", t):
            return lines[0]
        if re.search(r"\b(?:second|dusra|doosra)\b", t) and len(lines) > 1:
            return lines[-2]

    # quoted exact phrase:  button that says "Sign in"
    q = re.search(r"[\"']([^\"']+)[\"']", target or "")
    if q:
        needle = q.group(1).strip().lower()
        for ln in lines:
            if needle in ln["text"].lower():
                return ln

    keys = list(_ELEMENT_SYNONYMS.get(t, ()))
    if not keys:
        keys = [t]
    # exact containment first (synonyms), then fuzzy match on the raw name
    for ln in lines:
        lt = ln["text"].lower()
        for k in keys:
            if k and k in lt:
                return ln
    best = difflib.get_close_matches(
        t, [ln["text"].lower() for ln in lines], n=1, cutoff=0.6)
    if best:
        for ln in lines:
            if ln["text"].lower() == best[0]:
                return ln
    return None

# ---------------------------------------------------------------------------
# Gemini vision fallback - free-form names, answered in PERCENTAGES
# (percentages are converted internally; the user never handles pixels)
# ---------------------------------------------------------------------------
def _gemini():
    """Lazy access to nova_vision's Gemini; None when not configured."""
    try:
        from nova_vision import ask_gemini_vision
        return ask_gemini_vision
    except Exception:
        return None


def _parse_json_reply(reply):
    """Best-effort JSON extraction from an LLM reply (tolerates ``` fences)."""
    if not reply:
        return None
    m = re.search(r"```(?:json)?\s*(.*?)```", reply, re.DOTALL)
    text = m.group(1).strip() if m else reply.strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        text = text[start:end + 1]
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _resolve_by_vision(target):
    """Ask Gemini where '<target>' is, as a 0-100 percentage bounding box."""
    ask = _gemini()
    if ask is None:
        return None
    try:
        img = _grab()
    except Exception:
        return None
    prompt = (
        f"Ye Windows PC ki screenshot hai. Is par '{target}' naam/description "
        "wala element dhoondo. Us element ke bounding box ki position FULL "
        "SCREEN ke percentage mein do (0-100 numbers). Reply SIRF JSON:\n"
        '{"found": true, "left": <0-100>, "top": <0-100>, '
        '"right": <0-100>, "bottom": <0-100>, "label": "<matched text>"}\n'
        'Agar element nahi mila to reply: {"found": false}'
    )
    try:
        reply = ask(img, prompt)
    except Exception:
        log.debug("vision resolve failed", exc_info=True)
        return None
    obj = _parse_json_reply(reply)
    if not obj or not obj.get("found"):
        return None
    try:
        left, top = float(obj["left"]), float(obj["top"])
        right, bottom = float(obj["right"]), float(obj["bottom"])
    except (KeyError, TypeError, ValueError):
        return None
    vals = [left, top, right, bottom]
    if any(v < 0 or v > 100 for v in vals) or right <= left or bottom <= top:
        return None
    w, h = _screen_size()
    x = ((left + right) / 2.0 / 100.0) * w
    y = ((top + bottom) / 2.0 / 100.0) * h
    label = str(obj.get("label", "") or target)[:40]
    return {"point": (x, y), "how": "vision", "label": label}


# ---------------------------------------------------------------------------
# Unified resolver: place phrase -> OCR anchor -> vision
# ---------------------------------------------------------------------------
def resolve_target(target, img=None, use_vision=True):
    """Resolve a name/place into {'point': (x, y), 'how': ..., 'label': ...}.

    Returns None when the target cannot be found anywhere. *img* can be
    injected (tests); otherwise a screenshot is taken for the OCR step."""
    t = (target or "").strip()
    if not t:
        return None

    zone = resolve_zone(t)
    if zone:
        w, h = _screen_size()
        return {"point": (zone[0] * w, zone[1] * h),
                "how": "zone", "label": t}

    if img is None:
        try:
            img = _grab()
        except Exception:
            img = None
    if img is not None:
        hit = _match_line(t, _ocr_lines(img))
        if hit:
            return {"point": _box_center(hit["box"]), "how": "ocr",
                    "label": hit["text"][:40]}

    if use_vision:
        vis = _resolve_by_vision(t)
        if vis:
            return vis
    return None


_TARGET_FAIL = ("❌ '{target}' screen par nahi mila. Naam ya jagah bolo — "
                "jaise 'search bar', 'home button', 'top right corner', "
                "'last paragraph'.")

# ---------------------------------------------------------------------------
# Actions - every one is rate-limited + audited, friendly errors only
# ---------------------------------------------------------------------------
def _not_windows():
    return "🖱️ Computer control abhi sirf Windows par available hai."


def click(target, button="left", clicks=1):
    """Click a NAME or PLACE. This is the only click API - no raw x,y."""
    if os.name != "nt":
        return _not_windows()
    if not _check_rate():
        audit("rate_limited", "click")
        return _RATE_MSG
    res = resolve_target(target)
    if not res:
        audit("rejected_unknown_target", target)
        return _TARGET_FAIL.format(target=target)
    try:
        x, y = res["point"]
        _move_mouse(x, y)
        time.sleep(0.05)
        for _ in range(max(1, min(int(clicks), 3))):
            _mouse_click(button)
            time.sleep(0.03)
    except Exception as exc:
        log.error("click failed: %s", exc)
        audit("click", f"error:{type(exc).__name__}")
        return "❌ Click nahi ho paya (mouse control block lagta hai)."
    audit("click", f"{target} ({res['how']})")
    label = res.get("label") or str(target)
    desc = {"zone": "jagah se", "ocr": f"text '{label}' se",
            "vision": "AI vision se"}.get(res.get("how"), res.get("how"))
    suffix = " (double)" if int(clicks) > 1 else ""
    return f"✅ '{label}' {desc} click kiya{suffix}."


def type_text(text, into=None):
    """Type *text* (optionally after clicking into a named target)."""
    if os.name != "nt":
        return _not_windows()
    if not _check_rate():
        audit("rate_limited", "type")
        return _RATE_MSG
    text = str(text or "")
    if not text.strip():
        return "Kya type karu? Text bolo."
    if len(text) > 500:
        audit("rejected_too_long", f"{len(text)} chars")
        return "❌ Bahut lamba text hai (max 500 characters)."
    if into:
        res = click(into)
        if not res.startswith("✅"):
            return res + "\n(Type cancel — focus nahi mila.)"
        time.sleep(0.25)
    try:
        ok = _type_chars(text)
    except Exception as exc:
        log.error("type failed: %s", exc)
        audit("type", f"error:{type(exc).__name__}")
        return "❌ Typing nahi ho payi (keyboard control block lagta hai)."
    if not ok:
        audit("type", "error:no-input-channel")
        return "❌ Typing nahi ho payi (keyboard package check karo)."
    audit("type", f"{len(text)} chars" + (f" into {into}" if into else ""))
    return "⌨️ Type ho gaya." + (f" ({into} me)" if into else "")


def press_key(name):
    """Press one named key: enter/escape/tab/backspace/space/arrows/..."""
    if os.name != "nt":
        return _not_windows()
    if not _check_rate():
        audit("rate_limited", "press_key")
        return _RATE_MSG
    key = _KEY_ALIASES.get(str(name or "").strip().lower())
    if not key:
        audit("rejected_unknown_key", name)
        known = ", ".join(sorted(set(_KEY_ALIASES.values())))
        return f"❌ Ye key support nahi hai. Known keys: {known}"
    try:
        _press_physical_key(key)
    except Exception as exc:
        log.error("press_key failed: %s", exc)
        audit("press_key", f"error:{type(exc).__name__}")
        return "❌ Key press nahi hui (keyboard package check karo)."
    audit("press_key", key)
    return f"⌨️ '{key}' press ho gaya."


def scroll(direction, steps=3):
    """Scroll the window under the mouse up/down."""
    if os.name != "nt":
        return _not_windows()
    if not _check_rate():
        audit("rate_limited", "scroll")
        return _RATE_MSG
    direction = "up" if str(direction).lower() in ("up", "upar", "above") else "down"
    try:
        _mouse_wheel(direction, steps)
    except Exception as exc:
        log.error("scroll failed: %s", exc)
        audit("scroll", f"error:{type(exc).__name__}")
        return "❌ Scroll nahi hua."
    audit("scroll", direction)
    arrow = "⬆️" if direction == "up" else "⬇️"
    return f"{arrow} {direction.capitalize()} scroll ho gaya."

# ---------------------------------------------------------------------------
# Home screen / verify / describe
# ---------------------------------------------------------------------------
def go_home():
    """'Come back on home screen' -> show the Windows desktop (Win+D),
    then best-effort verify with vision."""
    if os.name != "nt":
        return _not_windows()
    if not _check_rate():
        audit("rate_limited", "go_home")
        return _RATE_MSG
    try:
        import keyboard
        keyboard.press_and_release("windows+d")
    except Exception as exc:
        log.error("go_home failed: %s", exc)
        audit("go_home", f"error:{type(exc).__name__}")
        return "❌ Home screen pe nahi ja paya (keyboard control block lagta hai)."
    time.sleep(0.8)
    audit("go_home", "windows+d")
    msg = "🏠 Home screen (desktop) pe aa gaye."
    verdict = _verify_vision(
        "Kya ye Windows desktop/home screen hai? (desktop icons ya taskbar "
        "dikhe, koi app window foreground mein na ho)")
    if verdict is True:
        msg += " (verified ✅)"
    elif verdict is False:
        msg += " (dhyan dena — verify nahi hua, ek baar khud dekh lo)"
    return msg


def _verify_vision(question):
    """Ask Gemini a yes/no question about the current screen.
    True / False, ya None (jab verify possible nahi)."""
    ask = _gemini()
    if ask is None:
        return None
    try:
        img = _grab()
    except Exception:
        return None
    prompt = (
        "Screenshot dekh kar ye sawaal jawab do. Reply SIRF JSON: "
        '{"answer": true} ya {"answer": false}.\n'
        f"Sawaal: {question}"
    )
    try:
        reply = ask(img, prompt)
    except Exception:
        return None
    obj = _parse_json_reply(reply)
    if not obj or "answer" not in obj:
        return None
    ans = obj.get("answer")
    if isinstance(ans, bool):
        return ans
    if isinstance(ans, str):
        return ans.strip().lower() in ("true", "yes", "haan", "ha")
    return None


def verify(condition):
    """Public 'kya ye sach hai screen par?' check with vision + OCR fallback."""
    if not _check_rate():
        audit("rate_limited", "verify")
        return _RATE_MSG
    condition = str(condition or "").strip()
    if not condition:
        return "Kya verify karu? Condition bolo."
    verdict = _verify_vision(
        f"Condition: {condition}. Kya ye condition is screen par true hai?")
    if verdict is True:
        audit("verify", f"true: {condition}")
        return f"✅ Haan — '{condition}' screen par verify hua."
    if verdict is False:
        audit("verify", f"false: {condition}")
        return f"❌ Nahi — '{condition}' abhi screen par nahi dikha."
    # No vision -> weak OCR containment fallback
    try:
        from nova_vision import extract_text_from_image
        ocr = extract_text_from_image(_grab()) or ""
        words = [w for w in re.findall(r"[a-zA-Z]{4,}", condition.lower())]
        if words and any(w in ocr.lower() for w in words):
            audit("verify", f"ocr-partial: {condition}")
            return f"🟡 OCR se '{condition}' ke kuch shabd screen par mile — partially verified."
    except Exception:
        pass
    audit("verify", f"unverified: {condition}")
    return "🤔 Verify nahi kar paya (Gemini key/network check karo)."


def describe_screen():
    """'Screen dekho' — describe the PC screen and list clickable element
    NAMES (never coordinates)."""
    if not _check_rate():
        audit("rate_limited", "describe")
        return _RATE_MSG
    try:
        img = _grab()
    except Exception as exc:
        audit("describe", f"error:{type(exc).__name__}")
        return "❌ Screenshot nahi le paya."
    ask = _gemini()
    if ask is not None:
        prompt = (
            "Ye Windows PC ki screen hai. Hinglish mein 2-3 line batao kya "
            "dikh raha hai. Phir visible UI elements ke NAAM list karo "
            "(jaise 'search bar', 'Home button', 'Settings', 'last paragraph') "
            "- KOI pixel coordinates NAHI, sirf naam. End mein 1 hint line: "
            "'click on <naam>' ya 'type <text> in <naam>' se control kar sakte ho."
        )
        try:
            reply = ask(img, prompt)
        except Exception:
            reply = None
        if reply and reply.strip():
            audit("describe", "gemini")
            return reply.strip()
    # OCR fallback
    try:
        from nova_vision import extract_text_from_image
        text = (extract_text_from_image(img) or "").strip()
    except Exception:
        text = ""
    audit("describe", "ocr-fallback")
    if not text:
        return ("🤔 Screen samajh nahi paya — Gemini key/network check karo, "
                "ya OCR me kuch readable nahi mila.")
    preview = text[:600] + ("..." if len(text) > 600 else "")
    return ("📷 OCR fallback — screen par ye text dikha:\n" + preview +
            "\n\nClick karna ho to: 'click on <naam>' ya 'top right corner pe click karo'.")

# ---------------------------------------------------------------------------
# Natural-language parser - name/place commands ONLY (tight on purpose)
# ---------------------------------------------------------------------------
_QUESTION_WORDS = re.compile(
    r"\b(?:kaise|kyun|kyu|kab|kahan|kaha|kitna|kitne|kitni|kaun|kya|"
    r"why|how|what|when|where|who)\b", re.IGNORECASE)


def _clean_target(t):
    """Drop filler words around a target name/place."""
    t = (t or "").strip().strip("?.,!").strip()
    t = re.sub(r"^(?:this|ye|yeh|the|a|an|wo|vo|us|is)\s+", "", t,
               flags=re.IGNORECASE).strip()
    return t


def parse_command(cmd):
    """Parse a chat string into (action_name, kwargs) for computer-use.

    Returns None when this is normal chat / another feature's command -
    execute_command() must fall through in that case. Pure string logic,
    no side effects, so it is fully unit-testable."""
    if not cmd or not cmd.strip():
        return None
    c = cmd.strip()
    low = c.lower().rstrip("?.,!")

    # -- describe: "screen dekho", "screen kya dikh raha", "screen check" --
    if re.search(r"\bscreen\b", low) and re.search(
            r"\b(?:dekho|dekh|dikh|dikha|check)\b", low):
        return ("describe", {})
    if re.search(r"\bkya\s+dikh", low):
        return ("describe", {})

    # -- home screen: "come back on home screen", "wapas home screen pe jao" --
    if re.search(r"\bshow\s+desktop\b", low):
        return ("go_home", {})
    if re.search(r"\bhome\s*(?:screen|page)?\b", low) and re.search(
            r"\b(?:wapas|come\s*back|back|jao|jaao|chale|return|le\s*aao|"
            r"pahuncho)\b", low):
        return ("go_home", {})

    # -- verify: "verify ki search bar screen par hai" --
    m = re.match(r"^(?:verify|verify\s+karo)(?:\s+ki)?\s+(.+)$", low)
    if m:
        return ("verify", {"condition": m.group(1).strip()})
    m = re.match(r"^check\s+karo\s+ki\s+(.+)$", low)
    if m:
        return ("verify", {"condition": m.group(1).strip()})

    # -- scroll --
    m = re.match(r"^(?:scroll|scrool)\s+(up|down|upar|niche|neeche)\b", low)
    if m:
        d = m.group(1)
        return ("scroll", {"direction": "up" if d in ("up", "upar") else "down"})
    m = re.match(r"^(?:up|upar|niche|neeche|down)\s+(?:scroll|scrool)"
                 r"(?:\s+(?:karo|kar\s*do))?$", low)
    if m:
        d = low.split()[0]
        return ("scroll", {"direction": "up" if d in ("up", "upar") else "down"})
    if re.match(r"^scroll(?:\s+karo)?$", low):
        return ("scroll", {"direction": "down"})

    # -- press key: "press enter", "enter dabao", "escape press karo" --

    # -- press key: "press enter", "enter dabao", "escape press karo" --
    keys = ("enter|return|escape|esc|tab|backspace|space|up|down|left|right|"
            "delete|del|home|end")
    m = re.match(rf"^(?:press|dabao|daba\s*do|dabado)\s+({keys})\b"
                 r"(?:\s+(?:karo|key|button))?$", low)
    if m:
        return ("press_key", {"name": m.group(1)})
    m = re.match(rf"^({keys})\s+(?:dabao|daba\s*do|dabado|press(?:\s+karo)?)$",
                 low)
    if m:
        return ("press_key", {"name": m.group(1)})

    # -- type ...: explicit verb required; question-looking text rejected --
    m = re.match(r"^(?:type|write)\s+(.+?)\s*(?:\s+(?:in|into|on)\s+(.+))?$",
                 low)
    if m and not _QUESTION_WORDS.search(m.group(1)):
        return ("type", {"text": m.group(1).strip("\"'"),
                         "into": _clean_target(m.group(2))})
    m = re.match(r"^(.+?)\s+(?:me|mein|par|pe)\s+[\"']?(.+?)[\"']?\s+"
                 r"(?:likho|likh\s*do|likh|type\s*karo|type\s*kar\s*do|write)$",
                 low)
    if m and not _QUESTION_WORDS.search(m.group(2)):
        return ("type", {"text": m.group(2).strip("\"'"),
                         "into": _clean_target(m.group(1))})
    m = re.match(r"^(.+?)\s+[\"']?(.+?)[\"']?\s+"
                 r"(?:likho|likh\s*do|type\s*karo|type\s*kar\s*do|write\s*karo)"
                 r"(?:\s+(?:in|into|me|mein|par|pe)\s+(.+))?$", low)
    if m and m.group(3) and not _QUESTION_WORDS.search(m.group(2)):
        return ("type", {"text": m.group(2).strip("\"'"),
                         "into": _clean_target(m.group(3))})

    # -- click/tap: explicit verb only --
    double = bool(re.match(r"^double\s*click\b", low))
    button = "right" if re.match(r"^right\s*click\b", low) else "left"
    m = re.match(r"^(?:(?:double\s*|right\s*)click|tap|click)"
                 r"(?:\s+(?:on|pe|par|per|at))?\s+(.+)$", low)
    if m and not _QUESTION_WORDS.search(m.group(1)):
        return ("click", {"target": _clean_target(m.group(1)),
                          "button": button, "clicks": 2 if double else 1})
    m = re.match(r"^(.+?)\s+(?:pe|par|per)\s+"
                 r"(?:(?:double\s*)?click|tap)(?:\s+(?:karo|kar\s*do))?$", low)
    if m and not _QUESTION_WORDS.search(m.group(1)):
        return ("click", {"target": _clean_target(m.group(1)),
                          "button": button, "clicks": 2 if double else 1})
    return None

# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
_ACTIONS = {
    "click": click,
    "type": type_text,
    "press_key": press_key,
    "scroll": scroll,
    "go_home": go_home,
    "verify": verify,
    "describe": describe_screen,
}


def execute_command(command):
    """Execute a computer-use chat command. Returns a reply string, or None
    when *command* is not a computer-use command (caller falls through to
    the normal router)."""
    parsed = parse_command(command)
    if not parsed:
        return None
    action, kwargs = parsed
    try:
        return _ACTIONS[action](**kwargs)
    except Exception as exc:
        log.error("computer_use %s failed: %s: %s",
                  action, type(exc).__name__, exc)
        audit("execute_error", f"{action}:{type(exc).__name__}")
        return ("❌ Computer-use action fail ho gaya. Details log me hain — "
                "dobara try karo.")


def get_capabilities():
    """Catalog for GUI/features list - shows HOW users control the PC."""
    return {
        "feature": "Computer Use (semantic)",
        "controls": [
            "screen dekho / screen check karo",
            "click on <naam ya jagah>  (search bar, home button, top right corner)",
            "double click on <naam>",
            "type <text> in <naam>  /  <naam> me <text> likho",
            "press enter / escape / tab ...",
            "scroll up / down",
            "come back on home screen",
            "verify ki <condition>",
        ],
        "resolution": ["place vocabulary", "OCR text anchors", "Gemini vision"],
        "safety": ["rate limit", "audit log", "no shell", "no raw coordinates"],
    }


__all__ = [
    "execute_command", "parse_command", "click", "type_text", "press_key",
    "scroll", "go_home", "verify", "describe_screen", "resolve_target",
    "resolve_zone", "get_capabilities", "audit",
]








