import os
import sys
import re
from datetime import datetime, timedelta

try:
    import requests
except ImportError:
    requests = None

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
# NOVA NEWS BRIEFING - CUSTOM FORMAT
# ==========================================
#
# Exact format:
#   1, 2, 3   -> Indian Cricket news
#   4, 5, 6   -> Indian news useful for NDA aspirant
#   7, 8, 9, 10 -> International + Indian (spy / strategic angle)
#
# Setup:
#   1. https://newsapi.org pe free account banao
#   2. Free API key lo
#   3. .env file mein daalo: NEWS_API_KEY=your_key_here
#
# Commands:
#   "today's news"
#   "news briefing"
#   "aaj ki news"
#   "daily briefing"
# ==========================================

NEWS_API_KEY        = os.getenv("NEWS_API_KEY")
HEADLINES_URL       = "https://newsapi.org/v2/top-headlines"
EVERYTHING_URL      = "https://newsapi.org/v2/everything"
_CACHE_TTL_SECONDS  = 10 * 60
_NEWS_CACHE         = {}


# ==========================================
# FETCH HELPER
# ==========================================

def _fetch(url, params):
    """
    NewsAPI call karta hai.
    Returns: (articles list, error string or None)
    """
    if not NEWS_API_KEY:
        return [], "NEWS_API_KEY nahi mili - .env file mein daalo."

    if requests is None:
        return [], "News is unavailable because the requests package is not installed."

    params["apiKey"]   = NEWS_API_KEY
    params["language"] = "en"  # NewsAPI only accepts a single 2-letter ISO 639-1 code

    try:
        resp = requests.get(url, params=params, timeout=8)
        data = resp.json()

        if data.get("status") != "ok":
            return [], f"API Error: {data.get('message', 'unknown')}"

        articles = [
            a for a in data.get("articles", [])
            if a.get("title") and a["title"] != "[Removed]"
        ]

        return articles, None

    except requests.ConnectionError:
        return [], "Internet connection nahi hai."
    except requests.Timeout:
        return [], "News server ne response nahi diya."
    except Exception as e:
        return [], f"Error: {e}"


def _get_cached_news(key, fetcher):
    """Return cached news for up to 10 minutes to avoid too-frequent refreshes."""
    now = datetime.now()
    cached = _NEWS_CACHE.get(key)
    if cached and (now - cached["fetched_at"]).total_seconds() < _CACHE_TTL_SECONDS:
        return cached["data"]

    data = fetcher()
    _NEWS_CACHE[key] = {"data": data, "fetched_at": now}
    return data


def parse_date_input(text):
    """Parse dates like 16-july-2026 or 16 july 2026 into YYYY-MM-DD."""
    if not text:
        return None

    normalized = text.strip().lower()
    if any(word in normalized for word in ["today", "current", "latest", "now"]):
        return None
    if "yesterday" in normalized:
        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    if "tomorrow" in normalized:
        return (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    patterns = [
        "%d-%b-%Y", "%d-%B-%Y", "%d %b %Y", "%d %B %Y",
        "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"
    ]

    for pattern in patterns:
        try:
            return datetime.strptime(text.strip(), pattern).strftime("%Y-%m-%d")
        except ValueError:
            continue

    match = re.search(r"\b(\d{1,2})[-/ ]([a-zA-Z]+)[-/ ](\d{4})\b", text)
    if match:
        try:
            return datetime.strptime(
                f"{match.group(1)} {match.group(2)} {match.group(3)}",
                "%d %B %Y"
            ).strftime("%Y-%m-%d")
        except ValueError:
            return None

    return None


def _extract_topic_query(request):
    """Extract a topic like 'm.s dhoni' from requests such as 'news about m.s dhoni'."""
    text = (request or "").strip().lower()

    for prefix in ["tell me current news about ", "current news about ", "news about ", "news on ", "news regarding "]:
        if text.startswith(prefix):
            return text[len(prefix):].strip()

    if "news about" in text:
        return text.split("news about", 1)[1].strip()
    if "news on" in text:
        return text.split("news on", 1)[1].strip()
    if "news regarding" in text:
        return text.split("news regarding", 1)[1].strip()

    return None


def _extract_place_query(request):
    """Extract places from requests like 'news in Delhi on 12 August 2026'."""
    text = (request or "").strip()
    match = re.search(
        r"\b(?:in|from|at|near)\s+([a-zA-Z .'-]+?)(?=\s+\b(?:on|for|at|after|before|around|today|yesterday|about|regarding)\b|$)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    place = match.group(1).strip(" .,")
    if place.lower() in {"india", "world", "latest", "current"}:
        return place
    return place or None


def _extract_time_hint(request):
    """Extract simple time intent. NewsAPI cannot filter by hour exactly,
    but including this in the query helps when the user asks for morning,
    evening, 9 pm, etc."""
    text = (request or "").strip().lower()
    named = re.search(r"\b(morning|afternoon|evening|night|midnight|noon)\b", text)
    if named:
        return named.group(1)
    clock = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text)
    if clock:
        return clock.group(0)
    clock_24 = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", text)
    if clock_24:
        return clock_24.group(0)
    return None


def _build_news_query(topic=None, place=None, time_hint=None):
    parts = []
    if topic:
        parts.append(topic)
    if place:
        parts.append(place)
    if time_hint:
        parts.append(time_hint)
    if not parts:
        parts.append("news")
    return " ".join(parts)


# ==========================================
# SECTION 1 - CRICKET (1, 2, 3)
# ==========================================

def fetch_cricket_news():
    """
    Indian cricket ki latest 3 headlines.
    """
    payload = _get_cached_news(("cricket",), lambda: _fetch(EVERYTHING_URL, {
        "q":       "India cricket OR IPL OR BCCI OR Team India cricket",
        "sortBy":  "publishedAt",
        "pageSize": 5
    }))
    articles, err = payload
    return articles[:3], err


# ==========================================
# SECTION 2 - NDA ASPIRANT (4, 5, 6)
# ==========================================

def fetch_merchant_navy_news():
    """
    Merchant Navey ke liye useful Indian news:
    Defence, government schemes, borders, UPSC topics,merchant navy, economy, infrastructure.
    Science & Technology, economy - jo merchant navy exams mein aata hai.
    """
    payload = _get_cached_news(("merchant_navy",), lambda: _fetch(EVERYTHING_URL, {
        "q": (
            "indian merchant navy or merchant navy "
            "OR DNS OR India border OR India government scheme "
            "OR India economy policy OR India infrastructure"
        ),
        "sortBy":  "publishedAt",
        "pageSize": 6
    }))
    articles, err = payload
    return articles[:3], err


# ==========================================
# SECTION 3 - SPY / STRATEGIC (7, 8, 9, 10)
# ==========================================

def fetch_spy_news():
    """
    Intelligence, geopolitics, cyber, covert ops angle wali news.
    International + India strategic topics.
    """
    payload = _get_cached_news(("spy",), lambda: _fetch(EVERYTHING_URL, {
        "q": (
            "intelligence agency OR cyber attack OR espionage OR "
            "geopolitics OR RAW OR CIA OR MI6 OR China military "
            "OR Pakistan ISI OR India strategic OR covert operation "
            "OR surveillance OR NATO OR nuclear"
        ),
        "sortBy":  "publishedAt",
        "pageSize": 6
    }))
    articles, err = payload
    return articles[:4], err


# ==========================================
# FORMAT ONE HEADLINE
# ==========================================

def _format_article(num, article):
    """
    Single article ko numbered line mein format karta hai.
    Source name bhi saath mein dikhata hai.
    """
    title  = article.get("title", "No title").strip()
    source = article.get("source", {}).get("name", "")

    # Long titles ko trim karo
    if len(title) > 120:
        title = title[:117] + "..."

    if source:
        return f"{num}. {title}  [{source}]"
    return f"{num}. {title}"


def get_news_for_request(request):
    """Handle topic-based, date-based, and main-news requests."""
    request = (request or "").strip()
    if not request:
        return get_news_briefing()

    normalized = request.lower()
    if any(word in normalized for word in [
        "today's news", "aaj ki news", "news briefing",
        "daily briefing", "news sunao", "news batao"
    ]):
        return get_news_briefing()

    date_value = parse_date_input(request)
    topic_query = _extract_topic_query(request)
    place_query = _extract_place_query(request)
    time_hint = _extract_time_hint(request)
    combined_query = _build_news_query(topic_query, place_query, time_hint)
    is_main_news = any(word in normalized for word in ["main news", "top news", "top headlines", "headlines"])

    if is_main_news:
        if date_value:
            params = {
                "q": _build_news_query(place=place_query, time_hint=time_hint),
                "from": date_value,
                "to": date_value,
                "sortBy": "publishedAt",
                "pageSize": 10,
            }
            url = EVERYTHING_URL
        else:
            params = {"country": "in", "pageSize": 10}
            url = HEADLINES_URL

        payload = _get_cached_news(("main_news", date_value or "today"), lambda: _fetch(url, params))
        articles, err = payload
        if err and not articles:
            return f"! {err}"
        if not articles:
            return "No main news found right now."

        lines = ["====================================", "       NOVA MAIN NEWS", "===================================="]
        if date_value:
            lines.append(f"Date: {date_value}")
        if place_query:
            lines.append(f"Place: {place_query}")
        if time_hint:
            lines.append(f"Time hint: {time_hint}")
        lines.append("")
        for i, article in enumerate(articles[:10], start=1):
            lines.append(_format_article(i, article))
        return "\n".join(lines)

    if topic_query or place_query or time_hint:
        params = {"q": combined_query, "sortBy": "publishedAt", "pageSize": 10}
        if date_value:
            params["from"] = date_value
            params["to"] = date_value

        payload = _get_cached_news(
            ("topic_place_time", combined_query, date_value or "today"),
            lambda: _fetch(EVERYTHING_URL, params),
        )
        articles, err = payload
        if err and not articles:
            return f"! {err}"
        if not articles:
            return f"No news found for: {combined_query}"

        lines = ["====================================", f"       NEWS FOR: {combined_query.upper()}", "===================================="]
        if date_value:
            lines.append(f"Date: {date_value}")
        if place_query:
            lines.append(f"Place: {place_query}")
        if time_hint:
            lines.append(f"Time hint: {time_hint}")
        lines.append("")
        for i, article in enumerate(articles[:10], start=1):
            lines.append(_format_article(i, article))
        return "\n".join(lines)

    if date_value:
        params = {
            "q": "news",
            "from": date_value,
            "to": date_value,
            "sortBy": "publishedAt",
            "pageSize": 10,
        }
        payload = _get_cached_news(("date", date_value), lambda: _fetch(EVERYTHING_URL, params))
        articles, err = payload
        if err and not articles:
            return f"! {err}"
        if not articles:
            return f"No news found for {date_value}."

        lines = ["====================================", f"       NEWS FOR {date_value}", "===================================="]
        lines.append("")
        for i, article in enumerate(articles[:10], start=1):
            lines.append(_format_article(i, article))
        return "\n".join(lines)

    return get_news_briefing()


# ==========================================
# MAIN BRIEFING FUNCTION
# ==========================================

def get_news_briefing():
    """
    Poora 10-news briefing return karta hai tumhare exact format mein.
    commands.py se call hoga.
    """

    lines = []
    lines.append("====================================")
    lines.append("       NOVA DAILY BRIEFING")
    lines.append("====================================\n")

    # -- SECTION 1: CRICKET --
    lines.append("[CRICKET] INDIAN CRICKET  (1-3)")
    lines.append("-------------------------------------")

    cricket, err1 = fetch_cricket_news()

    if err1 and not cricket:
        lines.append(f"  ! {err1}")
    elif not cricket:
        lines.append("  Koi cricket news nahi mili abhi.")
    else:
        for i, article in enumerate(cricket, start=1):
            lines.append(_format_article(i, article))

    lines.append("")

    # -- SECTION 2: NDA --
    lines.append("[NDA] merchant navy ASPIRANT NEWS  (4-6)")
    lines.append("-------------------------------------")

    nda, err2 = fetch_merchant_navy_news()

    if err2 and not nda:
        lines.append(f"  ! {err2}")
    elif not nda:
        lines.append("  Koi merchant navy relevant news nahi mili abhi.")
    else:
        for i, article in enumerate(nda, start=4):
            lines.append(_format_article(i, article))

    lines.append("")

    # -- SECTION 3: SPY / STRATEGIC --
    lines.append("[STRATEGIC] INTELLIGENCE & STRATEGIC  (7-10)")
    lines.append("-------------------------------------")

    spy, err3 = fetch_spy_news()

    if err3 and not spy:
        lines.append(f"  ! {err3}")
    elif not spy:
        lines.append("  Koi strategic news nahi mili abhi.")
    else:
        for i, article in enumerate(spy, start=7):
            lines.append(_format_article(i, article))

    lines.append("")
    lines.append("====================================")
    lines.append("Dobara sunne ke liye kaho: 'today's news'")

    return "\n".join(lines)
