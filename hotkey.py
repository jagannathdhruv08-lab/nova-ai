import threading
import keyboard

# ==========================================
# GLOBAL HOTKEY FEATURE
# ==========================================
#
# Setup kaise karein:
#   pip install keyboard
#
# Kaam kaise karta hai:
#   - App band ho ya minimize ho — koi baat nahi
#   - Ctrl+Z dabaao — Nova sunna shuru kar degi
#   - Default hotkey: Ctrl+Z
#   - Badal sakte ho neeche HOTKEY variable mein
# ==========================================

HOTKEY = "ctrl+z"   # <- Yahan apna pasandida shortcut daalo


# ==========================================
# HOTKEY SETUP
# ==========================================

def setup_hotkey(callback):
    """
    Global hotkey register karta hai.
    callback = woh function jo hotkey press hone pe chalega.

    gui.py mein call karo:
        from hotkey import setup_hotkey
        setup_hotkey(open_listening_window)
    """

    def _on_hotkey():
        # Alag thread mein chalate hain — GUI freeze na ho
        threading.Thread(target=callback, daemon=True).start()

    keyboard.add_hotkey(HOTKEY, _on_hotkey)

    print(f"Hotkey ready: {HOTKEY.upper()} dabaao Nova ko call karne ke liye")


def remove_hotkey():
    """Saare hotkeys hatata hai — app band karne pe call karo."""
    keyboard.unhook_all_hotkeys()
