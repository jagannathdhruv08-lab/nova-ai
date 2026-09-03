"""Generate the GitHub README banner for Nova AI (assets/banner.png).

Run:  .venv\\Scripts\\python.exe make_banner.py
Uses only PIL - no network. Delete this file after use if not needed.
"""
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 640
TOP = (8, 15, 35)      # deep navy
BOT = (16, 110, 140)   # ocean teal


def font(name, size):
    for cand in (name, "arialbd.ttf" if "bold" in name.lower() else name):
        try:
            return ImageFont.truetype(f"C:/Windows/Fonts/{cand}", size)
        except OSError:
            continue
    return ImageFont.load_default()


img = Image.new("RGB", (W, H), TOP)
d = ImageDraw.Draw(img)

# Vertical gradient
for y in range(H):
    t = y / H
    d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(TOP, BOT)))

# Soft glow circles (decorative)
glow = Image.new("RGB", (W, H), (0, 0, 0))
gd = ImageDraw.Draw(glow)
gd.ellipse((W - 380, -180, W + 180, 380), fill=(40, 160, 190))
gd.ellipse((-200, H - 260, 260, H + 200), fill=(30, 90, 150))
img = Image.blend(img, glow, 0.18)
d = ImageDraw.Draw(img)

# Accent bar
d.rounded_rectangle((84, 150, 196, 162), radius=6, fill=(64, 224, 208))

f_title = font("arialbd.ttf", 128)
f_tag = font("arial.ttf", 40)
f_chips = font("arialbd.ttf", 26)
f_sub = font("ariali.ttf", 28) or font("arial.ttf", 28)

d.text((80, 190), "NOVA AI", font=f_title, fill=(255, 255, 255))
d.text((84, 360), "Dimaag bhi, awaaz bhi, aankhein bhi.", font=f_tag, fill=(64, 224, 208))
d.text((84, 425), "Your personal JARVIS for Windows - speaks Hinglish, runs on FREE API keys",
       font=f_sub, fill=(210, 225, 235))

# Feature chips
chips = ["VOICE", "VISION", "MEMORY", "STUDY SUITE", "FREE FOREVER"]
x = 84
for chip in chips:
    w = d.textlength(chip, font=f_chips) + 36
    d.rounded_rectangle((x, 510, x + w, 558), radius=14,
                        outline=(64, 224, 208), width=2)
    d.text((x + 18, 522), chip, font=f_chips, fill=(255, 255, 255))
    x += w + 16

img.save("assets/banner.png")
print("banner saved -> assets/banner.png", img.size)
