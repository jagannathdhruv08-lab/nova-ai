# ==========================================
# NOVA VOICE ASSISTANT — Speech-to-Text + Text-to-Speech
# ==========================================
import os
import asyncio
import time


# ---------- Voice Input (Speech-to-Text) ----------
def listen_once(timeout=5):
    """Listen through microphone and return recognized text."""
    try:
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=timeout + 2)
        text = recognizer.recognize_google(audio)
        return {
            "success": True,
            "feature": "voice_assistant",
            "type": "speech_to_text",
            "text": text,
            "message": f"🎤 Suna: '{text}'",
        }
    except ImportError:
        return {"success": False, "feature": "voice_assistant",
                "message": "speech_recognition not installed. Run: pip install SpeechRecognition pyaudio"}
    except sr.WaitTimeoutError:
        return {"success": False, "feature": "voice_assistant",
                "message": "⏰ Kuch sunayi nahi diya - try again"}
    except sr.UnknownValueError:
        return {"success": False, "feature": "voice_assistant",
                "message": "😕 Samajh nahi paya - clearly boliye"}
    except Exception as e:
        return {"success": False, "feature": "voice_assistant",
                "message": f"Microphone error: {str(e)}"}


# ---------- Voice Output (Text-to-Speech) ----------
def speak_text(text):
    """Speak text aloud using edge-tts (online) or fallback to winsound."""
    try:
        # Prefer edge-tts for natural Hindi/English voices
        import edge_tts
        import asyncio

        # Detect if text has Devanagari -> use Hindi voice
        has_hindi = any('\u0900' <= ch <= '\u097F' for ch in text)
        voice = "hi-IN-MadhurNeural" if has_hindi else "en-US-JennyNeural"
        output_file = os.path.join(os.path.expanduser("~"), ".nova", "tts_output.mp3")
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        async def _generate():
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_file)

        asyncio.run(_generate())

        # Play the audio
        try:
            import winsound
            winsound.PlaySound(output_file, winsound.SND_FILENAME)
        except Exception:
            import subprocess
            subprocess.Popen(["start", output_file], shell=True)

        return {
            "success": True,
            "feature": "voice_assistant",
            "type": "text_to_speech",
            "spoken_text": text,
            "voice": voice,
            "message": f"🔊 Speaking: '{text[:40]}...'",
        }
    except Exception as e:
        # Fallback: beep-based / simple
        try:
            import winsound
            winsound.Beep(1000, 200)
        except Exception:
            pass
        return {
            "success": False,
            "feature": "voice_assistant",
            "error": str(e),
            "message": f"Voice output failed: {str(e)}",
        }


__version__ = "1.0.0"
__all__ = ["listen_once", "speak_text"]
