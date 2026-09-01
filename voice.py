import asyncio
try:
    import pygame
except ImportError:
    pygame = None
import tempfile
import os
import time
try:
    import speech_recognition as sr  # type: ignore[import]
    SR_AVAILABLE = True
    SR_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - optional dependency
    sr = None
    SR_AVAILABLE = False
    SR_IMPORT_ERROR = str(exc)

try:
    import sounddevice as sd  # type: ignore[import]
    import numpy as np  # type: ignore[import]
    SOUNDDEVICE_AVAILABLE = True
    SOUNDDEVICE_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - optional dependency
    sd = None
    np = None
    SOUNDDEVICE_AVAILABLE = False
    SOUNDDEVICE_IMPORT_ERROR = str(exc)

try:
    import edge_tts  # type: ignore[import]
    EDGE_TTS_AVAILABLE = True
except Exception as exc:  # noqa: BLE001
    # Catch all failures (not just ImportError) so a broken transitive
    # dependency never crashes the app on startup.
    edge_tts = None
    EDGE_TTS_AVAILABLE = False
    print("Warning: edge_tts not available. Install with: pip install edge_tts  |", exc)

VOICE = "en-IN-neerjaNeural"
if pygame is not None:
    try:
        pygame.mixer.init()
    except Exception as exc:
        print("Warning: pygame mixer could not initialize:", exc)

VOICE_ENABLED = True
LAST_LISTEN_ERROR = ""
LAST_LISTEN_DETAILS = ""

def mute_voice():
    global VOICE_ENABLED
    VOICE_ENABLED = False

def unmute_voice():
    global VOICE_ENABLED
    VOICE_ENABLED = True

def voice_status():
    return "enabled" if VOICE_ENABLED else "muted"

def _set_listen_error(message="", details=""):
    global LAST_LISTEN_ERROR, LAST_LISTEN_DETAILS
    LAST_LISTEN_ERROR = message
    LAST_LISTEN_DETAILS = details

def get_last_listen_error():
    if LAST_LISTEN_DETAILS:
        return f"{LAST_LISTEN_ERROR} ({LAST_LISTEN_DETAILS})"
    return LAST_LISTEN_ERROR

def list_microphones():
    if not SR_AVAILABLE:
        return []
    try:
        names = sr.Microphone.list_microphone_names()
        if names:
            return names
    except Exception:
        pass
    if SOUNDDEVICE_AVAILABLE:
        try:
            devices = sd.query_devices()
            return [
                device["name"] for device in devices
                if int(device.get("max_input_channels", 0)) > 0
            ]
        except Exception:
            return []
    return []

def _pyaudio_microphone_available():
    if not SR_AVAILABLE:
        return False
    try:
        return bool(sr.Microphone.list_microphone_names())
    except Exception:
        return False

def microphone_status():
    if not SR_AVAILABLE:
        return f"SpeechRecognition import failed: {SR_IMPORT_ERROR or 'not installed'}"
    names = list_microphones()
    if not names:
        if SOUNDDEVICE_AVAILABLE:
            return "No microphone devices found. Check Windows microphone permission and default input."
        return "No microphone backend found. Install PyAudio or sounddevice, then allow microphone access."
    backend = "PyAudio/SpeechRecognition" if _pyaudio_microphone_available() else "sounddevice fallback"
    return f"{len(names)} microphone device(s) found via {backend}: {', '.join(names[:4])}"

# ==========================================
# EMOTION DETECTION
# ==========================================

EMOTION_PROFILES = {
    "happy":   {"rate": "+15%", "pitch": "+20Hz"},
    "sad":     {"rate": "-10%", "pitch": "-15Hz"},
    "angry":   {"rate": "+10%", "pitch": "+5Hz"},
    "excited": {"rate": "+20%", "pitch": "+25Hz"},
    "calm":    {"rate": "-5%",  "pitch": "-5Hz"},
    "neutral": {"rate": "+0%",  "pitch": "+0Hz"},
}

def detect_emotion(text):
    text_lower = text.lower()

    happy_words = ["😄", "🎉", "great", "awesome", "yay", "nice", "happy", "congrat"]
    sad_words = ["💔", "😢", "sorry", "sad", "unfortunately", "miss you"]
    angry_words = ["😡", "angry", "annoyed", "frustrat"]
    excited_words = ["🚀", "✨", "wow", "amazing", "let's go", "incredible"]
    calm_words = ["calm", "relax", "peace", "gentle"]

    if any(w in text_lower for w in happy_words):
        return "happy"
    elif any(w in text_lower for w in sad_words):
        return "sad"
    elif any(w in text_lower for w in angry_words):
        return "angry"
    elif any(w in text_lower for w in excited_words):
        return "excited"
    elif any(w in text_lower for w in calm_words):
        return "calm"
    else:
        return "neutral"

# ==========================================
# SPEAK FUNCTION (emotion-aware)
# ==========================================

def speak(text, emotion=None):
    if not VOICE_ENABLED:
        return

    if not EDGE_TTS_AVAILABLE:
        print("TTS unavailable: edge_tts package not installed.")
        return

    if pygame is None:
        print("TTS unavailable: pygame package not installed.")
        return

    if emotion is None:
        emotion = detect_emotion(text)

    profile = EMOTION_PROFILES.get(emotion, EMOTION_PROFILES["neutral"])

    async def generate():
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            filename = f.name

        communicate = edge_tts.Communicate(
            text=text,
            voice=VOICE,
            rate=profile["rate"],
            pitch=profile["pitch"]
        )
        await communicate.save(filename)
        return filename

    try:
        filename = asyncio.run(generate())
        pygame.mixer.music.load(filename)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)

        pygame.mixer.music.unload()
        os.remove(filename)
    except Exception as e:
        print("TTS Error:", e)

# ==========================================
# LISTEN FUNCTION (with PyAudio + sounddevice fallback)
# ==========================================
# listen() below is the single, active voice-listening entry point used
# by gui.py and test_mic.py. It prefers the SpeechRecognition/PyAudio mic
# and falls back to a sounddevice recording if PyAudio cannot open the
# selected device. The earlier no-argument listen() was a shadowed
# duplicate (Python keeps the last definition) and has been removed.


def _record_with_sounddevice(timeout=7, phrase_time_limit=10, sample_rate=16000):
    if not SOUNDDEVICE_AVAILABLE:
        raise RuntimeError(SOUNDDEVICE_IMPORT_ERROR or "sounddevice is not installed")

    duration = max(1, min(timeout, 2) + phrase_time_limit)
    print("Listening with sounddevice fallback...")
    recording = sd.rec(
        int(duration * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
    )
    sd.wait()

    audio = recording.reshape(-1)
    if np is not None:
        peak = int(np.max(np.abs(audio))) if audio.size else 0
        if peak < 250:
            raise sr.WaitTimeoutError("recorded audio was nearly silent")

    return sr.AudioData(audio.tobytes(), sample_rate, 2)


def _recognize_audio(recognizer, audio, language):
    try:
        return recognizer.recognize_google(audio, language=language)
    except sr.UnknownValueError:
        if language != "en-US":
            return recognizer.recognize_google(audio, language="en-US")
        raise


# Active voice-listening entry point (used by gui.py and test_mic.py).
# Prefers the SpeechRecognition/PyAudio microphone and falls back to
# a sounddevice recording if PyAudio cannot open the selected device.
def listen(language="en-IN", timeout=7, phrase_time_limit=10):
    _set_listen_error()

    if not SR_AVAILABLE:
        _set_listen_error(
            "SpeechRecognition is not available",
            SR_IMPORT_ERROR or "Install with: py -m pip install SpeechRecognition",
        )
        print(get_last_listen_error())
        return ""

    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 0.8

    try:
        mic_index_raw = os.getenv("NOVA_MIC_INDEX", "").strip()
        mic_index = int(mic_index_raw) if mic_index_raw else None
    except ValueError:
        mic_index = None

    try:
        with sr.Microphone(device_index=mic_index) as source:
            print("Listening...")
            recognizer.adjust_for_ambient_noise(source, duration=0.8)
            audio = recognizer.listen(
                source,
                timeout=timeout,
                phrase_time_limit=phrase_time_limit,
            )
            print("Processing...")
            command = _recognize_audio(recognizer, audio, language)
            print("You said:", command)
            return command.lower()
    except sr.WaitTimeoutError:
        _set_listen_error("No speech detected", "Try speaking closer to the microphone.")
        print(get_last_listen_error())
        return ""
    except sr.UnknownValueError:
        _set_listen_error("Speech was heard but not understood", "Try again with less background noise.")
        print(get_last_listen_error())
        return ""
    except sr.RequestError as exc:
        _set_listen_error("Speech recognition service failed", str(exc))
        print(get_last_listen_error())
        return ""
    except AttributeError as exc:
        print("PyAudio microphone backend missing; trying sounddevice fallback.", exc)
        try:
            audio = _record_with_sounddevice(timeout, phrase_time_limit)
            command = _recognize_audio(recognizer, audio, language)
            print("You said:", command)
            return command.lower()
        except Exception as fallback_exc:
            _set_listen_error(
                "Microphone backend is missing",
                f"PyAudio failed and sounddevice fallback failed: {fallback_exc}",
            )
            print(get_last_listen_error())
            return ""
    except OSError as exc:
        print("PyAudio microphone could not open; trying sounddevice fallback.", exc)
        try:
            audio = _record_with_sounddevice(timeout, phrase_time_limit)
            command = _recognize_audio(recognizer, audio, language)
            print("You said:", command)
            return command.lower()
        except Exception as fallback_exc:
            _set_listen_error(
                "Microphone could not be opened",
                f"{exc}. Sounddevice fallback failed: {fallback_exc}",
            )
            print(get_last_listen_error())
            return ""
    except Exception as exc:
        _set_listen_error("Voice listening failed", str(exc))
        print(get_last_listen_error())
        time.sleep(0.2)
        return ""
