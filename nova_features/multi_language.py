# ==========================================
# NOVA FEATURES - MULTI-LANGUAGE (real implementation)
# ------------------------------------------
# Language detection via Unicode script ranges + Hinglish word
# markers (pure Python, zero dependencies, fully offline).
#
# Translation uses Nova's existing LLM brain (brain.llm_chat) for
# high-quality results and falls back to the enhanced_translation
# offline dictionary when every provider is unavailable, so the
# feature NEVER hard-fails.
# ==========================================

import logging
import re

log = logging.getLogger("nova.multi_language")

__version__ = "2.0.0"

# ---- Unicode script ranges (start, end) ------------------------------------
_SCRIPT_RANGES = {
    "hindi": [(0x0900, 0x097F)],            # Devanagari
    "arabic": [(0x0600, 0x06FF), (0x0750, 0x077F)],
    "hebrew": [(0x0590, 0x05FF)],
    "cyrillic": [(0x0400, 0x04FF)],
    "greek": [(0x0370, 0x03FF)],
    "japanese": [(0x3040, 0x309F), (0x30A0, 0x30FF)],
    "korean": [(0xAC00, 0xD7AF), (0x1100, 0x11FF)],
    "chinese": [(0x4E00, 0x9FFF)],
}

# Common romanised-Hindi (Hinglish) markers.
_HINGLISH_WORDS = {
    "kaise", "kaisa", "kaisi", "kya", "kyu", "kyun", "hai", "hain", "ho",
    "karo", "karna", "kar", "nahi", "nahin", "acha", "accha", "theek",
    "aur", "ya", "mein", "mai", "mera", "meri", "tera", "teri",
    "bhai", "behen", "kaam", "padhai", "padh", "khana", "pani", "kal",
    "aaj", "subah", "raat", "bilkul", "matlab", "sach", "bhaiya",
}

_LANGUAGE_NAMES = {
    "en": "English", "hi": "Hindi", "hinglish": "Hinglish",
    "arabic": "Arabic", "hebrew": "Hebrew", "cyrillic": "Russian/Cyrillic",
    "greek": "Greek", "japanese": "Japanese", "korean": "Korean",
    "chinese": "Chinese",
}


def _script_counts(text):
    counts = {}
    for ch in text:
        code = ord(ch)
        for lang, ranges in _SCRIPT_RANGES.items():
            for start, end in ranges:
                if start <= code <= end:
                    counts[lang] = counts.get(lang, 0) + 1
                    break
    return counts


def detect_language(text):
    """Detect the language of *text*.

    Returns a dict: {success, detected, confidence, message}.
    Pure-Python and offline - safe to call from anywhere.
    """
    if not text or not str(text).strip():
        return {
            "success": True, "feature": "multi_language",
            "detected": "unknown", "confidence": 0.0,
            "message": "No text given.",
        }
    text = str(text)

    counts = _script_counts(text)
    letters = sum(counts.values())

    # 1. A dominant non-Latin script wins outright.
    if letters:
        best = max(counts, key=counts.get)
        confidence = min(0.99, counts[best] / max(letters, 1))
        if confidence >= 0.5:
            name = _LANGUAGE_NAMES.get(best, best)
            return {
                "success": True, "feature": "multi_language",
                "detected": best, "confidence": round(confidence, 2),
                "message": f"Detected {name} ({best}) by script.",
            }

    # 2. Latin script -> english or hinglish via marker words.
    lowered = text.lower()
    words = set(re.findall(r"[a-z]+", lowered))
    hits = words & _HINGLISH_WORDS
    if hits and len(hits) / max(len(words), 1) >= 0.2:
        return {
            "success": True, "feature": "multi_language",
            "detected": "hinglish",
            "confidence": round(min(0.95, 0.4 + 0.6 * len(hits) / max(len(words), 1)), 2),
            "markers": sorted(hits)[:8],
            "message": f"Detected Hinglish (markers: {', '.join(sorted(hits)[:4])}...).",
        }
    return {
        "success": True, "feature": "multi_language",
        "detected": "english" if not letters else "english/mixed",
        "confidence": 0.8,
        "message": "Detected English (Latin script).",
    }

def _llm_translate(text, target_language):
    """Translate through the LLM brain. Returns translated string or None."""
    try:
        import brain  # local module, lazy import keeps this file standalone
    except Exception:
        return None
    system = (
        "You are a precise translator. Translate the user's text into "
        f"{target_language}. Reply with ONLY the translation - no quotes, "
        "no explanation, no transliteration notes. Preserve tone and emoji."
    )
    try:
        result, _used = brain.llm_chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
            max_tokens=400,
            temperature=0.2,
        )
        return result.strip() if isinstance(result, str) and result.strip() else None
    except Exception as exc:
        log.warning("LLM translate failed: %s", exc)
        return None


def _dictionary_translate(text, target_code):
    """Offline fallback using enhanced_translation's dictionary."""
    try:
        from nova_features.enhanced_translation import (
            detect_and_translate,
            translate_hinglish_to_english,
        )
    except Exception:
        return None
    try:
        if target_code == "en":
            det = detect_language(text).get("detected", "")
            if det == "hinglish":
                return translate_hinglish_to_english(text).get("to_text")
            return None  # english->english needs no translation
        # default: anything -> hindi via the offline dictionary path
        return detect_and_translate(text).get("to_text")
    except Exception:
        return None


def _target_name(code_or_name):
    code = (code_or_name or "hi").strip().lower()
    aliases = {
        "hindi": "Hindi", "hi": "Hindi",
        "english": "English", "en": "English",
        "hinglish": "Hinglish (romanised Hindi)",
        "spanish": "Spanish", "es": "Spanish",
        "french": "French", "fr": "French",
        "german": "German", "de": "German",
        "arabic": "Arabic", "ar": "Arabic",
        "japanese": "Japanese", "ja": "Japanese",
        "korean": "Korean", "ko": "Korean",
        "chinese": "Chinese (Simplified)", "zh": "Chinese (Simplified)",
        "marathi": "Marathi", "mr": "Marathi",
        "tamil": "Tamil", "ta": "Tamil",
        "telugu": "Telugu", "te": "Telugu",
        "gujarati": "Gujarati", "gu": "Gujarati",
        "bengali": "Bengali", "bn": "Bengali",
    }
    return aliases.get(code, code_or_name.title() if code_or_name else "Hindi")


def translate_text(text, target="hi"):
    """Translate *text* to *target* language.

    Chain: LLM brain -> offline dictionary -> passthrough. Always returns
    a usable dict; never raises for ordinary input problems.
    """
    if not text or not str(text).strip():
        return {
            "success": False, "feature": "multi_language",
            "from_text": text or "", "to_text": "",
            "message": "No text to translate.",
        }
    text = str(text)
    target_name = _target_name(target)
    detection = detect_language(text)

    translated = _llm_translate(text, target_name)
    engine = "llm"
    if translated is None:
        translated = _dictionary_translate(text, target.lower())
        engine = "offline-dictionary"
    if translated is None or not str(translated).strip():
        return {
            "success": False, "feature": "multi_language",
            "detected": detection.get("detected"),
            "from_text": text, "to_text": text,
            "engine": "passthrough",
            "message": "⚠️ Translation unavailable right now - returning original text.",
        }

    return {
        "success": True,
        "feature": "multi_language",
        "detected": detection.get("detected"),
        "target": target_name,
        "engine": engine,
        "from_text": text,
        "to_text": translated,
        "message": f"Translated {detection.get('detected')} → {target_name} ({engine}).",
    }


def translate_to_hindi(text):
    """Backward-compatible wrapper used by features_launcher."""
    return translate_text(text, target="hi")


def get_supported_languages():
    return {
        "success": True,
        "feature": "multi_language",
        "detectable": ["english", "hindi", "hinglish", "arabic", "hebrew",
                       "cyrillic", "greek", "japanese", "korean", "chinese"],
        "translatable_via_llm": [
            "Hindi", "English", "Spanish", "French", "German", "Arabic",
            "Japanese", "Korean", "Chinese", "Marathi", "Tamil", "Telugu",
            "Gujarati", "Bengali",
        ],
        "message": "Detection is offline; translation uses Nova's LLM brain "
                   "with an offline dictionary fallback.",
    }


__all__ = ["detect_language", "translate_text", "translate_to_hindi",
           "get_supported_languages"]