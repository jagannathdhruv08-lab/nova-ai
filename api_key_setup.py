# ==========================================
# NOVA API KEY SETUP - friendly .env manager
# ------------------------------------------
# Standalone window (also launchable as its own process) that reads the
# existing .env next to Nova, lets you update keys with masked inputs,
# and saves while PRESERVING every unrelated line/comment in the file.
#
#   python api_key_setup.py          # run standalone
# or:
#   from api_key_setup import launch_api_key_window
#   launch_api_key_window()          # open from inside Nova
#
# No network calls are made - keys are only format-checked locally.
# ==========================================

import os
import sys
import tkinter as tk
from tkinter import messagebox

try:
    from dotenv import dotenv_values
except ImportError:                       # pragma: no cover
    dotenv_values = None


def _base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


ENV_PATH = os.path.join(_base_dir(), ".env")

# key -> (label, placeholder, secret?)
FIELDS = [
    ("GROQ_API_KEY", "Groq (primary LLM)", "gsk_...", True),
    ("OPENROUTER_API_KEY", "OpenRouter (backup LLM)", "sk-or-v1-...", True),
    ("GEMINI_API_KEY", "Google Gemini (vision/OCR)", "AIza...", True),
    ("NEWS_API_KEY", "NewsAPI (briefings)", "32-char hex", True),
    ("WEATHER_API_KEY", "OpenWeatherMap", "32-char hex", True),
    ("OLLAMA_ENABLED", "Ollama local fallback (1/0)", "0", False),
    ("OLLAMA_MODEL", "Ollama model", "llama3.2", False),
    ("OLLAMA_KEEP_WARM", "Keep Ollama model loaded (1/0)", "1", False),
]

_PLACEHOLDER_MARKERS = ("replace_me", "xxx", "...", "<")


def _read_env_dict():
    """Existing values: real .env parse when possible, else naive parse."""
    if not os.path.exists(ENV_PATH):
        return {}
    if dotenv_values is not None:
        try:
            return {k: v for k, v in dotenv_values(ENV_PATH).items() if v}
        except Exception:
            pass
    values = {}
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    if v.strip():
                        values[k.strip()] = v.strip()
    except Exception:
        pass
    return values


def _looks_configured(value):
    """True when a value exists and isn't an obvious template."""
    if not value:
        return False
    lowered = value.lower()
    return not any(m in lowered for m in _PLACEHOLDER_MARKERS)


def save_env(new_values):
    """Rewrite .env, replacing known KEY=VALUE lines and keeping all
    other lines (comments, ordering, unrelated keys) intact.

    Returns (updated_keys, appended_keys)."""
    existing_lines = []
    if os.path.exists(ENV_PATH):
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                existing_lines = f.read().splitlines()
        except Exception:
            existing_lines = []

    to_write = dict(new_values)
    out_lines = []
    appended = []
    for line in existing_lines:
        stripped = line.strip()
        key = stripped.split("=", 1)[0].strip() if (
            stripped and not stripped.startswith("#") and "=" in stripped
        ) else None
        if key and key in to_write:
            value = to_write.pop(key)
            if value:
                out_lines.append(f"{key}={value}")
        elif key is None or key not in new_values:
            out_lines.append(line)

    # append any keys that weren't already present in the file
    for key, value in to_write.items():
        if value:
            out_lines.append(f"{key}={value}")
            appended.append(key)

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines).rstrip("\n") + "\n")
    return list(new_values.keys()), appended

def launch_api_key_window():
    root = tk.Tk()
    root.title("Nova - API Key Setup")
    root.geometry("560x470")
    root.configure(bg="#1a1a2e")
    root.resizable(False, False)

    tk.Label(root, text="🔑 Nova API Keys",
             font=("Arial", 15, "bold"), bg="#1a1a2e",
             fg="white").pack(pady=(14, 2))
    tk.Label(root, text=f"Saved to {ENV_PATH}",
             font=("Arial", 8), bg="#1a1a2e", fg="#888888").pack()

    body = tk.Frame(root, bg="#1a1a2e")
    body.pack(fill="both", expand=True, padx=18, pady=8)
    body.columnconfigure(1, weight=1)

    entries = {}
    status_labels = {}

    def refresh_status(key):
        val = entries[key].get().strip()
        ok = _looks_configured(val)
        status_labels[key].configure(
            text="✅ set" if ok else ("⚠️ template" if val else "—"),
            fg="#4ade80" if ok else "#fbbf24")

    def toggle_show(entry, btn):
        show = "*" if entry.cget("show") == "" else ""
        entry.configure(show=show)
        btn.configure(text="🙈" if show == "" else "👁️")

    existing = _read_env_dict()
    for row, (key, label, _placeholder, secret) in enumerate(FIELDS):
        tk.Label(body, text=label, font=("Arial", 10), bg="#1a1a2e",
                 fg="#eaeaea", anchor="w").grid(row=row, column=0,
                                                sticky="w", pady=4)
        var = tk.StringVar(value=existing.get(key, ""))
        entry = tk.Entry(body, textvariable=var, width=44,
                         bg="#16213e", fg="#eaeaea", insertbackground="white",
                         relief="flat",
                         show="*" if secret else "", font=("Consolas", 10))
        entry.grid(row=row, column=1, sticky="ew", padx=6, pady=4)
        entries[key] = entry

        side = tk.Frame(body, bg="#1a1a2e")
        side.grid(row=row, column=2, sticky="w")
        status = tk.Label(side, text="", font=("Arial", 9),
                          bg="#1a1a2e", fg="#888888", width=8)
        status.pack(side="left")
        status_labels[key] = status
        if secret:
            eye = tk.Button(side, text="👁️", width=3, relief="flat",
                            bg="#1a1a2e", fg="white", cursor="hand2")
            eye.configure(command=lambda e=entry, b=eye: toggle_show(e, b))
            eye.pack(side="left")

        entry.bind("<KeyRelease>", lambda _e, k=key: refresh_status(k))
        refresh_status(key)

    hint = tk.Label(root,
                    text="Free keys: console.groq.com | openrouter.ai | "
                         "aistudio.google.com | newsapi.org | openweathermap.org",
                    font=("Arial", 8), bg="#1a1a2e", fg="#666666")
    hint.pack(pady=2)

    def on_save():
        new_values = {}
        for key, _label, _ph, _sec in FIELDS:
            value = entries[key].get().strip()
            if value:
                new_values[key] = value
        try:
            updated, appended = save_env(new_values)
            messagebox.showinfo(
                "Nova API Keys",
                f"✅ Saved {len(updated)} key(s) to .env"
                + (f" ({len(appended)} new)" if appended else "")
                + "\nRestart Nova so the brain reloads them.")
            root.destroy()
        except Exception as exc:
            messagebox.showerror("Nova API Keys",
                                 f"Save failed: {type(exc).__name__}: {exc}")

    button_row = tk.Frame(root, bg="#1a1a2e")
    button_row.pack(pady=(6, 14))
    tk.Button(button_row, text="💾 Save .env", command=on_save,
              bg="#4ade80", fg="white", font=("Arial", 11, "bold"),
              relief="flat", cursor="hand2", padx=16).pack(side="left", padx=6)
    tk.Button(button_row, text="Cancel", command=root.destroy,
              bg="#7f1d1d", fg="white", font=("Arial", 10),
              relief="flat", cursor="hand2", padx=10).pack(side="left", padx=6)

    root.mainloop()


if __name__ == "__main__":
    launch_api_key_window()