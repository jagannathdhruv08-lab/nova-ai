try:
    import requests
except ImportError:
    requests = None
import os
import sys
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return None

# BUG FIX: load_dotenv() with no arguments searches from the current
# working directory, which changes depending on how Nova is launched.
# When frozen into a onefile .exe, __file__ points at a temp _MEIxxxx
# folder with no .env -- so look next to sys.executable (Nova.exe).
if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_PATH = os.path.join(_BASE_DIR, ".env")
load_dotenv(dotenv_path=_ENV_PATH)

# ==========================================
# WEATHER FEATURE
# ==========================================
#
# Setup kaise karein:
# 1. https://openweathermap.org pe free account banao
# 2. API key lo (free mein milti hai)
# 3. .env file mein daalo: WEATHER_API_KEY=your_key_here
#
# Command examples:
#   "weather in Delhi"
#   "weather in Mumbai"
#   "what is the weather in Bangalore"
# ==========================================

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


def get_weather(city):
    """
    City ka weather fetch karta hai OpenWeatherMap se.
    Returns: ek readable string jaise Nova bol sake
    """

    if not WEATHER_API_KEY:
        return "Weather API key nahi mili. .env file mein WEATHER_API_KEY daalo."

    if requests is None:
        return "Weather is unavailable because the requests package is not installed."

    try:
        # API call
        response = requests.get(WEATHER_URL, params={
            "q": city,
            "appid": WEATHER_API_KEY,
            "units": "metric",      # Celsius mein temperature
            "lang": "en"
        })

        # City nahi mili
        if response.status_code == 404:
            return f"Sorry, {city} nahi mili. City ka naam check karo."

        data = response.json()

        # Data extract karo
        temp        = round(data["main"]["temp"])
        feels_like  = round(data["main"]["feels_like"])
        humidity    = data["main"]["humidity"]
        description = data["weather"][0]["description"].capitalize()
        city_name   = data["name"]
        country     = data["sys"]["country"]

        return (
            f"{city_name}, {country} mein abhi {temp} degree Celsius hai. "
            f"{description}. "
            f"Humidity {humidity} percent hai aur feel {feels_like} degree jaisi ho rahi hai."
        )

    except requests.ConnectionError:
        return "Internet connection nahi hai. Weather nahi milega abhi."

    except Exception as e:
        return f"Weather error: {e}"


def handle_weather_command(command):
    """
    Command string se city nikalta hai aur weather deta hai.
    commands.py se call hoga.
    """

    # "weather in delhi" → "delhi"
    for keyword in ["weather in", "what is the weather in", "weather of"]:
        if keyword in command:
            city = command.replace(keyword, "").strip()
            if city:
                return get_weather(city)

    return "Kaunsi city ka weather chahiye? Bolo 'weather in Delhi'"
