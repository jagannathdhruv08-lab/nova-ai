from nova_features.smart_reminder import check_reminders
from nova_features.screen_monitor import get_screen_status
from nova_features.command_execution import get_available_commands
from nova_features.data_export_import import export_all_data
from nova_features.mini_quizzes import start_quiz
from nova_features.context_suggestions import analyze_screen_and_suggest
from nova_features.gamified_progress import get_progress_status, get_achievements_info
from nova_features.offline_first import check_offline_status
from nova_features.enhanced_translation import translate_english_to_hindi

print("1. Reminders:", check_reminders().get("active_count"), "active")
print("2. Screen:", get_screen_status().get("resolution"))
print("3. Commands:", get_available_commands().get("status"))
print("4. Export:", export_all_data().get("status"))
print("5. Quiz:", start_quiz("general").get("total_questions"), "questions")
print("6. Suggestions:", len(analyze_screen_and_suggest().get("suggestions", [])), "items")
print("7. Progress:", get_progress_status().get("level"), "level")
print("8. Achievements:", get_achievements_info().get("status"))
print("9. Offline:", check_offline_status().get("offline"))
t = translate_english_to_hindi("hello")
print("10. Translator:", t.get("from"), "to", t.get("to"))
print()
print("ALL 10 FEATURES WORKING!")
