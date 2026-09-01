# ==========================================
# NOVA AI - NUTRITION TRACKER
# Send a photo of your thali/plate -> Gemini vision estimates the
# food items (in grams), calories, protein, carbs, and fats -> Nova
# compares that against your body profile and the Merchant Navy
# weight-gain/protein targets from your routine, and tells you if
# today's intake is on track.
#
# This reuses the SAME Gemini vision call already built in
# nova_vision.py - no new AI setup needed, just new prompts + storage.
# ==========================================

import json
from datetime import date

from nova_storage import writable_data_path
from nova_vision import ask_gemini_vision, last_gemini_error

NUTRITION_PATH = writable_data_path("nova_nutrition_data.json")

# Defaults straight from the Merchant Navy routine plan (weight gain
# target 50-55kg, ~80-100g protein/day). Update via set_profile().
DEFAULT_PROFILE = {
    "height_cm": None,
    "weight_kg": None,
    "target_weight_kg": 55,
    "daily_protein_target_g": 90,
    "daily_calorie_target": 2800,  # reasonable bulking estimate for a growing teenager; adjust anytime
}


def _load():
    default = {"profile": dict(DEFAULT_PROFILE), "days": {}}
    try:
        import os
        if os.path.exists(NUTRITION_PATH):
            with open(NUTRITION_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in default.items():
                data.setdefault(k, v)
            for k, v in DEFAULT_PROFILE.items():
                data["profile"].setdefault(k, v)
            return data
    except Exception as exc:
        print("nutrition data load failed:", exc)
    return default


def _save():
    try:
        with open(NUTRITION_PATH, "w", encoding="utf-8") as f:
            json.dump(nutrition_data, f, indent=2)
    except Exception as exc:
        print("nutrition data save failed:", exc)


nutrition_data = _load()


def set_profile(height_cm=None, weight_kg=None, target_weight_kg=None, daily_protein_target_g=None):
    profile = nutrition_data["profile"]
    if height_cm is not None:
        profile["height_cm"] = height_cm
    if weight_kg is not None:
        profile["weight_kg"] = weight_kg
    if target_weight_kg is not None:
        profile["target_weight_kg"] = target_weight_kg
    if daily_protein_target_g is not None:
        profile["daily_protein_target_g"] = daily_protein_target_g
    _save()


def get_profile():
    return nutrition_data["profile"]


def _today_bucket():
    today_str = str(date.today())
    nutrition_data["days"].setdefault(today_str, {"meals": [], "totals": {"calories": 0, "protein_g": 0, "carbs_g": 0, "fats_g": 0}})
    return today_str, nutrition_data["days"][today_str]


def get_today_totals():
    _, bucket = _today_bucket()
    return bucket["totals"]


def analyze_meal_photo(pil_image, note=""):
    """Sends the plate photo to Gemini with the user's profile and
    today's running totals as context, asks for a structured
    breakdown, stores it, and returns the text response to show in
    chat. Returns None (and sets last_gemini_error) on failure."""
    if pil_image is None:
        return None

    profile = nutrition_data["profile"]
    today_str, bucket = _today_bucket()
    totals_so_far = bucket["totals"]

    height_line = f"{profile['height_cm']} cm" if profile["height_cm"] else "not told yet"
    weight_line = f"{profile['weight_kg']} kg" if profile["weight_kg"] else "not told yet"

    prompt = f"""Ye ek thali/plate ki photo hai. User ka goal Merchant Navy Deck Cadet banna hai, aur unka weight-gain target hai.

User profile:
- Height: {height_line}
- Current weight: {weight_line}
- Target weight: {profile['target_weight_kg']} kg
- Daily protein target: {profile['daily_protein_target_g']} g
- Daily calorie target (bulking): {profile['daily_calorie_target']} kcal

Aaj ab tak already khaya hua (running total): {totals_so_far['calories']} kcal, {totals_so_far['protein_g']}g protein, {totals_so_far['carbs_g']}g carbs, {totals_so_far['fats_g']}g fats.

User ka note (agar hai): {note or '(koi note nahi)'}

Is photo me jo khana dikh raha hai uska andaza lagao (grams me har item), aur total calories, protein, carbs, fats batao is EXACT format me sabse pehle (taaki main isko parse kar sakoon):

ESTIMATE: calories=<number> protein=<number> carbs=<number> fats=<number>

Uske baad normal Hindi-English (Hinglish) me:
1. Kaunse items dikhe aur kitne grams
2. Ye meal unke weight-gain/protein goal ke liye achi hai ya nahi
3. Aaj ke running total ko dekhte hue kya aur khana chahiye (protein ki kami hai kya)
4. Ek chhota sa encouragement/suggestion

Agar height/weight "not told yet" hai, to Hinglish jawab ke end me politely poochho ki wo apna height aur weight bata de taaki analysis aur accurate ho sake."""

    response_text = ask_gemini_vision(pil_image, prompt)
    if response_text is None:
        return None

    # Try to parse the ESTIMATE line Gemini was asked to put first.
    calories = protein = carbs = fats = 0
    for line in response_text.splitlines():
        if line.strip().upper().startswith("ESTIMATE:"):
            try:
                parts = dict(
                    p.split("=") for p in line.split(":", 1)[1].strip().split()
                )
                calories = float(parts.get("calories", 0))
                protein = float(parts.get("protein", 0))
                carbs = float(parts.get("carbs", 0))
                fats = float(parts.get("fats", 0))
            except Exception as exc:
                print("nutrition estimate parse failed:", exc)
            break

    bucket["meals"].append({
        "time": date.today().isoformat(),
        "note": note,
        "calories": calories,
        "protein_g": protein,
        "carbs_g": carbs,
        "fats_g": fats,
        "raw_response": response_text,
    })
    bucket["totals"]["calories"] += calories
    bucket["totals"]["protein_g"] += protein
    bucket["totals"]["carbs_g"] += carbs
    bucket["totals"]["fats_g"] += fats
    _save()

    return response_text


def get_today_summary_text():
    profile = nutrition_data["profile"]
    _, bucket = _today_bucket()
    totals = bucket["totals"]
    meal_count = len(bucket["meals"])
    if meal_count == 0:
        return "Aaj tak koi meal log nahi hua. Camera se thali ki photo lo aur \"Log Meal\" dabao."
    protein_left = max(profile["daily_protein_target_g"] - totals["protein_g"], 0)
    calorie_left = max(profile["daily_calorie_target"] - totals["calories"], 0)
    return (
        f"Aaj ke {meal_count} meals ka total: {totals['calories']:.0f} kcal, "
        f"{totals['protein_g']:.0f}g protein, {totals['carbs_g']:.0f}g carbs, {totals['fats_g']:.0f}g fats.\n"
        f"Target ({profile['daily_calorie_target']} kcal / {profile['daily_protein_target_g']}g protein) tak pahunchne ke liye "
        f"abhi ~{calorie_left:.0f} kcal aur ~{protein_left:.0f}g protein baaki hai."
    )
