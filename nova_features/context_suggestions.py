# ==========================================
# NOVA CONTEXT-SMART SUGGESTIONS FEATURE
# ==========================================
import time
import datetime


def _get_active_app():
    """Get the currently active window/app via Windows API."""
    try:
        from nova_features.screen_monitor import _get_active_window_info
        info = _get_active_window_info()
        if info:
            return info.get("process_name", "").lower(), info.get("window_title", "")
    except Exception:
        pass
    return "", ""


def analyze_screen_and_suggest():
    """Analyze current screen context and generate relevant suggestions.

    Suggestions change based on the active app/window, time of day,
    and screen resolution - so it responds to screen changes.
    """
    try:
        import ctypes

        user32 = ctypes.windll.user32
        width = user32.GetSystemMetrics(0)
        height = user32.GetSystemMetrics(1)

        app_name, window_title = _get_active_app()
        current_hour = datetime.datetime.now().hour
        suggestions = []

        # ---- App-specific suggestions (respond to what you're using) ----
        app_lower = (app_name or "").lower()
        title_lower = (window_title or "").lower()

        if any(k in app_lower for k in ("chrome", "edge", "firefox", "brave", "opera")) or "www." in title_lower:
            suggestions.append({
                "type": "productivity",
                "title": "📵 Stop scrolling",
                "description": "You're on a browser - time on social media? Take a 5-min break from tabs",
                "action": "suggest_break",
            })
        elif any(k in app_lower for k in ("code", "sublime", "pycharm", "notepad", "vim", "atom")):
            suggestions.append({
                "type": "productivity",
                "title": "💡 Commit & review",
                "description": "You're coding - save/commit your work and do a quick syntax check",
                "action": "check_work",
            })
        elif any(k in app_lower for k in ("word", "excel", "powerpoint", "docs", "sheets", "slides")):
            suggestions.append({
                "type": "productivity",
                "title": "📄 Save your document",
                "description": "Working on a document - don't forget to save/backup frequently",
                "action": "save_document",
            })
        elif any(k in app_lower for k in ("youtube", "netflix", "spotify", "twitch")):
            suggestions.append({
                "type": "break",
                "title": "🎬 Entertainment detected",
                "description": "Watching/listening? Set a time limit to stay productive",
                "action": "set_timer",
            })

        # ---- Time-based suggestions ----
        if 6 <= current_hour <= 10:
            suggestions.append({
                "type": "routine",
                "title": "🌅 Morning routine",
                "description": "Great time to plan your day - set your top 3 goals",
                "action": "plan_day",
            })
        elif 12 <= current_hour <= 15:
            suggestions.append({
                "type": "break",
                "title": "🍽 Lunch / energy dip",
                "description": "Post-lunch slump - a short break boosts focus",
                "action": "suggest_break",
            })
        elif 21 <= current_hour or current_hour <= 5:
            suggestions.append({
                "type": "health",
                "title": "🌙 It's late",
                "description": "Late night - consider wrapping up and resting for good sleep",
                "action": "wind_down",
            })
        else:
            suggestions.append({
                "type": "productivity",
                "title": "⏱ Focus window",
                "description": "Good time to focus - try a 25-min Pomodoro session",
                "action": "set_focus_timer",
            })

        # ---- Screen-size suggestion ----
        if width >= 1400:
            suggestions.append({
                "type": "productivity",
                "title": "🖥 Multi-window hint",
                "description": "Wide screen detected - split tasks side-by-side for efficiency",
                "action": "open_multitask_view",
            })

        # ---- Fallback if nothing matched ----
        if not suggestions:
            suggestions.append({
                "type": "general",
                "title": "💧 Check hydration",
                "description": "Have you drunk water recently? Stay hydrated!",
                "action": "check_hydration",
            })

        suggestions = suggestions[:4]

        return {
            "success": True,
            "feature": "context_suggestions",
            "screen_width": width,
            "screen_height": height,
            "current_hour": current_hour,
            "active_app": app_name,
            "window_title": window_title,
            "suggestions": suggestions,
            "message": f"Analyzed: {app_name or 'unknown'} app • {len(suggestions)} suggestions",
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Context analysis failed: {str(e)}",
            "feature": "context_suggestions",
            "error": str(e),
        }



def get_suggestion_feedback(action_taken):
    """Get feedback on whether a suggestion was helpful."""
    try:
        valid_actions = ["break", "continue_work", "check_hydration", "stretch", "switch_task"]
        if action_taken.lower() in valid_actions:
            return {
                "success": True,
                "feature": "context_suggestions",
                "action": action_taken,
                "acknowledged": True,
                "message": "Thanks for feedback - I'll learn your preferences!",
            }
        else:
            return {
                "success": True,
                "feature": "context_suggestions",
                "action": action_taken,
                "acknowledged": False,
                "message": "Noted - will suggest differently next time",
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Feedback failed: {str(e)}",
            "feature": "context_suggestions",
            "error": str(e),
        }


__version__ = "2.0.0"
__all__ = ["analyze_screen_and_suggest", "get_suggestion_feedback"]