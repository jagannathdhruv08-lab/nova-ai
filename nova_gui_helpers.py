# ==========================================
# NOVA AI - GUI HELPERS (pure logic, no Tk)
# Carved out of gui.py so the pure file/text helpers can be unit-tested
# without a display. gui.py re-imports these names, so every existing
# bare-name call site keeps working unchanged.
# ==========================================

import os


def completion_text(items):
    total = len(items)
    done = sum(1 for item in items if item.get("done"))
    return f"{done}/{total}" if total else "0/0"


def read_file_preview(path, max_chars=4500):
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".pdf":
            try:
                from pypdf import PdfReader  # type: ignore
            except ImportError:
                try:
                    from PyPDF2 import PdfReader  # type: ignore  # legacy fallback
                except ImportError:
                    return None, "PDF support needs 'pypdf'. Install it: pip install pypdf"
            try:
                reader = PdfReader(path)
                text = "\n".join((page.extract_text() or "") for page in reader.pages[:5])
            except Exception as exc:
                return None, f"PDF read failed: {type(exc).__name__}: {exc}"
        else:
            with open(path, "r", encoding="utf-8", errors="ignore") as file:
                text = file.read(max_chars)
    except Exception as exc:
        return None, str(exc)
    return text[:max_chars], None


def is_supported_image(path):
    return os.path.splitext(path)[1].lower() in {
        ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"
    }
