# ==========================================
# NOVA INTENTS - function-calling style router
# ------------------------------------------
# When the deterministic command matcher can't help, this module asks
# the LLM (one small forced-JSON call) whether the user's sentence maps
# to one of Nova's FEATURE actions - reminders, alarms, focus timer,
# flashcards, exams, backup, translation, weather, news, quizzes.
#
# Safety model (mirrors brain.route_to_agent):
#   * The model may only choose from a fixed whitelist of intents.
#   * Every argument is clamped / type-checked before use.
#   * Unknown action names are rejected, never executed.
#   * A cheap keyword pre-gate avoids burning an LLM call on ordinary
#     questions ("what is Merchant Navy?" stays pure chat).
# ==========================================

import logging
import re

log = logging.getLogger("nova.intents")

__version__ = "1.0.0"

_ACTION_HINTS = (
    "remind", "reminder", "alarm", "wake me", "focus", "pomodoro", "timer",
    "quiz", "quiz me", "flashcard", "flash card", "revise", "revision",
    "exam", "countdown", "test date", "backup", "export my data",
    "translate", "translation", "in hindi", "in english", "in spanish",
    "weather", "mausam", "news", "khabar",
)


def _looks_like_action(text):
    """Cheap pre-gate so ordinary questions skip the LLM entirely."""
    lowered = text.lower()
    return any(h in lowered for h in _ACTION_HINTS)


INTENT_SCHEMA_PROMPT = """You map the user's request to ONE feature action for Nova, a personal study assistant.

Choose exactly one "action" value:
- "set_reminder"   args: {"task": str, "time": str}   e.g. time "18:30" or "in 30 minutes"
- "set_alarm"      args: {"label": str, "time": str}
- "start_focus"    args: {"minutes": int 5..180}
- "add_flashcard"  args: {"front": str, "back": str, "subject": str}
- "review_cards"   args: {}
- "add_exam"       args: {"name": str, "date": "YYYY-MM-DD"}
- "exam_countdown" args: {}
- "export_backup"  args: {}
- "translate"      args: {"text": str, "target": str language name}
- "weather"        args: {"city": str}
- "news"           args: {}
- "quiz_me"        args: {"topic": str, "count": int 3..10}

Rules:
- If the request is NOT clearly one of these actions, respond:
  {"action": "chat"}
- Include ONLY relevant arg fields. Dates MUST be YYYY-MM-DD.
- Respond with ONLY the JSON object."""


def _clean(value, cap=300):
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value or "")).strip()[:cap]


def _clamp_minutes(raw, default=25):
    try:
        minutes = int(raw)
    except (TypeError, ValueError):
        return default
    return max(5, min(180, minutes))


def _clamp_count(raw, default=5):
    try:
        count = int(raw)
    except (TypeError, ValueError):
        return default
    return max(3, min(10, count))

# ---------------------------------------------------------------------------
# Dispatchers - every handler returns a user-facing string
# ---------------------------------------------------------------------------
def _do_set_reminder(args):
    task = _clean(args.get("task"), 200)
    time_str = _clean(args.get("time"), 40)
    if not task or not time_str:
        return "Reminder ke liye task aur time dono chahiye."
    from nova_features.smart_reminder import set_reminder
    result = set_reminder(task, time_str)
    msg = result.get("message") if isinstance(result, dict) else str(result)
    return f"⏰ Reminder set: {task} ({time_str}). {msg or ''}".strip()


def _do_set_alarm(args):
    label = _clean(args.get("label"), 80) or "Alarm"
    time_str = _clean(args.get("time"), 40)
    if not time_str:
        return "Alarm ka time batao (jaise 06:30)."
    from nova_features.alarm_scheduler import set_alarm
    result = set_alarm(label, time_str)
    msg = result.get("message") if isinstance(result, dict) else str(result)
    return f"⏰ Alarm '{label}' set for {time_str}. {msg or ''}".strip()


def _do_start_focus(args):
    minutes = _clamp_minutes(args.get("minutes"))
    try:
        from nova_features.focus_timer import start_focus_session
        start_focus_session(minutes)
        return f"🎯 Focus session started: {minutes} minutes. All the best!"
    except Exception as exc:
        log.warning("focus intent failed: %s", exc)
        return f"Focus timer shuru nahi ho paya ({type(exc).__name__})."


def _do_add_flashcard(args):
    front = _clean(args.get("front"), 300)
    back = _clean(args.get("back"), 600)
    subject = _clean(args.get("subject"), 40) or "general"
    if not front or not back:
        return "Flashcard ke liye front aur back dono do."
    import nova_srs
    card = nova_srs.add_card(front, back, subject=subject)
    return (f"🃏 Flashcard #{card['id']} added to '{subject}'. "
            "Bolo 'review cards' jab revise karna ho.")


def _do_review_cards(_args):
    import nova_srs
    return nova_srs.review_session_summary()


def _do_add_exam(args):
    name = _clean(args.get("name"), 100)
    date_str = _clean(args.get("date"), 12)
    if not name or not date_str:
        return "Exam name aur date (YYYY-MM-DD) dono do."
    import nova_exams
    return nova_exams.set_exam(name, date_str)


def _do_exam_countdown(_args):
    import nova_exams
    return nova_exams.exams_overview_text()


def _do_export_backup(_args):
    from nova_features.data_export_import import export_all_data
    report = export_all_data()
    return report.get("message", "Backup attempt finished.")

def _do_translate(args):
    text = _clean(args.get("text"), 500)
    target = _clean(args.get("target"), 30) or "hindi"
    if not text:
        return "Kya translate karna hai?"
    from nova_features.multi_language import translate_text
    result = translate_text(text, target=target)
    if result.get("success"):
        return f"🌐 Translation ({result.get('engine')}):\n{result['to_text']}"
    return result.get("message", "Translation unavailable.")


def _do_weather(args):
    city = _clean(args.get("city"), 60)
    try:
        import weather
        return weather.get_weather(city)
    except Exception as exc:
        log.warning("weather intent failed: %s", exc)
        return "Weather fetch failed. Internet check karo."


def _do_news(_args):
    try:
        import news
        return news.get_news_briefing()
    except Exception as exc:
        log.warning("news intent failed: %s", exc)
        return "News fetch failed. Internet check karo."


def _do_quiz_me(args):
    topic = _clean(args.get("topic"), 100)
    count = _clamp_count(args.get("count"))
    try:
        import nova_srs
        return nova_srs.generate_quiz(topic=topic, count=count)
    except Exception as exc:
        log.warning("quiz intent failed: %s", exc)
        return f"Quiz generate nahi ho paya ({type(exc).__name__})."


HANDLERS = {
    "set_reminder": _do_set_reminder,
    "set_alarm": _do_set_alarm,
    "start_focus": _do_start_focus,
    "add_flashcard": _do_add_flashcard,
    "review_cards": _do_review_cards,
    "add_exam": _do_add_exam,
    "exam_countdown": _do_exam_countdown,
    "export_backup": _do_export_backup,
    "translate": _do_translate,
    "weather": _do_weather,
    "news": _do_news,
    "quiz_me": _do_quiz_me,
}


def route_intent(text, force=False):
    """Try to interpret *text* as one of the whitelisted actions.

    Returns a user-facing string when an action ran, otherwise None
    (caller should continue down its normal chat fallback chain).
    """
    if not text or not str(text).strip():
        return None
    text = str(text).strip()
    if not force and not _looks_like_action(text):
        return None

    try:
        import brain
    except Exception:
        return None

    decision = brain.llm_json(
        INTENT_SCHEMA_PROMPT, text, max_tokens=220, temperature=0.0)
    if not decision:
        return None

    action = decision.get("action")
    if action == "chat" or action is None:
        return None
    handler = HANDLERS.get(action)
    if handler is None:
        log.warning("intent router proposed unknown action %r", action)
        return None

    args = decision.get("args")
    if not isinstance(args, dict):
        args = {}
    try:
        return handler(args)
    except Exception as exc:
        log.error("intent %s handler failed: %s", action, exc)
        return f"'{action}' action failed ({type(exc).__name__})."


__all__ = ["route_intent", "HANDLERS", "_looks_like_action"]