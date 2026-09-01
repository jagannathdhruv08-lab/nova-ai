"""Tests for nova_knowledge.py - Nova's personal knowledge base ("Train Nova").

Every test runs against an ISOLATED in-memory KB (the real
nova_knowledge.json on disk is snapshotted and restored, and _save() is
stubbed out) so running the tests can never wipe a user's trained data.
"""
import pytest

import nova_knowledge as nk


@pytest.fixture(autouse=True)
def isolated_kb(monkeypatch):
    """Empty in-memory KB per test; _save() becomes a no-op."""
    original = nk._KB
    nk._KB = {"sources": {}, "chunks": []}
    monkeypatch.setattr(nk, "_save", lambda: None)
    yield
    nk._KB = original


# ---------------------------------------------------------------------------
# tokenization / chunking
# ---------------------------------------------------------------------------
def test_tokenize_drops_stopwords_and_short_tokens():
    tokens = nk._tokenize("The Merchant Navy IS a great career!")
    assert "the" not in tokens
    assert "is" not in tokens
    assert "merchant" in tokens and "navy" in tokens


def test_chunk_text_splits_oversized_paragraphs():
    para = " ".join(f"Sentence {i} explains a physics concept." for i in range(80))
    chunks = nk._chunk_text(para)
    assert len(chunks) >= 2
    limit = nk.MAX_CHUNK_CHARS + nk.CHUNK_OVERLAP + 10
    assert all(len(c) <= limit for c in chunks)


def test_chunk_text_keeps_short_paragraph_whole():
    chunks = nk._chunk_text("Short note about ships.")
    assert chunks == ["Short note about ships."]


def test_chunk_text_handles_empty_input():
    assert nk._chunk_text("") == []
    assert nk._chunk_text(None) == []


# ---------------------------------------------------------------------------
# ingestion
# ---------------------------------------------------------------------------
def test_ingest_text_creates_chunks_and_stats():
    count = nk.ingest_text(
        "notes.txt", "Merchant Navy trains deck cadets in navigation and radar."
    )
    assert count >= 1
    stats = nk.knowledge_stats()
    assert stats["sources"] == 1
    assert stats["chunks"] == count


def test_ingest_text_rejects_blank_content():
    assert nk.ingest_text("empty.txt", "") == 0
    assert nk.ingest_text("spaces.txt", "   \n  ") == 0


def test_reingesting_same_source_replaces_old_chunks():
    nk.ingest_text("a.txt", "first version of the ship notes")
    first_count = len(nk._KB["chunks"])
    nk.ingest_text("a.txt", "second version of the ship notes")
    # replaced in place, not appended twice
    assert len(nk._KB["chunks"]) == first_count
    assert nk.knowledge_stats()["sources"] == 1


# ---------------------------------------------------------------------------
# retrieval
# ---------------------------------------------------------------------------
def test_search_ranks_relevant_source_first():
    nk.ingest_text(
        "navy.txt",
        "The Merchant Navy is a career in shipping. "
        "Deck cadets learn navigation, radar and ship handling.",
    )
    nk.ingest_text(
        "food.txt",
        "Paneer is rich in protein and calcium, good for strong bones.",
    )
    results = nk.search_knowledge("merchant navy deck cadet navigation", limit=2)
    assert results
    top_sim, top_chunk = results[0]
    assert top_chunk["source"] == "navy.txt"
    assert top_sim > 0


def test_search_returns_empty_for_unrelated_query():
    nk.ingest_text("navy.txt", "Merchant Navy ships sail across oceans.")
    assert nk.search_knowledge("quantum entanglement particle physics") == []


def test_knowledge_context_includes_source_and_text():
    nk.ingest_text(
        "navy.txt", "Deck cadets study celestial navigation while at sea."
    )
    ctx = nk.knowledge_context("celestial navigation at sea")
    assert "Trained Knowledge" in ctx
    assert "[From: navy.txt]" in ctx
    assert "celestial navigation" in ctx.lower()


def test_knowledge_context_is_empty_without_a_match():
    nk.ingest_text("navy.txt", "Ships sail on open water.")
    assert nk.knowledge_context("baking chocolate cake recipes") == ""


# ---------------------------------------------------------------------------
# management
# ---------------------------------------------------------------------------
def test_clear_knowledge_resets_stats_and_sources():
    nk.ingest_text("x.txt", "temporary content that gets cleared")
    assert nk.clear_knowledge() is True
    assert nk.knowledge_stats()["chunks"] == 0
    assert nk.knowledge_stats()["sources"] == 0
    assert nk.list_sources() == []


def test_ingest_file_reports_missing_paths():
    count, src, err = nk.ingest_file(r"C:\definitely\not\a\real\file.txt")
    assert count == 0
    assert err


def test_ingest_folder_reports_missing_paths():
    total, files, errs = nk.ingest_folder(r"C:\definitely\not\a\real\dir")
    assert total == 0 and files == 0 and errs


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
