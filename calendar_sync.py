# ==========================================
# NOVA CALENDAR SYNC - .ics without OAuth pain
# ------------------------------------------
# Real Google Calendar API sync needs OAuth credentials + a cloud
# project; this module gets you 90% of the value with zero setup by
# using the universal iCalendar (.ics) format that Windows Calendar,
# Google Calendar and phone calendars all import natively:
#
#   EXPORT: exams + tasks with due dates -> nova_calendar.ics
#           (double-click the file to add them to any calendar app)
#   IMPORT: parse a user-provided .ics into Nova reminders/events
#
# Pure stdlib - no external dependencies.
# ==========================================

import logging
import os
import re
import uuid
from datetime import datetime, timedelta

from nova_storage import writable_data_path

log = logging.getLogger("nova.calendar")

__version__ = "1.0.0"

DEFAULT_ICS_PATH = writable_data_path("nova_calendar.ics")

_ICS_DT_FMT = "%Y%m%dT%H%M%S"
_CRLF = "\r\n"


def _escape(text):
    return (str(text).replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def _unescape(text):
    return (str(text).replace("\\n", "\n").replace("\\,", ",")
            .replace("\\;", ";").replace("\\\\", "\\"))


def _fold_line(line):
    """RFC 5545 line folding at 75 octets."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    parts = []
    while encoded:
        parts.append(encoded[:73].decode("utf-8", errors="ignore"))
        encoded = encoded[73:]
    return (parts[0] + _CRLF + "".join(" " + p for p in parts[1:]))


def _vevent(summary, start_dt, end_dt=None, description="", uid=None):
    end_dt = end_dt or (start_dt + timedelta(hours=1))
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid or (uuid.uuid4().hex + '@nova')}",
        f"DTSTAMP:{datetime.now().strftime(_ICS_DT_FMT)}",
        f"DTSTART:{start_dt.strftime(_ICS_DT_FMT)}",
        f"DTEND:{end_dt.strftime(_ICS_DT_FMT)}",
        f"SUMMARY:{_escape(summary)}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{_escape(description)}")
    # 10-minute reminder before every event
    lines += ["BEGIN:VALARM", "TRIGGER:-PT10M", "ACTION:DISPLAY",
              f"DESCRIPTION:{_escape(summary)}", "END:VALARM"]
    lines.append("END:VEVENT")
    return [_fold_line(l) for l in lines]


def export_calendar(path=DEFAULT_ICS_PATH, include_exams=True,
                    include_tasks=True):
    """Write exams (+ dashboard tasks/goals with dates) to an .ics file.

    Returns dict report with path + event count."""
    events = []

    if include_exams:
        try:
            import nova_exams
            for exam in nova_exams.exams_with_days():
                day = datetime.strptime(exam["date"], "%Y-%m-%d")
                days = exam["days_left"]
                note = ("All the best! " if 0 <= days <= 7 else "")
                events += _vevent(f"📝 Exam: {exam['name']}",
                                  day.replace(hour=9, minute=0),
                                  day.replace(hour=12, minute=0),
                                  description=f"{note}Good luck from Nova!")
        except Exception as exc:
            log.warning("exam export skipped: %s", exc)

    if include_tasks:
        try:
            import nova_storage
            base = datetime.now().replace(hour=18, minute=0, second=0,
                                          microsecond=0)
            goals = nova_storage.dashboard_data.get("goals", [])
            pending = [g.get("text", "") for g in goals
                       if isinstance(g, dict) and not g.get("done")][:10]
            for i, text in enumerate(pending):
                if not text:
                    continue
                day = base + timedelta(days=i)
                events += _vevent(f"🎯 Goal: {text}", day,
                                  description="From your Nova goals list.")
        except Exception as exc:
            log.warning("task export skipped: %s", exc)

    if not events:
        return {"success": False,
                "message": "Koi export-able event nahi mila.",
                "path": path, "events": 0}

    body = ["BEGIN:VCALENDAR", "VERSION:2.0",
            "PRODID:-//Nova AI//Calendar Export//EN", "CALSCALE:GREGORIAN"]
    body += events
    body.append("END:VCALENDAR")

    try:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(_CRLF.join(body) + _CRLF)
        event_count = sum(1 for e in events if e == "BEGIN:VEVENT")
        return {
            "success": True,
            "path": path,
            "events": event_count,
            "message": (f"📅 {path} likh diya ({event_count} event(s)). "
                        "Double-click karke calendar app mein import karo."),
        }
    except Exception as exc:
        return {"success": False, "message": f"Export failed: "
                 f"{type(exc).__name__}", "path": path, "events": 0}

# ---------------------------------------------------------------------------
# Import: parse a .ics file into Nova-friendly events
# ---------------------------------------------------------------------------
def _unfold(text):
    """Undo RFC 5545 line folding."""
    return re.sub(r"\r?\n[ \t]", "", text)


def _parse_ics_datetime(value):
    value = value.strip().rstrip("Z")
    for fmt in (_ICS_DT_FMT, "%Y%m%dT%H%M", "%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def import_ics(path, add_reminders=False):
    """Parse *path* (.ics) into [{summary, start, end?, description}].

    With add_reminders=True, upcoming events also become Nova reminders
    (via smart_reminder). Returns dict report.
    """
    if not os.path.isfile(path):
        return {"success": False, "events": [],
                "message": f"File not found: {path}"}

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = _unfold(f.read())
    except Exception as exc:
        return {"success": False, "events": [],
                "message": f"Read failed ({type(exc).__name__})."}

    events = []
    current = None
    for line in raw.splitlines():
        if line == "BEGIN:VEVENT":
            current = {"summary": "", "start": None,
                       "description": ""}
        elif line == "END:VEVENT":
            if current and current["start"]:
                events.append(current)
            current = None
        elif current is not None and ":" in line:
            key, _, value = line.partition(":")
            key = key.split(";")[0].upper()
            if key == "SUMMARY":
                current["summary"] = _unescape(value)
            elif key == "DESCRIPTION":
                current["description"] = _unescape(value)[:500]
            elif key in ("DTSTART", "DTSTART;VALUE=DATE"):
                current["start"] = _parse_ics_datetime(value)

    added_reminders = 0
    if add_reminders:
        now = datetime.now()
        from nova_features.smart_reminder import set_reminder
        for ev in events[:20]:
            start = ev.get("start")
            if not start or start <= now:
                continue
            delta = start - now
            minutes = max(1, int(delta.total_seconds() // 60))
            try:
                set_reminder(ev["summary"] or "Calendar event",
                             f"in {minutes} minutes")
                added_reminders += 1
            except Exception:
                pass

    msg = f"Parsed {len(events)} event(s) from {os.path.basename(path)}."
    if added_reminders:
        msg += f" {added_reminders} upcoming → Nova reminders."
    return {"success": True, "events": events,
            "reminders_added": added_reminders, "message": msg}


if __name__ == "__main__":
    print(export_calendar()["message"])