"""Hermetic tests for secure_store.py - encrypted JSON at rest."""
import json

import pytest

import secure_store


@pytest.fixture(autouse=True)
def isolated_key_dir(monkeypatch, tmp_path):
    """Point APPDATA/XDG dirs at a temp folder so real keys are untouched."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    yield


def _roundtrip(tmp_path, data):
    path = tmp_path / "data.json"
    secure_store.save_json_encrypted(str(path), data)
    assert secure_store.is_encrypted(str(path))
    assert secure_store.load_json_encrypted(str(path)) == data
    return path


@pytest.mark.skipif(not secure_store._CRYPTO_OK, reason="cryptography missing")
def test_roundtrip_nested_data(tmp_path):
    data = {"name": "Dhruv", "facts": {"dream": "Merchant Navy"}, "n": [1, 2]}
    _roundtrip(tmp_path, data)


@pytest.mark.skipif(not secure_store._CRYPTO_OK, reason="cryptography missing")
def test_file_on_disk_is_not_plaintext_json(tmp_path):
    path = _roundtrip(tmp_path, {"secret": "birthday 12 may"})
    raw = path.read_bytes()
    assert b"birthday" not in raw
    assert raw.startswith(secure_store.MAGIC_PREFIX)


@pytest.mark.skipif(not secure_store._CRYPTO_OK, reason="cryptography missing")
def test_wrong_key_raises_secure_store_error(tmp_path):
    path = _roundtrip(tmp_path, {"a": 1})
    # simulate a different machine/user by replacing the key
    from cryptography.fernet import Fernet
    secure_store.key_file().write_bytes(Fernet.generate_key())
    with pytest.raises(secure_store.SecureStoreError):
        secure_store.load_json_encrypted(str(path))


@pytest.mark.skipif(not secure_store._CRYPTO_OK, reason="cryptography missing")
def test_migrate_plaintext_in_place(tmp_path):
    path = tmp_path / "memory.json"
    path.write_text(json.dumps({"name": "Dhruv"}), encoding="utf-8")

    status = secure_store.migrate_plaintext(str(path))
    assert status == "migrated"
    assert secure_store.is_encrypted(str(path))
    assert not (tmp_path / "memory.json.bak").exists()   # verified & removed
    assert secure_store.load_json_encrypted(str(path)) == {"name": "Dhruv"}


def test_migrate_is_noop_when_already_encrypted(tmp_path):
    path = _roundtrip(tmp_path, {"x": 1}) if secure_store._CRYPTO_OK else None
    if path is None:
        pytest.skip("cryptography missing")
    assert secure_store.migrate_plaintext(str(path)) == "already-encrypted"


def test_migrate_missing_file(tmp_path):
    assert secure_store.migrate_plaintext(str(tmp_path / "nope.json")) == "missing"


@pytest.mark.skipif(not secure_store._CRYPTO_OK, reason="cryptography missing")
def test_load_default_when_missing(tmp_path):
    assert secure_store.load_json_encrypted(
        str(tmp_path / "ghost.json"), default={}) == {}