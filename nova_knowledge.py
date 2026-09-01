# ==========================================
# NOVA AI - PERSONAL KNOWLEDGE BASE ("TRAIN NOVA")
# ------------------------------------------
# This is how Nova "learns" from your personal data - written paragraphs,
# photos, and PDFs - without fine-tuning the hosted LLM.
#
# It works the standard RAG way:
#   1. INGEST   - extract text from a file / paste a paragraph / scan a folder.
#                 The text is split into small "chunks" and stored on disk.
#   2. INDEX    - each chunk is tokenized (in-memory) so retrieval is fast.
#   3. RETRIEVE - for every chat question, the chunks most relevant to that
#                  question are fetched (TF-IDF cosine similarity).
#   4. INJECT   - brain.ask_nova() prepends the retrieved chunks to the LLM
#                 prompt so Nova can *apply* what you taught it.
#
# Nothing here touches the network except the image path, which reuses the
# existing nova_vision OCR / Gemini helpers. Pure-Python retrieval = snappy.
# ==========================================

import json
import math
import os
import re
import sys
from collections import Counter
from datetime import datetime

from nova_storage import writable_data_path

# Stable, writable location next to the .exe (see nova_storage.writable_data_path).
KNOWLEDGE_FILE = writable_data_path("nova_knowledge.json")

# ---- chunking tuning --------------------------------------------------------
MAX_CHUNK_CHARS = 500       # chars per chunk (~75-100 words)
CHUNK_OVERLAP = 80          # overlap between consecutive chunks (chars)
MAX_INJECT_CHUNKS = 6       # cap retrieved chunks sent to the LLM per turn
MAX_INJECT_CHARS = 3000     # hard cap on injected knowledge chars total

# Small English stop-word set so common words don't dominate retrieval.
# (No nltk dependency - keeps startup fast.)
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "at", "for",
    "is", "are", "was", "were", "be", "been", "being", "this", "that", "these",
    "those", "it", "its", "as", "by", "with", "from", "not", "no", "so", "if",
    "then", "than", "into", "about", "can", "will", "would", "should", "could",
    "i", "you", "he", "she", "we", "they", "my", "your", "our", "their",
    "what", "how", "why", "when", "where", "which", "who", "whom",
    "do", "does", "did", "has", "have", "had", "am",
    "very", "just", "only", "also", "such", "same", "too", "per", "via",
    "etc", "yes", "no", "one", "two", "new", "now",
}


def _tokenize(text):
    """Lowercase, split on word boundaries, drop stopwords + 1-char tokens."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]


# ---------------------------------------------------------------------------
# Persistence - load once at import (mirrors nova_study / nova_storage pattern).
# The in-memory _KB dict is the single source of truth; _save() mirrors it
# to disk without the cached token lists.
# ---------------------------------------------------------------------------
_KB = {"sources": {}, "chunks": []}


def _load():
    data = {"sources": {}, "chunks": []}
    try:
        if os.path.exists(KNOWLEDGE_FILE):
            with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            data["sources"] = raw.get("sources", {})
            for c in raw.get("chunks", []):
                c["tokens"] = _tokenize(c.get("text", ""))
                data["chunks"].append(c)
    except Exception as exc:
        print("nova_knowledge load failed:", exc)
    return data


def _save():
    persist = {
        "sources": _KB["sources"],
        "chunks": [
            {"source": c["source"], "index": c["index"], "text": c["text"]}
            for c in _KB["chunks"]
        ],
    }
    try:
        with open(KNOWLEDGE_FILE, "w", encoding="utf-8") as f:
            json.dump(persist, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        print("nova_knowledge save failed:", exc)


_KB = _load()


# ---------------------------------------------------------------------------
# Text chunking
# ---------------------------------------------------------------------------
def _chunk_text(text, chunk_size=MAX_CHUNK_CHARS, overlap=CHUNK_OVERLAP):
    """Split *text* into overlapping chunks.

    Splits on blank-line separated paragraphs first, then on sentence
    boundaries, keeping each chunk <= chunk_size chars. Adjacent chunks
    overlap by `overlap` chars so ideas aren't cut in half.
    """
    if not text:
        return []
    text = text.strip()

    # 1. paragraph boundaries
    paragraphs = re.split(r"\n\s*\n", text)
    chunks = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) <= chunk_size:
            chunks.append(para)
        else:
            # 2. sentence boundaries within a long paragraph
            sentences = re.split(r"(?<=[.!?])\s+", para)
            current = ""
            for sentence in sentences:
                if len(current) + len(sentence) + 1 <= chunk_size:
                    current = (current + " " + sentence).strip() if current else sentence
                else:
                    if current:
                        chunks.append(current)
                    current = sentence
            if current:
                chunks.append(current)

    # 3. merge tiny chunks
    merged = []
    for chunk in chunks:
        if merged and len(merged[-1]) < chunk_size // 3:
            merged[-1] = (merged[-1] + "\n" + chunk)[:chunk_size]
        else:
            merged.append(chunk)

    # 4. apply overlap on any chunk that still exceeds the limit
    if not merged:
        return []
    final = []
    for chunk in merged:
        if len(chunk) <= chunk_size:
            final.append(chunk)
        else:
            start = 0
            while start < len(chunk):
                end = start + chunk_size
                final.append(chunk[start:end])
                if end >= len(chunk):
                    break
                start = end - overlap
    return final


# ---------------------------------------------------------------------------
# Ingestion - text
# ---------------------------------------------------------------------------
def ingest_text(source_name, text):
    """Chunk and store text under *source_name*.

    Re-ingesting a source with the same name replaces its previous chunks
    (so you can re-run 'learn' on an updated file). Returns chunk count.
    """
    if not text or not text.strip():
        return 0
    source_name = (source_name or "text").strip()[:120]
    chunks = _chunk_text(text)
    if not chunks:
        return 0

    # Remove old chunks for this source, then append fresh ones.
    _KB["chunks"] = [c for c in _KB["chunks"] if c.get("source") != source_name]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_chunks = []
    for i, chunk in enumerate(chunks):
        new_chunks.append({
            "source": source_name,
            "index": i,
            "text": chunk,
            "tokens": _tokenize(chunk),
        })
    _KB["chunks"].extend(new_chunks)
    _KB["sources"][source_name] = {
        "added_at": now,
        "updated_at": now,
        "chunks": len(new_chunks),
        "chars": len(text),
    }
    # bound memory/disk for huge libraries
    if len(_KB["chunks"]) > 2000:
        _KB["chunks"] = _KB["chunks"][-2000:]
        _save()
    return len(new_chunks)


# ---------------------------------------------------------------------------
# Extraction helpers (lazy imports so the module stays cheap to load)
# ---------------------------------------------------------------------------
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"}
_TEXT_EXTS = {".txt", ".md", ".csv", ".json", ".log", ".py", ".ipynb",
              ".html", ".xml"}


def _extract_pdf_text(path):
    """Extract text from a PDF using pypdf (pure-Python, no heavy deps)."""
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore  # legacy fallback
        except ImportError:
            return "", "PDF support needs 'pypdf'. Install it: pip install pypdf"
    try:
        reader = PdfReader(path)
        texts = []
        for page in reader.pages:
            texts.append(page.extract_text() or "")
        text = "\n".join(texts).strip()
        if not text:
            return "", "PDF had no extractable text (it may be a scanned image only)."
        return text, None
    except Exception as exc:
        return "", f"PDF read failed: {type(exc).__name__}: {exc}"


def _extract_text_file(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip(), None
    except Exception as exc:
        return "", f"Text read failed: {type(exc).__name__}: {exc}"


def _extract_image_text(path):
    """Extract knowledge from an image: OCR text + Gemini vision description."""
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return "", "Pillow (PIL) is required to read images."

    parts = []
    try:
        img = Image.open(path).convert("RGB")
    except Exception as exc:
        return "", f"Could not open image: {type(exc).__name__}: {exc}"

    # 1. OCR - real text in the photo (notes, documents, screenshots...)
    ocr_text = ""
    try:
        from nova_vision import extract_text_from_image  # lazy
        ocr_text = (extract_text_from_image(img) or "").strip()
        if ocr_text:
            parts.append("## Text detected in image:\n" + ocr_text)
    except Exception:
        pass

    # 2. Gemini Vision - describe the scene / diagram / chart if no OCR
    try:
        from nova_vision import ask_gemini_vision, GEMINI_API_KEY  # lazy
        if GEMINI_API_KEY:
            desc = ask_gemini_vision(
                img,
                "Describe this image in detail - objects, text, diagrams, charts, "
                "layout, colours, and anything visually important. Write 1-3 short "
                "paragraphs.",
            )
            if desc:
                parts.append("## Visual description of image:\n" + desc.strip())
        else:
            if not ocr_text:
                parts.append("## Visual description of image:\n"
                             "(Gemini Vision not configured - only OCR text was used.)")
    except Exception:
        pass

    if not parts:
        return "", "No readable text or vision description found in this image."
    return "\n\n".join(parts), None


def ingest_file(path):
    """Ingest a single file by type. Returns (chunk_count, source_name, error)."""
    if not path or not os.path.exists(path):
        return 0, "", "File not found."
    ext = os.path.splitext(path)[1].lower()
    source_name = os.path.basename(path)

    if ext == ".pdf":
        text, err = _extract_pdf_text(path)
    elif ext in _IMAGE_EXTS:
        text, err = _extract_image_text(path)
    elif ext in _TEXT_EXTS:
        text, err = _extract_text_file(path)
    else:
        text, err = _extract_text_file(path)  # try-as-text fallback

    if err and not text:
        return 0, source_name, err
    count = ingest_text(source_name, text or "")
    if count == 0:
        return 0, source_name, err or "No text could be extracted."
    return count, source_name, None


def ingest_folder(path):
    """Recursively ingest every supported file in *path*.

    Returns (total_chunks, files_ingested, errors).
    """
    if not path or not os.path.exists(path):
        return 0, 0, ["Folder not found."]
    supported = _IMAGE_EXTS | _TEXT_EXTS | {".pdf"}
    total_chunks = 0
    files_ingested = 0
    errors = []
    for root, _dirs, files in os.walk(path):
        for fname in sorted(files):
            ext = os.path.splitext(fname)[1].lower()
            if ext not in supported:
                continue
            fpath = os.path.join(root, fname)
            count, _src, err = ingest_file(fpath)
            if count > 0:
                total_chunks += count
                files_ingested += 1
            elif err:
                errors.append(f"{fname}: {err}")
        return total_chunks, files_ingested, errors


# ---------------------------------------------------------------------------
# Retrieval (lightweight TF-IDF cosine similarity, in-memory)
# ---------------------------------------------------------------------------
def search_knowledge(query, limit=MAX_INJECT_CHUNKS):
    """Return the *limit* most relevant (score, chunk) pairs for *query*."""
    chunks = _KB.get("chunks", [])
    if not chunks:
        return []
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []

    N = len(chunks)
    q_tf = Counter(q_tokens)

    # document frequency for every query term
    df = Counter()
    for c in chunks:
        chunk_terms = set(c["tokens"])
        for t in q_tf:
            if t in chunk_terms:
                df[t] += 1

    results = []
    for c in chunks:
        tf = Counter(c["tokens"])
        if not tf:
            continue
        score = 0.0
        norm_c = 0.0
        norm_q = 0.0
        for t, qf in q_tf.items():
            ct = tf.get(t, 0)
            if ct == 0:
                continue
            # Smoothed IDF (sklearn style): always >= 1 so a term that
            # appears in every chunk (df == N) or a 1-chunk KB still scores.
            idf = math.log((N + 1) / (1 + df.get(t, 0))) + 1.0
            w_c = ct * idf
            w_q = qf * idf
            score += w_c * w_q
            norm_c += w_c * w_c
            norm_q += w_q * w_q
        if norm_c > 0 and norm_q > 0:
            sim = score / (math.sqrt(norm_c) * math.sqrt(norm_q))
            if sim > 0:
                results.append((sim, c))

    results.sort(key=lambda x: x[0], reverse=True)
    # de-duplicate by source so one source can't crowd the top
    seen = set()
    out = []
    for sim, c in results[:limit * 3]:
        src = c["source"]
        if src in seen:
            continue
        seen.add(src)
        out.append((sim, c))
        if len(out) >= limit:
            break
    if not out:
        out = [(s, c) for s, c in results[:limit]]
    return out


def knowledge_context(query, limit=MAX_INJECT_CHUNKS):
    """Build a ready-to-inject context block for *query* (RAG prompt snippet).

    Returns '' when nothing is relevant or the KB is empty.
    """
    results = search_knowledge(query, limit=limit)
    if not results:
        return ""
    lines = ["## Trained Knowledge (from your personal data - apply this when "
             "relevant to the question):"]
    total_chars = 0
    for sim, c in results:
        text = c.get("text", "").strip()
        if not text:
            continue
        if total_chars + len(text) > MAX_INJECT_CHARS:
            text = text[: max(0, MAX_INJECT_CHARS - total_chars)]
        lines.append(f"[From: {c['source']}]\n{text}")
        total_chars += len(text)
        if total_chars >= MAX_INJECT_CHARS:
            break
    if total_chars == 0:
        return ""
    lines.append("")
    return "\n".join(lines) + "\n\n"


# ---------------------------------------------------------------------------
# Introspection / management
# ---------------------------------------------------------------------------
def list_sources():
    """Return a list of (source_name, info) for every ingested source."""
    return list(_KB.get("sources", {}).items())


def knowledge_stats():
    sources = _KB.get("sources", {})
    chunks = _KB.get("chunks", [])
    total_chars = sum(s.get("chars", 0) for s in sources.values())
    return {
        "sources": len(sources),
        "chunks": len(chunks),
        "chars": total_chars,
    }


def clear_knowledge():
    """Wipe the entire knowledge base (sources + chunks)."""
    _KB["sources"] = {}
    _KB["chunks"] = []
    _save()
    return True


# ---------------------------------------------------------------------------
# CLI / self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] in ("ingest", "learn"):
        path = sys.argv[2]
        count, src, err = ingest_file(path)
        if count:
            print(f"Learned {count} chunk(s) from '{src}'.")
        else:
            print("Failed:", err or "no text")
    elif len(sys.argv) >= 2 and sys.argv[1] == "clear":
        clear_knowledge()
        print("Cleared all trained knowledge.")
    elif len(sys.argv) >= 4 and sys.argv[1] == "search":
        q = sys.argv[2]
        for sim, c in search_knowledge(q, 3):
            print(f"  [{sim:.3f}] {c['source']}: {c['text'][:80]}...")
    else:
        stats = knowledge_stats()
        print(f"Knowledge base: {stats['sources']} source(s), "
              f"{stats['chunks']} chunk(s), {stats['chars']} chars.")
        for src, info in list_sources():
            print(f"  - {src}: {info['chunks']} chunks, {info['chars']} chars")

