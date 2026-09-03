"""check_keys.py - one-shot LIVE health check for every Nova AI provider.

Run:  .venv\\Scripts\\python.exe check_keys.py
Tests the EXACT models/features the app uses (no mocks):
  1. Groq chat  (brain.py ask_nova -> MODEL)
  2. Groq vision(photo_detector.py -> qwen/qwen3.6-27b, 16x16 test image)
  3. Gemini     (nova_vision.py fallback chain, text-only ping per model)
  4. plyer      (native Windows notification - a real toast will appear)
"""
import base64
import io
import os
import time

import requests
from dotenv import load_dotenv
from PIL import Image

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

GEMINI_FALLBACKS = ["gemini-flash-latest", "gemini-flash-lite-latest",
                    "gemini-3-flash-preview"]


def groq_chat():
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
            json={"model": os.getenv("NOVA_MODEL", "openai/gpt-oss-20b"),
                  "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                  "max_tokens": 200},
            timeout=60)
        if r.status_code == 200:
            return f"OK - {r.json()['choices'][0]['message']['content'][:20]!r}"
        return f"FAIL HTTP {r.status_code}: {r.text[:120]}"
    except Exception as e:
        return f"FAIL {type(e).__name__}: {e}"


def groq_vision():
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), (200, 30, 30)).save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
            json={"model": "qwen/qwen3.6-27b",
                  "messages": [{"role": "user", "content": [
                      {"type": "text", "text": "What color? One word."},
                      {"type": "image_url",
                       "image_url": {"url": f"data:image/png;base64,{b64}"}}]}],
                  "temperature": 0, "max_tokens": 300},
            timeout=60)
        if r.status_code == 200:
            return f"OK - {r.json()['choices'][0]['message']['content'][:30]!r}"
        return f"FAIL HTTP {r.status_code}: {r.text[:120]}"
    except Exception as e:
        return f"FAIL {type(e).__name__}: {e}"


def gemini_chain():
    results = []
    for model in GEMINI_FALLBACKS:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": os.getenv("GEMINI_API_KEY")},
                json={"contents": [{"parts": [{"text": "Reply with exactly: OK"}]}],
                      "generationConfig": {"maxOutputTokens": 200}},
                timeout=60)
            if r.status_code == 200:
                results.append(f"{model}=OK")
            else:
                err = r.json().get("error", {}).get("message", "")[:60]
                results.append(f"{model}=HTTP {r.status_code} ({err})")
            time.sleep(1)
        except Exception as e:
            results.append(f"{model}=EXC {type(e).__name__}")
    return " | ".join(results)


def native_notification():
    try:
        from plyer import notification
        notification.notify(title="Nova AI", message="check_keys: notification test",
                            app_name="Nova AI", timeout=8)
        return "OK - toast fired"
    except Exception as e:
        return f"FAIL {type(e).__name__}: {e} (reminders will use in-app popup)"


if __name__ == "__main__":
    print("1. Groq chat (brain.py MODEL):", groq_chat())
    print("2. Groq vision (photo_detector):", groq_vision())
    print("3. Gemini fallback chain:", gemini_chain())
    print("4. Native notification:", native_notification())










