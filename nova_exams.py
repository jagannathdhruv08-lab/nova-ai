# ==========================================
# NOVA EXAMS - exam countdown tracker
# ------------------------------------------
# Small, dependency-free module: store exam dates, get chat-friendly
# countdowns with urgency colours, and a context block the coach can
# inject into its prompts so Nova naturally says "IMU CET is in 12
# days" when discussing study plans.
# ==========================================

import json
import logging
import os
from datetime import date, datetime

from nova_storage import writable_data_path

log = logging.getLogger("nova.exams")

__version__ = "1.0.0"

EXAMS_FILE = writable_data_path("nova_exams.json")

_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %B %Y",
                 "%d %b %Y", "%B %d %Y")


def _load():
    try:
        if os.path.exists(EXAMS_FILE):
            with open(EXAMS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("exams", [])
                return data
    except Exception as exc:
        log.error("exams load failed: %s", exc)
    return {"exams": []}


def _save(data):
    try:
        with open(EXAMS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception as exc:
        log.error("exams save failed: %s", exc)


def _parse_date(raw):
    s = str(raw or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def set_exam(name, date_str):
    """Add/update an exam by name. Returns a user-facing message."""
    name = str(name or "").strip()[:100]
    parsed = _parse_date(date_str)
    if not name:
        return "Exam ka naam batao."
    if parsed is None:
        return (f"'{date_str}' date samajh nahi aayi - format: "
                "YYYY-MM-DD (jaise 2027-04-12).")
    data = _load()
    today = date.today()
    for exam in data["exams"]:
        if exam["name"].lower() == name.lower():
            exam["date"] = parsed.isoformat()
            days = (parsed - today).days
            _save(data)
            return f"📅 {name} updated → {parsed.isoformat()} ({_urgency(days)})."
    data["exams"].append({"name": name, "date": parsed.isoformat(),
                          "created": today.isoformat()})
    # keep list bounded & sorted by date
    data["exams"] = sorted(data["exams"], key=lambda e: e["date"])[:30]
    _save(data)
    days = (parsed - today).days
    if days < 0:
        return f"📅 {name} saved — note: woh date ({parsed}) guzar chuki hai."
    return f"📅 {name} saved! {_urgency(days)}"


def delete_exam(name):
    data = _load()
    keep = [e for e in data["exams"] if e["name"].lower() != str(name).strip().lower()]
    if len(keep) == len(data["exams"]):
        return f"'{name}' naam ka koi exam nahi mila."
    data["exams"] = keep
    _save(data)
    return f"🗑️ '{name}' removed."


def _urgency(days):
    if days < 0:
        return "ho gaya (past)"
    if days == 0:
        return "🔴 AAJ HAI! All the best!"
    if days <= 7:
        return f"🔴 sirf {days} din baaki"
    if days <= 30:
        return f"🟡 {days} din baaki"
    return f"🟢 {days} din baaki"


def exams_with_days(as_of=None):
    """List of {name, date, days_left} sorted soonest-first."""
    day = as_of or date.today()
    out = []
    for exam in _load()["exams"]:
        try:
            exam_date = date.fromisoformat(exam["date"])
        except (KeyError, ValueError):
            continue
        out.append({
            "name": exam["name"],
            "date": exam["date"],
            "days_left": (exam_date - day).days,
        })
    return sorted(out, key=lambda e: e["days_left"])


def exams_overview_text(as_of=None):
    """Chat-friendly countdown block."""
    exams = exams_with_days(as_of=as_of)
    if not exams:
        return ("📅 Koi exam track nahi ho raha. Bolo jaise: "
                "'set IMU CET exam 2027-04-12'.")
    lines = ["🗓️ Exam countdowns:\n"]
    for e in exams[:8]:
        lines.append(f"• {e['name']} — {e['date']} → {_urgency(e['days_left'])}")
    return "\n".join(lines)


def exams_context_block(max_chars=500):
    """Prompt-injection block for coach/chat prompts ('' when empty)."""
    exams = [e for e in exams_with_days() if 0 <= e["days_left"] <= 365]
    if not exams:
        return ""
    parts = [f"- {e['name']}: {e['days_left']} days left" for e in exams[:5]]
    block = ("## Upcoming exams (mention naturally when planning study):\n"
             + "\n".join(parts) + "\n\n")
    return block[:max_chars]


__all__ = ["set_exam", "delete_exam", "exams_with_days", "exams_overview_text",
           "exams_context_block", "_parse_date", "EXAMS_FILE"]