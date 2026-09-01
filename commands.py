"""
commands.py — Deterministic command router (audit-patched)
Changes from the original:
  1. `print("COMMAND RECEIVED:", command)` removed (it was leaking user
     input to stdout / log files).
  2. `os.system("start chrome")` replaced with list-form `subprocess.run`.
  3. `shutdown pc` and `restart pc` now require an explicit confirmation
     flag, have a 60s cool-down, and use list-form `subprocess.run`.
  4. `open whatsapp` no longer falls back silently to web; the user is
     told the desktop app is missing.
  5. `_handle_remember_command` now sanitises & length-caps values to
     defend against prompt-injection via memory.
  6. The "song" argument is URL-encoded before being passed to
     `pywhatkit.playonyt` (defence-in-depth even though pywhatkit
     already does it).
"""

import os
import re
import time
import shlex
import subprocess
import webbrowser
import logging
import urllib.parse

try:
    import screen_brightness_control as sbc
except ImportError:
    sbc = None

try:
    import pywhatkit
except ImportError:
    pywhatkit = None

from memory import remember, recall
from news import get_news_briefing, get_news_for_request
from history import clear_history as clear_chat_history, get_recent_history
from weather import handle_weather_command
from voice import mute_voice, unmute_voice
import nova_study

log = logging.getLogger("nova.commands")

WHATSAPP_WEB_URL = "https://web.whatsapp.com"

# --- 1. Cool-down for destructive commands ------------------------------
_LAST_DESTRUCTIVE_AT = 0.0
_DESTRUCTIVE_COOLDOWN = 60.0  # seconds

# --- 2. Memory sanitisation ---------------------------------------------
MAX_FACT_VALUE_LEN = 200
_INJECTION_HINT = re.compile(
    r"ignore (previous|all)|system prompt|you are now|disregard|"
    r"act as|new instructions|override|reveal",
    re.IGNORECASE,
)


def _sanitise_fact(value: str) -> str:
    v = value.strip()
    v = v[:MAX_FACT_VALUE_LEN]
    if _INJECTION_HINT.search(v):
        log.warning("Refused memory value that looks like prompt-injection.")
        return ""
    return v


# --- 3. The deterministic command router --------------------------------
def _memory_key(text):
    text = text.strip().lower()
    if text.startswith("my "):
        text = text[3:]
    return "_".join(text.split())


def _handle_remember_command(command):
    if not command.startswith("remember "):
        return None

    fact = command.replace("remember ", "", 1).strip()
    if not fact:
        return "Tell me what to remember."

    if "my name is" in fact:
        name = _sanitise_fact(fact.replace("my name is", "", 1).strip())
        if not name:
            return "Tell me the name to remember."
        remember("username", name)
        return f"I will remember your name {name}"

    if "my favorite color is" in fact:
        color = _sanitise_fact(fact.replace("my favorite color is", "", 1).strip())
        if not color:
            return "Tell me the color to remember."
        remember("favorite_color", color)
        return f"I will remember that your favorite color is {color}"

    if " is " in fact:
        key, value = fact.split(" is ", 1)
        key = _memory_key(key)
        value = _sanitise_fact(value.strip())
        if key and value:
            remember(key, value)
            return f"I will remember {key.replace('_', ' ')} is {value}"

    return "Please say it like: remember my name is Dhruv."


# ---------------------------------------------------------------------------
# Train / Learn commands — ingest the user's personal data into Nova's
# knowledge base so it can be applied in later answers (RAG).
# ---------------------------------------------------------------------------
def _handle_learn_command(command, attached_file=None):
    """Route 'learn / train' commands to nova_knowledge.

    Returns a reply string when the command is a learn/train command,
    or None / empty string so the router keeps trying other command types.
    """
    import nova_knowledge as nk  # lazy

    # ---- clear / forget -------------------------------------------------
    if any(phrase in command for phrase in (
        "clear my knowledge", "clear training data", "forget what you learned",
        "forget learned data", "clear learned knowledge", "wipe knowledge",
    )):
        if nk.clear_knowledge():
            return "🗑️ Cleared all trained knowledge. Nova will answer fresh next time."
        return "Nothing to clear — no knowledge base exists yet."

    # ---- show / list ----------------------------------------------------
    if any(phrase in command for phrase in (
        "what did you learn", "show my knowledge", "show my training data",
        "list learned data", "list training sources", "show knowledge",
        "show learned sources", "what have you learned",
    )):
        sources = nk.list_sources()
        stats = nk.knowledge_stats()
        if not sources:
            return ("📭 Nova hasn't learned anything yet. Attach a file and say "
                    "'learn from file', paste a paragraph and say 'learn paragraph: ...', "
                    "or point me at a folder: 'learn from folder: C:\\path'.")
        lines = [f"## **Knowledge trained** 📚  ({stats['chunks']} chunks, "
                 f"~{stats['chars']} chars)"]
        for src, info in sources:
            lines.append(f"- **{src}** — {info['chunks']} chunks "
                         f"({info.get('chars', 0)} chars, added {info.get('added_at', '?')})")
        return "\n".join(lines)

    # ---- learn from a pasted paragraph -------------------------------
    # "learn paragraph: <text>"  /  "train on paragraph: <text>"
    # "learn from paragraph: <text>"
    for marker in ("learn paragraph:", "train on paragraph:",
                   "learn from paragraph:"):
        if marker in command:
            text = command.split(marker, 1)[1].strip()
            count = nk.ingest_text("pasted paragraph", text)
            if count:
                return (f"✅ Learned from your paragraph — added {count} chunk(s) "
                        f"to my knowledge base. I'll apply this when relevant. 📚")
            return "Hmm, that paragraph had no text I could save."
    if command.startswith("learn "):
        # bare "learn <text>" with no file -> treat the rest as a paragraph
        rest = command.replace("learn ", "", 1).strip()
        if rest and not rest.endswith("file") and "folder" not in rest:
            count = nk.ingest_text("pasted paragraph", rest)
            if count:
                return (f"✅ Learned from your text — added {count} chunk(s). "
                        f"Nova will use this going forward. 📚")

    # ---- learn from folder -------------------------------------------
    for phrase in ("learn from folder:", "learn folder:", "train on folder:",
                   "train from folder:"):
        if phrase in command:
            folder = command.split(phrase, 1)[1].strip()
            if not folder:
                return "Tell me the folder path, e.g. 'learn from folder: C:\\Users\\Me\\Documents\\Notes'"
            folder = os.path.expanduser(folder)
            total, files, errs = nk.ingest_folder(folder)
            if files:
                msg = (f"✅ Learned from **{files} file(s)** in '{folder}' — "
                       f"{total} chunk(s) added.")
                if errs:
                    msg += f"\n\nSkipped: " + "; ".join(errs[:3])
                return msg
            return f"📭 No learnable files found in '{folder}'." + \
                   (" Errors: " + "; ".join(errs) if errs else "")

    # ---- learn from attached file --------------------------------------
    if any(phrase in command for phrase in (
        "learn from file", "learn this file", "learn from the attached file",
        "train on this file", "learn from attachment", "train on this",
        "learn this", "train on this", "learn from attached file",
    )) and attached_file:
        # images carry a 'path'; documents carry 'path' + 'text' preview
        fpath = attached_file.get("path")
        fname = attached_file.get("name", "file")
        if not fpath:
            # document without path: use the stored text preview
            text = attached_file.get("text", "")
            count = nk.ingest_text(fname, text)
            if count:
                return (f"✅ Learned from **{fname}** (text preview) — {count} "
                        f"chunk(s) added. 📚")
            return f"Could not extract text from {fname}."
        count, src, err = nk.ingest_file(fpath)
        if count:
            return (f"✅ Learned from **{src}** — {count} chunk(s) added to "
                    f"Nova's knowledge. I'll apply it when relevant. 📚")
        return f"Could not learn from **{fname}**: {err or 'no text found'}"

    if any(phrase in command for phrase in (
        "learn from file", "learn this file", "train on this file",
        "learn this", "train on this",
    )) and not attached_file:
        return ("Attach a file first (📎 button), then say 'learn from file'. "
                "Or paste a paragraph and say 'learn paragraph: ...'.")

    return None





def open_whatsapp(use_web=False):
    if use_web:
        webbrowser.open(WHATSAPP_WEB_URL)
        return "Opening WhatsApp Web"
    try:
        os.startfile("whatsapp:")  # safe — URI scheme, no shell parsing
        return "Opening WhatsApp"
    except Exception:
        webbrowser.open(WHATSAPP_WEB_URL)
        return "WhatsApp desktop is not available, opening WhatsApp Web"


# Phone number: optional leading +, digits/spaces/dashes/parens, min 8 digits.
_WA_NUMBER_RE = re.compile(r"(\+?\d[\d\s()\-]{8,}\d)")
# Text after the number may start with a connector word before the real text.
_WA_CONNECTOR_RE = re.compile(
    r"^\s*(?:saying|to say|with|with the text|text|message|the message|"
    r"that (?:says|reads)|the text|followed by|and text|:)\s*[:,-]?\s*",
    re.IGNORECASE,
)

# Leading junk to skip before a contact name: "send whatsapp message to …"
_WA_PREFIX_JUNK_RE = re.compile(
    r"^\s*(?:send\s+)?(?:a\s+)?(?:whatsapp\s+)?(?:message\s+)?"
    r"(?:on\s+whatsapp\s+)?(?:to\s+)?(?:the\s+)?",
    re.IGNORECASE,
)
# Words that mark the END of the contact name ("…to <name> SAYING <text>").
_WA_NAME_STOP_RE = re.compile(
    r"\b(?:saying|to say|say|text|message|that)\b|:",
    re.IGNORECASE,
)

# Contacts are stored inside encrypted memory under a "_"-prefixed key so they
# stay out of the free-form fact block (get_saved_facts() skips "_"-keys).
_CONTACTS_KEY = "_contacts"
_CONTACT_SAVE_PREFIX_RE = re.compile(
    r"^\s*(?:save|remember|store|add)\s+(?:a\s+)?(?:contact|number|person|friend)"
    r"\s*(?:named|for|of)?\s+",
    re.IGNORECASE,
)
_CONTACT_SAVE_SUFFIX_RE = re.compile(
    r"(?:'s|s)?\s*(?:number|is|as|with)\s*$",
    re.IGNORECASE,
)


def _load_contacts():
    """Saved contact dict {name.lower(): digits-only phone}."""
    try:
        val = recall(_CONTACTS_KEY)
        return dict(val) if isinstance(val, dict) else {}
    except Exception:
        return {}


def _save_contact(name_, number):
    contacts = _load_contacts()
    contacts[name_.strip().lower()] = re.sub(r"[^\d]", "", number)
    try:
        remember(_CONTACTS_KEY, contacts)
        return True
    except Exception:
        return False


def _find_contact(name_):
    return _load_contacts().get(name_.strip().lower(), None)


def _launch_whatsapp(number, text):
    deep_link = f"whatsapp://send?phone={number}&text={urllib.parse.quote(text)}"
    try:
        os.startfile(deep_link)  # safe URI scheme, no shell parsing
        return (f"WhatsApp khol diya - \"{text}\" ready type hai. "
                f"Bas Enter dabakar send kar do ✅")
    except Exception:
        webbrowser.open(f"https://wa.me/{number}?text={urllib.parse.quote(text)}")
        return ("WhatsApp desktop nahi khul raha, web.me link khol diya. "
                "WhatsApp Web mein Enter dabakar send karo.")


def save_whatsapp_contact(command):
    """Parse and store a contact: 'save contact <name> number <number>'."""
    num_m = _WA_NUMBER_RE.search(command or "")
    if not num_m:
        return ("Number batao. Example:\n"
                "save contact amma number 919876543210")
    number = re.sub(r"[^\d]", "", num_m.group(1))
    if len(number) < 10:
        return ("Number chhota lag raha hai. Country code ke saath daalo "
                "(jaise 919876543210).")

    name = _CONTACT_SAVE_PREFIX_RE.sub("", command[:num_m.start()])
    name = _CONTACT_SAVE_SUFFIX_RE.sub("", name).strip().strip("\"' ")
    if not name:
        return ("Contact ka naam batao. Example:\n"
                "save contact amma number 919876543210")

    if _save_contact(name, number):
        return f"✅ Contact save ho gaya: {name} = {number}"
    return "Contact save nahi ho paya."


def send_whatsapp_message(command):
    """Send a WhatsApp message via the desktop app's `whatsapp://` deep link.

    WhatsApp has no free/mass-authorised send API, so we open the compose
    window pre-filled (phone + text) using the URI scheme the installed
    desktop app registers. The user presses Enter to deliver the message.

    Accepted phrasing (case-insensitive):
      "send whatsapp message to +91XXXXXXXXXX saying hello"
      "whatsapp 91XXXXXXXXXX text see you tomorrow"
    Falls back to WhatsApp Web if the desktop app isn't installed.
    """
    bare = (command or "").strip()

    # 1) A literal phone number present -> prefer it.
    m = _WA_NUMBER_RE.search(bare)
    if m:
        number = re.sub(r"[^\d]", "", m.group(1))
        tail = _WA_CONNECTOR_RE.sub("", bare[m.end():]).strip()
        if len(number) >= 10:
            if not tail:
                return ("Message kya bhejna hai? Batao: "
                        "send whatsapp message to <number> saying <text>")
            return _launch_whatsapp(number, tail)
        # A too-short digit run is likely a name/typo — fall through to name.

    # 2) Try a saved contact name: "… to <name> saying <text>".
    stripped = _WA_PREFIX_JUNK_RE.sub("", bare)
    stop = _WA_NAME_STOP_RE.search(stripped)
    if stop:
        name, tail = stripped[:stop.start()].strip(), stripped[stop.end():].strip()
    else:
        name, tail = stripped.strip(), ""

    if name:
        number = _find_contact(name)
        if number is None:
            return (f"Contact \"{name}\" nahi mila. Pehle save karo:\n"
                    "save contact <name> number <number>")
        if not tail:
            return ("Message kya bhejna hai? Batao: "
                    f"send whatsapp message to {name} saying <text>")
        return _launch_whatsapp(number, tail)

    return ("WhatsApp number ya contact naam aur message batayein. Example:\n"
            "send whatsapp message to amma saying good morning "
            "(naam pehle save karo: save contact amma number 919876543210)")


def _destructive_ok() -> bool:
    """Return True if a destructive command is allowed by the cool-down."""
    global _LAST_DESTRUCTIVE_AT
    now = time.monotonic()
    if now - _LAST_DESTRUCTIVE_AT < _DESTRUCTIVE_COOLDOWN:
        return False
    _LAST_DESTRUCTIVE_AT = now
    return True


# --- Study workflow callbacks (registered by gui.py) ----------------------
# These let the (headless-ish) command layer trigger GUI side-effects:
#   * _timer_callback(subject_key, minutes)  -> start a subject focus timer
#   * _refresh_callback()                    -> rebuild the Study Hub panels
_study_timer_cb = None
_study_refresh_cb = None


def set_study_callbacks(timer_cb=None, refresh_cb=None):
    global _study_timer_cb, _study_refresh_cb
    if timer_cb is not None:
        _study_timer_cb = timer_cb
    if refresh_cb is not None:
        _study_refresh_cb = refresh_cb


def _refresh_study():
    if _study_refresh_cb is not None:
        try:
            _study_refresh_cb()
        except Exception:
            log.exception("study refresh failed")


# ---------------------------------------------------------------------------
# Study slash commands
# ---------------------------------------------------------------------------
def _subject_help(key, topic=""):
    info = nova_study.SUBJECTS.get(key, {})
    name = info.get("name", "Study")
    color = nova_study.subject_color(key)
    nova_study.set_active_subject(key)
    _refresh_study()
    topic = topic.strip() or "a specific topic"
    return (
        f"## **{name} mode** {info.get('icon','')}\n"
        f"Active subject set to **{name}** (accent {color}).\n"
        f"I'll answer **{topic}** with the study-friendly breakdown "
        "(analogy + error journal + practice drill). Ask away, or type "
        f"`/log-error {key} | topic | what went wrong` to start your error journal. 🎯"
    )


def _parse_log_error(cmd):
    """Parse: /log-error subject | topic | error [| root cause]"""
    body = cmd.replace("/log-error", "", 1).strip()
    if not body:
        return None
    parts = [p.strip() for p in body.split("|")]
    while len(parts) < 3:
        parts.append("")
    subject, topic, error = parts[0], parts[1], parts[2]
    root = parts[3] if len(parts) > 3 else ""
    if not topic or not error:
        return None
    entry = nova_study.log_error(subject, topic, error, root)
    _refresh_study()
    name = nova_study.SUBJECTS.get(entry["subject"], {}).get("name", entry["subject"])
    return (
        f"✅ Logged to your **error journal**: `{name}` / `{entry['topic']}`\n"
        f"- **Error:** {entry['error']}\n"
        f"- **Root cause:** {entry['root_cause'] or '(add later)'}\n"
        f"Logged **{len(nova_study.list_error_journal())}** entries total. "
        f"Keep reviewing weak topics before mocks! 📔"
    )


def _parse_mock_score(cmd):
    """Parse: /mock-score 85 [| physics:82 | chemistry:88 ...]"""
    body = cmd.replace("/mock-score", "", 1).strip()
    if not body:
        return None
    segs = [s.strip() for s in body.split("|")]
    try:
        score = float(segs[0].replace("%", "").strip())
    except ValueError:
        return None
    subject_scores = {}
    for s in segs[1:]:
        if ":" in s:
            k, v = s.split(":", 1)
            try:
                subject_scores[nova_study.subject_key(k)] = float(v.strip().replace("%", ""))
            except ValueError:
                pass
    entry = nova_study.log_mock_score(score, subject_scores=subject_scores)
    _refresh_study()
    line = f"📊 **{entry['name']}** saved → **{score:.0f}%**"
    if subject_scores:
        bits = ", ".join(
            f"{nova_study.SUBJECTS.get(k,{}).get('name',k)}: {v:.0f}%"
            for k, v in subject_scores.items()
        )
        line += f"\n  Subject-wise: {bits}"
    line += "\nKeep the trend up — target **+5%** on the next mock! 🎯"
    return line


def _handle_study_command(command):
    """Route study slash commands. Returns a reply string or None."""
    if command.startswith("/log-error"):
        reply = _parse_log_error(command)
        if reply is not None:
            return reply
        return ("Usage: `/log-error subject | topic | what went wrong | root cause`\n"
                "Example: `/log-error physics | Kinematics | confused a and v | careless`")

    if command.startswith("/mock-score"):
        reply = _parse_mock_score(command)
        if reply is not None:
            return reply
        return ("Usage: `/mock-score 85 | physics:82 | chemistry:88 | maths:86`\n"
                "Example: `/mock-score 82 | physics:80 | maths:85` to log your mock result.")

    if command.startswith("/today-plan"):
        rows = []
        for time, sub, desc in nova_study.get_daily_schedule():
            name = nova_study.SUBJECTS.get(sub, {}).get("name", "Routine")
            icon = nova_study.SUBJECTS.get(sub, {}).get("icon", "")
            rows.append(f"- **{time}**  {icon} **{name}** — {desc}")
        return (
            "## **Today's study plan** 🗓\n" + "\n".join(rows) +
            "\n\nTip: `timer 50 physics` to start a focused block on any slot."
        )

    if command.startswith("/weak-topics"):
        weak = nova_study.weak_topics_list(8)
        if not weak:
            return "No errors logged yet — use `/log-error subject | topic | error` to start tracking weak areas!"
        lines = []
        for topic, sub, count in weak:
            name = nova_study.SUBJECTS.get(sub, {}).get("name", sub)
            lines.append(f"- **{topic}** ({name}) — repeated **{count}×**")
        return "## **Your weak topics** 🎯\n" + "\n".join(lines) + \
            "\n\nAdd to your weekly revision plan or nail them with practice drills."

    if command.startswith("/error-journal") or command.startswith("/journal-errors"):
        entries = nova_study.list_error_journal(10)
        if not entries:
            return "Your error journal is empty. Log one with `/log-error subject | topic | error` 📔"
        lines = []
        for e in entries:
            name = nova_study.SUBJECTS.get(e["subject"], {}).get("name", e["subject"])
            lines.append(
                f"- `{e['date']}` **{name}** — *{e.get('topic','')}*: {e.get('error','')}"
            )
        return "## **Error journal (recent)** 📔\n" + "\n".join(lines)

    if command.startswith("/timer"):
        body = command.replace("/timer", "", 1).strip()
        parts = [p for p in body.split() if p]
        minutes = 25
        subject = nova_study.get_active_subject()
        nums = [p for p in parts if p.isdigit()]
        words = [p for p in parts if not p.isdigit()]
        if nums:
            minutes = int(nums[0])
        if words:
            subject = nova_study.subject_key(" ".join(words))
        name = nova_study.SUBJECTS.get(subject, {}).get("name", "Focus")
        icon = nova_study.SUBJECTS.get(subject, {}).get("icon", "")
        if _study_timer_cb is not None:
            _study_timer_cb(subject, minutes)
            return (
                f"⏱ Started a **{minutes}-min {name}** focus session "
                f"on **{icon} {name}**. Take a **5-min break** after it. Push through! 💪"
            )
        return f"Timer requested ({name}, {minutes} min) — run the desktop app for the live timer."

    if command.startswith("/physics") or command.startswith("/chemistry") or \
       command.startswith("/maths") or command.startswith("/math ") or \
       command.startswith("/english") or command.startswith("/mn"):
        # strip the leading slash + subject, remainder is topic
        first = command.split()[0]
        topic = command[len(first):].strip()
        key = first.lstrip("/")
        if key == "math":
            key = "maths"
        return _subject_help(key, topic)

    return None


def execute_command(command, *, confirm_destructive: bool = False, attached_file=None):
    """
    `confirm_destructive` must be True for shutdown / restart. The GUI
    will set this to True only after the user clicks "Confirm" in a
    modal dialog.

    `attached_file` is the dict set by gui.attach_file() (None when no
    file is attached). It lets "learn" commands ingest the attached file.
    """
    command = command.lower().strip()

    # Study slash commands run before the generic router so "/physics" etc.
    # are handled deterministically instead of falling to free-form chat.
    study_reply = _handle_study_command(command)
    if study_reply is not None:
        return study_reply

    remember_response = _handle_remember_command(command)
    if remember_response:
        return remember_response

    # --- TRAIN / LEARN commands (nova_knowledge) --------------------------
    learn_reply = _handle_learn_command(command, attached_file)
    if learn_reply:
        return learn_reply

    # ---------------- DOCTOR (self-diagnostic) -----------------------------
    # "doctor", "nova doctor", "health check" - Nova inspects its own
    # health (API keys, packages, OCR, internet, data files, git) and
    # returns a report. Lazy import: PyInstaller needs
    # --hidden-import nova_doctor (wired in build.py).
    if command in ("doctor", "nova doctor", "health check", "health",
                   "run diagnostics", "diagnostics", "doctor report"):
        try:
            from nova_doctor import handle_doctor_command
            return handle_doctor_command(command)
        except Exception as exc:
            log.exception("doctor command failed")
            return f"Doctor is unavailable right now: {type(exc).__name__}: {exc}"

    # ---------------- COMPUTER USE (semantic screen control) --------------
    # "screen dekho", "click on search bar", "search bar me hello likho",
    # "come back on home screen" - naam/jagah se PC control, no coordinates.
    # parse_command() is tight; returns None for normal chat so we fall
    # through to the rest of the router.
    try:
        from nova_features import computer_use as _cu
    except Exception:
        _cu = None
    if _cu:
        cu_reply = _cu.execute_command(command)
        if cu_reply:
            return cu_reply

    if "stop speaking" in command:
        mute_voice()
        return "Okay, I will stay silent until you enable voice again."
    if "start speaking" in command:
        unmute_voice()
        return "Voice mode enabled."

    # ---------------- OPEN YOUTUBE / GOOGLE / CHROME / WHATSAPP ---------
    if "open youtube" in command or "open yt" in command:
        webbrowser.open("https://www.youtube.com")
        return "Opening YouTube"

    if "open google" in command:
        webbrowser.open("https://www.google.com")
        return "Opening Google"

    if "open chrome" in command:
        # list-form, no shell, no injection vector
        try:
            subprocess.Popen(["cmd", "/c", "start", "", "chrome"], shell=False)
        except Exception:
            log.exception("Failed to start chrome")
        return "Opening Chrome"

    if "open whatsapp" in command:
        return open_whatsapp(use_web="web" in command)

    # ---------------- SAVE WHATSAPP CONTACT --------------------------------
    if ("save contact" in command or "remember contact" in command or
            "add contact" in command or "store contact" in command):
        reply = save_whatsapp_contact(command)
        if reply:
            return reply

    # ---------------- SEND WHATSAPP MESSAGE -------------------------------
    # Matches "send whatsapp message to <number|name> saying <text>" etc.
    if ("whatsapp" in command and
            any(w in command for w in
                ("send", "message", "saying", "text"))):
        reply = send_whatsapp_message(command)
        if reply:
            return reply

    # ---------------- BROWSER: SEARCH / OPEN URL ----------------------
    if "search for" in command:
        query = command.replace("search for", "", 1).strip()
        if not query:
            return "What do you want me to search for?"
        try:
            from nova_features.browser_control import search as _bc_search
            return _bc_search(query, "google").get("message", f"Searching for {query}")
        except Exception as e:
            return f"Search failed: {e}"
    if "open website" in command or "open site" in command:
        site = command.replace("open website", "").replace("open site", "").strip()
        if not site:
            return "Which website?"
        try:
            from nova_features.browser_control import open_new_tab as _bc_open
            return _bc_open(site).get("message", f"Opening {site}")
        except Exception as e:
            return f"Failed to open: {e}"

    # ---------------- ALARM SCHEDULER ----------------------------------
    if "set alarm" in command or "alarm at" in command or "alarm for" in command:
        try:
            from nova_features.alarm_scheduler import set_alarm as _set_alarm
            m = re.search(r"(\d{1,2})[.:h](\d{2})", command)
            t = (m.group(1).zfill(2) + ":" + m.group(2)) if m else None
            label = "Alarm"
            for kw in ["set alarm for", "alarm for", "set alarm at", "alarm at"]:
                if kw in command:
                    after = command.split(kw, 1)[1]
                    label = re.split(r"\d{1,2}[.:h]\d{2}", after)[0].strip() or label
                    break
            if t:
                return _set_alarm(label, t, "daily").get("message", "Alarm set")
            return "I need a time. Example: 'set alarm for meeting at 09:30'"
        except Exception as e:
            return f"Alarm failed: {e}"
    if "list alarms" in command or "show alarms" in command:
        try:
            from nova_features.alarm_scheduler import get_alarms as _get_alarms
            return _get_alarms().get("message", "No alarms.")
        except Exception as e:
            return f"Alarm check failed: {e}"

    # ---------------- EMAIL NOTIFICATIONS ------------------------------
    if "send email" in command or "email reminder" in command:
        try:
            from nova_features.email_notifications import get_email_status as _email_st, send_reminder_email as _send_email
            if not _email_st().get("configured"):
                return _email_st().get("message", "Configure email first in Nova's Email Notifications panel.")
            recip = command.replace("send email", "").replace("email reminder", "").replace("to", "").strip()
            if "@" not in recip:
                return "Please say the recipient, e.g. 'send email to friend@gmail.com'"
            return _send_email("Reminder from Nova", recip).get("message", "Email sent")
        except Exception as e:
            return f"Email failed: {e}"
    if "email status" in command or "check email" in command:
        try:
            from nova_features.email_notifications import get_email_status as _email_st
            return _email_st().get("message", "Email status checked")
        except Exception as e:
            return f"Email check failed: {e}"

    # ---------------- PLAY SONG ----------------------------------------
    if command.startswith("run"):
        song = command.replace("run", "", 1).strip()
        if not song:
            return "Tell me the song name."
        if pywhatkit is None:
            return "Song playback is unavailable because pywhatkit is not installed."
        # URL-encode for safety (pywhatkit does this internally, but
        # explicit defence-in-depth).
        safe_song = urllib.parse.quote(song, safe="")
        try:
            pywhatkit.playonyt(safe_song)
        except Exception:
            log.exception("pywhatkit.playonyt failed")
            return "Couldn't play that song."
        return f"Playing {song} on YouTube"

    # ---------------- BRIGHTNESS ---------------------------------------
    if "increase brightness" in command:
        if sbc is None:
            return "Brightness control is not available on this system."
        try:
            current = sbc.get_brightness()[0]
            sbc.set_brightness(min(100, current + 10))
        except Exception:
            log.exception("set_brightness failed")
            return "Couldn't change brightness."
        return "Increasing brightness"

    if "decrease brightness" in command:
        if sbc is None:
            return "Brightness control is not available on this system."
        try:
            current = sbc.get_brightness()[0]
            sbc.set_brightness(max(0, current - 10))
        except Exception:
            log.exception("set_brightness failed")
            return "Couldn't change brightness."
        return "Decreasing brightness"

    # ---------------- SHUTDOWN / RESTART (now safe) --------------------
    if "shutdown pc" in command:
        if not confirm_destructive:
            return "Shutdown requires confirmation. Tap the 'Confirm' button."
        if not _destructive_ok():
            return "Shutdown was just used — try again in a minute."
        try:
            subprocess.run(["shutdown", "/s", "/t", "30"], check=False)
        except Exception:
            log.exception("shutdown failed")
            return "Couldn't issue the shutdown command."
        return "Shutting down in 30 seconds — cancel with: shutdown /a"

    if "restart pc" in command:
        if not confirm_destructive:
            return "Restart requires confirmation. Tap the 'Confirm' button."
        if not _destructive_ok():
            return "Restart was just used — try again in a minute."
        try:
            subprocess.run(["shutdown", "/r", "/t", "30"], check=False)
        except Exception:
            log.exception("restart failed")
            return "Couldn't issue the restart command."
        return "Restarting in 30 seconds — cancel with: shutdown /a"

    # ---------------- MOOD MUSIC ---------------------------------------
    if "happy" in command:
        webbrowser.open("https://www.youtube.com/results?search_query=happy+songs")
        return "Playing happy songs for you"
    if "angry" in command:
        webbrowser.open("https://www.youtube.com/results?search_query=calm+music")
        return "Calming your mood"
    if "romantic" in command:
        webbrowser.open("https://www.youtube.com/results?search_query=romantic+songs")
        return "Opening romantic playlist"
    if "motivational" in command:
        webbrowser.open("https://www.youtube.com/results?search_query=motivational+playlist")
        return "Opening motivational playlist"
    if "english vibe" in command:
        webbrowser.open("https://www.youtube.com/results?search_query=english+sad+vibe+playlist")
        return "Feel some English music to relax your mood"
    if "sad" in command:
        webbrowser.open("https://www.youtube.com/results?search_query=sad+romantic+playlist")
        return "Opening a sad romantic playlist to relax your mood"

    # ---------------- NEWS / WEATHER -----------------------------------
    if any(w in command for w in [
        "today's news", "aaj ki news", "news briefing",
        "daily briefing", "news sunao", "news batao",
        "main news", "top news", "top headlines",
        "headlines", "news about", "news on", "news regarding",
        "tell me current news",
    ]) or command.startswith("news") or any(w in command for w in [" news in ", " news from ", " news at "]):
        return get_news_for_request(command)

    if any(w in command for w in ["weather in", "weather of", "what is the weather in"]):
        return handle_weather_command(command)

    # ---------------- THANKS / MEMORY RECALL ---------------------------
    if "thank you" in command or "thanks" in command:
        return "You're welcome! Have a great day ahead"

    if "my name is" in command:
        return "Say 'remember my name is ...' if you want me to save it."

    if "what is my name" in command:
        name = recall("username")
        return f"Your name is {name}" if name else "I don't know your name yet"

    if "my favorite color is" in command:
        return "Say 'remember my favorite color is ...' if you want me to save it."

    if "what is my favorite color" in command:
        color = recall("favorite_color")
        return f"Your favorite color is {color}" if color else "I don't know your favorite color yet"

    if "show history" in command:
        return get_recent_history()

    if "clear history" in command:
        clear_chat_history()
        return "History cleared"

    return "Command not recognized"


# ---------------- FUZZY FALLBACK ----------------------------------------
KNOWN_PHRASES = [
    "stop speaking", "start speaking",
    "open youtube", "open yt",
    "open google", "open chrome",
    "open whatsapp",
    "send whatsapp", "whatsapp message", "send whatsapp message",
    "whatsapp to", "message on whatsapp", "message whatsapp",
    "save contact", "add contact", "set contact",
    "screen dekho", "screen check karo", "kya dikh raha hai",
    "click on search bar", "click on home button", "double click",
    "search bar me type karo", "press enter", "scroll down",
    "come back on home screen", "show desktop",
    "increase brightness", "decrease brightness",
    "shutdown pc", "restart pc",
    "happy", "angry", "romantic", "motivational",
    "english vibe", "sad",
    "today's news", "aaj ki news", "news briefing",
    "daily briefing", "news sunao", "news batao",
    "main news", "top news", "top headlines", "headlines",
    "news about", "news on", "news regarding",
    "tell me current news", "news in", "news from", "news at",
    "weather in", "weather of", "what is the weather in",
    "thank you", "thanks",
    "remember my name is", "my name is", "what is my name",
    "remember my favorite color is", "my favorite color is", "what is my favorite color",
    "show history", "clear history",
]


def smart_execute(command, cutoff=0.75, *, confirm_destructive: bool = False):
    import difflib
    command = command.lower().strip()
    matches = difflib.get_close_matches(command, KNOWN_PHRASES, n=1, cutoff=cutoff)
    if matches:
        return execute_command(matches[0], confirm_destructive=confirm_destructive)

    # Fuzzy match missed -> try the LLM intent router (function-calling).
    # It only fires when the sentence contains an action keyword, and it
    # returns None for ordinary questions so chat fallback stays fast.
    try:
        import nova_intents
        intent_result = nova_intents.route_intent(command)
        if intent_result:
            return intent_result
    except Exception as exc:  # never let an add-on break the command chain
        import logging
        logging.getLogger("nova.commands").debug(
            "intent router unavailable: %s", exc)
    return None
