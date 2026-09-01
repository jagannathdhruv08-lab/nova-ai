# ==========================================
# NOVA AI - BUILD SCRIPT
# ==========================================
#
# Packages the Nova AI app into a single standalone .exe using PyInstaller.
#
# USAGE:
#   1. Place this file in your nova.ai project folder (next to main.py).
#   2. Run:  python build.py
#   3. Find your app in the "dist" folder as Nova.exe
#
# NOTE: Run this from Windows if you want a .exe. PyInstaller builds for
# whatever OS it runs on (Windows -> .exe, Mac -> .app, Linux -> binary).
# ==========================================

import os
import sys
import stat
import time
import shutil
import subprocess

APP_NAME = "Nova"
ENTRY_POINT = "main.py"
ASSETS_FOLDER = "assets"
ICON_PATH = os.path.join(ASSETS_FOLDER, "nova_icon.ico")  # optional

# ==========================================================
# MODE: which packaging strategy to use.
#   "onedir"  -> fast startup, produces dist/Nova/Nova.exe (RECOMMENDED)
#               No temp-folder unpacking at launch, so the app opens much
#               faster than a onefile build. This alone gives the biggest
#               startup-speed win.
#   "onefile" -> dist/Nova.exe, but every launch unpacks + Defender-scans
#               the whole archive into %TEMP% (slow). Use only if you really
#               need a single portable .exe file.
# You can override at the command line:  python build.py --onefile
#                                                 python build.py --onedir
# ==========================================================
DEFAULT_MODE = "onedir"

# ==========================================================
# HEAVY LIBRARIES THAT ARE BUNDLED BY MISTAKE (DEAD WEIGHT)
# ----------------------------------------------------------
# PyInstaller's analysis drags these into the .exe through optional /
# transitive import chains, but the app NEVER loads them at runtime
# (verified by importing every app module and inspecting sys.modules).
# They add ~600 MB and slow BOTH build time and first paint. Excluding
# them is safe — Nova's features (voice, vision, photos, reminders, etc.)
# do not depend on any of them.
#
# NOTE: scipy / sklearn / nltk are NOT in this list on purpose — they ARE
# loaded at runtime by edge-tts/gruut (text-to-speech), so they must stay.
# ==========================================================
EXCLUDE_MODULES = [
    "torch",
    "torchaudio",
    "torchvision",
    "transformers",
    "einops",
    "encodec",
    "librosa",
    "safetensors",
    "tensorboard",
    "tensorboard-data-server",
    "torchgen",
    "functorch",
]


def check_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
        return True
    except ImportError:
        return False


def install_pyinstaller():
    print("PyInstaller not found. Installing...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)


def _remove_readonly(func, path, exc_info):
    """Clear the read-only bit and retry — fixes many Windows PermissionErrors."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def _rmtree_with_retries(folder, attempts=5, delay=1.0):
    for attempt in range(1, attempts + 1):
        try:
            shutil.rmtree(folder, onerror=_remove_readonly)
            return True
        except PermissionError:
            if attempt == attempts:
                return False
            print(f"  '{folder}' is locked (attempt {attempt}/{attempts}) — "
                  f"this is usually OneDrive sync or antivirus. Retrying in {delay}s...")
            time.sleep(delay)
    return False


def clean_previous_build():
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            print(f"Removing old '{folder}' folder...")
            if not _rmtree_with_retries(folder):
                print(
                    f"WARNING: could not fully remove '{folder}' (a file is still locked).\n"
                    f"  This usually means OneDrive is syncing it, or an old Nova.exe/antivirus\n"
                    f"  scan still has a file open. Close any running Nova.exe, wait a moment\n"
                    f"  for OneDrive to finish syncing, then re-run this script.\n"
                    f"  Continuing anyway — PyInstaller will try to overwrite what it can."
                )

    spec_file = f"{APP_NAME}.spec"
    if os.path.exists(spec_file):
        try:
            os.remove(spec_file)
        except PermissionError:
            print(f"WARNING: could not remove '{spec_file}' (locked) — continuing anyway.")


def build():

    mode = DEFAULT_MODE
    if "--onefile" in sys.argv:
        mode = "onefile"
    elif "--onedir" in sys.argv:
        mode = "onedir"
    elif sys.argv[1:2] and sys.argv[1].startswith("-"):
        # Swallow the recognized mode flag so PyInstaller doesn't choke on it
        pass

    if not os.path.exists(ENTRY_POINT):
        print(f"ERROR: '{ENTRY_POINT}' not found. Run this script from your nova.ai project folder.")
        sys.exit(1)

    if not check_pyinstaller():
        install_pyinstaller()

    clean_previous_build()

    # Windows uses ';' to separate src;dest in --add-data, Mac/Linux use ':'
    data_separator = ";" if os.name == "nt" else ":"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--windowed",
        "--name", APP_NAME,
    ]

    if mode == "onedir":
        cmd.append("--onedir")
        print(f"\n>>> Mode: ONEDIR (fast startup)  output -> dist/{APP_NAME}/{APP_NAME}.exe")
    else:
        cmd.append("--onefile")
        print(f"\n>>> Mode: ONEFILE (slow startup)  output -> dist/{APP_NAME}.exe")

    if os.path.isdir(ASSETS_FOLDER):
        cmd += ["--add-data", f"{ASSETS_FOLDER}{data_separator}{ASSETS_FOLDER}"]
    else:
        print(f"WARNING: '{ASSETS_FOLDER}' folder not found — images may be missing from the build.")

    # customtkinter ships its own theme/asset files that need to be bundled
    cmd += ["--collect-all", "customtkinter"]

    # google-genai (Gemini) is imported LAZILY inside a function in
    # nova_vision.py, so PyInstaller's static analysis frequently misses it
    # and the built exe silently reports "Gemini not configured". Force it in:
    cmd += ["--collect-all", "google"]
    cmd += ["--hidden-import", "google.genai"]
    # pypdf is imported lazily inside nova_knowledge.py /
    # nova_gui_helpers.read_file_preview, so PyInstaller can miss it -
    # force it into the bundle.
    cmd += ["--hidden-import", "pypdf"]
    # nova_doctor is imported lazily inside commands.py (the "doctor"
    # command), so PyInstaller can miss it too - force it in as well.
    cmd += ["--hidden-import", "nova_doctor"]
    # google-genai pulls these heavy runtime deps that the graph can miss:
    for mod in ("grpcio", "grpcio._cython", "protobuf",
                "google.auth", "google.auth.transport", "google.auth.compute_engine"):
        cmd += ["--hidden-import", mod]

    # Drop the heavy libraries that are included by mistake (see EXCLUDE_MODULES).
    # This shrinks the build by hundreds of MB and speeds up both build & startup.
    for mod in EXCLUDE_MODULES:
        cmd += ["--exclude-module", mod]

    if os.path.exists(ICON_PATH):
        cmd += ["--icon", ICON_PATH]
        print(f"Using icon: {ICON_PATH}")
    else:
        print(f"NOTE: no icon found at '{ICON_PATH}' — building with the default icon.")

    cmd.append(ENTRY_POINT)

    print("\nRunning PyInstaller with:")
    print(" ".join(cmd), "\n")

    subprocess.run(cmd, check=True)

    if mode == "onedir":
        exe_path = os.path.join("dist", APP_NAME, f"{APP_NAME}.exe")
    else:
        exe_name = f"{APP_NAME}.exe" if os.name == "nt" else APP_NAME
        exe_path = os.path.join("dist", exe_name)

    if os.path.exists(exe_path):
        print(f"\nBuild complete! Your app is at: {exe_path}")
        print("Tip: run the .exe from that folder (onedir) — it stays there and launches fast.")
    else:
        print("\nBuild finished, but the expected output file wasn't found. Check the log above for errors.")
        return

    # ----------------------------------------------------------
    # Ship .env next to the exe so API features (Gemini, Groq,
    # Weather, News...) work in the BUILT app too.
    # When frozen, Nova reads its keys from the folder NEXT TO the
    # exe (see nova_vision.py / brain.py / photo_detector.py) — not
    # from the project root. Without this copy, the built app has an
    # empty GEMINI_API_KEY and Gemini reports "not configured".
    # ----------------------------------------------------------
    env_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if mode == "onedir":
        env_dst = os.path.join("dist", APP_NAME, ".env")
    else:
        env_dst = os.path.join("dist", ".env")
    if os.path.exists(env_src):
        import shutil as _shutil
        try:
            _shutil.copy2(env_src, env_dst)
            print(f"Copied .env next to the exe -> {env_dst}")
            print("  (So Gemini / Groq / Weather / News keys work in the built app.)")
        except Exception as _exc:
            print(f"WARNING: could not copy .env next to the exe: {_exc}")
            print("  Vision/Gemini and other API features may show 'not configured'.")
    else:
        print("NOTE: no .env at project root — API keys won't be available in the built app.")


if __name__ == "__main__":
    build()