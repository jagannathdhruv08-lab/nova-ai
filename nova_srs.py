# ==========================================
# NOVA SRS - Spaced Repetition Flashcards (SM-2 algorithm)
# ------------------------------------------
# The same scheduling family Anki uses:
#   * quality >= 3  -> card graduates: interval grows x ease factor
#   * quality < 3   -> card lapses: back to 1 day, repetitions reset
#   * ease factor per-card, clamped to [1.3, 2.8]
#
# Storage: nova_srs_cards.json next to the .exe (writable_data_path).
#
# Also hosts LLM-powered helpers that connect to the "Train Nova"
# knowledge base:
#   generate_cards_from_knowledge() -> flashcards from your PDFs/notes
#   generate_quiz()                 -> MCQ quiz on a topic
# ==========================================

import json
import logging
import os
import time
import uuid
from datetime import date, timedelta

from nova_storage import writable_data_path

log = logging.getLogger("nova.srs")

__version__ = "1.0.0"

SRS_FILE = writable_data_path("nova_srs_cards.json")

_EASE_MIN = 1.3
_EASE_MAX = 2.8


def _today():
    return date.today()


def _default_store():
    return {"version": 1, "cards": {}, "reviews": []}


def _load():
    try:
        if os.path.exists(SRS_FILE):
            with open(SRS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("cards", {})
            data.setdefault("reviews", [])
            data.setdefault("version", 1)
            return data
    except Exception as exc:
        log.error("SRS load failed: %s", exc)
    return _default_store()


def _save(store):
    try:
        with open(SRS_FILE, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=1)
    except Exception as exc:
        log.error("SRS save failed: %s", exc)


def add_card(front, back, subject="general"):
    """Create one flashcard. Returns the stored card dict."""
    store = _load()
    card_id = uuid.uuid4().hex[:8]
    card = {
        "id": card_id,
        "front": str(front).strip()[:300],
        "back": str(back).strip()[:800],
        "subject": str(subject or "general").strip().lower()[:40],
        # SM-2 state
        "ease": 2.5,
        "interval_days": 0,
        "repetitions": 0,
        "lapses": 0,
        "due": str(_today()),
        "created": str(_today()),
        "last_reviewed": None,
        "review_count": 0,
    }
    store["cards"][card_id] = card
    _save(store)
    return card


def add_cards(pairs, subject="general"):
    """Bulk create from an iterable of (front, back) tuples."""
    made = []
    for front, back in pairs:
        if str(front).strip() and str(back).strip():
            made.append(add_card(front, back, subject=subject))
    return made


def get_card(card_id):
    return _load()["cards"].get(card_id)


def list_cards(subject=None):
    cards = list(_load()["cards"].values())
    if subject:
        key = subject.strip().lower()
        cards = [c for c in cards if c.get("subject") == key]
    return sorted(cards, key=lambda c: c.get("due", ""))


def delete_card(card_id):
    store = _load()
    if card_id in store["cards"]:
        del store["cards"][card_id]
        _save(store)
        return True
    return False


def due_cards(as_of=None):
    """Cards whose due date has arrived (oldest first)."""
    day = (as_of or _today()).isoformat()
    return [c for c in list_cards() if c.get("due", "") <= day]


def sm2_update(card, quality):
    """Pure SM-2 transition on a card dict; returns (card, new_interval).

    quality: 0-5 self-rating.
    """
    quality = max(0, min(5, int(quality)))
    if quality < 3:
        card["repetitions"] = 0
        card["lapses"] = card.get("lapses", 0) + 1
        interval = 1
    else:
        reps = card.get("repetitions", 0) + 1
        card["repetitions"] = reps
        q = quality
        ease = card.get("ease", 2.5) + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
        card["ease"] = round(max(_EASE_MIN, min(_EASE_MAX, ease)), 3)
        if reps == 1:
            interval = 1
        elif reps == 2:
            interval = 6
        else:
            prev = max(card.get("interval_days", 1), 1)
            interval = max(1, round(prev * card["ease"]))
    card["interval_days"] = interval
    card["due"] = str((_today() + timedelta(days=interval)).isoformat())
    return card, interval

def review_card(card_id, quality):
    """Grade a card and log the review. Returns (card, message)."""
    store = _load()
    card = store["cards"].get(card_id)
    if not card:
        return None, f"Card '{card_id}' not found."

    card, interval = sm2_update(card, quality)
    card["last_reviewed"] = str(_today())
    card["review_count"] = card.get("review_count", 0) + 1
    store.setdefault("reviews", []).append({
        "id": card_id,
        "subject": card["subject"],
        "quality": int(quality),
        "date": str(_today()),
        "hour": time.localtime().tm_hour,
    })
    # keep review log bounded (~1 year of heavy use)
    store["reviews"] = store["reviews"][-4000:]
    _save(store)

    verdict = ("✅ Graduated" if quality >= 3 else "🔁 Repeat")
    msg = (f"{verdict} — next review in {interval} day(s) "
           f"(ease {card['ease']:.2f}).")
    return card, msg


def review_session_summary(limit=10):
    """Chat-friendly block describing today's review queue."""
    queue = due_cards()
    if not queue:
        total = len(list_cards())
        return (f"🎉 Aaj koi card due nahi hai! Total cards: {total}. "
                "Kal wapas aana.")
    lines = [f"📚 {len(queue)} card(s) due for review:\n"]
    for c in queue[:limit]:
        lines.append(f"• #{c['id']} [{c['subject']}] {c['front'][:70]}")
    if len(queue) > limit:
        lines.append(f"...aur {len(queue) - limit} more")
    lines.append("\nGrade each 1(forgot)-5(easy), e.g.: 'grade abc12345 4'")
    return "\n".join(lines)


def grade_from_text(text):
    """Parse 'grade <card_id> <quality>' -> (card_id, quality) or None."""
    import re
    match = re.match(r"^\s*grade\s+([a-f0-9]{4,8})\s+([1-5])\s*$",
                     str(text).strip(), flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).lower(), int(match.group(2))


def srs_stats():
    cards = list(_load()["cards"].values())
    due = len(due_cards())
    learned = sum(1 for c in cards if c.get("repetitions", 0) >= 2)
    avg_ease = (round(sum(c.get("ease", 2.5) for c in cards) / len(cards), 2)
                if cards else 0.0)
    subjects = {}
    for c in cards:
        key = c.get("subject", "general")
        subjects[key] = subjects.get(key, 0) + 1
    return {
        "total": len(cards),
        "due_today": due,
        "learned": learned,
        "avg_ease": avg_ease,
        "subjects": subjects,
    }

# ---------------------------------------------------------------------------
# LLM-powered generation (knowledge base -> cards / quizzes)
# ---------------------------------------------------------------------------
_FLASHCARD_PROMPT = """You create study flashcards from study material.
Return ONLY a JSON object: {"cards": [{"front": "...", "back": "..."}]}
Make 1 fact per card, front is a question, back is the crisp answer.
Maximum {count} cards."""

_QUIZ_PROMPT = """You create multiple-choice quizzes for exam practice.
Return ONLY a JSON object:
{{"questions": [{{"question": str, "options": [4 strings],
"answer_index": 0-3, "explain": short reason}}]}}
Exactly {count} questions on the topic "{topic}". CBSE/entrance level."""


def _brain():
    try:
        import brain
        return brain if brain._PROVIDERS else None
    except Exception:
        return None


def generate_cards_from_knowledge(query, count=5):
    """Turn trained knowledge (Train Nova KB) into flashcards.

    Pulls relevant chunks from nova_knowledge, asks the LLM to write
    Q/A cards, stores them under subject 'trained'. Returns a summary
    string either way so it can go straight to chat."""
    count = max(3, min(10, int(count or 5)))
    context = ""
    try:
        import nova_knowledge as nk
        results = nk.search_knowledge(query, limit=4)
        if results:
            context = "\n\n".join(
                f"[{c['source']}] {c['text']}" for _s, c in results)
    except Exception:
        context = ""

    brain_mod = _brain()
    if not brain_mod:
        return ("LLM configured nahi hai - flashcards generate karne ke "
                "liye GROQ_API_KEY chahiye.")
    if not context:
        # still allow topic-based generation even without KB hits
        context = f"(No trained material found; use general knowledge about: {query})"

    decision = brain_mod.llm_json(
        _FLASHCARD_PROMPT.format(count=count),
        f"Material:\n{context[:3500]}\n\nMake exactly {count} flashcards.",
        max_tokens=900,
        temperature=0.3,
    )
    raw_cards = (decision or {}).get("cards")
    if not isinstance(raw_cards, list) or not raw_cards:
        return "Cards generate nahi ho paye - thoda specific topic do."

    made = add_cards(
        [(c.get("front"), c.get("back")) for c in raw_cards
         if isinstance(c, dict)],
        subject="trained",
    )
    if not made:
        return "Cards generate nahi ho paye - format samajh nahi aaya."
    return (f"🃏 {len(made)} flashcard(s) created from '{query}'. "
            f"Bolo 'review cards' shuru karne ke liye.")


def generate_quiz(topic="general", count=5):
    """MCQ quiz on *topic*, grounded in trained knowledge when available.

    Returns a formatted quiz string; correct answers listed upside-down
    style at the end so the user can self-check.
    """
    count = max(3, min(10, int(count or 5)))
    topic = (topic or "general").strip()[:100]
    context = ""
    try:
        import nova_knowledge as nk
        results = nk.search_knowledge(topic, limit=3)
        if results:
            context = "\n\n".join(c["text"] for _s, c in results)
    except Exception:
        pass

    brain_mod = _brain()
    if not brain_mod:
        # fall back to the offline static quizzes
        try:
            from nova_features.mini_quizzes import start_quiz
            data = start_quiz("science" if topic == "general" else "general")
            q = data["questions"][0]
            return (f"📝 Offline quiz ({data.get('category', 'general')}):\n\n"
                    f"Q: {q['question']}\n" +
                    "\n".join(f"  {chr(65 + i)}) {o}"
                              for i, o in enumerate(q["options"])) +
                    f"\n\nAnswer: {q['answer']}")
        except Exception:
            return ("Quiz ke liye LLM ya offline bank dono unavailable. "
                    "GROQ_API_KEY check karo.")

    user = f"Topic: {topic}\nCount: {count}"
    if context:
        user = f"Base it on this material when possible:\n{context[:2500]}\n\n{user}"

    decision = brain_mod.llm_json(
        _QUIZ_PROMPT.format(topic=topic, count=count), user,
        max_tokens=1200, temperature=0.5,
    )
    questions = (decision or {}).get("questions")
    if not isinstance(questions, list) or not questions:
        return "Quiz generate nahi hua - dobara try karo."

    out = [f"📝 Quiz time! Topic: {topic.title()} — {len(questions)} questions\n"]
    answers = []
    letters = "ABCD"
    for i, q in enumerate(questions, 1):
        opts = q.get("options") or []
        if len(opts) < 2:
            continue
        out.append(f"Q{i}. {q.get('question', '')}")
        for j, opt in enumerate(opts[:4]):
            out.append(f"   {letters[j]}) {opt}")
        try:
            ai = int(q.get("answer_index", 0))
            ai = max(0, min(len(opts) - 1, ai))
        except (TypeError, ValueError):
            ai = 0
        answers.append(f"A{i}: {letters[ai]} — {q.get('explain', '')}")
        out.append("")
    out.append("--- Answers (peek only when done!) ---")
    out.extend(answers)
    return "\n".join(out)


__all__ = ["add_card", "add_cards", "get_card", "list_cards", "delete_card",
           "due_cards", "sm2_update", "review_card", "review_session_summary",
           "grade_from_text", "srs_stats", "generate_cards_from_knowledge",
           "generate_quiz", "SRS_FILE"]