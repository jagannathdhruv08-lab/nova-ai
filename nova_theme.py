# ==========================================
# NOVA AI - THEME / COLOR PALETTE
# Pure constants, no dependencies on anything else. Safe to import
# from any other Nova file without risk of circular imports.
# ==========================================

BG_COLOR = "#0f1117"
SIDEBAR_COLOR = "#151821"
TOPBAR_COLOR = "#181c25"
CARD_COLOR = "#1c212c"
CARD_COLOR_SOFT = "#252b38"
ACCENT = "#4f8cff"
ACCENT_HOVER = "#3d73d7"
ACCENT_SOFT = "#203353"
TEXT_MAIN = "#f5f7fb"
TEXT_MUTED = "#a5adbd"
DANGER = "#e75a66"
DANGER_HOVER = "#bd4651"
SUCCESS = "#42d392"
BORDER_COLOR = "#313846"

# Per-subject accent colours used by the Study Hub (PCM + Merchant Navy).
# Keys match nova_study.SUBJECTS so gui can look up a subject's colour.
SUBJECT_COLORS = {
    "physics": "#185FA5",
    "chemistry": "#D85A30",
    "maths": "#7C4AB7",
    "english": "#3B6D11",
    "mn": "#0F6E56",
    "general": "#4f8cff",
}
