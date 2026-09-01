"""Tests for nova_features/multi_language.py (detection + translation)."""
import pytest

from nova_features import multi_language as ml


# ---------------------------------------------------------------------------
# detection - pure offline logic
# ---------------------------------------------------------------------------
def test_detect_english():
    assert ml.detect_language("Hello world, how are you?")["detected"] == "english"


def test_detect_hindi_script():
    result = ml.detect_language("नमस्ते दोस्त, कैसे हो?")
    assert result["detected"] == "hindi"
    assert result["confidence"] >= 0.5


def test_detect_hinglish():
    result = ml.detect_language("kaise ho bhai, khana kha liya?")
    assert result["detected"] == "hinglish"
    assert "kaise" in result["markers"]


def test_detect_arabic_and_cyrillic_scripts():
    assert ml.detect_language("مرحبا كيف حالك")["detected"] == "arabic"
    assert ml.detect_language("Привет мир")["detected"] == "cyrillic"


def test_detect_empty_input():
    result = ml.detect_language("   ")
    assert result["detected"] == "unknown"


def test_plain_english_is_not_hinglish():
    # 'main'/'kar' style false positives must not fire on normal English
    result = ml.detect_language("The merchant navy sails across oceans")
    assert result["detected"] != "hinglish"


# ---------------------------------------------------------------------------
# translation chain: LLM -> dictionary -> passthrough
# ---------------------------------------------------------------------------
def test_translate_uses_llm_when_available(monkeypatch):
    monkeypatch.setattr(ml, "_llm_translate",
                        lambda text, target: "नमस्ते" if text else None)
    result = ml.translate_text("hello", target="hi")
    assert result["success"] is True
    assert result["to_text"] == "नमस्ते"
    assert result["engine"] == "llm"


def test_translate_falls_back_to_offline_dictionary(monkeypatch):
    monkeypatch.setattr(ml, "_llm_translate", lambda text, target: None)
    result = ml.translate_text("hello my friend", target="hi")
    # offline path may or may not translate every word, but never fails hard
    assert isinstance(result.get("to_text"), str)


def test_translate_passthrough_when_all_engines_fail(monkeypatch):
    monkeypatch.setattr(ml, "_llm_translate", lambda t, g: None)
    monkeypatch.setattr(ml, "_dictionary_translate", lambda t, c: None)
    result = ml.translate_text("something unique", target="hi")
    assert result["success"] is False
    assert result["to_text"] == "something unique"
    assert result["engine"] == "passthrough"


def test_translate_empty_text():
    result = ml.translate_text("", target="hi")
    assert result["success"] is False


def test_backward_compat_wrapper(monkeypatch):
    monkeypatch.setattr(ml, "_llm_translate", lambda text, target: "धन्यवाद")
    result = ml.translate_to_hindi("thank you")
    assert result["success"] is True


def test_supported_languages_catalog():
    langs = ml.get_supported_languages()
    assert "english" in langs["detectable"]
    assert "Hindi" in langs["translatable_via_llm"]