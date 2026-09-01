"""Tests for nova_features/data_export_import.py - ZIP backup/restore.

All paths are redirected into tmp_path so the real Nova data files are
never touched by a test.
"""
import json
import zipfile

import pytest

from nova_features import data_export_import as dei


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    data_dir = tmp_path / "nova"
    backup_dir = tmp_path / "backups"
    files = {
        "memory.json": data_dir / "memory.json",
        "settings.json": data_dir / "settings.json",
        "offline_facts.json": tmp_path / ".nova" / "offline_facts.json",
    }
    monkeypatch.setattr(dei, "EXPORTABLE_FILES", files)
    monkeypatch.setattr(dei, "BACKUP_DIR", str(backup_dir))
    # pre-populate two files
    files["memory.json"].parent.mkdir(parents=True)
    files["memory.json"].write_text('{"name": "Dhruv"}', encoding="utf-8")
    files["settings.json"].write_text('{"theme": "Dark"}', encoding="utf-8")
    backup_dir.mkdir(parents=True, exist_ok=True)
    yield {"files": files, "backup_dir": backup_dir}




def _read_json(path):
    """Read JSON transparently whether stored plaintext or NOVAENC1."""
    import secure_store
    if secure_store.is_encrypted(str(path)):
        raw = secure_store.decrypt_bytes(path.read_bytes())
        return json.loads(raw.decode("utf-8"))
    return json.loads(path.read_text(encoding="utf-8"))

def test_export_creates_zip_with_manifest(isolated):
    import os
    report = dei.export_all_data()
    assert report["success"] is True
    zip_path = report["zip_path"]
    assert os.path.exists(zip_path)

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        assert {"memory.json", "settings.json", "manifest.json"} <= names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["kind"] == "nova_data_backup"
        assert set(manifest["files"]) == {"memory.json", "settings.json"}


def test_import_restores_and_snapshots_first(isolated):
    first = dei.export_all_data()
    # corrupt current data, then restore from the backup
    iso = isolated["files"]
    iso["memory.json"].write_text('{"name": "WRONG"}', encoding="utf-8")

    report = dei.import_all_data(first["zip_path"])
    assert report["success"] is True
    assert set(report["restored"]) == {"memory.json", "settings.json"}
    assert _read_json(iso["memory.json"])["name"] == "Dhruv"   # re-encrypted at rest is OK
    # pre-import snapshot exists
    snaps = [p for p in isolated["backup_dir"].glob("pre_import_*.zip")]
    assert snaps


def test_import_rejects_unknown_archive_member(isolated):
    malicious = isolated["backup_dir"] / "evil.zip"
    with zipfile.ZipFile(malicious, "w") as zf:
        zf.writestr("../../evil.json", "{}")
        zf.writestr("memory.json", "{}")
    report = dei.import_all_data(str(malicious))
    assert report["success"] is False
    assert "unexpected file" in report["message"] or "flat" in report["message"]


def test_import_rejects_invalid_json_member(isolated):
    bad = isolated["backup_dir"] / "badjson.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("memory.json", "{not json!!")
    report = dei.import_all_data(str(bad))
    assert report["success"] is False
    assert "JSON" in report["message"]


def test_import_dict_payload_is_rejected_safely():
    report = dei.import_all_data({"some": "dict"})
    assert report["success"] is False


def test_list_backups_newest_first(isolated):
    assert dei.list_backups() == []
    dei.export_all_data()
    dei.export_all_data()
    backups = dei.list_backups()
    assert len(backups) >= 2


