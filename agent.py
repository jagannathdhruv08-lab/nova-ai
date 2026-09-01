"""
agent.py — System agent for File Explorer + OS access.
Drop-in module for the next phase of Nova AI. Wired into brain.py via
a new INTENT_LABEL ("agent") and into commands.py via a new branch.

Design rules (DO NOT BREAK):
  1. NO `os.system`. NO `shell=True`. Every external process is launched
     via `subprocess.run([...])` with a list.
  2. Every file path the agent touches MUST pass through `safe_path()`.
     That function refuses any path that is outside ALLOWED_ROOTS or
     inside a FORBIDDEN_PATH. It also follows symlinks (via resolve())
     so a symlink in the user's home can't escape to system32.
  3. Destructive actions require `confirm_callback()` to return True.
     The GUI passes its modal-confirm helper.
  4. Every action is appended to an append-only audit log.
  5. Per-minute rate limit: 30 actions total, 1 destructive per minute.
  6. If anything throws, the error is logged with type-only and a
     generic user-facing message is returned. No stack traces to the
     chat bubble.
"""

import os
import sys
import json
import re
import time
import shutil
import hashlib
import logging
import subprocess
import platform
from collections import deque
from datetime import datetime
from pathlib import Path

from settings import load_settings

log = logging.getLogger("nova.agent")

# ---------------------------------------------------------------------------
# 1. Roots
# ---------------------------------------------------------------------------
def _user_data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    p = base / "Nova"
    p.mkdir(parents=True, exist_ok=True)
    return p


AUDIT_LOG = _user_data_dir() / "agent_audit.log"

FORBIDDEN_PATHS = {
    Path(os.environ.get("SystemRoot", r"C:\Windows")).resolve(),
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")).resolve(),
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")).resolve(),
}

# Default allow-list: only the user's home + Desktop + Documents + Downloads.
# Configurable in user settings later.
ALLOWED_ROOTS = [
    p.resolve() for p in [
        Path.home(),
        Path.home() / "Desktop",
        Path.home() / "Documents",
        Path.home() / "Downloads",
    ]
]


def _is_forbidden_path(path: Path, forbidden: Path) -> bool:
    try:
        path.relative_to(forbidden)
        return True
    except ValueError:
        return False


def _load_allowed_folders() -> list[Path]:
    try:
        settings = load_settings()
    except Exception:
        return []

    raw_folders = settings.get("allowed_folders", []) or []
    allowed_folders = []
    seen = set()
    for raw in raw_folders:
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            folder = Path(os.path.expandvars(os.path.expanduser(raw))).resolve(strict=False)
        except (OSError, RuntimeError, ValueError):
            continue
        if any(_is_forbidden_path(folder, forbidden) for forbidden in FORBIDDEN_PATHS):
            continue
        path_key = str(folder)
        if path_key not in seen:
            seen.add(path_key)
            allowed_folders.append(folder)
    return allowed_folders


def get_allowed_roots() -> list[Path]:
    roots = []
    seen = set()
    for root in ALLOWED_ROOTS:
        root_key = str(root)
        if root_key not in seen:
            seen.add(root_key)
            roots.append(root)

    for extra in _load_allowed_folders():
        extra_key = str(extra)
        if extra_key not in seen:
            seen.add(extra_key)
            roots.append(extra)
    return roots

# ---------------------------------------------------------------------------
# 2. Allow-list
# ---------------------------------------------------------------------------
ALLOWED_ACTIONS = {
    "list_dir", "open_file", "search_file", "read_file_summary",
    "create_folder", "move_file", "rename_file", "delete_file",
    "run_app", "system_info", "disk_usage", "empty_recycle_bin",
}
DESTRUCTIVE = {"delete_file", "move_file", "rename_file",
               "empty_recycle_bin", "create_folder"}

# ---------------------------------------------------------------------------
# 3. Rate limit
# ---------------------------------------------------------------------------
_ACTION_TIMES: deque[float] = deque(maxlen=100)
_DESTRUCTIVE_TIMES: deque[float] = deque(maxlen=10)
RATE_LIMIT_WINDOW = 60.0
MAX_ACTIONS_PER_MIN = 30
MAX_DESTRUCTIVE_PER_MIN = 1


def _check_rate(is_destructive: bool) -> str | None:
    now = time.monotonic()
    while _ACTION_TIMES and now - _ACTION_TIMES[0] > RATE_LIMIT_WINDOW:
        _ACTION_TIMES.popleft()
    while _DESTRUCTIVE_TIMES and now - _DESTRUCTIVE_TIMES[0] > RATE_LIMIT_WINDOW:
        _DESTRUCTIVE_TIMES.popleft()

    if len(_ACTION_TIMES) >= MAX_ACTIONS_PER_MIN:
        return f"Rate limit: max {MAX_ACTIONS_PER_MIN} actions per minute."
    if is_destructive and len(_DESTRUCTIVE_TIMES) >= MAX_DESTRUCTIVE_PER_MIN:
        return f"Rate limit: max {MAX_DESTRUCTIVE_PER_MIN} destructive action per minute."
    return None


def _record(is_destructive: bool):
    now = time.monotonic()
    _ACTION_TIMES.append(now)
    if is_destructive:
        _DESTRUCTIVE_TIMES.append(now)


# ---------------------------------------------------------------------------
# 4. Path validation
# ---------------------------------------------------------------------------
def safe_path(raw: str) -> Path | None:
    if not raw:
        return None
    try:
        p = Path(os.path.expandvars(os.path.expanduser(raw))).resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None

    # Block NUL bytes and other weirdness.
    if "\x00" in raw:
        return None

    # Reject forbidden paths.
    for forbidden in FORBIDDEN_PATHS:
        try:
            p.relative_to(forbidden)
            return None
        except ValueError:
            continue

    # Require it to be inside one of the allowed roots.
    for allowed in get_allowed_roots():
        try:
            p.relative_to(allowed)
            return p
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# 5. Audit
# ---------------------------------------------------------------------------
def audit(action: str, target: str, status: str, confirmed: bool, extra: dict | None = None):
    record = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "action": action,
        "target": target[:500],
        "status": status,
        "confirmed": confirmed,
    }
    if extra:
        record["extra"] = {k: str(v)[:200] for k, v in extra.items()}
    try:
        with AUDIT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        log.exception("Failed to write audit log")


# ---------------------------------------------------------------------------
# 6. The action router
# ---------------------------------------------------------------------------
def handle(action_json: dict, confirm_callback=None) -> str:
    """
    `action_json` is the dict returned by the LLM. `confirm_callback(msg)`
    is a function that returns True if the user accepted the modal.
    """
    action = action_json.get("action", "")
    args = action_json.get("args", {}) or {}
    confidence = float(action_json.get("confidence", 0.0))

    if action not in ALLOWED_ACTIONS:
        audit(action, "<unknown>", "denied:not_allowed", False)
        return f"Action '{action}' is not allowed."

    if confidence < 0.55:
        audit(action, str(args), "denied:low_confidence", False)
        return f"Action '{action}' rejected — model confidence too low ({confidence:.0%})."

    is_destructive = action in DESTRUCTIVE

    rl = _check_rate(is_destructive)
    if rl is not None:
        audit(action, str(args), f"denied:rate_limit:{rl}", False)
        return rl

    target_str = str(args.get("path") or args.get("exe") or "")
    target = safe_path(target_str) if target_str else None
    if target_str and target is None:
        audit(action, target_str, "denied:bad_path", False)
        return f"Refused: '{target_str}' is outside your allowed folders."

    if is_destructive:
        msg = f"About to {action} '{target or target_str}'. Confirm?"
        if not confirm_callback or not confirm_callback(msg):
            audit(action, target_str, "denied:user_cancelled", False)
            return "Cancelled."

    _record(is_destructive)

    # --- the vetted primitives -----------------------------------------
    try:
        if action == "list_dir":
            if not target or not target.is_dir():
                return f"Not a directory: {target_str}"
            items = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
            lines = [("📁 " if p.is_dir() else "📄 ") + p.name for p in items[:200]]
            audit(action, str(target), "ok", False)
            return "\n".join(lines) if lines else "(empty)"

        if action == "open_file":
            if not target or not target.exists():
                return f"File not found: {target_str}"
            if target.is_dir() and sys.platform == "win32":
                subprocess.Popen(["explorer", str(target)], shell=False)
            else:
                os.startfile(str(target))
            audit(action, str(target), "ok", False)
            return f"Opened {target.name}"

        if action == "read_file_summary":
            if not target or not target.is_file():
                return f"Not a file: {target_str}"
            if target.stat().st_size > 1_000_000:
                return f"File too big to summarise ({target.stat().st_size} bytes)."
            data = target.read_text(encoding="utf-8", errors="replace")[:8000]
            audit(action, str(target), "ok", False)
            return data

        if action == "search_file":
            root = target or Path.home()
            query = str(args.get("query") or "").strip().lower()
            if not query:
                return "Provide a query."
            hits = []
            for p in root.rglob("*"):
                if query in p.name.lower():
                    hits.append(str(p))
                if len(hits) >= 50:
                    break
            audit(action, str(root), "ok", False, {"query": query})
            return "\n".join(hits) if hits else f"No matches for '{query}'."

        if action == "create_folder":
            target.mkdir(parents=True, exist_ok=True)
            audit(action, str(target), "ok", True)
            return f"Created {target.name}"

        if action == "move_file":
            dst_str = str(args.get("destination") or "")
            dst = safe_path(dst_str)
            if dst is None:
                return f"Refused: destination '{dst_str}' is outside allowed folders."
            shutil.move(str(target), str(dst))
            audit(action, str(target), "ok", True, {"dst": str(dst)})
            return f"Moved to {dst}"

        if action == "rename_file":
            new_name = re.sub(r"[^\w.\- ]", "_", str(args.get("new_name") or ""))[:200]
            if not new_name:
                return "Provide new_name."
            dst = target.with_name(new_name)
            target.rename(dst)
            audit(action, str(target), "ok", True, {"dst": str(dst)})
            return f"Renamed to {dst.name}"

        if action == "delete_file":
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            audit(action, str(target), "ok", True)
            return f"Deleted {target.name}"

        if action == "run_app":
            if not target or not target.is_file():
                return f"Executable not found: {target_str}"
            subprocess.Popen([str(target)])  # list form, no shell
            audit(action, str(target), "ok", False)
            return f"Launched {target.name}"

        if action == "system_info":
            info = {
                "os": platform.platform(),
                "python": sys.version.split()[0],
                "machine": platform.machine(),
                "node": platform.node(),
            }
            audit(action, "<system>", "ok", False)
            return json.dumps(info, indent=2)

        if action == "disk_usage":
            usage = shutil.disk_usage(str(Path.home()))
            return (
                f"Free: {usage.free // (1024**3)} GB\n"
                f"Total: {usage.total // (1024**3)} GB\n"
                f"Used: {usage.used // (1024**3)} GB"
            )

        if action == "empty_recycle_bin":
            # platform-specific; not implemented here for brevity
            return "Empty recycle bin: not yet implemented on this OS."

    except FileNotFoundError as e:
        audit(action, str(target), f"error:not_found", is_destructive, {"err": type(e).__name__})
        return f"Not found: {e.filename}"
    except PermissionError as e:
        audit(action, str(target), f"error:permission", is_destructive, {"err": type(e).__name__})
        return "Permission denied."
    except Exception as e:
        log.exception("agent action %s failed", action)
        audit(action, str(target), f"error:{type(e).__name__}", is_destructive)
        return f"Error: {type(e).__name__}"

    return f"Action '{action}' is recognised but not implemented in this build."


# ---------------------------------------------------------------------------
# 7. Self-test (run with `python agent.py`)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(safe_path("~/Documents"))                  # should print a Path
    print(safe_path("C:/Windows/System32"))          # should print None
    print(safe_path("../../etc/passwd"))             # should print None
    print(safe_path("\x00evil"))                     # should print None
    print(handle({"action": "system_info", "args": {}, "confidence": 1.0}))
