import json
import logging
import os
import sys
import time

# Resolve memory.json to a STABLE location — next to the .exe when packaged
# (so it follows Nova.exe and survives), or next to this script otherwise.
# Mirrors nova_storage.writable_data_path(). Without this, a packaged exe
# would look for memory.json in whatever folder it happened to be launched
# from, so saved memories could appear 'lost'.
if getattr(sys, "frozen", False):
    _MEM_DIR = os.path.dirname(sys.executable)
else:
    _MEM_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE = os.path.join(_MEM_DIR, "memory.json")

if not os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "w") as file:
        json.dump({}, file)

# ---------------------------------------------------------------------------
# Encrypted-at-rest plumbing (Phase 4 security upgrade).
# memory.json holds personal facts + conversation summaries, so it now
# goes through secure_store (Fernet). A pre-existing plaintext file is
# migrated automatically on first save/load; if the cryptography package
# is unavailable everything silently falls back to plaintext so Nova
# keeps working.
# ---------------------------------------------------------------------------
try:
    import secure_store
except Exception:
    secure_store = None

_MEMORY_MIGRATION_DONE = False


def _ensure_migrated():
    """One-time in-place encryption of a legacy plaintext memory.json."""
    global _MEMORY_MIGRATION_DONE
    if _MEMORY_MIGRATION_DONE or secure_store is None:
        return
    try:
        status = secure_store.migrate_plaintext(MEMORY_FILE)
        if status == "migrated":
            logging.getLogger("nova.memory").info(
                "memory.json encrypted at rest.")
    except Exception:
        pass
    finally:
        _MEMORY_MIGRATION_DONE = True


def load_memory():
    if secure_store is not None:
        _ensure_migrated()
        try:
            return secure_store.load_json_encrypted(MEMORY_FILE, default={})
        except secure_store.SecureStoreError as exc:
            # Wrong key / corrupted file: never crash the app over this,
            # but DO NOT silently destroy the unreadable file either.
            logging.getLogger("nova.memory").error(
                "memory.json unreadable (%s); starting with empty memory.", exc)
            return {}
    with open(MEMORY_FILE, "r") as file:
        return json.load(file)

def save_memory(memory):
    if secure_store is not None:
        _ensure_migrated()
        try:
            secure_store.save_json_encrypted(MEMORY_FILE, memory)
            return
        except Exception:
            logging.getLogger("nova.memory").exception(
                "encrypted memory write failed; falling back to plaintext")
    with open(MEMORY_FILE, "w") as file:
        json.dump(memory, file, indent=4)

def remember(key, value):
    memory = load_memory()
    memory[key] = value
    save_memory(memory)

def recall(key):
    memory = load_memory()
    return memory.get(key, None)

def get_saved_facts():
    memory = load_memory()
    return {
        key: value
        for key, value in memory.items()
        if not key.startswith("_")
    }


def memory_facts_block(max_facts=12):
    """Returns a short, formatted block of the user's saved memories so it
    can be injected into every chat/coach prompt. Nova reads these BEFORE
    replying, so answers are personalised (name, favourite subject, bad days,
    Merchant Navy dream job, etc.). Returns '' when nothing is saved."""
    try:
        facts = get_saved_facts()
    except Exception:
        return ""
    if not facts:
        return ""

    lines = []
    for key, value in list(facts.items())[:max_facts]:
        if isinstance(value, (dict, list)):
            try:
                value = json.dumps(value, ensure_ascii=False)
            except Exception:
                continue
        lines.append(f"- {key.replace('_', ' ')}: {value}")
    return (
        "Nova ko user ke baare mein ye yaad hai (inhe apne jawab mein use karo, "
        "sirf jab related ho):\n" + "\n".join(lines) + "\n\n"
    )

def delete_memory(key):
    memory = load_memory()
    if key in memory:
        del memory[key]
        save_memory(memory)
        return True
    return False

def clear_saved_facts():
    memory = {
        key: value
        for key, value in load_memory().items()
        if key.startswith("_")
    }
    save_memory(memory)


def clear_memory():
    """Wipe ALL memory (including system/internal keys)."""
    save_memory({})
    return True


# ===========================================================================
# LONG-TERM CONVERSATION MEMORY
# ---------------------------------------------------------------------------
# Keys prefixed with "_" are internal (get_saved_facts() already filters
# them out of user-facing facts), so conversation data lives happily next
# to user facts without leaking into "what do you remember" listings.
#
#   _conversation          -> rolling list of recent {u, a, t} turns
#   _conversation_summary  -> running compressed summary of older turns
#
# When the rolling buffer crosses _SUMMARY_TRIGGER turns, the older half
# is compressed by the LLM into the summary. ask_nova callers inject
# conversation_context_block() so Nova remembers across sessions.
# ===========================================================================
_CONVO_KEY = "_conversation"
_SUMMARY_KEY = "_conversation_summary"

_MAX_RAW_TURNS = 30        # rolling window size
_SUMMARY_TRIGGER = 24      # summarize when the window gets this full


def remember_turn(user_text, assistant_text, max_turns=_MAX_RAW_TURNS):
    """Append one chat exchange to the rolling conversation memory.

    Never raises; silently no-ops on empty input. Auto-triggers a
    background-friendly summarize when the buffer fills up.
    """
    if not user_text or not assistant_text:
        return False
    try:
        memory = load_memory()
        turns = memory.get(_CONVO_KEY)
        if not isinstance(turns, list):
            turns = []
        turns.append({
            "u": str(user_text)[:500],
            "a": str(assistant_text)[:900],
            "t": time.strftime("%Y-%m-%d %H:%M"),
        })
        memory[_CONVO_KEY] = turns[-max_turns:]
        memory[_SUMMARY_KEY] = memory.get(_SUMMARY_KEY, "")
        save_memory(memory)

        if len(memory[_CONVO_KEY]) >= _SUMMARY_TRIGGER:
            summarize_conversation()
        return True
    except Exception:
        return False


def get_recent_turns(count=8):
    """Most-recent-first would be awkward for prompts - returns oldest-
    first list of the last *count* turns."""
    try:
        turns = load_memory().get(_CONVO_KEY, [])
        return list(turns[-count:])
    except Exception:
        return []


def get_conversation_summary():
    try:
        return str(load_memory().get(_SUMMARY_KEY, "") or "")
    except Exception:
        return ""


def summarize_conversation(brain_module=None):
    """Compress the older half of the rolling buffer into the summary.

    Uses brain.llm_chat (pass brain_module for testing). Returns True
    when a summary was produced. Without providers this degrades to a
    cheap truncation summary so memory never grows unbounded.
    """
    try:
        memory = load_memory()
        turns = memory.get(_CONVO_KEY, [])
        if len(turns) < _SUMMARY_TRIGGER // 2:
            return False

        split_at = len(turns) // 2
        old_turns, keep_turns = turns[:split_at], turns[split_at:]
        transcript = "\n".join(
            f"[{t.get('t', '')}] User: {t['u']}\nNova: {t['a']}"
            for t in old_turns
        )
        existing_summary = memory.get(_SUMMARY_KEY, "")

        system = (
            "You compress chat history into a compact running summary "
            "(max 120 words) of facts, decisions, plans and ongoing "
            "topics about the user. Merge the previous summary with the "
            "new transcript. Reply with ONLY the summary text."
        )
        user = (
            f"Previous summary:\n{existing_summary or '(none)'}\n\n"
            f"New transcript:\n{transcript}"
        )

        summary_text = None
        try:
            brain_mod = brain_module
            if brain_mod is None:
                import brain as _brain
                brain_mod = _brain
            result, _info = brain_mod.llm_chat(
                [{"role": "system", "content": system},
                 {"role": "user", "content": user}],
                max_tokens=300,
                temperature=0.2,
            )
            summary_text = result.strip() if isinstance(result, str) and result.strip() else None
        except Exception:
            summary_text = None

        if summary_text is None:
            # Offline fallback: crude but bounded keyword-ish digest.
            topics = []
            for t in old_turns[-6:]:
                snippet = t["u"][:80].replace("\n", " ")
                topics.append(snippet)
            summary_text = ((existing_summary + " | ") if existing_summary else "") \
                + "Earlier: " + " ; ".join(topics)
            summary_text = summary_text[:1500]

        memory[_SUMMARY_KEY] = summary_text
        memory[_CONVO_KEY] = keep_turns
        save_memory(memory)
        return True
    except Exception:
        return False


def conversation_context_block(max_chars=1200, recent=6):
    """Prompt-ready block: running summary + last few raw turns.
    Returns '' when there is nothing stored yet."""
    summary = get_conversation_summary()
    turns = get_recent_turns(recent)
    if not summary and not turns:
        return ""

    parts = ["## Recent conversation context:"]
    if summary:
        parts.append(f"Summary of older chats: {summary}")
    if turns:
        lines = [f"User: {t['u'][:160]} / Nova: {t['a'][:220]}" for t in turns]
        parts.append("Last turns:\n" + "\n".join(lines))
    block = "\n".join(parts) + "\n\n"
    return block[:max_chars]
