# ==========================================
# NOVA BROWSER CONTROL — Open tabs, search, manage browser
# ==========================================
import os
import subprocess
import webbrowser

# Default search engines
SEARCH_ENGINES = {
    "google": "https://www.google.com/search?q={query}",
    "youtube": "https://www.youtube.com/results?search_query={query}",
    "bing": "https://www.bing.com/search?q={query}",
    "wikipedia": "https://en.wikipedia.org/wiki/Special:Search?search={query}",
}


def open_new_tab(url):
    """Open a URL/website in a new browser tab."""
    if not url:
        return {"success": False, "feature": "browser_control",
                "message": "URL required. Try: youtube.com, google.com..."}
    if not url.startswith("http"):
        url = "https://" + url
    try:
        webbrowser.open_new_tab(url)
        return {"success": True, "feature": "browser_control",
                "url": url, "message": f"🌐 Opened new tab: {url}"}
    except Exception as e:
        return {"success": False, "feature": "browser_control",
                "error": str(e), "message": f"Failed: {str(e)}"}


def search(query, engine="google"):
    """Search the web in a new tab using a search engine."""
    if not query:
        return {"success": False, "feature": "browser_control",
                "message": "Search query required."}
    engine = engine.lower()
    template = SEARCH_ENGINES.get(engine, SEARCH_ENGINES["google"])
    url = template.replace("{query}", query.replace(" ", "+"))
    try:
        webbrowser.open_new_tab(url)
        return {"success": True, "feature": "browser_control",
                "engine": engine, "query": query, "url": url,
                "message": f"🔍 Searching {query} on {engine}"}
    except Exception as e:
        return {"success": False, "feature": "browser_control",
                "error": str(e), "message": f"Failed: {str(e)}"}


def open_multi_tabs(urls):
    """Open multiple websites in new tabs."""
    if not urls:
        return {"success": False, "feature": "browser_control",
                "message": "Provide a list of URLs."}
    opened = 0
    for url in urls:
        try:
            if not url.startswith("http"):
                url = "https://" + url
            webbrowser.open_new_tab(url)
            opened += 1
        except Exception:
            continue
    return {"success": opened > 0, "feature": "browser_control",
            "opened": opened, "total": len(urls),
            "message": f"📑 Opened {opened}/{len(urls)} tabs"}


def get_search_engines():
    """List available search engines."""
    return {"success": True, "feature": "browser_control",
            "engines": list(SEARCH_ENGINES.keys()),
            "message": f"🔧 Search engines: {', '.join(SEARCH_ENGINES.keys())}"}


__version__ = "1.0.0"
__all__ = ["open_new_tab", "search", "open_multi_tabs", "get_search_engines"]
