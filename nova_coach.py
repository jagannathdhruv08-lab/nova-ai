# ==========================================
# NOVA AI - COACH CHAT
# A separate, topic-locked chat (only studies/PCM, goals, tasks, and
# nutrition/protein) that:
#   - remembers everything said TODAY (own persisted history)
#   - automatically rates the day (Bad -> Good) at 9:00 PM based on
#     how many tasks/goals were completed and how close nutrition was
#     to target
#   - wipes today's conversation at midnight so tomorrow starts fresh
#     (the daily ratings themselves are kept as a permanent log, so
#     you can see your trend over time)
# ==========================================

import os
import json
import time
from datetime import date

from nova_storage import writable_data_path, dashboard_data
from nova_nutrition import get_today_totals, get_profile
from memory import memory_facts_block
from brain import _strip_emojis

COACH_PATH = writable_data_path("nova_coach_data.json")

SYSTEM_SCOPE = (
    "Tum Nova ke andar ek focused Study & Health Coach ho. Tum SIRF in topics pe baat karte ho: "
    "Class 12 PCM padhai, Merchant Navy preparation, goals, tasks, aur nutrition/protein/fitness. "
    "Agar user kisi bilkul alag topic pe baat kare (jaise movies, games, random chit-chat), to politely "
    "usse wapas study/goals/nutrition pe le aao - lekin rude ya cold mat bano, ek supportive coach ki tarah baat karo. "
    "Chhote, seedhe, motivating jawab do - lecture mat do."
    "baar baar wahi baat repeat mat karo, aur user ke progress ko acknowledge karo."
    "ejaculation, masturbation, ya sexual content ke baare mein acche se samjhao.baat ko taalne ki koshis mat karo, lekin usse study aur health pe focus karne ke liye motivate karo."
    " Jab aap koi concept samjhate ho (especially maths, science, ya study topics), "
    "use this study-friendly structure so students retain faster:\n\n"
    "1. Open with praise + emoji, e.g. \"This is **excellent** breakdown! 🎯\"\n"
    "2. Give a super-simplified \"Even MORE for quick retention\" version\n"
    "3. Add \"## **Real-world analogy** 🎯\" — use a vivid, relatable analogy\n"
    "4. Add \"## **For your error journal** 📔\" — list common mistakes, "
    "root causes, and remedies\n"
    "5. Add \"## **Quick CBSE practice drill** 🎓\" — 2-3 practice problems "
    "with answers\n"
    "6. End with a friendly call-to-action encouraging more practice\n\n"
    "Use Markdown bold (**text**) and headers (##). Keep each section tight "
    "and scannable. For short questions or non-study topics, reply normally "
    "without forcing the full structure."
)


def _default_data():
    return {"date": str(date.today()), "chat_history": [], "ratings": [], "rating_done_date": None}


def _load():
    default = _default_data()
    try:
        if os.path.exists(COACH_PATH):
            with open(COACH_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in default.items():
                data.setdefault(k, v)
            return data
    except Exception as exc:
        print("coach data load failed:", exc)
    return default


def _save():
    try:
        with open(COACH_PATH, "w", encoding="utf-8") as f:
            json.dump(coach_data, f, indent=2)
    except Exception as exc:
        print("coach data save failed:", exc)


coach_data = _load()


def reset_for_new_day_if_needed():
    """At midnight rollover: wipe today's coach CHAT (not the
    permanent ratings log) so tomorrow starts with a clean slate.
    Returns True if a reset just happened."""
    today_str = str(date.today())
    if coach_data["date"] != today_str:
        coach_data["date"] = today_str
        coach_data["chat_history"] = []
        coach_data["rating_done_date"] = None
        _save()
        return True
    return False


def add_coach_message(sender, text, time_str=None):
    coach_data.setdefault("chat_history", []).append({
        "sender": sender,
        "text": text,
        "time": time_str or time.strftime("%I:%M %p"),
    })
    coach_data["chat_history"] = coach_data["chat_history"][-200:]
    _save()


def _describe_items(title, items):
    """Returns 2 lines specifically naming WHICH items are done vs pending,
    so the coach can directly see what got completed instead of only counts."""
    done = [x.get("text", "").strip() for x in items if x.get("done")]
    pending = [x.get("text", "").strip() for x in items if not x.get("done")]
    done_s = ", ".join(f'"{d}"' for d in done) if done else "koi nahi"
    pend_s = ", ".join(f'"{p}"' for p in pending) if pending else "koi nahi — sab complete hai! 🎉"
    return [
        f"{title} done: {done_s}",
        f"{title} pending: {pend_s}",
    ]


def build_coach_prompt(user_message):
    """Builds the full prompt sent to ask_nova(): scope instructions +
    today's real progress numbers + recent coach conversation + the
    new message. Keeps the coach grounded in actual data instead of
    guessing."""
    tasks = dashboard_data.get("tasks", [])
    goals = dashboard_data.get("goals", [])
    done_tasks = sum(1 for t in tasks if t.get("done"))
    done_goals = sum(1 for g in goals if g.get("done"))
    totals = get_today_totals()
    profile = get_profile()

    progress = (
        f"Aaj ka progress - Tasks: {done_tasks}/{len(tasks)} complete. "
        f"Goals: {done_goals}/{len(goals)} complete. "
        f"Nutrition aaj tak: {totals['calories']:.0f} kcal, {totals['protein_g']:.0f}g protein "
        f"(target: {profile.get('daily_calorie_target')} kcal, {profile.get('daily_protein_target_g')}g protein)."
    )

    # NEW: specifically name WHICH goals/tasks the user completed (and which
    # are still pending), so the coach can acknowledge real progress instead
    # of just seeing totals.
    detail_lines = (
        _describe_items("Tasks", tasks)
        + _describe_items("Goals", goals)
    )
    detail = "\n".join(detail_lines)

    # Expanded context: remember more of today's coach conversation (from 8
    # to 20 messages). The Groq model has a 131K-token window and is fast, so
    # this gives the coach better continuity without slowing replies.
    recent = coach_data.get("chat_history", [])[-20:]
    transcript = "\n".join(f"{'You' if m['sender']=='user' else 'Coach'}: {_strip_emojis(m['text'])}" for m in recent)

    # Aaj ka plan (agar koi banaya gaya hai) — coach ko daily direction deta hai.
    _today_str = str(date.today())
    _plan = dashboard_data.get("daily_plan", {})
    plan_line = ""
    if isinstance(_plan, dict) and _plan.get("date") == _today_str and _plan.get("plan"):
        plan_line = f"Aaj ka plan:\n{_strip_emojis(str(_plan.get('plan')))}\n\n"

    # Memorised facts — coach bhi user ko personal jaanta hai.
    memory_block = memory_facts_block()

    return (
        f"{SYSTEM_SCOPE}\n\n{progress}\n\n{detail}\n\n"
        + (plan_line or "")
        + (memory_block or "")
        + (f"Ab tak ki baatcheet:\n{transcript}\n\n" if transcript else "")
        + f"User ka naya message: {_strip_emojis(user_message)}"
    )


# ==========================================
# DAILY RATING (fires once at/after 9 PM)
# ==========================================

def compute_daily_score():
    """Deterministic score (0-100), no AI call needed - always works
    even offline. Based on: task completion %, goal completion %,
    and protein-target %."""
    tasks = dashboard_data.get("tasks", [])
    goals = dashboard_data.get("goals", [])
    task_pct = (sum(1 for t in tasks if t.get("done")) / len(tasks) * 100) if tasks else 0
    goal_pct = (sum(1 for g in goals if g.get("done")) / len(goals) * 100) if goals else 0

    totals = get_today_totals()
    profile = get_profile()
    protein_target = profile.get("daily_protein_target_g") or 0
    protein_pct = min(totals["protein_g"] / protein_target * 100, 100) if protein_target else 0

    overall = (task_pct + goal_pct + protein_pct) / 3
    return overall, task_pct, goal_pct, protein_pct


def rating_label(score):
    if score >= 85:
        return "Excellent"
    if score >= 65:
        return "Good"
    if score >= 40:
        return "Average"
    return "Needs Improvement"


def should_generate_rating_now():
    """True exactly once per day, from 9:00 PM onward."""
    now = time.localtime()
    today_str = str(date.today())
    if coach_data.get("rating_done_date") == today_str:
        return False
    return now.tm_hour >= 21


def generate_daily_rating():
    overall, task_pct, goal_pct, protein_pct = compute_daily_score()
    label = rating_label(overall)
    today_str = str(date.today())

    summary = (
        f"\U0001F31F Aaj ki Rating: {label} ({overall:.0f}/100)\n\n"
        f"- Tasks (routine/study/exercise): {task_pct:.0f}% complete\n"
        f"- Goals: {goal_pct:.0f}% complete\n"
        f"- Protein target: {protein_pct:.0f}% achieved\n\n"
    )
    if overall >= 85:
        summary += "Bahut badhiya din tha - discipline top level pe hai! Kal bhi yehi maintain karo."
    elif overall >= 65:
        summary += "Accha din tha. Thoda aur push karo to kal Excellent ban sakta hai."
    elif overall >= 40:
        summary += "Average raha - kal tasks aur protein dono pe zyada dhyaan do."
    else:
        summary += "Aaj ka din target se kaafi peeche raha. Deck Cadet banne ke liye kal se strict routine follow karna zaroori hai - ek din pichhe rehna theek hai, lekin habit mat banne do."

    coach_data.setdefault("ratings", []).append({
        "date": today_str, "score": round(overall, 1), "label": label, "summary": summary,
    })
    coach_data["rating_done_date"] = today_str
    _save()
    return summary


def get_rating_history():
    return coach_data.get("ratings", [])
