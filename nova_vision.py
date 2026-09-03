# ==========================================
# NOVA AI - VISION (Gemini + OCR + screen capture)
# Everything about "seeing" - screenshots, camera frames, OCR text
# extraction, and real Gemini vision calls. No Tkinter/live-widget
# dependencies here; every function just takes a PIL image (or
# nothing) and returns text/tuples. Safe to import from anywhere.
# ==========================================

import os
import sys
from PIL import ImageGrab

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return None

# BUG FIX: load_dotenv() with no arguments searches from the current
# working directory, which changes depending on how Nova is launched.
# We force it to look for .env next to this script. When Nova is frozen
# into a onefile .exe, __file__ points at a temp _MEIxxxx folder with no
# .env -- so look next to sys.executable (the Nova.exe folder) instead.
if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_PATH = os.path.join(_BASE_DIR, ".env")
load_dotenv(dotenv_path=_ENV_PATH)

# ---------------------------------------------------------------------------
# Heavy optional deps (google-genai is ~5 s at import, pytesseract slower) are
# LAZY-LOADED so that importing nova_vision — and therefore starting Nova —
# stays fast. The SDK is only imported the first time a Vision/OCR feature is
# actually used, pushing that cost out of app startup (the main reason Nova's
# .exe "hangs" before the first paint). This does NOT change any feature; it
# only delays when the import happens.
# ---------------------------------------------------------------------------
google_genai = None   # populated on first use by _load_google_genai()
pytesseract = None    # populated on first use by _load_pytesseract()
_TESSERACT_ENGINE_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def _load_pytesseract():
    """Import pytesseract on first use (kept out of module import for speed)."""
    global pytesseract
    if pytesseract is None:
        try:
            import pytesseract as _pt  # type: ignore[import]
            _pt.pytesseract.tesseract_cmd = _TESSERACT_ENGINE_PATH
            pytesseract = _pt
        except Exception as exc:  # noqa: BLE001
            # Catch *all* failures, not just ImportError. A broken transitive
            # dependency (pandas/numpy binary incompat: "numpy.dtype size
            # changed") raises ValueError, which `except ImportError` would
            # let propagate and crash the whole app. OCR is optional, so we
            # degrade gracefully instead.
            print("pytesseract unavailable (OCR disabled):", exc)
            pytesseract = None
    return pytesseract


def _load_google_genai():
    """Import the google.genai SDK on first use.

    google-genai takes ~5 seconds to import; importing it at module load makes
    every Nova startup hang. Loading it here (once) defers the cost to the
    first actual vision call instead of blocking first paint.
    """
    global google_genai
    if google_genai is None:
        try:
            from google import genai as _genai
            google_genai = _genai
        except Exception:
            google_genai = None
    return google_genai

# If OCR ("path nahi mila" type errors) doesn't work even after
# installing Tesseract-OCR, uncomment the line below and put the
# exact path to tesseract.exe on your system (the same path that
# fixed test_ocr.py for you):
if pytesseract is not None:
 pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# google_genai is imported lazily by _load_google_genai() (defined above) so
# that Nova doesn't pay the ~5 s google.genai import cost on every startup.

# ==========================================
# GEMINI VISION (free tier) - real image understanding
# ==========================================
# OCR (pytesseract) can only read plain text - it can't describe a
# photo, a face, an expression, or read a screen accurately when
# there's UI/colour/formatting involved. Gemini's free tier is
# multimodal (actually "looks" at the image), so we use it as the
# primary brain for Screen Watch / Camera, and fall back to OCR only
# if Gemini isn't configured.
#
# Setup (free, no card needed for the free tier):
#   1. pip install google-genai
#   2. Get a free key at https://aistudio.google.com/apikey
#   3. Paste it below (or set env var GEMINI_API_KEY instead)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")  # <-- paste your free key here between the quotes if you don't want to use an env var
# Primary Gemini model. "gemini-flash-latest" is Google's auto-updating alias
# for the current stable free Flash model - this avoids hardcoding a version
# number that Google later retires (as happened with gemini-2.5-flash, which
# now 404s for new keys).
GEMINI_MODEL = "gemini-flash-latest"
# If the primary model is unavailable for any reason (overloaded/deprecated/
# permission), try these fallbacks in order. Live-verified on a free key
# (Sep 2026): gemini-flash-latest intermittently returns 503 "high demand",
# and the old fallbacks (gemini-2.5-flash-lite, gemini-2.0-flash,
# gemini-1.5-flash) now 404 for new keys. gemini-flash-lite-latest and
# gemini-3-flash-preview both answered 200 with this key.
_GEMINI_MODEL_FALLBACKS = [
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-3-flash-preview",
]

_gemini_client = None


def get_gemini_client():
    global _gemini_client
    _load_google_genai()
    if google_genai is None or not GEMINI_API_KEY:
        return None
    if _gemini_client is None:
        try:
            _gemini_client = google_genai.Client(api_key=GEMINI_API_KEY)
        except Exception as exc:
            print("Gemini client init failed:", exc)
            return None
    return _gemini_client


last_gemini_error = None


def get_last_gemini_error() -> str:
    """Return the most recent Gemini error message (live, not a stale copy).

    gui.py historically did ``from nova_vision import last_gemini_error`` which
    copies the *value* (None) at import time — so the chat always showed the
    generic "not configured" fallback even when Gemini set a real error. Read
    it via this function instead so the actual reason surfaces.
    """
    return last_gemini_error


def ask_gemini_vision(pil_image, prompt_text):
    """Sends an actual image + question to Gemini and returns its
    answer, or None if Gemini isn't available/configured/failed. On
    failure, the real error is saved in last_gemini_error so it can
    be shown in the chat instead of only printing to a console you
    may never see (e.g. when running as a packaged .exe)."""
    global last_gemini_error
    last_gemini_error = None
    client = get_gemini_client()
    if client is None:
        last_gemini_error = "Gemini client set up nahi hai (key ya package check karo)."
        return None
    if pil_image is None:
        last_gemini_error = "Koi image capture nahi hui thi."
        return None

    last_err = None
    for model in _GEMINI_MODEL_FALLBACKS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=[prompt_text, pil_image],
            )
            text = (response.text or "").strip()
            if not text:
                last_gemini_error = "Gemini ne khali response diya (shayad safety filter ki wajah se)."
                return None
            # Remember a working model for the next image call.
            global GEMINI_MODEL
            if model != GEMINI_MODEL:
                GEMINI_MODEL = model
            return text
        except Exception as exc:
            last_err = exc
            # ANY failure moves on to the next model: 404 = the model was
            # retired for this key, 503 = "high demand" overload, 429 = that
            # model's quota ran out. Each model has its own quota, so trying
            # the next candidate is always the right recovery. (The old code
            # broke out on non-404 errors, which meant a single 503 on the
            # primary silently killed the whole chain.)
            print(f"Gemini model {model} unavailable, trying next:", exc)

    if last_err is not None:
        last_gemini_error = f"{type(last_err).__name__}: {last_err}"
        print("Gemini vision call failed:", last_err)
    return None


def check_gemini_status():
    _load_google_genai()
    if google_genai is None:
        return False, "google-genai package install nahi hai. Chalao: pip install google-genai"
    if not GEMINI_API_KEY:
        return False, "Gemini API key set nahi hai - gui.py (ya nova_vision.py) me GEMINI_API_KEY variable me apni free key daalo (aistudio.google.com/apikey se milegi)"
    return True, f"Gemini Vision ({GEMINI_MODEL}) ready hai"


def ask_gemini_text(prompt_text):
    """Text-only Gemini call (no image) - used for manual food logging
    where there's no photo, just a typed description."""
    global last_gemini_error
    last_gemini_error = None
    client = get_gemini_client()
    if client is None:
        last_gemini_error = "Gemini client set up nahi hai (key ya package check karo)."
        return None
    try:
        response = client.models.generate_content(model=GEMINI_MODEL, contents=[prompt_text])
        text = (response.text or "").strip()
        if not text:
            last_gemini_error = "Gemini ne khali response diya."
            return None
        return text
    except Exception as exc:
        last_gemini_error = f"{type(exc).__name__}: {exc}"
        print("Gemini text call failed:", exc)
        return None


# ==========================================
# OCR (Tesseract) - fallback for when Gemini isn't configured
# ==========================================

def check_ocr_status():
    """Returns (ready, message). Two separate things can be missing:
    the pytesseract PYTHON package, or the actual Tesseract-OCR
    program on the system (pytesseract can be installed even if the
    engine itself isn't - that's the #1 confusion point)."""
    _load_pytesseract()
    if pytesseract is None:
        return False, "pytesseract package install nahi hai. Chalao: pip install pytesseract"
    try:
        version = pytesseract.get_tesseract_version()
    except Exception:
        return False, (
            "pytesseract install hai, lekin Tesseract-OCR engine nahi mila. "
            "https://github.com/UB-Mannheim/tesseract/wiki se install karo, "
            "ya pytesseract.pytesseract.tesseract_cmd me uska exe path set karo."
        )
    return True, f"Tesseract OCR v{version} ready hai"


def extract_text_from_image(pil_image):
    if pil_image is None:
        return ""
    _load_pytesseract()
    if pytesseract is None:
        return ""
    try:
        return pytesseract.image_to_string(pil_image).strip()
    except Exception as exc:
        print("OCR failed:", exc)
        return ""


# ==========================================
# SCREEN CAPTURE
# ==========================================

def capture_screen_image():
    try:
        return ImageGrab.grab()
    except Exception as exc:
        print("Screen capture failed:", exc)
        return None
