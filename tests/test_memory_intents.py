"""Tests for memory.py conversation turns + summarization, and the
nova_intents router. Everything hermetic (tmp files, fake brain)."""
import json

import pytest

import memory
import nova_intents


# ===========================================================================
# conversation memory
# ===========================================================================
@pytest.fixture(autouse=True)
def isolated_memory(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "MEMORY_FILE", str(tmp_path / "memory.json"))
    monkeypatch.setattr(memory, "_MEMORY_MIGRATION_DONE", True)
    # start each test from an empty store
    with open(tmp_path / "memory.json", "w", encoding="utf-8") as f:
        json.dump({}, f)
    yield


def test_remember_turn_stores_and_trims():
    for i in range(10):
        memory.remember_turn(f"question {i}", f"answer {i}", max_turns=5)
    turns = memory.get_recent_turns(50)
    assert len(turns) == 5                      # trimmed to max_turns
    assert turns[-1]["u"] == "question 9"
    assert turns[0]["u"] == "question 5"


def test_internal_keys_hidden_from_user_facts():
    memory.remember_turn("hi", "hello")
    memory.remember("name", "Dhruv")
    facts = memory.get_saved_facts()
    assert facts == {"name": "Dhruv"}           # _conversation filtered


def test_conversation_context_block_contents():
    memory.remember_turn("my exam is on monday", "all the best!")
    block = memory.conversation_context_block()
    assert "Recent conversation context" in block
    assert "exam is on monday" in block


def test_context_block_empty_when_no_history():
    assert memory.conversation_context_block() == ""


def test_summarize_uses_llm_and_compacts(monkeypatch):
    class FakeBrain:
        @staticmethod
        def llm_chat(messages, max_tokens=300, temperature=0.2):
            return ("User is preparing for IMU CET; likes physics.", "Groq")

    for i in range(memory._SUMMARY_TRIGGER):
        memory.remember_turn(f"q{i}", f"a{i}")
    assert memory.summarize_conversation(brain_module=FakeBrain) is True

    summary = memory.get_conversation_summary()
    assert "IMU CET" in summary
    # older half was compressed away
    assert len(memory.get_recent_turns(100)) <= memory._SUMMARY_TRIGGER // 2 + 1


def test_summarize_offline_fallback_still_bounds_memory(monkeypatch):
    class DeadBrain:
        @staticmethod
        def llm_chat(messages, **kw):
            return None, "no providers"

    for i in range(memory._SUMMARY_TRIGGER):
        memory.remember_turn(f"topic number {i} about ships", f"a{i}")
    assert memory.summarize_conversation(brain_module=DeadBrain) is True
    summary = memory.get_conversation_summary()
    assert summary                              # crude digest exists
    assert "ships" in summary.lower()


# ===========================================================================
# intent router
# ===========================================================================
class _RouterBrain:
    """Stands in for brain inside route_intent via monkeypatched llm_json."""
    def __init__(self, decision):
        self._decision = decision

    def llm_json(self, system_prompt, user_prompt, **kw):
        self.last_user = user_prompt
        return self._decision


@pytest.fixture(autouse=True)
def isolated_feature_files(tmp_path, monkeypatch):
    import nova_features.smart_reminder as sr
    if hasattr(sr, "REMINDER_FILE"):
        monkeypatch.setattr(sr, "REMINDER_FILE",
                            str(tmp_path / "reminders.json"))
    yield


def test_route_intent_dispatches_reminder(monkeypatch):
    import types
    import builtins
    real_import = builtins.__import__
    fake_brain = _RouterBrain({
        "action": "set_reminder",
        "args": {"task": "study maths", "time": "18:30"},
    })

    def fake_import(name, *args, **kwargs):
        if name == "brain":
            mod = types.ModuleType("brain")
            mod.llm_json = fake_brain.llm_json
            return mod
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = nova_intents.route_intent("remind me to study maths at 6:30pm")
    assert result is not None
    assert "study maths" in result


def test_route_intent_returns_none_for_chat(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "brain":
            import types
            mod = types.ModuleType("brain")
            mod.llm_json = lambda s, u, **k: {"action": "chat"}
            return mod
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert nova_intents.route_intent("remind me of something", force=True) is None


def test_route_intent_rejects_unknown_action(monkeypatch):
    import types
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "brain":
            mod = types.ModuleType("brain")
            mod.llm_json = lambda s, u, **k: {"action": "format_c_drive"}
            return mod
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    # unknown action -> handler lookup fails -> None (never executed)
    assert nova_intents.route_intent("remind me please", force=True) is None


def test_pre_gate_blocks_plain_questions():
    assert nova_intents.route_intent("what is merchant navy?") is None


def test_pre_gate_allows_action_words():
    assert nova_intents._looks_like_action("remind me to drink water")
    assert not nova_intents._looks_like_action("who wrote hamlet")


def test_arg_clamping():
    assert nova_intents._clamp_minutes(9999) == 180
    assert nova_intents._clamp_minutes("abc") == 25
    assert nova_intents._clamp_count(1) == 3