# ==========================================
# NOVA SECURE STORE - encrypted JSON at rest
# ------------------------------------------
# memory.json holds personal facts (name, birthday, dreams) and chat
# summaries; it currently sits in plaintext next to OneDrive sync.
# This module adds Fernet symmetric encryption:
#
#   * Key lives in %APPDATA%/Nova/secret.key, auto-created on first use,
#     OUTSIDE the synced project folder and outside any backup zip.
#   * Encrypted files carry a "NOVAENC1:" prefix so they are easy to
#     identify and impossible to confuse with plaintext JSON.
#   * migrate_plaintext() upgrades an existing plaintext file in place,
#     keeping a .bak until the encrypted copy verifies.
#
# If the cryptography package is somehow missing, every function
# degrades gracefully (plaintext passthrough + warning) so Nova never
# crashes over security plumbing.
# ==========================================

import base64
import json
import logging
import os
from pathlib import Path

log = logging.getLogger("nova.secure_store")

__version__ = "1.0.0"

MAGIC_PREFIX = b"NOVAENC1:"

try:
    from cryptography.fernet import Fernet, InvalidToken
    _CRYPTO_OK = True
except ImportError:      # pragma: no cover - depends on env
    Fernet = None
    InvalidToken = Exception
    _CRYPTO_OK = False
    log.warning("cryptography package missing - secure_store disabled")


class SecureStoreError(Exception):
    """Raised when decryption fails (wrong key / corrupted file)."""


def key_directory():
    """Stable per-user key folder (mirrors agent._user_data_dir)."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif os.name == "posix" and os.sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / "Nova"
    d.mkdir(parents=True, exist_ok=True)
    return d


def key_file():
    return key_directory() / "secret.key"


def load_or_create_key():
    """Return the Fernet key bytes, creating one on first run."""
    if not _CRYPTO_OK:
        return None
    kf = key_file()
    try:
        if kf.exists():
            key = kf.read_bytes().strip()
            if key:
                return key
        key = Fernet.generate_key()
        # restrict to current user on Windows (best-effort; POSIX chmod below)
        kf.write_bytes(key)
        try:
            os.chmod(kf, 0o600)
        except OSError:
            pass
        return key
    except Exception as exc:
        log.error("key handling failed: %s", exc)
        return None


def _fernet():
    key = load_or_create_key()
    if not key:
        return None
    try:
        return Fernet(key)
    except Exception:
        return None


def is_encrypted(path):
    """True when *path* starts with the NOVAENC1 magic prefix."""
    try:
        with open(path, "rb") as f:
            return f.read(len(MAGIC_PREFIX)) == MAGIC_PREFIX
    except OSError:
        return False


def encrypt_bytes(raw: bytes) -> bytes:
    f = _fernet()
    if f is None:
        return raw          # graceful degradation: plaintext passthrough
    token = f.encrypt(bytes(raw))
    return MAGIC_PREFIX + token


def decrypt_bytes(blob: bytes) -> bytes:
    if not blob.startswith(MAGIC_PREFIX):
        return blob         # legacy plaintext file
    f = _fernet()
    if f is None:
        raise SecureStoreError("encrypted file but no crypto backend")
    token = blob[len(MAGIC_PREFIX):]
    try:
        return f.decrypt(token)
    except InvalidToken as exc:
        raise SecureStoreError(
            "decryption failed (wrong/corrupt secret.key?)") from exc


def save_json_encrypted(path, data):
    """Serialize *data* as JSON and write it encrypted."""
    raw = json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")
    out = encrypt_bytes(raw)
    with open(path, "wb") as f:
        f.write(out)


def load_json_encrypted(path, default=None):
    """Read a JSON file regardless of whether it's encrypted.

    Returns *default* when the file doesn't exist.
    Raises SecureStoreError only when an encrypted payload can't be
    decrypted - callers decide their own fallback policy.
    """
    if not os.path.exists(path):
        return default
    with open(path, "rb") as f:
        blob = f.read()
    raw = decrypt_bytes(blob)
    return json.loads(raw.decode("utf-8"))


def migrate_plaintext(path):
    """Encrypt an existing plaintext JSON file in place.

    Keeps <path>.bak until the new file round-trips; returns status str.
    Safe to call repeatedly (no-op when already encrypted).
    """
    if is_encrypted(path):
        return "already-encrypted"
    if not os.path.exists(path):
        return "missing"

    with open(path, "rb") as f:
        raw = f.read()
    try:
        json.loads(raw.decode("utf-8"))     # sanity: must be valid JSON
    except Exception as exc:
        return f"not-valid-json ({type(exc).__name__})"

    bak = f"{path}.bak"
    try:
        with open(bak, "wb") as f:
            f.write(raw)
        save_json_encrypted(path, json.loads(raw.decode("utf-8")))
        # verify before removing backup
        load_json_encrypted(path)
        os.remove(bak)
        return "migrated"
    except Exception as exc:
        log.error("migration of %s failed: %s", path, exc)
        return f"failed ({type(exc).__name__})"


__all__ = ["SecureStoreError", "is_encrypted", "encrypt_bytes",
           "decrypt_bytes", "save_json_encrypted", "load_json_encrypted",
           "migrate_plaintext", "load_or_create_key", "key_file"]