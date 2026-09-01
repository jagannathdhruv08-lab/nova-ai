# NOVA AI - POORA GUIDE (Simple Hinglish Mein)

Namaste! Yeh guide Nova AI ki har cheez ko simple Hinglish mein samjhata hai.

## Index
1. Nova Kya Hai? (Overview)
2. Kitne Functions Hain? (Kul Count)
3. Har Module Ki Functions (Purpous ke saath)
4. Nova Kaise Kaam Karti Hai? (Process)
5. Security Features
6. Setup / Installation
7. Quick Reference - Commands

---

## 1. Nova Kya Hai? (Overview)

Nova AI ek personal assistant hai jo aapke computer par chalti hai. Iska main kaam: chat karna, voice se baat karna, news/weather batana, study routine manage karna, nutrition track karna, files handle karna, aur bhi bahut kuchh.

Nova ke code bahut saare Python files mein bata hain. Har file ek alag kaam karti hai:

| File | Kya Karta Hai |
|------|---------------|
| brain.py | Nova ki dimaag (LLM) - sawalon ka jawab deta hai Groq API se |
| agent.py | File/folder actions - delete, move, rename, list, search |
| commands.py | Direct commands - open youtube, shutdown pc, news, weather |
| gui.py | Poori user interface - window, chat box, camera, dashboard |
| memory.py | User ki baatein yaad rakhna (name, birthday, facts) |
| voice.py | Awaaz sunna (speech-to-text) aur bolna (text-to-speech) |
| nova_coach.py | Study coach - daily rating, padhai ke goals |
| nova_vision.py | Aankhein - photo dekhna, OCR, Gemini vision |
| nova_nutrition.py | Khane ka hisaab - thali ki photo se nutrition |
| nova_routine.py | Daily routine - Merchant Navy study schedule |
| nova_storage.py | Data save/load - goals, tasks, chat history |
| nova_theme.py | Colors/theme - sirf constants |
| news.py | News briefing - cricket, NDA, strategic |
| weather.py | Mausam ka haal |
| history.py | Chat history save/clear |
| settings.py | Settings - language, theme, voice |
| hotkey.py | Ctrl+Z hotkey - Nova ko bulana |
| license.py | License check - app ki paid access |
| build.py | .exe build karna (PyInstaller) |
| launcher.py | Background launcher - system tray |
| features_launcher.py | Features panel - 10 test buttons |
| gui_integration.py | GUI ke liye patches (privacy mode) |
| photo_detector.py | AI-generated image check |
| emoji_render.py | Chat mein colour emoji dikhana |
| nova_doctor.py | Doctor - self health check ("doctor" / "health check" command) |
| nova_gui_helpers.py | GUI ke pure helpers (file preview, image check) - unit-tested |
| nova_features/ | 18 extra features - alarms, quizzes, focus timer, etc. |

---

## 2. Kitne Functions Hain? (Kul Count)

Nova ke code mein total 200+ functions hain, 30+ files mein. Yahan tabular count diya gaya hai:

| Module | Functions | Kya Karta Hai |
|--------|-----------|---------------|
| brain.py | 8 | LLM brain (ask_nova, route_to_agent, rate-limit) |
| agent.py | 9 | System agent (safe_path, handle, audit, rate) |
| commands.py | 5 | Command router (execute_command, smart_execute) |
| gui.py | 60+ | Main UI (pages, chat, camera, notifications) |
| memory.py | 7 | Memory (remember, recall, clear) |
| voice.py | 13 | Voice (speak, listen, emotion, mic status) |
| nova_coach.py | 10 | Study coach (daily rating, prompt build) |
| nova_vision.py | 7 | Vision (Gemini, OCR, screen capture) |
| nova_nutrition.py | 7 | Nutrition (meal analysis, profile) |
| nova_routine.py | 3 | Daily routine (sync tasks/goals) |
| nova_storage.py | 5 | Data storage (dashboard load/save) |
| nova_theme.py | 0 (12 constants) | Sirf colours |
| news.py | 11 | News briefing (fetch, format) |
| weather.py | 2 | Weather fetch |
| history.py | 5 | Chat history (save, show, clear) |
| settings.py | 3 | Settings (load, save, update) |
| hotkey.py | 2 | Hotkey (setup, remove) |
| license.py | 13 | License (activate, validate, status) |
| build.py | 5 | Build script (PyInstaller) |
| launcher.py | 8 | Background launcher |
| features_launcher.py | 14 | Features panel |
| gui_integration.py | 8 | Integration patches (privacy, forget) |
| photo_detector.py | 6 | AI image detect |
| emoji_render.py | 12 | Emoji rendering + EmojiBubble class |
| nova_features/ (18 files) | 70+ | Alarms, reminders, quizzes, translation, etc. |
| **Total** | **200+** | |

---

## 3. Har Module Ki Functions (Purpous ke saath)

### 3.1 brain.py - Nova Ki Dimaag (LLM Brain)

Yeh Nova ka sabse important module hai. Jab aap kuchh puchte ho, to yeh Groq API (free LLM) se jawab mangata hai.

**Functions (8 total):**

1. **ask_nova(prompt)** - MAIN FUNCTION. Aap jo bhi likhte ho, ye Groq LLM ko bhejta hai aur jawab wapas laata hai. 800 tokens tak ka jawab deta hai. Agar rate-limit lage to friendly message dikhata hai.
2. **route_to_agent(command)** - Yeh check karta hai ki aapki baat ek system action hai (jaise file delete) ya sirf sawal. Agar system action hai, to agent.py ko bhej deta hai.
3. **_is_rate_limited()** - Check karta hai ki abhi 60-second ka rate-limit band hai ya nahi.
4. **_rate_limit_message()** - Rate-limit ka message return karta hai.
5. **_mark_rate_limited(msg)** - Rate-limit ka timer start karta hai (default 60 sec).
6. **_short_exc(exc)** - Error ko chhota format mein likhne ke liye.
7. **_redact(text)** - Error messages se API keys chhupata hai, taaki keys leak na hon.
8. **_strip_emojis(text)** - Text se emojis hatata hai, kyunki LLM emojis samajhne mein confuse hota hai.

---

### 3.2 agent.py - File/System Operations (Security Ke Saath)

Jab Nova ko files/folders ke saath khelna padta hai (delete, move, rename, list, search), to yeh module use hota hai. Bahut strict security rules hain.

**Functions (9 total):**

1. **safe_path(raw)** - SABSE IMPORTANT SECURITY FUNCTION. User diye gaye path ko check karta hai - agar wo Windows/Program Files jaise system folders mein hai, ya bahar allowed folders se, to refuse kar deta hai. Symlink se bachata hai.
2. **handle(action_json)** - MAIN ACTION ROUTER. LLM se aaya action (jaise delete_file) ko process karta hai - safe_path check, rate-limit check, confirmation, phir actual operation.
3. **audit(action, target, status)** - Har action ka log likhta hai (audit trail) taaki pata chale kya kya hua.
4. **_user_data_dir()** - User ka data folder banata hai (AppData/Roaming/Nova on Windows).
5. **_is_forbidden_path(path, forbidden)** - Check karta hai path forbidden folder ke andar hai ya nahi.
6. **_load_allowed_folders()** - Settings se allowed folders list padhta hai.
7. **get_allowed_roots()** - Allowed roots ki final list banata hai (Home, Desktop, Documents, Downloads + user ke extra).
8. **_check_rate(is_destructive)** - Rate-limit check - 30 actions/minute, 1 destructive/minute.
9. **_record(is_destructive)** - Har action ko queue mein record karta hai rate-limit ke liye.

**Supported Actions (12):** list_dir, open_file, search_file, read_file_summary, create_folder, move_file, rename_file, delete_file, run_app, system_info, disk_usage, empty_recycle_bin
---

### 3.3 commands.py - Direct Commands (Bina LLM Ke)

Jab aap kehte ho "open youtube", "shutdown pc", "today news", to yeh module direct match karke kaam karta hai - fast aur reliable.

**Functions (5 total):**

1. **execute_command(command)** - MAIN FUNCTION. Aapki baat ko pattern match karke sahi action leta hai. Jaise "open youtube" match karke browser kholta hai. Agar match na ho to "Command not recognised" bolta hai.
2. **smart_execute(command)** - Fuzzy match. Agar aap thoda galat likho ("open yotube"), to yeh difflib se closest match dhoondh ke sahi command chala deta hai.
3. **_sanitise_fact(value)** - Memory mein save hone se pehle value sanitize karta hai (length cap 200 chars + prompt-injection block). Yeh security ke liye hai.
4. **_memory_key(text)** - Memory ke liye clean key banata hai (jaise "my favorite color" -> "favorite_color").
5. **_handle_remember_command(command)** - "remember my name is Dhruv" jaisi commands parse karke memory.py mein save karta hai.

**Known Commands (50+):** open youtube/google/chrome/whatsapp, play song, mood playlists (happy/sad/romantic/motivational), increase/decrease brightness, shutdown/restart pc, take screenshot, battery, current time, news (today's news, aaj ki news, news briefing, news sunao), weather in <city>, thank you, remember/ask name/color, show/clear history, stop/start speaking.

---

### 3.4 memory.py - Yaad Rakhe Jaane Wale Facts

Nova aapke baare mein chhoti baatein yaad rakhti hai (naam, birthday, favourite colour). memory.json file mein save hoti hain.

**Functions (7 total):**

1. **remember(key, value)** - Fact save karta hai (jaise remember("username", "Dhruv")).
2. **recall(key)** - Fact return karta hai. Agar nahi hai to None.
3. **load_memory()** - memory.json file padhta hai.
4. **save_memory(memory)** - File mein save karta hai.
5. **get_saved_facts()** - User ke saare facts return karta hai (internal keys filter karke).
6. **delete_memory(key)** - Specific fact delete karta hai.
7. **clear_memory()** - Poori memory wipe karta hai (internal keys bhi).

---
### 3.5 gui.py - Poori User Interface (Window, Pages, Chat)

Yeh Nova ka sabse bada file hai (~4400 lines, 60+ functions). Yeh puri window banata hai - chat box, sidebar, dashboard, camera, etc.

**Kuchh main functions:**

1. **send_message()** - MAIN CHAT FUNCTION. Jab aap Enter dabate ho, to yeh message ko chat mein add karta hai, command/LLM se jawab leta hai, aur reply dikhata hai.
2. **show_page(page_name)** - Pages switch karta hai (home, dashboard, coach, routine, nutrition, tools, quizzes, progress, camera, screen_watch).
3. **create_home_page()** - Home page banat hai - chat bubbles, message entry, send button, voice button.
4. **create_dashboard()** - Dashboard page - metrics, goals, tasks, journal, notes.
5. **create_coach_page()** - Coach chat + daily rating display.
6. **create_routine_page()** - Daily routine tasks + goals checkbox.
7. **create_nutrition_page()** - Nutrition totals + profile + meal log.
8. **create_tools_page()** - Tools grid (app launcher, browser, alarm, email, etc.).
9. **open_app_launcher()** - App launcher window (type app name to launch).
10. **open_camera_window()** - Camera window - photo le kar analyze karta hai.
11. **open_settings()** - Settings window - theme, language, voice, privacy.
12. **open_license_window()** - License activation window.
13. **open_command_guide()** - Sarre commands ki list dikhati hai.
14. **open_browser_control()** - URL open ya web search.
15. **open_alarm_manager()** - Alarm set karne ka dialog.
16. **open_email_manager()** - Email config + send test email.
17. **send_notification(title, message)** - System notification/popup dikhati hai.
18. **check_reminders()** - Har 30 sec chatati hai - agar goal/task ka time aa gaya to reminder fire karti hai.
19. **confirm_destructive(message)** - Confirmation dialog (red Confirm vs Cancel) - shutdown/delete se pehle.
20. **forget_everything()** - Double confirmation ke saath saara data wipe karta hai.
21. **apply_theme(choice)** - Dark/light theme switch.
22. **make_thread()** - Nayi chat thread banata hai.
23. **rebuild_home_chat()** - Chat history re-render karta hai.
24. **read_file_preview()** - Chat mein file ka content preview dikhati hai.
25. **add_message()** - Chat box mein message bubble add karti hai (with typing animation).
26. **toggle_voice()** / **set_voice_enabled()** - Voice on/off.
27. **make_metric_card()**, **make_tool_card()**, **make_section_title()** - UI building helpers.
28. **completion_text()**, **read_file_preview()**, **is_supported_image()** - ab **nova_gui_helpers.py** mein hain (pure logic, unit-tested). **current_streak_count()**, **log_activity()** - Dashboard helpers (gui.py).
29. **run_gui()** - Poori app launch karta hai (entry point).

---

### 3.6 voice.py - Awaaz System (Sunna + Bolna)

Nova ki awaaz - microphone se sunna (speech-to-text) aur speaker se bolna (text-to-speech).

**Functions (13 total):**

1. **speak(text)** - Text ko awaaz mein bolta hai (edge-tts se Indian voice "en-IN-neerjaNeural", pygame se play).
2. **listen(language, timeout)** - MAIN LISTEN FUNCTION. Microphone se sunta hai, speech ko text mein convert karta hai. PyAudio aur sounddevice dono support karta hai.
3. **mute_voice()** - Voice output band karta hai.
4. **unmute_voice()** - Voice output chalu karta hai.
5. **voice_status()** - "enabled" ya "muted" batata hai.
6. **list_microphones()** - Available microphones ki list.
7. **microphone_status()** - Mic ka full status message (kitni devices, kaunse backend).
8. **_pyaudio_microphone_available()** - Check karta hai PyAudio mic available hai ya nahi.
9. **_detect_emotion(audio)** - Awaaz se emotion detect karta hai (happy, sad, angry, neutral).
10. **_record_with_sounddevice()** - Sounddevice se audio record (fallback jab PyAudio fail ho).
11. **_recognize_audio()** - Audio ko Google Web Speech se text mein convert karta hai.
12. **_set_listen_error(msg)** - Listen error ko store karta hai.
13. **get_last_listen_error()** - Last error ka message return karta hai.

---
### 3.7 nova_coach.py - AI Study Coach

Yeh ek focused study coach hai jo sirf padhai, goals, tasks, aur nutrition ke baare mein baat karta hai. Har din 9 PM par automatic rating deta hai (tasks/goals/protein ke % ke hisaab se).

**Functions (10 total):**

1. **generate_daily_rating()** - 9 PM ke baad daily rating generate karta hai - score (0-100), label (Excellent/Good/Average), aur Hinglish summary + motivation.
2. **compute_daily_score()** - Score calculate karta hai (tasks completion % + goals % + protein % ka average). Koi AI nahi, offline bhi chalta hai.
3. **should_generate_rating_now()** - Check karta hai ki 9 PM ho gaya aur rating aaj nahi bani - to True.
4. **build_coach_prompt(user_message)** - Coach ko bhejne wala prompt banata hai - instructions + aaj ka progress + recent chat + naya message.
5. **add_coach_message(sender, text)** - Coach chat mein message add karta hai.
6. **reset_for_new_day_if_needed()** - Midnight pe chat clear karta hai (ratings history rehti hai).
7. **rating_label(score)** - Score se label banata hai (85+ Excellent, 65+ Good, 40+ Average, else Needs Improvement).
8. **get_rating_history()** - Saari past ratings ki list.
9. **_load()** / **_save()** - nova_coach_data.json se load/save.

---

### 3.8 nova_vision.py - Nova Ki Aankhein (Gemini Vision + OCR)

Photo dekhna, screen capture, OCR text extraction. Gemini Flash free tier image samajhne ke liye, OCR fallback ke liye.

**Functions (7 total):**

1. **ask_gemini_vision(pil_image, prompt_text)** - MAIN FUNCTION. Photo + sawaal Gemini ko bhejta hai, jawab text mein laata hai. Fail hone par last_gemini_error mein reason set karta hai.
2. **ask_gemini_text(prompt_text)** - Sirf text (bina photo) Gemini call - manually food log ke liye.
3. **get_gemini_client()** - Gemini API client banata hai (lazy - ek baar bana ke reuse).
4. **check_gemini_status()** - Check karta hai Gemini ready hai ya nahi (package + key + model).
5. **check_ocr_status()** - Tesseract OCR check (package + engine dono).
6. **extract_text_from_image(pil_image)** - OCR se photo ka text nikaalta hai.
7. **capture_screen_image()** - Screen ka screenshot le leta hai.

---

### 3.9 nova_nutrition.py - Khane Ka Hisaab

Thali/plate ki photo le kar Gemini se nutrition estimate karwata hai - calories, protein, carbs, fats. Merchant Navy weight-gain targets se compare karta hai.

**Functions (7 total):**

1. **analyze_meal_photo(pil_image, note)** - MAIN FUNCTION. Thali ki photo Gemini ko bhejta hai (profile + running totals ke saath). Response se ESTIMATE line parse karke totals update karta hai.
2. **get_today_summary_text()** - Aaj ke meals ka summary (kitna khaya, kitna baaki target tak).
3. **set_profile(height, weight, target, protein)** - Body profile update.
4. **get_profile()** - Current profile return.
5. **get_today_totals()** - Aaj ke total calories/protein/carbs/fats.
6. **_today_bucket()** - Aaj ki date ka data bucket banata/return karta hai.
7. **_load()** / **_save()** - nova_nutrition_data.json load/save.

---

### 3.10 nova_routine.py - Daily Routine (Merchant Navy Schedule)

Fixed daily study/fitness routine ko dashboard mein tasks/goals ke roop mein dalta hai, alarms ke saath.

**Functions (3 total):**

1. **sync_routine_for_today(force)** - MAIN FUNCTION. Aaj ka routine generate karta hai - 11 clock-based tasks (05:30 wake up se 22:15 sleep tak) + weekday subjects + daily habits. Har din ek baar hi chalta hai.
2. **_today_weekday_name()** - Aaj ka weekday name (Monday, Tuesday...).
3. **_clear_previous_routine_entries()** - Kal ki auto-generated routine entries hata deta hai (user ke manually add kare hue ko touch nahi karta).

**Routine data:** DAILY_ROUTINE (11 items), WEEKLY_SUBJECTS (Monday-Sunday subjects), DAILY_HABITS (Run 2-3km, 20-30 Maths questions, 5 English words, 1 news article).

---
### 3.11 nova_storage.py - Data Save/Load (Dashboard)

Nova ka data storage - goals, tasks, notes, journal, focus time, chat history sab yahin manage hota hai.

**Functions (5 total):**

1. **dashboard_data** - MOST IMPORTANT. Yeh ek shared dict hai jisme poori app ka data rehta hai (goals, tasks, notes, chat_threads, focus, streak). Har module isse import karta hai aur sabko same data dikhta hai.
2. **load_dashboard_data()** - nova_dashboard_data.json se data load karta hai (default values ke saath).
3. **save_dashboard_data()** - Data ko file mein save karta hai.
4. **resource_path()** - Read-only assets (images, icons) ka path. PyInstaller mode mein temp folder use karta hai.
5. **writable_data_path()** - Write-keep data ka stable path. IMPORTANT FIX - PyInstaller .exe ke saath data restart pe wipe na ho isliye ye executable ke folder use karta hai.
6. **persist_message(thread_id, message)** - Chat message ko thread mein save karta hai (max 100 messages).

---

### 3.12 nova_theme.py - Colors/Theme

Koi functions nahi - sirf 12 colour constants (BG_COLOR, ACCENT, DANGER, SUCCESS, TEXT_MAIN, etc.). Dark theme ki palette.

---

### 3.13 news.py - News Briefing

NewsAPI se 10 headlines - 3 sections mein: Cricket (1-3), Merchant Navy/NDA (4-6), Strategic/Intelligence (7-10). 10-minute cache.

**Functions (11 total):**

1. **get_news_briefing()** - MAIN FUNCTION. Full 10-article briefing formatted text mein.
2. **get_news_for_request(request)** - User ke specific request se news (jaise "news about China" ya "news on 12 July").
3. **fetch_cricket_news()** - Indian cricket headlines.
4. **fetch_merchant_navy_news()** - Defence/government/Navy related news.
5. **fetch_spy_news()** - Intelligence/geopolitics/cyber news.
6. **_fetch(url, params)** - NewsAPI HTTP call + error handling.
7. **_get_cached_news(key, fetcher)** - 10-min cache se news (bar-bar refresh nahi).
8. **parse_date_input(text)** - "16 july 2026" jaisi date parse karta hai.
9. **_format_article(num, article)** - Article ko readable text format mein.
10. **_extract_topic/place/time** - Request se topic, place, time nikalna.
11. **_build_news_query()** - Search query banata hai.

---

### 3.14 weather.py - Mausam

1. **get_weather(city)** - OpenWeatherMap se temperature, humidity, description, feels-like.
2. **handle_weather_command(command)** - Command se city nikal kar weather laata hai ("weather in Delhi" -> "Delhi").

---

### 3.15 history.py - Chat History

1. **save_message(user_text, nova_reply)** - Conversation entry save (max 150).
2. **get_recent_history(count=5)** - Last N conversations readable format mein.
3. **clear_history()** - Poori history delete.
4. **handle_history_command(command)** - "show history" / "clear history" handle.
5. **_load_history()** / **_save_history()** - history.json load/save.

---

### 3.16 settings.py - App Settings

1. **load_settings()** - settings.json se load (defaults ke saath merge).
2. **save_settings(settings)** - File mein save.
3. **update_setting(key, value)** - Individual setting update.

**Settings fields:** language, theme, voice_enabled, privacy_mode, allowed_folders.

---

### 3.17 hotkey.py - Global Hotkey (Ctrl+Z)

1. **setup_hotkey(callback)** - Ctrl+Z register karta hai - callback alag thread mein chalta hai (GUI freeze nahi hota).
2. **remove_hotkey()** - Saare hotkeys remove.

---

### 3.18 license.py - License System

SHA-256 hash se license verify - internet nahi chahiye.

1. **is_license_valid()** - license.json mein activated key valid hai ya nahi.
2. **activate_license(key, owner)** - Valid key ko save karta hai.
3. **is_key_valid(key)** - Raw key check (hmac.compare_digest se timing-safe).
4. **hash_key(key)** / **normalize_key(key)** - Key ka SHA-256 hash / clean key.
5. **get_license_status()** - Human-readable status.
6. **require_license()** - Agar invalid to RuntimeError.
7. **clear_license()** - Activation remove.
8. **_read_license_file()** / **_write_license_file()** - File I/O.
9. **main(argv)** - CLI commands (hash, activate, status, clear).

---

### 3.19 build.py - .exe Build Script

1. **build()** - PyInstaller se Nova.exe banata hai (onefile, windowed).
2. **check_pyinstaller()** / **install_pyinstaller()** - PyInstaller check/install.
3. **clean_previous_build()** - Old build/dist folders clean.
4. **_rmtree_with_retries()** / **_remove_readonly()** - Windows folder delete helpers (OneDrive/antivirus lock handle).

---

### 3.20 launcher.py - Background Launcher (System Tray)

Alag background program jo system tray mein rehta hai. Hotkey (Ctrl+Windows+Alt) se Nova ko launch karta hai agar band ho.

1. **launch_nova()** - dist/Nova.exe ko launch karta hai (agar already running nahi hai).
2. **is_nova_running()** - Check karta hai Nova process chal raha hai ya nahi.
3. **main()** - Entry point - hotkey register + tray icon + autostart flags.
4. **install_autostart()** / **uninstall_autostart()** - Windows startup registry add/remove.
5. **start_tray_icon()** - System tray icon (Open Nova / Exit menu).
6. **should_trigger_combo()** / **normalize_hotkey_name()** - Hotkey matching helpers.
7. **_build_tray_icon_image()** - Tray icon image.

---
### 3.21 features_launcher.py - Features Panel

Ek alag window jo 10 feature buttons dikhati hai (test karne ke liye).

1. **launch()** - Tk window banata hai (350x480) - 10 buttons (Smart Reminder, Screen Monitor, Command Execution, Data Export, Multi-Language, Mini-Quizzes, Context Suggestions, Gamified Progress, Offline Mode, Enhanced Translation).
2. **run_in_thread(func)** - Feature ko alag thread mein chalat hai (UI freeze nahi).
3. **show_result_text(title, message)** - Result text window mein dikhata hai.
4. Har run_* function (10 total) - corresponding nova_features module import karke test karta hai.

---

### 3.22 gui_integration.py - GUI Integration Helpers

GUI ke liye privacy/security helpers (gui.py mein integrated hain):

1. **confirm_destructive(message)** - Confirmation dialog.
2. **forget_everything()** - Double confirm ke saath data wipe.
3. **set_privacy_mode(enabled)** / **toggle_privacy_mode()** / **_is_privacy_mode_on()** - Privacy mode control.
4. **open_settings_window()** - Settings window.
5. **add_privacy_chip(sidebar)** - Sidebar privacy chip.

---

### 3.23 photo_detector.py - AI Image Detection

Photo AI-generated hai ya nahi - Groq vision model se detect karta hai.

1. **detect_ai_image(image_path)** - MAIN FUNCTION. Image ko base64 convert, Groq API se analysis, result format.
2. **_handle_rate_limit_error(error)** - 429 rate-limit error se friendly message + wait time.
3. **_call_vision_model_with_retry()** - Retry logic ke saath API call.
4. **_build_messages()** / **_call_vision_model()** - Message build + API call.
5. **image_to_base64()** - Image ko base64 + MIME convert.
6. **parse_response()** / **format_result()** - Response parse + format.

---

### 3.24 emoji_render.py - Colour Emoji System

Tkinter Windows pe colour emoji nahi dikhata (sirf monochrome). Isliye ye Twemoji PNGs ka use karta hai - har emoji inline image ki tarah.

1. **EmojiBubble (class)** - Chat bubble jo colour emoji + typewriter animation ke saath render karta hai.
2. **tokenize(text)** - Text ko text/emoji runs mein split karta hai.
3. **get_photo(emoji, master, size)** - Emoji ka cached PhotoImage.
4. **_is_emoji_char()** / **_is_continuation()** - Emoji detection helpers.
5. **count_available_emoji_images()** - Kitne emoji PNGs available.

---

### 3.25 nova_features/ - 18 Extra Features (70+ Functions)

| File | Kya Karta Hai |
|------|---------------|
| **alarm_scheduler.py** | Recurring alarms (set_alarm, snooze_alarm, disable_alarm, get_alarms) - snooze ke saath |
| **smart_reminder.py** | Reminders (set_reminder, check_reminders) - "in 30 minutes" jaisi time bhi samjhta hai |
| **app_launcher.py** | Apps launch (launch_app, open_website, get_known_apps) - 23 known apps |
| **browser_control.py** | Browser control (open_new_tab, search, open_multi_tabs) |
| **clipboard_manager.py** | Clipboard history (get/set clipboard) - max 20 items |
| **command_execution.py** | Safe command execution (stub - placeholder) |
| **context_suggestions.py** | Screen context se suggestions (analyze_screen_and_suggest) - browser/coding/entertainment detect |
| **daily_recap.py** | Daily recap summary (get_daily_recap) - level, XP, streak, achievements |
| **data_export_import.py** | Data export/import (stub - placeholder) |
| **email_notifications.py** | Email send (save_email_config, send_email_notification) - Gmail/Outlook/Yahoo |
| **enhanced_translation.py** | Offline English<->Hindi dictionary translation |
| **focus_timer.py** | Pomodoro timer (start_focus_session, start_break, stop_timer) - beep ke saath |
| **gamified_progress.py** | XP/Levels/Achievements system (10 achievements, 10 levels) |
| **mini_quizzes.py** | Quizzes (science/general/math categories) |
| **multi_language.py** | Language detect/translate (stub - placeholder) |
| **offline_first.py** | Offline mode (check_offline_status, get_offline_response, store_user_fact) |
| **screen_monitor.py** | Screen status (get_screen_status, capture_and_analyze) - active window tracking |
| **screen_ocr.py** | Screenshot + OCR text extraction |
| **system_health.py** | CPU/RAM/Disk/Battery monitor (get_system_health, get_top_processes) |
| **voice_assistant.py** | Standalone voice (listen_once, speak_text) - edge-tts |

---
---

## 4. Nova Kaise Kaam Karti Hai? (Process)

**Jab aap kuchh type/bolte ho, to ye hota hai (step-by-step):**

1. **Message** - Chat box mein likh kar Enter dabate ho (ya mic se bolte ho -> listen() -> text).
2. **send_message()** - Aapka message chat bubble mein add hota hai.
3. **Command check** - Pehle commands.py try karta hai (deterministic match). Agar match mila to turant execute - fast, bina AI ke.
4. **No match?** - Phir brain.py ka route_to_agent() LLM se poochta hai - ye system action hai ya sawal?
   - System action (file delete, etc.) -> agent.py handle() -> safe_path check -> confirmation -> execute -> audit
   - Sawal -> ask_nova() -> Groq LLM -> jawab Hinglish mein.
5. **Response** - Nova ka jawab chat bubble mein typewriter animation ke saath dikhta hai (colour emoji ke saath).
6. **Voice** - Agar voice enabled hai to jawab bol kar bhi sunaya jata hai (speak()).
7. **History** - Conversation history mein save ho jaati hai.

**Example flows:**
- "open youtube" -> commands.py match -> webbrowser.open -> "Opening YouTube"
- "what is Merchant Navy?" -> commands.py no match -> ask_nova() -> Groq LLM -> Hinglish jawab
- "delete file X" -> route_to_agent() -> agent.handle() -> safe_path() -> confirm_destructive() -> delete -> audit log
- "today news" -> commands.py match -> news.py get_news_briefing() -> 10 headlines
- "weather in Delhi" -> commands.py match -> weather.py -> OpenWeatherMap -> mausam ka haal

---

## 5. Security Features

Nova mein kaafi security patches lagaye gaye hain:

| Feature | File | Kya Karta Hai |
|---------|------|---------------|
| Path validation | agent.py safe_path() | System folders (Windows, Program Files) block, sirf allowed folders allow |
| Rate limiting | agent.py _check_rate() | 30 actions/min, 1 destructive/min |
| Audit logging | agent.py audit() | Har action log file mein (agent_audit.log) |
| No shell=True | agent.py | Sirf subprocess.run([...]) list form - shell injection se bachat |
| API key redaction | brain.py _redact() | Errors mein keys chhupata hai (sk-or-v1-***) |
| Memory sanitization | commands.py _sanitise_fact() | Prompt-injection block + 200 char cap |
| Destructive confirmation | gui.py confirm_destructive() | Shutdown/restart/delete pe confirm dialog (Enter = Cancel) |
| Privacy mode | gui.py set_privacy_mode() | ON hone par saare system/file actions block |
| Forget me | gui.py forget_everything() | Double confirmation ke saath saara data delete |
| Timing-safe compare | license.py | hmac.compare_digest se key compare |

---

## 6. Setup / Installation

1. **Project folder** - c:\Users\dell\OneDrive\Documents\nova.ai (ya jahan bhi Nova hai)
2. **Dependencies** - `pip install -r requirements.txt`
3. **API keys** (.env file mein):
   - GROQ_API_KEY - console.groq.com se free
   - GEMINI_API_KEY - aistudio.google.com/apikey se free
   - NEWS_API_KEY - newsapi.org se free
   - WEATHER_API_KEY - openweathermap.org se free
4. **Tesseract OCR** (optional) - github.com/UB-Mannheim/tesseract/wiki
5. **Run** - `python main.py`
6. **.exe build** (optional) - `python build.py` -> dist/Nova.exe
7. **Autostart launcher** (optional) - `python launcher.py --install-autostart`

---

## 7. Quick Reference - Commands

- **doctor** (ya "health check" / "diagnostics") - Nova apni health check karta hai: API keys, packages, OCR, internet, data files, write access, git. Report chat mein dikhta hai.

### Direct Commands (commands.py):
- **Open Apps:** open youtube / open google / open chrome / open whatsapp
- **Music:** play song, run <song name>, happy, sad, romantic, motivational, english vibe
- **System:** increase/decrease brightness, shutdown pc, restart pc, take screenshot, battery, what is the time
- **Nova:** stop speaking, start speaking, thank you

### News & Weather:
- today's news / aaj ki news / news briefing / daily briefing / news sunao / news batao
- news about <topic> / news in <city> / news on <date>
- weather in <city>

### Memory:
- remember my name is <name> / what is my name
- remember my favorite color is <color> / what is my favorite color
- remember <fact> is <value>

### History:
- show history / clear history

### Chat (LLM):
- Kuchh bhi pooch sakte ho - "Nova, Merchant Navy ke liye kya padhna chahiye?", "sirf 5 lines mein samjha do", etc.

---

**Yeh guide Nova AI ke source code analysis se banaya gaya hai. Total 200+ functions, 30+ files.**

*Nova AI - Full Guide (Hinglish)*

