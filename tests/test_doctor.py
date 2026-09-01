"""Tests for nova_doctor.py - the self-diagnostic health check.

All tests are hermetic: the environment, data files, network and mic
checks are monkeypatched or pointed at tmp_path. Nothing here touches
the real .env, the real network or the microphone.
"""
import json

import pytest

import nova_doctor as nd


def _write_env(tmp_path, lines):
    path = tmp_path / ".env"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# env keys
# ---------------------------------------------------------------------------

def test_env_check_missing_file_warns(tmp_path, monkeypatch):
    monkeypatch.setattr(nd, "ENV_PATH", str(tmp_path / "missing.env"))
    res = nd._env_keys_check()
    assert res["status"] == "warn"
    assert "not found" in res["detail"]


def test_env_check_reports_missing_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(
        nd, "ENV_PATH", _write_env(tmp_path, ["GROQ_API_KEY=abc123"])
    )
    res = nd._env_keys_check()
    assert res["status"] == "warn"
    assert "GROQ_API_KEY" in res["detail"]
    assert "GEMINI_API_KEY" in res["detail"]  # listed as missing


def test_env_check_all_keys_ok(tmp_path, monkeypatch):
    lines = [f"{key}=secretvalue123" for key in nd.KNOWN_API_KEYS]
    monkeypatch.setattr(nd, "ENV_PATH", _write_env(tmp_path, lines))
    res = nd._env_keys_check()
    assert res["status"] == "ok"
    # secret VALUES must never leak into the report
    assert "secretvalue123" not in res["detail"]


def test_env_check_empty_file_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(
        nd, "ENV_PATH", _write_env(tmp_path, ["# only a comment"])
    )
    assert nd._env_keys_check()["status"] == "fail"


# ---------------------------------------------------------------------------
# data files
# ---------------------------------------------------------------------------

def test_data_files_detect_corrupt_json(tmp_path, monkeypatch):
    bad = tmp_path / "memory.json"
    bad.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(nd, "_data_file_paths", lambda: [str(bad)])
    res = nd._data_files_check()
    assert res["status"] == "fail"
    assert "memory.json" in res["detail"]


def test_data_files_missing_is_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(
        nd, "_data_file_paths", lambda: [str(tmp_path / "nope.json")]
    )
    res = nd._data_files_check()
    assert res["status"] == "ok"
    assert "0/10" in res["detail"]


def test_data_files_valid_json_ok(tmp_path, monkeypatch):
    good = tmp_path / "srs.json"
    good.write_text(json.dumps({"cards": []}), encoding="utf-8")
    monkeypatch.setattr(nd, "_data_file_paths", lambda: [str(good)])
    assert nd._data_files_check()["status"] == "ok"

def test_load_json_lenient_plaintext(tmp_path):
    good = tmp_path / "plain.json"
    good.write_text('{"a": 1}', encoding="utf-8")
    assert nd._load_json_lenient(str(good)) == {"a": 1}


def test_load_json_lenient_garbage_returns_none(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{oops not json", encoding="utf-8")
    assert nd._load_json_lenient(str(bad)) is None


def test_load_json_lenient_secure_store_encrypted(tmp_path, monkeypatch):
    """memory.json-style NOVAENC1 files must pass the health check."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    import secure_store
    data = {"name": "Dhruv", "facts": {"dream": "Merchant Navy"}, "n": [1, 2]}
    path = tmp_path / "memory.json"
    secure_store.save_json_encrypted(str(path), data)
    assert secure_store.is_encrypted(str(path))
    assert nd._load_json_lenient(str(path)) == data


def test_data_files_encrypted_file_is_ok(tmp_path, monkeypatch):
    """Regression: doctor must NOT flag encrypted-at-rest data as corrupt."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    import secure_store
    enc = tmp_path / "memory.json"
    secure_store.save_json_encrypted(str(enc), {"remembered": True})
    monkeypatch.setattr(nd, "_data_file_paths", lambda: [str(enc)])
    res = nd._data_files_check()
    assert res["status"] == "ok"


def test_required_packages_use_import_names():
    """find_spec() probes IMPORT names, not PyPI names. Regression for
    the SpeechRecognition false-negative (module is speech_recognition)."""
    assert "speech_recognition" in nd.REQUIRED_PACKAGES
    assert "SpeechRecognition" not in nd.REQUIRED_PACKAGES


# ---------------------------------------------------------------------------
# report assembly / schema
# ---------------------------------------------------------------------------

def _stub_ok(name):
    return {"name": name, "status": "ok", "detail": "stub"}


_ALL_CHECKS = (
    "_python_check", "_env_keys_check", "_imports_check", "_ocr_check",
    "_internet_check", "_data_files_check", "_write_access_check",
    "_git_check",
)


def _stub_all_checks(monkeypatch, override=None):
    for name in _ALL_CHECKS:
        if override and name in override:
            monkeypatch.setattr(nd, name, override[name])
        else:
            monkeypatch.setattr(
                nd, name,
                (lambda n: lambda: _stub_ok(n.lstrip("_")))(name),
            )


def test_run_doctor_schema_with_stubbed_checks(monkeypatch):
    _stub_all_checks(monkeypatch)
    results = nd.run_doctor(include_mic=False)
    assert len(results) == 8
    assert all(r["status"] in nd.VALID_STATUSES for r in results)
    assert all(set(r) == {"name", "status", "detail"} for r in results)


def test_run_doctor_never_raises_on_crashing_check(monkeypatch):
    def boom():
        raise RuntimeError("kaboom")

    _stub_all_checks(monkeypatch, override={"_python_check": boom})
    results = nd.run_doctor(include_mic=False)
    assert results[0]["status"] == "fail"
    assert "RuntimeError" in results[0]["detail"]


def test_invalid_status_coerced_to_fail(monkeypatch):
    def weird():
        return {"name": "P", "status": "weird", "detail": ""}

    _stub_all_checks(monkeypatch, override={"_python_check": weird})
    results = nd.run_doctor(include_mic=False)
    assert results[0]["status"] == "fail"


def test_format_report_and_summary():
    results = [
        {"name": "Alpha Check", "status": "ok", "detail": "fine"},
        {"name": "B", "status": "warn", "detail": "meh"},
        {"name": "C", "status": "fail", "detail": "bad"},
    ]
    report = nd.format_report(results)
    assert "[ OK ]" in report and "[WARN]" in report and "[FAIL]" in report
    assert "1 ok, 1 warn, 1 fail" in report
    assert "needs attention" in report
    assert "Alpha Check" in report


def test_format_report_all_clear_verdict():
    results = [{"name": "A", "status": "ok", "detail": ""}]
    assert "all clear" in nd.format_report(results)


def test_summarize_counts():
    counts = nd.summarize([
        {"name": "a", "status": "ok", "detail": ""},
        {"name": "b", "status": "ok", "detail": ""},
        {"name": "c", "status": "warn", "detail": ""},
    ])
    assert counts["ok"] == 2 and counts["warn"] == 1 and counts["fail"] == 0


def test_handle_doctor_command_returns_string(monkeypatch):
    monkeypatch.setattr(
        nd, "run_doctor", lambda include_mic=True: [_stub_ok("X")]
    )
    out = nd.handle_doctor_command("doctor")
    assert isinstance(out, str)
    assert "Nova Doctor" in out


# ---------------------------------------------------------------------------
# gui helpers carve-out (nova_gui_helpers.py)
# ---------------------------------------------------------------------------

from nova_gui_helpers import (  # noqa: E402
    completion_text, is_supported_image, read_file_preview,
)


def test_completion_text_counts():
    assert completion_text([]) == "0/0"
    assert completion_text([{"done": True}, {"done": False}]) == "1/2"
    assert completion_text([{"done": True}, {"done": True}]) == "2/2"


def test_is_supported_image_extensions():
    assert is_supported_image("photo.PNG")
    assert is_supported_image("shot.jpeg")
    assert not is_supported_image("doc.pdf")
    assert not is_supported_image("noext")


def test_read_file_preview_text(tmp_path):
    file = tmp_path / "note.txt"
    file.write_text("hello nova", encoding="utf-8")
    text, err = read_file_preview(str(file))
    assert err is None and text == "hello nova"


def test_read_file_preview_caps_length(tmp_path):
    file = tmp_path / "big.txt"
    file.write_text("x" * 9000, encoding="utf-8")
    text, err = read_file_preview(str(file), max_chars=100)
    assert err is None and len(text) == 100


def test_read_file_preview_missing_file_errors(tmp_path):
    text, err = read_file_preview(str(tmp_path / "ghost.txt"))
    assert text is None and err


def test_read_file_preview_pdf_without_pypdf(tmp_path, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def no_pypdf(name, *args, **kwargs):
        if name.split(".")[0] in ("pypdf", "PyPDF2"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_pypdf)
    fake = tmp_path / "doc.pdf"
    fake.write_bytes(b"%PDF-1.4 fake")
    text, err = read_file_preview(str(fake))
    assert text is None
    assert "pypdf" in err


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

