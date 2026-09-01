# ==========================================
# NOVA SCREEN OCR — Screenshot + Text Extraction
# ==========================================
import os
import time


def capture_screen_text(region=None):
    """Capture the screen and extract text using OCR (pytesseract)."""
    try:
        from PIL import ImageGrab
        import pytesseract

        screenshot = ImageGrab.grab(bbox=region) if region else ImageGrab.grab()
        timestamp = time.strftime("%Y%m%d_%H%M%S")

        # Save screenshot copy
        save_dir = os.path.join(os.path.expanduser("~"), ".nova", "screenshots")
        os.makedirs(save_dir, exist_ok=True)
        screenshot_path = os.path.join(save_dir, f"nova_capture_{timestamp}.png")
        screenshot.save(screenshot_path)

        # Extract text
        text = pytesseract.image_to_string(screenshot)
        text = text.strip()

        if not text:
            return {
                "success": True,
                "feature": "screen_ocr",
                "text": "",
                "screenshot_path": screenshot_path,
                "size": f"{screenshot.size[0]}x{screenshot.size[1]}",
                "message": "📷 Screenshot saved, but no text detected",
            }

        preview = text[:150] + ("..." if len(text) > 150 else "")
        return {
            "success": True,
            "feature": "screen_ocr",
            "text": text,
            "char_count": len(text),
            "screenshot_path": screenshot_path,
            "size": f"{screenshot.size[0]}x{screenshot.size[1]}",
            "message": f"📷 Text extracted ({len(text)} chars). Preview: {preview}",
        }
    except ImportError as e:
        return {
            "success": False,
            "feature": "screen_ocr",
            "message": f"OCR dependency missing: {str(e)}",
        }
    except Exception as e:
        return {
            "success": False,
            "feature": "screen_ocr",
            "error": str(e),
            "message": f"Screen capture failed: {str(e)}",
        }


def capture_and_save():
    """Capture the screen and save it as an image (no OCR)."""
    try:
        from PIL import ImageGrab
        import time

        screenshot = ImageGrab.grab()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        save_dir = os.path.join(os.path.expanduser("~"), ".nova", "screenshots")
        os.makedirs(save_dir, exist_ok=True)
        path = os.path.join(save_dir, f"nova_capture_{timestamp}.png")
        screenshot.save(path)
        return {
            "success": True,
            "feature": "screen_ocr",
            "path": path,
            "size": f"{screenshot.size[0]}x{screenshot.size[1]}",
            "message": f"📸 Screenshot saved: {os.path.basename(path)}",
        }
    except Exception as e:
        return {
            "success": False,
            "feature": "screen_ocr",
            "error": str(e),
            "message": f"Screenshot failed: {str(e)}",
        }


__version__ = "1.0.0"
__all__ = ["capture_screen_text", "capture_and_save"]
