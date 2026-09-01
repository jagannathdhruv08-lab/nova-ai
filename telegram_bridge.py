# ==========================================
# NOVA TELEGRAM BRIDGE - talk to Nova from your phone
# ------------------------------------------
# Long-polling Telegram bot built directly on the Bot HTTP API with the
# already-installed `requests` lib (no extra dependency).
#
# Setup:
#   1. Chat with @BotFather on Telegram -> /newbot -> copy the token.
#   2. Put in .env:  TELEGRAM_BOT_TOKEN=123456:ABC...
#      Optionally:   TELEGRAM_ALLOWED_CHAT_IDS=123456789,987654321
#   3. Run:  python telegram_bridge.py
#   4. Send your bot a message; your chat id is printed once so you can
#      allow-list yourself.
#
# SECURITY MODEL:
#   * Only allow-listed chat ids get answers (empty list = nobody until
#     you add your id - the bot tells you your id on first contact).
#   * Remote requests NEVER touch file/OS actions (agent.py stays
#     local-only). Only safe intents + news/weather/chat are exposed.
#   * Per-chat rate limit: 20 messages/min.
# ==========================================

import logging
import os
import time
from collections import deque

import requests

try:
    from dotenv import load_dotenv
    _base = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(_base, ".env"))
except ImportError:
    pass

log = logging.getLogger("nova.telegram")

API_BASE = "https://api.telegram.org/bot{token}/{method}"
POLL_TIMEOUT_S = 25          # long-poll window
SEND_TIMEOUT_S = 15
RATE_LIMIT = 20              # msgs per chat per minute


class TelegramBridge:
    def __init__(self, token=None, allowed_ids=None):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        raw_ids = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "")
        if allowed_ids is not None:
            self.allowed_ids = set(allowed_ids)
        else:
            self.allowed_ids = {
                s.strip() for s in raw_ids.split(",") if s.strip().isdigit()
            }
        self._offset = 0
        self._sent_times = {}
        self.session = requests.Session()

    # ---------------- transport ----------------
    def _call(self, method, payload=None):
        url = API_BASE.format(token=self.token, method=method)
        resp = self.session.post(url, json=payload or {},
                                 timeout=(10, SEND_TIMEOUT_S))
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method}: {data.get('description')}")
        return data.get("result")

    def send(self, chat_id, text):
        # Telegram hard-caps messages at 4096 chars - split politely.
        for i in range(0, len(text), 4000):
            self._call("sendMessage", {"chat_id": chat_id,
                                       "text": text[i:i + 4000]})

    def _rate_ok(self, chat_id):
        now = time.monotonic()
        dq = self._sent_times.setdefault(chat_id, deque())
        while dq and now - dq[0] > 60:
            dq.popleft()
        if len(dq) >= RATE_LIMIT:
            return False
        dq.append(now)
        return True

    def _allowed(self, update):
        msg = update.get("message") or {}
        chat_id = str((msg.get("chat") or {}).get("id", ""))
        if not chat_id:
            return None
        if chat_id not in self.allowed_ids:
            log.warning("blocked message from chat id %s", chat_id)
            self.send(chat_id,
                      "🔒 You're not on Nova's allow-list.\n"
                      f"Your chat id: {chat_id}\n"
                      "Add it to TELEGRAM_ALLOWED_CHAT_IDS in .env.")
            return None
        return chat_id

    # ---------------- handlers (safe surface only) ----------------
    def handle(self, text):
        """Map an incoming remote message to a reply. Deliberately does
        NOT expose agent.py file/system actions."""
        text = (text or "").strip()
        lowered = text.lower()

        if lowered.startswith("/start") or lowered == "/help":
            return ("🤖 Nova Telegram Bridge\n\n"
                    "/ask <question> - chat with Nova's brain\n"
                    "/status - study snapshot\n"
                    "/due - flashcards due today\n"
                    "/exams - exam countdowns\n"
                    "/news - today's briefing\n"
                    "/weather <city> - weather\n"
                    "/remind <minutes> <text> - quick reminder\n"
                    "plain text -> treated like /ask")

        if lowered.startswith("/ask "):
            return self._safe_ask(text[5:].strip())
        if lowered.startswith("/status"):
            return self._safe_status()
        if lowered.startswith("/due"):
            return self._safe_due()
        if lowered.startswith("/exams"):
            return self._safe_exams()
        if lowered.startswith("/news"):
            return self._safe_news()
        if lowered.startswith("/weather "):
            return self._safe_weather(text[len("/weather "):].strip())
        if lowered.startswith("/remind "):
            return self._safe_remind(text[len("/remind "):].strip())
        return self._safe_ask(text)

    def _safe_ask(self, question):
        if not question:
            return "Kuch poocho! 🙂"
        try:
            import brain
            return brain.ask_nova(question)
        except Exception as exc:
            log.error("remote ask failed: %s", exc)
            return f"Brain error ({type(exc).__name__})."

    def _safe_status(self):
        try:
            import nova_analytics
            return nova_analytics.analytics_report(days=7)
        except Exception as exc:
            return f"Status unavailable ({type(exc).__name__})."

    def _safe_due(self):
        try:
            import nova_srs
            return nova_srs.review_session_summary()
        except Exception as exc:
            return f"SRS unavailable ({type(exc).__name__})."

    def _safe_exams(self):
        try:
            import nova_exams
            return nova_exams.exams_overview_text()
        except Exception as exc:
            return f"Exams unavailable ({type(exc).__name__})."

    def _safe_news(self):
        try:
            import news
            return news.get_news_briefing()
        except Exception as exc:
            return f"News unavailable ({type(exc).__name__})."

    def _safe_weather(self, city):
        try:
            import weather
            return weather.get_weather(city)
        except Exception as exc:
            return f"Weather unavailable ({type(exc).__name__})."

    def _safe_remind(self, rest):
        parts = rest.split(None, 1)
        if len(parts) < 2 or not parts[0].isdigit():
            return ("Format: /remind <minutes> <text>\n"
                    "Example: /remind 30 revise physics")
        minutes, task = int(parts[0]), parts[1].strip()
        try:
            from nova_features.smart_reminder import set_reminder
            result = set_reminder(task, f"in {minutes} minutes")
            msg = result.get("message") if isinstance(result, dict) else ""
            return f"⏰ Reminder set: {task} in {minutes} min. {msg or ''}".strip()
        except Exception as exc:
            return f"Reminder failed ({type(exc).__name__})."

    # ---------------- polling loop ----------------
    def poll_once(self):
        """One long-poll round; returns number of updates handled."""
        updates = self._call("getUpdates", {
            "offset": self._offset,
            "timeout": POLL_TIMEOUT_S,
            "allowed_updates": ["message"],
        }) or []
        handled = 0
        for update in updates:
            self._offset = max(self._offset, update["update_id"] + 1)
            try:
                chat_id = self._allowed(update)
                if not chat_id:
                    continue
                text = (update.get("message") or {}).get("text", "")
                if not text:
                    continue
                if not self._rate_ok(chat_id):
                    self.send(chat_id, "⏳ Slow down - max 20 msgs/min.")
                    continue
                self.send(chat_id, self.handle(text))
                handled += 1
            except Exception as exc:
                log.error("update handling failed: %s", exc)
        return handled

    def run_forever(self):
        if not self.token:
            print("❌ TELEGRAM_BOT_TOKEN missing in .env - bridge not started.")
            return
        print(f"🌉 Telegram bridge polling... (allow-list: "
              f"{len(self.allowed_ids)} id(s))")
        backoff = 2
        while True:
            try:
                if self.poll_once():
                    backoff = 2
            except KeyboardInterrupt:
                print("Bridge stopped.")
                return
            except requests.RequestException as exc:
                log.warning("network hiccup: %s - retrying in %ss",
                            exc, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    TelegramBridge().run_forever()


if __name__ == "__main__":
    main()