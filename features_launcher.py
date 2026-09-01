# ==========================================
# NOVA FEATURES LAUNCHER (v1.0)
# ==========================================
# Separate button panel for all Nova features
# Run alongside Nova (python main.py)

import tkinter as tk
from tkinter import messagebox
import threading

def run_in_thread(func):
    threading.Thread(target=func, daemon=True).start()

def show_result(title, message):
    messagebox.showinfo(title, message)

def show_result_text(title, message):
    w = tk.Toplevel()
    w.title(title)
    w.geometry("400x350")
    w.configure(bg="#1a1a2e")
    tk.Label(w, text=title, font=("Arial", 12, "bold"), bg="#1a1a2e", fg="white").pack(pady=5)
    ta = tk.Text(w, wrap="word", bg="#16213e", fg="#eaeaea", relief="flat", height=14)
    ta.pack(padx=10, pady=5, fill="both", expand=True)
    ta.insert("1.0", message)
    ta.config(state="disabled")
    tk.Button(w, text="Close", command=w.destroy, bg="#4ade80", fg="white").pack(pady=5)

# Feature functions
def run_smart_reminder():
    try:
        from nova_features.smart_reminder import check_reminders
        show_result_text("Smart Reminder", str(check_reminders()))
    except Exception as e:
        show_result("Error", str(e))

def run_screen_monitor():
    try:
        from nova_features.screen_monitor import get_screen_status
        show_result_text("Screen Monitor", str(get_screen_status()))
    except Exception as e:
        show_result("Error", str(e))

def run_command_execution():
    try:
        from nova_features.command_execution import get_available_commands
        show_result_text("Commands", str(get_available_commands().get("message", "")))
    except Exception as e:
        show_result("Error", str(e))

def run_data_export():
    try:
        from nova_features.data_export_import import export_all_data, format_result
        show_result_text("Data Export", format_result(export_all_data()))
    except Exception as e:
        show_result("Error", str(e))

def run_multi_language():
    try:
        from nova_features.multi_language import detect_language, translate_to_hindi
        det = detect_language("Kaise ho?")
        tra = translate_to_hindi("good morning my friend")
        msg = (f"Detect: {det.get('detected')} ({det.get('message')})\n\n"
               f"Translate: {tra.get('message')}\n→ {tra.get('to_text', '')[:200]}")
        show_result_text("Multi-Language", msg)
    except Exception as e:
        show_result("Error", str(e))

def run_mini_quizzes():
    try:
        from nova_features.mini_quizzes import start_quiz, get_quiz_category_options
        cats = get_quiz_category_options()
        quiz = start_quiz("general")
        msg = "Categories: " + str(cats.get("categories", [])) + "\n\nQuestion: " + str(quiz['questions'][0]['question'])
        show_result_text("Mini-Quizzes", msg)
    except Exception as e:
        show_result("Error", str(e))

def run_context_suggestions():
    try:
        from nova_features.context_suggestions import analyze_screen_and_suggest
        show_result_text("Context Suggestions", str(analyze_screen_and_suggest()))
    except Exception as e:
        show_result("Error", str(e))

def run_gamified_progress():
    try:
        from nova_features.gamified_progress import get_progress_status, get_achievements_info
        s = get_progress_status()
        a = get_achievements_info()
        msg = "Level: " + str(s.get("level", 1)) + "\nXP: " + str(s.get("xp", 0)) + "\nStreak: " + str(s.get("daily_streak", 0)) + " days\nAchievements: " + str(a.get("count", 0))
        show_result_text("Gamified Progress", msg)
    except Exception as e:
        show_result("Error", str(e))

def run_offline_mode():
    try:
        from nova_features.offline_first import check_offline_status
        show_result_text("Offline Mode", str(check_offline_status()))
    except Exception as e:
        show_result("Error", str(e))

def run_enhanced_translation():
    try:
        from nova_features.enhanced_translation import get_supported_languages
        show_result_text("Enhanced Translation", str(get_supported_languages()))
    except Exception as e:
        show_result("Error", str(e))

# Create main launcher window
def launch():
    root = tk.Tk()
    root.title("Nova Features Launcher")
    root.geometry("350x480")
    root.configure(bg="#1a1a2e")
    root.resizable(False, False)
    
    tk.Label(root, text="NOVA FEATURES PANEL", font=("Arial", 14, "bold"),
             bg="#1a1a2e", fg="white").pack(pady=10)
    tk.Label(root, text="All 10 New Features Access", font=("Arial", 9),
             bg="#1a1a2e", fg="#888888").pack(pady=2)
    
    btns = [
        ("1. Smart Reminder", "#4ade80", run_smart_reminder),
        ("2. Screen Monitor", "#60a5fa", run_screen_monitor),
        ("3. Command Execution", "#fbbf24", run_command_execution),
        ("4. Data Export/Import", "#f87171", run_data_export),
        ("5. Multi-Language", "#a78bfa", run_multi_language),
        ("6. Mini-Quizzes", "#f471b5", run_mini_quizzes),
        ("7. Context Suggestions", "#4ade80", run_context_suggestions),
        ("8. Gamified Progress", "#fbbf24", run_gamified_progress),
        ("9. Offline Mode", "#60a5fa", run_offline_mode),
        ("10. Enhanced Translation", "#a78ba", run_enhanced_translation),
    ]
    
    for text, color, cmd in btns:
        tk.Button(root, text=text,
                  command=lambda c=cmd: run_in_thread(c),
                  bg=color, fg="white", font=("Arial", 10, "bold"),
                  relief="flat", cursor="hand2", padx=5, pady=3, width=20).pack(pady=2, padx=15, fill="x")
    
    tk.Label(root, text="Tip: Run Nova main.py first!", font=("Arial", 7),
             bg="#1a1a2e", fg="#666666").pack(side="bottom", pady=5)
    
    root.after(100, lambda: messagebox.showinfo("Nova Features", "All 10 features ready!\nClick any button to test."))
    root.mainloop()

if __name__ == "__main__":
    launch()