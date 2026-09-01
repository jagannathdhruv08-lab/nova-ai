# ==========================================
# NOVA FEATURES - DATA EXPORT / IMPORT (real implementation)
# ------------------------------------------
# One-click ZIP backup of every Nova data file (memory, dashboard,
# knowledge base, chat history, settings, coach, nutrition, offline
# facts) and a validated restore that can never overwrite your data
# with a corrupt or malicious archive.
#
# Safety rules (mirroring agent.py's design philosophy):
#   1. Only KNOWN filenames are accepted from an archive - a zip can
#      never drop arbitrary files anywhere on disk.
#   2. Every member is size-capped and must parse as valid UTF-8 JSON
#      BEFORE anything is overwritten.
#   3. The current data is backed up to backups/pre_import_<ts>.zip
#      first, so a bad import is always reversible.
#   4. All writes go through nova_storage.writable_data_path() so the
#      packaged .exe reads/writes the same stable folder.
# ==========================================

import json
import os
import shutil
import tempfile
import time
import zipfile

from nova_storage import writable_data_path

__version__ = "2.0.0"

# Every Nova-owned data file, by archive name -> absolute path.
# Archive names are flat (no folders) and are the ONLY entries an
# import archive may contain.
EXPORTABLE_FILES = {
    "memory.json": writable_data_path("memory.json"),
    "nova_dashboard_data.json": writable_data_path("nova_dashboard_data.json"),
    "nova_knowledge.json": writable_data_path("nova_knowledge.json"),
    "history.json": writable_data_path("history.json"),
    "settings.json": writable_data_path("settings.json"),
    "nova_coach_data.json": writable_data_path("nova_coach_data.json"),
    "nova_nutrition_data.json": writable_data_path("nova_nutrition_data.json"),
}

OFFLINE_FACTS_FILE = os.path.join(os.path.expanduser("~"), ".nova", "offline_facts.json")
EXPORTABLE_FILES["offline_facts.json"] = OFFLINE_FACTS_FILE

BACKUP_DIR = writable_data_path("backups")

MAX_MEMBER_BYTES = 64 * 1024 * 1024   # 64 MB per file - generous, catches abuse
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024

# Files that may be encrypted-at-rest on this machine. Backups must stay
# PORTABLE (restorable on a fresh machine), so they always store decrypted
# JSON; the local encrypted copy is re-encrypted after an import.
_ENCRYPTABLE = {"memory.json"}


def _read_for_backup(path):
    """Bytes for the zip: decrypt transparently when secure-encrypted."""
    try:
        import secure_store
        if secure_store.is_encrypted(path):
            with open(path, "rb") as f:
                return secure_store.decrypt_bytes(f.read())
    except Exception:
        pass
    with open(path, "rb") as f:
        return f.read()


def _ensure_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    return BACKUP_DIR


def _timestamp():
    return time.strftime("%Y%m%d_%H%M%S")


def _unique_path(prefix):
    """Collision-safe zip path (same-second exports get -1, -2 suffixes)."""
    base = f"{prefix}_{_timestamp()}"
    candidate = os.path.join(BACKUP_DIR, base + ".zip")
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(BACKUP_DIR, f"{base}-{counter}.zip")
        counter += 1
    return candidate


def export_all_data():
    """Zip every existing Nova data file into backups/nova_backup_<ts>.zip.

    Returns a dict report; always succeeds unless the disk itself fails.
    """
    try:
        _ensure_backup_dir()
        zip_path = _unique_path("nova_backup")
        included = []
        skipped = []
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            sizes = {}
            for arcname, path in EXPORTABLE_FILES.items():
                if os.path.isfile(path):
                    # Flat arcname - never store folder components.
                    # Encrypted-at-rest files go in as portable plaintext.
                    payload = _read_for_backup(path)
                    zf.writestr(arcname, payload)
                    included.append(arcname)
                    sizes[arcname] = len(payload)
                else:
                    skipped.append(arcname)
            manifest = {
                "app": "Nova AI",
                "kind": "nova_data_backup",
                "version": 1,
                "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "files": included,
                "sizes": sizes,
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        size = os.path.getsize(zip_path)
        return {
            "success": True,
            "feature": "data_export_import",
            "action": "export",
            "zip_path": zip_path,
            "files_included": included,
            "files_skipped_missing": skipped,
            "size_bytes": size,
            "message": (
                f"✅ Backup saved: {os.path.basename(zip_path)} "
                f"({len(included)} files, {size // 1024} KB)"
            ),
        }
    except Exception as exc:
        return {
            "success": False,
            "feature": "data_export_import",
            "action": "export",
            "error": f"{type(exc).__name__}: {exc}",
            "message": f"❌ Export failed: {type(exc).__name__}",
        }


def list_backups():
    """Return newest-first list of backup zip paths in the backups folder."""
    if not os.path.isdir(BACKUP_DIR):
        return []
    zips = [
        os.path.join(BACKUP_DIR, n)
        for n in os.listdir(BACKUP_DIR)
        if n.endswith(".zip")
    ]
    return sorted(zips, key=os.path.getmtime, reverse=True)

def _validate_archive(zf):
    """Security + integrity gate for an import archive.

    Raises ValueError with a user-safe reason when the archive must be
    rejected. Returns the list of data-file arcnames it carries.
    """
    names = zf.namelist()

    # 1. Only flat, known filenames. Reject folders, traversal, unknowns.
    allowed = set(EXPORTABLE_FILES.keys()) | {"manifest.json"}
    for name in names:
        if name not in allowed:
            raise ValueError(f"unexpected file in archive: {name}")
        if os.path.isabs(name) or ".." in name or "\\" in name or "/" in name:
            raise ValueError("archive entries must be flat filenames")

    total = 0
    for info in zf.infolist():
        total += info.file_size
        if info.file_size > MAX_MEMBER_BYTES:
            raise ValueError(f"{info.filename} is too large")
    if total > MAX_ARCHIVE_BYTES:
        raise ValueError("archive is too large overall")

    # 2. Every data member must be valid UTF-8 JSON right now.
    for name in names:
        raw = zf.read(name)
        try:
            json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"{name} is not valid JSON ({type(exc).__name__})")

    data_names = [n for n in names if n != "manifest.json"]
    if not data_names:
        raise ValueError("archive contains no Nova data files")
    return data_names


def import_all_data(data):
    """Restore Nova data from a backup archive.

    *data* is normally a path to a zip produced by export_all_data().
    A dict payload is accepted for backward compatibility with the old
    stub API; in that case it is only echoed back (nothing is written),
    because restoring raw nested dicts safely requires per-file schemas.
    """
    if isinstance(data, dict):
        return {
            "success": False,
            "feature": "data_export_import",
            "action": "import",
            "message": (
                "Please pass a backup .zip path (from export_all_data) - "
                f"received dict keys: {list(data.keys())[:8]}"
            ),
        }

    zip_path = str(data)
    if not os.path.isfile(zip_path):
        return {
            "success": False,
            "feature": "data_export_import",
            "action": "import",
            "message": f"❌ Backup not found: {zip_path}",
        }
    if os.path.getsize(zip_path) > MAX_ARCHIVE_BYTES:
        return {
            "success": False,
            "feature": "data_export_import",
            "action": "import",
            "message": "❌ Backup archive is too large.",
        }

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            data_names = _validate_archive(zf)

            # 3. Safety net: snapshot current data before touching anything.
            _ensure_backup_dir()
            pre_zip = _unique_path("pre_import")
            with zipfile.ZipFile(pre_zip, "w", zipfile.ZIP_DEFLATED) as snap:
                for arcname, path in EXPORTABLE_FILES.items():
                    if os.path.isfile(path):
                        snap.write(path, arcname)

            # Extract to a temp dir, then copy validated files into place.
            restored = []
            with tempfile.TemporaryDirectory() as td:
                for name in data_names:
                    target = EXPORTABLE_FILES[name]
                    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
                    extracted = os.path.join(td, name)
                    with open(extracted, "wb") as out:
                        out.write(zf.read(name))
                    shutil.copyfile(extracted, target)
                    # Re-encrypt files that are encrypted-at-rest locally.
                    if name in _ENCRYPTABLE:
                        try:
                            import secure_store
                            secure_store.migrate_plaintext(target)
                        except Exception:
                            pass
                    restored.append(name)

        return {
            "success": True,
            "feature": "data_export_import",
            "action": "import",
            "restored": restored,
            "pre_import_snapshot": pre_zip,
            "message": (
                f"✅ Restored {len(restored)} file(s) from "
                f"{os.path.basename(zip_path)}. Restart Nova so every "
                "module reloads the restored data. Previous data was "
                f"saved to {os.path.basename(pre_zip)}."
            ),
        }
    except ValueError as exc:
        return {
            "success": False,
            "feature": "data_export_import",
            "action": "import",
            "message": f"❌ Rejected backup: {exc}",
        }
    except Exception as exc:
        return {
            "success": False,
            "feature": "data_export_import",
            "action": "import",
            "error": f"{type(exc).__name__}: {exc}",
            "message": f"❌ Import failed: {type(exc).__name__}",
        }


def format_result(report):
    """Human-readable block for popup windows."""
    if not isinstance(report, dict):
        return str(report)
    lines = [report.get("message", "")]
    if report.get("files_included"):
        lines.append("Included: " + ", ".join(report["files_included"]))
    if report.get("restored"):
        lines.append("Restored: " + ", ".join(report["restored"]))
    if report.get("zip_path"):
        lines.append(f"Location: {report['zip_path']}")
    return "\n".join(l for l in lines if l)


__all__ = [
    "export_all_data",
    "import_all_data",
    "list_backups",
    "format_result",
    "EXPORTABLE_FILES",
]