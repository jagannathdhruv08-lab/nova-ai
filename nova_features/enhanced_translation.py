# Simple offline English -> Hindi translation dictionary
# Covers common words/phrases. Not exhaustive, but real translation.

EN_TO_HI = {
    "hello": "नमस्ते", "hi": "नमस्ते", "good": "अच्छा", "morning": "सुबह",
    "evening": "शाम", "night": "रात", "how": "कैसे", "are": "हैं", "you": "आप",
    "thank": "धन्यवाद", "thanks": "शुक्रिया", "please": "कृपया", "yes": "हाँ",
    "no": "नहीं", "i": "मैं", "am": "हूँ", "fine": "ठीक", "name": "नाम",
    "my": "मेरा", "your": "आपका", "friend": "दोस्त", "family": "परिवार",
    "love": "प्यार", "happy": "खुश", "sad": "उदास", "today": "आज",
    "tomorrow": "कल", "yesterday": "बीता कल", "time": "समय", "day": "दिन",
    "work": "काम", "school": "स्कूल", "home": "घर", "book": "किताब",
    "water": "पानी", "food": "खाना", "eat": "खाना", "drink": "पीना",
    "study": "पढ़ना", "learn": "सीखना", "sleep": "सोना", "go": "जाना",
    "come": "आना", "help": "मदद", "goodbye": "अलविदा", "bye": "अलविदा",
    "welcome": "स्वागत",
}

HINGLISH_OVERRIDES = {
    "kaise": "how", "hai": "is", "kya": "what", "karo": "do", "ho": "are",
    "kya kar rahe ho": "what are you doing", "theek": "fine",
    "acha": "good", "accha": "good", "nahi": "no", "main": "I",
    "mein": "in", "aur": "and", "ya": "or", "chahie": "want",
    "mera": "my", "tera": "your", "bhai": "brother", "behen": "sister",
    "kaam": "work", "padhai": "study", "khana": "food",
}


def translate_english_to_hindi(text):
    """Translate English text to Hindi using the offline dictionary."""
    if not text:
        return {"success": True, "feature": "enhanced_translation",
                "from_text": "", "to_text": "", "message": ""}
    words = text.lower().split()
    result = []
    translated_count = 0
    for word in words:
        # remove punctuation
        clean = word.strip(".,!?;:")
        punct = word[len(clean):] if len(clean) < len(word) else ""
        if clean in EN_TO_HI:
            result.append(EN_TO_HI[clean] + punct)
            translated_count += 1
        else:
            result.append(word)
    return {
        "success": True,
        "feature": "enhanced_translation",
        "from": "en", "to": "hi",
        "from_text": text,
        "to_text": " ".join(result),
        "translated_words": translated_count,
        "message": f"Translated {translated_count} word(s) to Hindi (dictionary)",
    }


def translate_hinglish_to_english(text):
    """Translate Hinglish (Romanized Hindi) to English."""
    if not text:
        return {"success": True, "feature": "enhanced_translation",
                "from_text": "", "to_text": "", "message": ""}
    lowered = text.lower().strip()
    # Try whole-phrase overrides first
    for phrase, eng in HINGLISH_OVERRIDES.items():
        if phrase in lowered:
            lowered = lowered.replace(phrase, eng)
    return {
        "success": True,
        "feature": "enhanced_translation",
        "from": "hinglish", "to": "en",
        "from_text": text,
        "to_text": lowered,
        "message": "Translated to English (hinglish dictionary)",
    }


def detect_and_translate(text):
    """Detect language and translate accordingly."""
    if not text:
        return {"success": True, "feature": "enhanced_translation",
                "from_text": "", "to_text": "", "detected": "unknown"}
    # Check if text contains Devanagari characters
    has_devanagari = any('\u0900' <= ch <= '\u097F' for ch in text)
    # Check for common Hinglish words
    lowered = text.lower()
    is_hinglish = any(w in lowered for w in ["kaise", "kya", "hai", "karo", "nahi", "acha"])

    if has_devanagari:
        return {"success": True, "feature": "enhanced_translation",
                "detected": "hindi", "to_text": text,
                "message": "Text already in Hindi (Devanagari)"}
    if is_hinglish:
        result = translate_hinglish_to_english(text)
        result["detected"] = "hinglish"
        return result
    result = translate_english_to_hindi(text)
    result["detected"] = "english"
    return result


def get_supported_languages():
    return {
        "success": True,
        "feature": "enhanced_translation",
        "supported": ["en", "hi", "hinglish"],
        "description": "English, Hindi (Devanagari), and Hinglish (Romanized Hindi)",
    }


__version__ = "2.0.0"
__all__ = ["translate_english_to_hindi", "translate_hinglish_to_english",
           "detect_and_translate", "get_supported_languages"]
