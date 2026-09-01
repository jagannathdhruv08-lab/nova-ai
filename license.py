import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path


# ==========================================
# NOVA LICENSE SYSTEM
# ==========================================
#
# How to use later:
#   1. Make your own license key, for example:
#        NOVA-2026-DHRUV-1234
#
#   2. Run this command to get its hash:
#        .\venv\Scripts\python.exe license.py hash NOVA-2026-DHRUV-1234
#
#   3. Copy the printed hash into VALID_LICENSE_HASHES below.
#
#   4. In your app startup, call:
#        from license import is_license_valid
#        if not is_license_valid():
#            print("License required")
#
# This file stores the activated key hash in license.json.
# It does not need internet.
# ==========================================


APP_NAME = "Nova AI"
LICENSE_FILE = Path(__file__).with_name("license.json")

# Put your real license key hashes here later.
# Do not put public keys here if you want to keep them private.
# the key is "NOVA-2026"
VALID_LICENSE_HASHES = {"470a8d0da1490e499629edd9dcd000a2dab89232fdadb1a1083a475849027fc0"}
    # Example:
    # "paste_your_license_hash_here",


# Optional: while developing, you can set this in .env or Windows environment:
# NOVA_LICENSE_KEYS=NOVA-KEY-1,NOVA-KEY-2
ENV_LICENSE_KEYS = "ENV_LICENSE_KEYS" 


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def normalize_key(key):
    """Clean user input so spaces and casing do not break activation."""
    return str(key).strip().upper().replace(" ", "")


def hash_key(key):
    """Return the SHA-256 hash for a license key."""
    normalized = normalize_key(key)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _env_license_hashes():
    keys = os.getenv(ENV_LICENSE_KEYS, "")
    return {
        hash_key(key)
        for key in keys.split(",")
        if key.strip()
    }


def _valid_hashes():
    return set(VALID_LICENSE_HASHES) | _env_license_hashes()


def _read_license_file():
    if not LICENSE_FILE.exists():
        return {}

    try:
        with open(LICENSE_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_license_file(data):
    with open(LICENSE_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)


def is_key_valid(key):
    """Check a raw license key against the configured allowed keys."""
    key_hash = hash_key(key)
    return any(
        hmac.compare_digest(key_hash, valid_hash)
        for valid_hash in _valid_hashes()
    )


def activate_license(key, owner=""):
    """
    Save a valid license key to license.json.

    Returns:
        (True, "message") if activation succeeds.
        (False, "message") if the key is invalid.
    """
    if not is_key_valid(key):
        return False, "Invalid license key."

    data = {
        "app": APP_NAME,
        "owner": owner.strip(),
        "license_hash": hash_key(key),
        "activated_at": _now_iso(),
    }
    _write_license_file(data)
    return True, "License activated successfully."


def is_license_valid():
    """Check whether license.json contains an activated valid license."""
    data = _read_license_file()
    saved_hash = data.get("license_hash", "")

    if not saved_hash:
        return False

    return any(
        hmac.compare_digest(saved_hash, valid_hash)
        for valid_hash in _valid_hashes()
    )


def get_license_status():
    """Return readable license status for GUI or console output."""
    data = _read_license_file()

    if is_license_valid():
        owner = data.get("owner") or "Unknown owner"
        activated_at = data.get("activated_at") or "unknown time"
        return f"Licensed to {owner}. Activated at {activated_at}."

    if not _valid_hashes():
        return "No valid license hashes are configured yet."

    return "License not activated."


def clear_license():
    """Remove local activation from license.json."""
    if LICENSE_FILE.exists():
        LICENSE_FILE.unlink()
    return "License cleared."


def require_license():
    """
    Use this at app startup if you want to block unlicensed access.

    Raises:
        RuntimeError if license is missing or invalid.
    """
    if not is_license_valid():
        raise RuntimeError("Nova AI license is missing or invalid.")


def _print_usage():
    print("Nova AI License Tool")
    print("")
    print("Commands:")
    print("  license.py hash <key>")
    print("  license.py activate <key> [owner]")
    print("  license.py status")
    print("  license.py clear")


def main(argv=None):
    argv = list(argv or os.sys.argv[1:])

    if not argv:
        _print_usage()
        return

    command = argv[0].lower()

    if command == "hash" and len(argv) >= 2:
        print(hash_key(argv[1]))
        return

    if command == "activate" and len(argv) >= 2:
        owner = " ".join(argv[2:]) if len(argv) > 2 else ""
        success, message = activate_license(argv[1], owner=owner)
        print(message)
        raise SystemExit(0 if success else 1)

    if command == "status":
        print(get_license_status())
        return

    if command == "clear":
        print(clear_license())
        return

    _print_usage()
    raise SystemExit(1)


if __name__ == "__main__":
    main()
