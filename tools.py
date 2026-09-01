import requests
import webbrowser
import re
import threading
from voice import speak

def get_weather(city=""):
    try:
        url = f"https://wttr.in/{city}?format=3"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.text.strip()
        return "Sorry, I couldn't fetch the weather right now."
    except Exception as e:
        print("Weather error:", e)
        return "Weather service is unavailable right now."

def web_search(query):
    if not query:
        return "What do you want me to search for?"
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    webbrowser.open(url)
    return f"Searching the web for {query}"

def set_reminder(command):
    # Order 1: "remind me to <task> in <number> <unit>"
    match = re.search(
        r"remind me to (.+?) in (\d+)\s*(minutes?|mins?|hours?|hrs?)",
        command
    )
    swapped = False

    if not match:
        # Order 2: "remind me in <number> <unit> to <task>"
        match = re.search(
            r"remind me in (\d+)\s*(minutes?|mins?|hours?|hrs?) to (.+)",
            command
        )
        swapped = False

    if not match:
        # Order 2: "remind me in <number> <unit> to <task>"
        match = re.search(
            r"set reminder of (\d+)\s*(minutes?|mins?|hours?|hrs?) to (.+)",
            command
        )
        swapped = True

    if not match:
        return "Please say it like: remind me to <task> in <number> minutes"

    if swapped:
        amount = int(match.group(1))
        unit = match.group(2)
        task = match.group(3).strip()
    else:
        task = match.group(1).strip()
        amount = int(match.group(2))
        unit = match.group(3)

    seconds = amount * 60 if "min" in unit else amount * 3600

    def fire_reminder():
        speak(f"Reminder: {task}")

    threading.Timer(seconds, fire_reminder).start()
    return f"Okay, I will remind you to {task} in {amount} {unit}"