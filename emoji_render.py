# ==========================================
# emoji_render.py — COLOUR emoji for Nova chat bubbles
# ------------------------------------------
# Tkinter on Windows (GDI) cannot draw colour emoji — even with the
# "Segoe UI Emoji" font, every emoji renders as a black & white outline.
# This module solves it the way desktop chat apps do: each emoji is
# drawn inline as a real image (bundled Twemoji 72x72 PNGs, colourised
# and scaled with Pillow).
#
# It provides:
#   * tokenize()                 -> split text into text/emoji runs
#   * get_photo(emoji, master)   -> cached tk.PhotoImage for one emoji
#   * EmojiBubble(ctk.CTkFrame)  -> rounded chat bubble that renders a
#                                   plain-text message with colour emoji
#                                   images, autosizes to its content and
#                                   supports step-by-step typing (used by
#                                   gui.py's typewriter_into_bubble()).
#
# Everything degrades gracefully: if a PNG is missing or Pillow is not
# present, the emoji glyph is still shown as text (Segoe UI Emoji).
# ==========================================

import os
import re
import sys
import time
import tkinter as tk
from tkinter import font as tkfont

import customtkinter as ctk

try:
    from PIL import Image, ImageTk
    _PIL_OK = True
except Exception:
    _PIL_OK = False

# Bundled colour emoji PNGs live here (see build_emoji_assets.py).
_EMOJI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "emojis", "72x72")

# ---------------------------------------------------------------------------
# Emoji character detection (same ranges as brain.py's _strip_emojis).
# ---------------------------------------------------------------------------
_EMOJI_RANGES = (
    (0x1F600, 0x1F64F),  # Emoticons
    (0x1F300, 0x1F5FF),  # Misc Symbols and Pictographs
    (0x1F680, 0x1F6FF),  # Transport and Map
    (0x1F1E0, 0x1F1FF),  # Flags (regional indicators)
    (0x2700, 0x27BF),    # Dingbats
    (0x1F900, 0x1F9FF),  # Supplemental Symbols and Pictographs
    (0x1FA00, 0x1FA6F),  # Chess Symbols
    (0x1FA70, 0x1FAFF),  # Symbols and Pictographs Extended-A
    (0x2600, 0x26FF),    # Misc Symbols
    (0x2B00, 0x2BFF),    # Misc Symbols and Arrows
)

# Combining characters that continue an emoji "sequence".
_CONTINUATION = {0xFE0F, 0xFE0E, 0x20E3, 0x200D}
_SKIN_TONES = range(0x1F3FB, 0x1F400)
_REGIONAL = range(0x1F1E6, 0x1F200)   # flags = 2 regional-indicator letters

# ---------------------------------------------------------------------------
# Markdown parsing for formatted chat responses
# ---------------------------------------------------------------------------
# The LLM (guided by SYSTEM_PROMPT in brain.py) emits Markdown-style formatting
# inside chat bubbles. Tkinter's tk.Text does **not** understand Markdown, so we
# pre-parse the text into (segment, tag) pairs here, then apply tk.Text tags
# (bold font, larger font, etc.) when writing into the widget.
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_H2 = re.compile(r"^##\s+(.+)$")
_MD_H3 = re.compile(r"^###\s+(.+)$")
_MD_CODE = re.compile(r"`([^`]+)`")
_MD_SEP = re.compile(r"^\s*-{3,}\s*$")
_MD_FENCE = re.compile(r"^\s*```")          # fenced code block marker
_MD_BULLET = re.compile(r"^(\s*)[-*]\s+(.*)$")  # "- item" / "* item"
# Matches either **bold** or `code` (whichever comes first on a line)
_MD_INLINE = re.compile(r"(\*\*.*?\*\*)|(`[^`]+`)")

_PHOTO_CACHE = {}          # (twemoji_key, size_px) -> tk.PhotoImage or None


def _is_emoji_char(ch: str) -> bool:
    cp = ord(ch)
    return any(a <= cp <= b for a, b in _EMOJI_RANGES)


def _is_continuation(ch: str) -> bool:
    cp = ord(ch)
    return cp in _CONTINUATION or cp in _SKIN_TONES


def tokenize(text: str):
    """Yield (kind, value) runs: ('text', str) or ('emoji', str).

    Consecutive emoji + continuation chars (variation selectors, skin
    tones, ZWJ sequences) are grouped into a single emoji run so they can
    be looked up as one Twemoji asset. Flags are exactly two regional
    indicator letters, so touching flags stay separate emoji.
    """
    text = "" if text is None else str(text)
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if not _is_emoji_char(ch) and not _is_continuation(ch):
            j = i
            while j < n:
                c = text[j]
                if _is_emoji_char(c) or _is_continuation(c):
                    break
                j += 1
            if j > i:
                yield ("text", text[i:j])
            i = j
            continue

        # --- emoji run (munch emoji + its continuation chars) ----------
        j = i + 1
        after_zwj = False
        region_count = 1 if ord(ch) in _REGIONAL else 0
        while j < n:
            c = text[j]
            if _is_continuation(c):
                after_zwj = (c == "\u200d")
                j += 1
            elif after_zwj and _is_emoji_char(c):
                after_zwj = False
                if ord(c) in _REGIONAL:
                    region_count += 1
                j += 1
            elif (ord(c) in _REGIONAL and ord(text[j - 1]) in _REGIONAL
                    and region_count % 2 == 1):
                # flags are pairs of regional letters: 🇮+🇳 -> 🇮🇳
                region_count += 1
                after_zwj = False
                j += 1
            else:
                break
        yield ("emoji", text[i:j])
        i = j


# ---------------------------------------------------------------------------
# Markdown parsing — converts inline Markdown (##, **, `, ---) into
# (segment_text, tag) pairs so EmojiBubble can apply tk.Text tags.
# ---------------------------------------------------------------------------
def _strip_bold(text: str) -> str:
    """Remove ** markers from *text* (used for header content)."""
    return _MD_BOLD.sub(r"\1", text)


def _split_markdown(text: str):
    """Split *text* into ``(segment, tag)`` pairs, parsing Markdown.

    Recognises:
    • ``## **Header**`` / ``## Header``  → tag ``'h2'``
    • ``### **Header**`` / ``### Header`` → tag ``'h3'``
    • ``**bold**``      → tag ``'bold'``   (inline)
    • `` `code` ``      → tag ``'code'``   (inline)
    • ``---``           → tag ``'separator'``
    • ``` fenced blocks  → tag ``'codeblock'`` (Consolas + dark bg)
    • ``- item``/``* item`` → bullet rendered as "• item"

    Returns a list of ``(text, tag)`` tuples where *tag* is ``None``
    for plain text.  Each segment is designed to be fed to ``tokenize()``
    so that emoji are still rendered as colour images.
    """
    if not text:
        return [(text or "", None)]

    segments = []
    in_code_block = False

    for line in text.split("\n"):
        # --- fenced code block toggle -------------------------------
        if _MD_FENCE.match(line):
            in_code_block = not in_code_block
            # the fence line itself disappears (like GitHub rendering)
            continue

        if in_code_block:
            segments.append((line + "\n", "codeblock"))
            continue

        # --- separator ---
        if _MD_SEP.match(line):
            segments.append(("━" * 30 + "\n", "separator"))
            continue

        # --- h2 header ---
        h2 = _MD_H2.match(line)
        if h2:
            segments.append((_strip_bold(h2.group(1)) + "\n", "h2"))
            continue

        # --- h3 header ---
        h3 = _MD_H3.match(line)
        if h3:
            segments.append((_strip_bold(h3.group(1)) + "\n", "h3"))
            continue

        # --- bullet list: "- item" / "* item" -> "• item" ------------
        bullet = _MD_BULLET.match(line)
        if bullet:
            line = f"{bullet.group(1)}• {bullet.group(2)}"

        # --- empty line ---
        if not line:
            segments.append(("\n", None))
            continue

        # --- inline bold / code ---
        pos = 0
        parts = []
        for m in _MD_INLINE.finditer(line):
            if m.start() > pos:
                parts.append((line[pos:m.start()], None))
            if m.group(1):          # bold
                parts.append((_MD_BOLD.match(m.group(1)).group(1), "bold"))
            else:                    # code
                parts.append((_MD_CODE.match(m.group(2)).group(1), "code"))
            pos = m.end()
        if pos < len(line):
            parts.append((line[pos:], None))

        if parts:
            # Attach trailing newline to the last part
            last_text, last_tag = parts[-1]
            parts[-1] = (last_text + "\n", last_tag)
            segments.extend(parts)
        else:
            segments.append(("\n", None))

    return segments


def _iter_markdown_tokens(text: str):
    """Yield ``(kind, token, tag)`` tuples from *text* with Markdown parsing.

    Combines Markdown inline parsing (bold, headers, code, separators)
    with emoji tokenization.  Each yielded tuple has:
    • *kind*: ``'text'`` or ``'emoji'``
    • *token*: the raw text or emoji string
    • *tag*: ``None`` or a font tag name
      (``'h2'``, ``'h3'``, ``'bold'``, ``'code'``, ``'separator'``)
    """
    for seg_text, tag in _split_markdown(text):
        for kind, token in tokenize(seg_text):
            yield kind, token, tag


def twemoji_key(emoji: str) -> str:
    """Twemoji asset file name (hex codepoints joined by '-', no U+FE0F)."""
    return "-".join("%x" % ord(c) for c in emoji if ord(c) != 0xFE0F)


def key_variants(key: str):
    """Asset file names that may exist for a Twemoji key.

    Some ZWJ emoji are stored by Twemoji with an explicit U+FE0F on part
    of the sequence (e.g. the rainbow flag is 1f3f3-fe0f-200d-1f308).
    """
    out = [key]
    if "200d" in key:
        idx = key.index("200d")
        out.append(key[:idx] + "fe0f-" + key[idx:])
        out.append(key + "-fe0f")
    return out


def _png_path(emoji: str) -> str:
    for key in key_variants(twemoji_key(emoji)):
        path = os.path.join(_EMOJI_DIR, key + ".png")
        if os.path.exists(path):
            return path
    return os.path.join(_EMOJI_DIR, twemoji_key(emoji) + ".png")


def get_photo(emoji: str, master=None, size: int = 26):
    """Return a cached colour-emoji tk.PhotoImage for *emoji* (or None)."""
    key = (twemoji_key(emoji), size)
    if key in _PHOTO_CACHE:
        return _PHOTO_CACHE[key]

    photo = None
    if _PIL_OK:
        path = _png_path(emoji)
        if os.path.exists(path):
            try:
                base = Image.open(path).convert("RGBA")
                photo = ImageTk.PhotoImage(base.resize((size, size), Image.LANCZOS), master=master)
            except Exception:
                photo = None

    _PHOTO_CACHE[key] = photo
    return photo


def count_available_emoji_images() -> int:
    """Number of bundled colour emoji PNGs on disk (for diagnostics)."""
    if not os.path.isdir(_EMOJI_DIR):
        return 0
    return sum(1 for f in os.listdir(_EMOJI_DIR) if f.lower().endswith(".png"))


class EmojiBubble(ctk.CTkFrame):
    """Rounded chat bubble that renders colour emojis as inline images.

    Drop-in replacement for the CTkLabel bubbles used by gui.py:
    created like a frame (grid/pack), exposes set_text()/stream_text()
    instead of configure(text=...).
    """

    def __init__(
        self,
        master,
        bg_color="#252b38",
        text_color="#f5f7fb",
        corner_radius=10,
        wraplength=520,
        font_size=13,
        font_family="Segoe UI",
        inner_padx=14,
        inner_pady=10,
    ):
        super().__init__(master=master, fg_color=bg_color, corner_radius=corner_radius)
        self._bg = bg_color
        self._fg = text_color
        self._font_size = font_size
        self._emoji_px = max(18, int(font_size * 1.9))
        self._font_family = font_family
        self._pending_images = []   # prevent GC of embedded PhotoImages

        # --- measure font so the Text widget wraps to the target width ----
        unit = 7
        try:
            from tkinter import font as tkfont_module
            measure_font = tkfont_module.Font(self, family=font_family, size=font_size)
            unit = max(1, measure_font.measure("0"))
        except Exception:
            pass
        width_chars = max(int((wraplength - 2 * inner_padx) / unit), 20)

        self.txt = tk.Text(
            self,
            bg=bg_color,
            fg=text_color,
            font=(font_family, font_size),
            wrap="word",
            width=width_chars,
            height=1,
            bd=0,
            highlightthickness=0,
            relief="flat",
            padx=inner_padx,
            pady=inner_pady,
            cursor="arrow",
            insertwidth=0,
            takefocus=0,
            state="disabled",
        )
        self.txt.pack(fill="both", expand=True, padx=2, pady=2)
        self.txt.tag_configure("emoji_fallback", font=("Segoe UI Emoji", font_size))
        # --- Markdown font tags ---
        if tkfont:
            _bold_f = tkfont.Font(self, family=font_family, size=font_size, weight="bold")
            self.txt.tag_configure("bold", font=_bold_f)
            _h2_f = tkfont.Font(self, family=font_family, size=int(font_size * 1.3), weight="bold")
            self.txt.tag_configure("h2", font=_h2_f)
            _h3_f = tkfont.Font(self, family=font_family, size=int(font_size * 1.15), weight="bold")
            self.txt.tag_configure("h3", font=_h3_f)
            _code_f = tkfont.Font(self, family="Consolas", size=font_size)
            self.txt.tag_configure("code", font=_code_f)
            # fenced code blocks: monospace on a darker panel
            _codeb_f = tkfont.Font(self, family="Consolas", size=font_size)
            self.txt.tag_configure(
                "codeblock", font=_codeb_f,
                background="#161b26", foreground="#c9d4e8",
                lmargin1=10, lmargin2=10, rmargin=10)
            _sep_f = tkfont.Font(self, family=font_family, size=font_size)
            self.txt.tag_configure("separator", font=_sep_f)
        # Height depends on the real on-screen width: re-fit once laid out.
        self.bind("<Configure>", self._on_resize, add="+")
        # A plain tk.Text has a built-in MouseWheel class binding that would
        # scroll the bubble's own content instead of the chat window.
        # Route the wheel to the nearest scrollable container instead.
        self.txt.bind("<MouseWheel>", self._on_mouse_wheel)
        self.txt.bind("<Button-4>", self._on_mouse_wheel)
        self.txt.bind("<Button-5>", self._on_mouse_wheel)

    def _on_resize(self, _event=None):
        try:
            self.after_idle(self._autosize)
        except Exception:
            pass

    def _on_mouse_wheel(self, event):
        """Scroll the chat container behind this bubble (prevents the raw
        tk.Text from scrolling itself into a blank view)."""
        try:
            canvas = self._nearest_scroll_canvas()
            if canvas is None:
                return "break"
            if event.num in (4, 5):            # Linux wheel buttons
                canvas.yview_scroll(-1 if event.num == 4 else 1, "units")
                return "break"
            if not sys.platform.startswith("win"):
                return "break"
            shift = (event.state & 0x0001) != 0
            if shift:
                if canvas.xview() != (0.0, 1.0):
                    canvas.xview("scroll", -int(event.delta / 6), "units")
            else:
                if canvas.yview() != (0.0, 1.0):
                    canvas.yview("scroll", -int(event.delta / 6), "units")
        except Exception:
            pass
        return "break"

    def _nearest_scroll_canvas(self):
        widget = self
        while widget is not None:
            parent = widget.master
            if parent is not None and hasattr(parent, "_parent_canvas"):
                return parent._parent_canvas
            widget = parent
        return None

    # ------------------------------------------------------------------
    # content API
    # ------------------------------------------------------------------
    def set_text(self, text) -> None:
        """Instantly render the whole message (no animation)."""
        self._full_text = "" if text is None else str(text)
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self._insert_all(text)
        self._schedule_autosize()
        self.txt.configure(state="disabled")

    def stream_text(self, text, after_step=None, delay=0.012) -> None:
        """Typewriter animation: appends one char/emoji at a time.

        ``after_step`` is called after every step (used to auto-scroll the
        chat window). Runs in the caller's thread (Tk main thread).
        """
        self._full_text = "" if text is None else str(text)
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        try:
            for kind, token, tag in _iter_markdown_tokens(text):
                if kind == "text":
                    for ch in token:
                        self._write_char(ch, tag)
                        self._step(after_step, delay)
                else:
                    self._write_emoji(token)
                    self._step(after_step, delay)
        finally:
            self._schedule_autosize()
            self.txt.configure(state="disabled")

    def get_text(self) -> str:
        """Return the bubble's full plain-text content (the ORIGINAL string
        passed to set_text/stream_text, including emoji) — not the emoji
        images drawn in the tk.Text. Used by Copy/Save/Speak so they grab
        the real message instead of an empty/label placeholder."""
        return getattr(self, "_full_text", "")

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _insert_all(self, text) -> None:
        for kind, token, tag in _iter_markdown_tokens(text):
            if kind == "text":
                self._write_char(token, tag)
            else:
                self._write_emoji(token)

    def _write_char(self, ch, tag=None) -> None:
        """Insert a single character, optionally applying a Markdown tag."""
        if tag:
            self.txt.insert("end", ch, tag)
        else:
            self.txt.insert("end", ch)

    def _write_emoji(self, emoji, tag=None) -> None:
        """Insert an emoji (image or fallback glyph).

        *tag* is accepted for signature parity with ``_write_char`` but
        is **not** applied — colour emoji are rendered as Tk images (tags
        don't affect images) and monochrome fallbacks already use the
        dedicated ``emoji_fallback`` tag.
        """
        photo = get_photo(emoji, master=self, size=self._emoji_px)
        if photo is not None:
            self._pending_images.append(photo)
            self.txt.image_create("end", image=photo, align="center")
        else:
            # Colour PNG missing -> show the glyph as text (monochrome fallback)
            self.txt.insert("end", emoji)
            self.txt.tag_add("emoji_fallback", "end-%dc" % len(emoji), "end")

    def _step(self, after_step, delay) -> None:
        if after_step is not None:
            try:
                after_step()
            except Exception:
                pass
        try:
            self.update()
        except Exception:
            pass
        if delay and delay > 0:
            time.sleep(delay)

    def _schedule_autosize(self) -> None:
        try:
            self.after_idle(self._autosize)
        except Exception:
            pass

    def _autosize(self) -> None:
        """Size the Text widget to exactly fit its (wrapped) content.

        The wrap height can only be measured once the widget has an
        on-screen width, so when the bubble is still unmapped (e.g. on a
        hidden page) we pad to the logical line count; a <Configure>
        event re-fits the height as soon as it becomes visible.
        """
        try:
            self.update_idletasks()
            if self.winfo_ismapped():
                lines = int(self.txt.tk.call(self.txt._w, "count", "-displaylines", "1.0", "end"))
            else:
                lines = int(self.txt.index("end-1c").split(".")[0])
            self.txt.configure(height=max(1, lines))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Convenience used by health-check scripts.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("colour emoji PNGs on disk:", count_available_emoji_images())
    for kind, tok in tokenize("Heyy 👋😀 aaja! Bol 🚢⚓"):
        print(f"  {kind!r:8}: {tok!r}")