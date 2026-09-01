import base64
import json
import os
import re
import sys
import time
from dotenv import load_dotenv
from openai import OpenAI

# ==========================================================
# AIKO AI - PHOTO DETECTOR
# ==========================================================

# BUG FIX: load_dotenv() with no arguments searches from the current
# working directory, which changes depending on how Nova is launched
# (double-click vs terminal vs different folder) - so GROQ_API_KEY
# could silently fail to load. This forces it to always look for
# .env next to this script. But when frozen into a onefile .exe,
# __file__ points at a temp _MEIxxxx folder with no .env, so look
# next to sys.executable (the Nova.exe folder) instead.
if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_PATH = os.path.join(_BASE_DIR, ".env")
load_dotenv(dotenv_path=_ENV_PATH)

API_KEY = os.getenv("GROQ_API_KEY")

# ==========================================================
# RATE LIMIT HANDLER
# ==========================================================
# Groq returns 429 when you hit TPM/RPM/TPD/RPD limits.
# This function extracts helpful info from error headers
# and waits before retrying.
# ==========================================================

def _handle_rate_limit_error(error, attempt=1):
    """
    Detects if the error is a 429 (rate limit) and returns:
    - A user-friendly message explaining the wait time
    - How long to wait before retrying (in seconds)
    """

    error_str = str(error)

    # Look for common Groq rate limit messages
    if "429" in error_str or "Rate limit" in error_str or "Too Many Requests" in error_str:

        # Try to extract wait time from error message
        if "retry-after" in error_str:
            try:
                match = re.search(r'retry-after["\']?\s*:\s*(\d+)', error_str)
                if match:
                    wait_seconds = int(match.group(1))
                    return (
                        f"⏳ Rate limit hit! Daily token quota used.\n\n"
                        f"Please wait ~{wait_seconds} seconds and try again.\n"
                        f"(Or wait until tomorrow for quota to reset.)",
                        wait_seconds + 5
                    )
            except:
                pass

        # If we can't parse wait time, use exponential backoff
        wait_seconds = min(2 ** attempt, 60)  # 2, 4, 8, 16, 32, 60 seconds max

        return (
            f"⏳ Rate limit hit! You've used too many tokens today.\n\n"
            f"Photo analysis has a daily budget (200K tokens).\n"
            f"Please wait a few hours or try again tomorrow.",
            wait_seconds
        )

    return None, 0


def _call_vision_model_with_retry(client, mime, image_data, use_advanced_params, max_retries=2):
    """
    Wraps the API call with retry logic + proper rate limit handling.
    """

    for attempt in range(max_retries):
        try:
            response = _call_vision_model(client, mime, image_data, use_advanced_params)
            return response

        except Exception as e:

            message, wait_seconds = _handle_rate_limit_error(str(e), attempt=attempt)

            if message:
                # This is a rate limit error — don't retry, just tell user
                return None  # Signal the caller that we hit a rate limit

            # If it's not a rate limit error, maybe retry once
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # exponential backoff: 2, 4 seconds
                continue

            # All retries exhausted, raise the error
            raise

    return None

# ==========================================================
# VISION MODEL
# ==========================================================
# BUG FIX: old value ("llama-3.3-70b-versatile") was a text-only
# model, so image detection could never actually work.
#
# This is Groq's current vision-capable model (checked July 2026):
#   qwen/qwen3.6-27b
#
# Groq retires/renames models often. If this ever stops working,
# check the live list here: https://console.groq.com/docs/vision
# Backup option: "meta-llama/llama-4-scout-17b-16e-instruct"
# ==========================================================

VISION_MODEL = "qwen/qwen3.6-27b"


# ==========================================================
# DETECTOR PROMPT
# ==========================================================
# IMPORTANT BIAS: calling a fake image "REAL" is a much worse
# mistake than being overly cautious about a real photo. So the
# model is explicitly told to lean cautious and only say REAL
# when it is very confident.
# ==========================================================

DETECTOR_PROMPT = """
You are a strict, cautious AI image forensic analyst.

Your top priority: NEVER confidently call an AI-generated image "REAL".
Missing a fake is a much worse mistake than being overly cautious
about a real photo.

Rules:
- If you notice ANY artifact, inconsistency, or "too smooth/perfect" pattern, do NOT say REAL.
- Only say REAL if you are highly confident (90+) there are zero red flags.
- If you are not fully sure either way, say UNCERTAIN instead of guessing REAL.

Check carefully for: hands and fingers, eyes, teeth, hair, skin texture,
text quality, lighting, shadows, reflections, background consistency,
perspective, object boundaries.

Respond with ONLY a single valid JSON object — no markdown fences, no
extra words, no step-by-step thinking, nothing before or after it.
Use exactly this shape:

{
  "verdict": "REAL" or "AI_GENERATED" or "UNCERTAIN",
  "confidence": <integer from 0 to 100>,
  "reason": "<one or two sentence explanation>",
  "clues": ["<short clue>", "<short clue>", "<short clue>"]
}

Keep "clues" to at most 5 short bullet points.
"""

# ==========================================================
# IMAGE -> BASE64
# ==========================================================

def image_to_base64(image_path):

    extension = image_path.lower().split(".")[-1]

    mime_types = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "gif": "image/gif",
        "bmp": "image/bmp"
    }

    mime = mime_types.get(extension, "image/jpeg")

    with open(image_path, "rb") as image_file:
        encoded = base64.b64encode(
            image_file.read()
        ).decode("utf-8")

    return encoded, mime

# ==========================================================
# NORMALIZE VERDICT TEXT
# ==========================================================
# The model can phrase the verdict slightly differently
# (e.g. "AI-GENERATED" vs "AI_GENERATED"). This makes sure we
# never mis-read a fake verdict just because of formatting.
# ==========================================================

def normalize_verdict(raw):

    v = raw.upper().replace("-", "_").replace(" ", "_")

    if "UNCERTAIN" in v or "UNSURE" in v or "UNKNOWN" in v:
        return "UNCERTAIN"

    if "AI" in v and "GENERAT" in v:
        return "AI_GENERATED"

    if "REAL" in v:
        return "REAL"

    return "UNCERTAIN"

# ==========================================================
# SAFETY NET
# ==========================================================
# a REAL verdict with low confidence gets downgraded to
# UNCERTAIN instead of being shown as a confident REAL.
# This is the main "don't call a fake image real" guard.
# ==========================================================

def _apply_safety_net(result):

    if result["verdict"] == "REAL" and result["confidence"] < 75:
        result["verdict"] = "UNCERTAIN"
        result["reason"] = (
            "Leaning real, but confidence was too low to be certain. "
            + result["reason"]
        )

    return result

# ==========================================================
# RESPONSE PARSER
# ==========================================================
# Tries structured JSON first (the format we asked for).
# Falls back to the older line-based format only if the model
# ignores JSON mode for some reason. "parse_failed" tells the
# caller whether we actually understood the model's answer or
# not, so a technical hiccup is never shown as if it were a
# genuine "uncertain" verdict.
# ==========================================================

def parse_response(text):

    result = {
        "verdict": "UNCERTAIN",
        "confidence": 0,
        "reason": "No explanation returned.",
        "clues": [],
        "parse_failed": True
    }

    # ------------------------------------------------------
    # ATTEMPT 1: JSON (expected format)
    # ------------------------------------------------------
    try:
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE).strip()

        data = json.loads(cleaned)

        result["verdict"] = normalize_verdict(str(data.get("verdict", "")))

        try:
            result["confidence"] = max(0, min(100, int(data.get("confidence", 0))))
        except (TypeError, ValueError):
            result["confidence"] = 0

        reason = str(data.get("reason", "")).strip()
        result["reason"] = reason if reason else "No explanation returned."

        clues = data.get("clues", [])
        if isinstance(clues, list):
            result["clues"] = [str(c).strip() for c in clues if str(c).strip()][:5]

        result["parse_failed"] = False

        return _apply_safety_net(result)

    except (json.JSONDecodeError, TypeError, AttributeError):
        pass

    # ------------------------------------------------------
    # ATTEMPT 2: legacy "VERDICT: / CONFIDENCE: / REASON:" format
    # (kept as a fallback in case the model ever ignores JSON mode)
    # ------------------------------------------------------
    found_anything = False
    in_clues_section = False

    for line in text.splitlines():

        line = line.strip()

        if not line:
            continue

        upper = line.upper()

        if upper.startswith("VERDICT:"):
            result["verdict"] = normalize_verdict(line.split(":", 1)[1].strip())
            found_anything = True
            in_clues_section = False

        elif upper.startswith("CONFIDENCE:"):
            numbers = re.findall(r"\d+", line)
            if numbers:
                result["confidence"] = min(int(numbers[0]), 100)
                found_anything = True
            in_clues_section = False

        elif upper.startswith("REASON:"):
            result["reason"] = line.split(":", 1)[1].strip()
            found_anything = True
            in_clues_section = False

        elif upper.startswith("CLUES"):
            in_clues_section = True

        elif line.startswith("-") and in_clues_section:
            clue = line[1:].strip()
            if clue:
                result["clues"].append(clue)

    result["parse_failed"] = not found_anything

    return _apply_safety_net(result)


# ==========================================================
# FORMAT RESULT
# ==========================================================

def format_result(result):

    verdict = result["verdict"]
    confidence = result["confidence"]
    reason = result["reason"]
    clues = result["clues"]

    # If we genuinely couldn't understand the model's response at all
    # (not even a verdict line/field), say so honestly instead of
    # presenting an empty result as if it were a real "uncertain" call.
    if result.get("parse_failed"):
        return (
            "⚠️ Aiko couldn't get a clean read on this image this time "
            "(the AI's response came back in an unexpected format).\n\n"
            "This isn't a verdict about the photo — it's a technical hiccup. "
            "Please try again."
        )

    if verdict == "REAL":
        heading = f"✅ REAL IMAGE\nConfidence: {confidence}%"

    elif verdict == "AI_GENERATED":
        heading = f"🤖 AI-GENERATED IMAGE\nConfidence: {confidence}%"

    else:
        heading = f"❓ UNCERTAIN\nConfidence: {confidence}%"

    output = heading + "\n\n"

    output += "Reason:\n"
    output += reason + "\n"

    if clues:

        output += "\nMain Clues:\n"

        for clue in clues:
            output += f"• {clue}\n"

    output += "\n⚠️ Note: No AI detector is 100% accurate. Treat this as a helpful estimate, not proof."

    return output


# ==========================================================
# DETECT IMAGE
# ==========================================================

def _build_messages(mime, image_data):
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": DETECTOR_PROMPT
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime};base64,{image_data}"
                    }
                }
            ]
        }
    ]


def _call_vision_model(client, mime, image_data, use_advanced_params):

    kwargs = dict(
        model=VISION_MODEL,
        temperature=0,
        messages=_build_messages(mime, image_data)
    )

    if use_advanced_params:
        # Preferred path: disable "thinking" rambling + force clean JSON.
        kwargs["max_tokens"] = 700
        kwargs["reasoning_effort"] = "none"
        kwargs["response_format"] = {"type": "json_object"}
    else:
        # Fallback path: in case Groq ever rejects those params for this
        # model, give it a much bigger token budget instead so a "thinking"
        # response still has room to reach the actual answer.
        kwargs["max_tokens"] = 1500

    return client.chat.completions.create(**kwargs)


def detect_ai_image(image_path):

    if not API_KEY:
        return "❌ GROQ_API_KEY not found inside .env"

    if not os.path.exists(image_path):
        return "❌ Image file not found."

    image_data, mime = image_to_base64(image_path)

    client = OpenAI(
        api_key=API_KEY,
        base_url="https://api.groq.com/openai/v1"
    )

    response = None
    last_error = None

    # Try with advanced params first (JSON + reasoning_effort=none)
    try:
        response = _call_vision_model_with_retry(client, mime, image_data, use_advanced_params=True, max_retries=2)
    except Exception as e:
        last_error = e

    # If we got a rate limit signal, return the informative message
    if response is None and last_error:
        message, _ = _handle_rate_limit_error(str(last_error))
        if message:
            return message

    # If no response yet, try fallback (bigger token budget, no JSON mode)
    if response is None:
        try:
            response = _call_vision_model_with_retry(client, mime, image_data, use_advanced_params=False, max_retries=1)
        except Exception as e2:
            message, _ = _handle_rate_limit_error(str(e2))
            if message:
                return message

            return (
                "❌ Photo Analysis Failed\n\n"
                f"{last_error or e2}"
            )

    # If still no response (both attempts failed), something's wrong
    if response is None:
        return (
            "⏳ Photo analysis is taking too long.\n\n"
            "This might mean:\n"
            "• Rate limit was hit (too many photos today)\n"
            "• Network issue\n"
            "• Groq service is slow\n\n"
            "Please wait a moment and try again."
        )

    if (
        not response.choices
        or response.choices[0].message is None
        or response.choices[0].message.content is None
    ):
        return "❌ Vision model returned an empty response."

    raw_response = response.choices[0].message.content

    parsed = parse_response(raw_response)

    return format_result(parsed)


# ==========================================================
# LOCAL TEST
# ==========================================================

if __name__ == "__main__":

    print("AIKO PHOTO DETECTOR")

    path = input("Image Path: ").strip()

    print()

    print(detect_ai_image(path))
