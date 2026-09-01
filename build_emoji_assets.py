# ==========================================
# build_emoji_assets.py — download colour Twemoji PNGs for Nova chat
# ------------------------------------------
# Scans the Nova codebase + data files for every emoji the app can show
# (plus a base set of common chat emojis) and downloads the matching
# colour 72x72 PNG from the Twemoji CDN into assets/emojis/72x72/.
#
# Run:  python build_emoji_assets.py
# Safe to re-run any time — files already on disk are skipped. Without
# internet the app simply keeps the bundle as it is.
# ==========================================

import os
import urllib.request

import emoji_render

ROOT = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(ROOT, "assets", "emojis", "72x72")
TWEMOJI_URL = "https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72"

# Directories never to scan (keeps the bundle lean).
SKIP_DIRS = {"venv", ".venv", "dist", "build", "__pycache__", ".git", ".agents"}

# Extra common chat emojis that the LLM may reply with even though they are
# never typed literally in source files — keeps the bundle ChatGPT-flavoured.
COMMON_EMOJIS = (
    "😀😃😄😁😆😅😂🤣😊😇🙂😉😌😍🥰😘😗😙😋😛😜🤪😝🤗🤭🤫🤔🤨😐😑😶😏😒🙄😬😮😥🤐🥱😴😳🤯😱😨😰😢😭😤😡😠🤬🤒🤕🤢🤮🤧🥳🥺🤠😎🤩🥴🤖💀💩🤡👻👽👾💪🦾👍👎👌👊✌️🤞🤟🤘👈👉👆👇☝️👏🙌🤲🤝👐✍️💅🤳🧠🦷👀👂💋"
    "⭐🌟✨⚡🔥💫💥💦💨💤🎉🎊🎈🎁🎂🍰🍕🍔🍟🍿🥗🍎🍌🍊🍇🍉🍓🍄☕🍵🍺🥂🌍🌎🌏🌐🗺️🏝️🏖️🌊🌋🏔️⛰️🏙️🌆🌃🌉🕌🏯🏰🗼🗽⛵🚢⚓🛳️🚤🚁✈️🚄🚆🚗🚌🚑🚒🎧🎤🎹🎸🥁🎷🎺🎻🎼🎬🎥📺📷📸🎭🎨🎲🎯🎮🕹️🏆🏅🥇🥈🥉📚📖📝✏️🖊️✂️📌📎📐📂📁📅📆⏰⏳⌛💼💻🖥️⌨️🖱️🖨️📟📠☎️📡💾⚙️🔧🔨🔩⛓️🔗🔒🔓🔑💡🔌💰📦📕📗📘📙📔📒📓📃🀄"
    "❤️🧡💛💚💙💜🖤🤍🤎💖💕💞💓💗💘💝💟🎀🎀🏆🥇🌹🌸🌼🌻🥀💐🌺🍄🎃⭐🌙☀️🌈☁️⛅🌧️⛈️⚡🔥🌪️🌬️💫🌊🌫️🏁🚩🇮🇳🇺🇸🇬🇧🇸🇦🇦🇪🇯🇵🇰🇷🇩🇪🇫🇷🇧🇷🫡🥹🫢🩷🩵🩶🎌🏳️🌈🤍💙⚽🏀🏈🎾🎱🏓🏸🏹🎣🥊🏊🚴🏋️🤸🤾🚣🏄⛸️🧗🧜‍♀️🐬🐳🐋🦈🦭🐠🐡🐟🐙🦀🦞🐚🪸🐠🦞🧬🧪🔬🔭🪐🌌"
)


def collect_sources():
    """Every Twemoji key found in source files plus the common set."""
    keys = set()
    found_emoji = set()
    for root_dir, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            if not fname.endswith((".py", ".json")):
                continue
            path = os.path.join(root_dir, fname)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
            except Exception:
                continue
            for kind, token in emoji_render.tokenize(content):
                if kind == "emoji":
                    found_emoji.add(token)
    for token in found_emoji:
        keys.add(emoji_render.twemoji_key(token))
    for kind, token in emoji_render.tokenize("".join(COMMON_EMOJIS)):
        if kind == "emoji":
            keys.add(emoji_render.twemoji_key(token))
    return keys
def download(keys):
    os.makedirs(ASSET_DIR, exist_ok=True)
    ok, missing = 0, []
    for key in sorted(keys):
        downloaded_any = False
        for variant in emoji_render.key_variants(key):
            path = os.path.join(ASSET_DIR, variant + ".png")
            if os.path.exists(path):
                downloaded_any = True
                break
            url = "%s/%s.png" % (TWEMOJI_URL, variant)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = resp.read()
                if not data:
                    continue
                with open(path, "wb") as fh:
                    fh.write(data)
                ok += 1
                downloaded_any = True
                print("  +", variant)
                break
            except Exception:
                continue
        if not downloaded_any:
            missing.append(key)

    print(f"\nDownloaded {ok} new PNGs.  Missing: {len(missing)}")
    if missing:
        print("Missing (fall back to mono glyph):", ", ".join(sorted(missing)[:120]))

    manifest = os.path.join(ROOT, "assets", "emojis", "manifest.txt")
    try:
        with open(manifest, "w", encoding="utf-8") as fh:
            fh.write("\n".join(sorted(keys)))
    except Exception:
        pass


if __name__ == "__main__":
    print("Scanning Nova sources for emojis…")
    keys = collect_sources()
    print(f"Found {len(keys)} unique emoji sequences.")
    download(keys)
    print("Done: assets/emojis/72x72")