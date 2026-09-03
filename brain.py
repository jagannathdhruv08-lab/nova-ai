"""
brain.py — Nova's LLM brain.

Two entry points:
  1. ask_nova(prompt)        — free-form chat / Q&A (used by Home chat,
                               Coach chat, OCR-fallback answers, etc.)
  2. route_to_agent(command) — LLM decides if the user's request is a
                               system action (file/OS), returns JSON,
                               and forwards it to agent.handle().

Uses Groq (OpenAI-compatible API) so any model on Groq can
be swapped in by changing the MODEL constant below.
"""

import json
import logging
import os
import re
import socket
import sys
import threading
import time

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

log = logging.getLogger("nova.brain")

# ---------------------------------------------------------------------------
# Load .env from the same directory as this script (not the CWD, which
# changes depending on how Nova is launched).
# ---------------------------------------------------------------------------
# BUG FIX: load_dotenv() with no arguments searches from the current
# working directory, which changes depending on how Nova is launched,
# so GROQ_API_KEY could silently fail to load. We force it to look for
# .env next to this script. BUT when Nova is frozen into a onefile .exe
# (PyInstaller), __file__ points at a temp _MEIxxxx extraction folder
# where no .env exists -- so we instead look next to sys.executable
# (the folder containing Nova.exe). This mirrors nova_storage.py.
if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_PATH = os.path.join(_BASE_DIR, ".env")
load_dotenv(dotenv_path=_ENV_PATH)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Groq model — fast, free tier. Change this to any model listed at
# https://console.groq.com/docs/models if you want to switch, or set
# NOVA_MODEL=<model id> in .env (that override was documented in
# env.example for ages but was never actually read — fixed now).
#
# NOTE: the old defaults "llama-3.3-70b-versatile" and
# "llama-3.1-8b-instant" were retired by Groq, so every call returned
# HTTP 404 ("model_not_found") and the app showed "Sorry, I couldn't
# process that right now. (NotFoundError)" for every message.
# "openai/gpt-oss-20b" is a current production model and works for both
# chat (ask_nova) and forced-JSON routing (route_to_agent).
MODEL = os.getenv("NOVA_MODEL", "openai/gpt-oss-20b").strip() or "openai/gpt-oss-20b"

# Backup provider — used AUTOMATICALLY whenever Groq fails (rate limit,
# network error, retired model, auth problem) so Nova never stops replying.
# The same openai/gpt-oss-20b model runs on OpenRouter, so answer quality
# stays consistent. Override in .env with OPENROUTER_MODEL=<slug> if needed.
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-20b")

# Bounded waits: a dead provider must never hang Nova's chat thread forever.
_CLIENT_TIMEOUT_S = 45    # total request budget once connected (slow streams)
_CONNECT_TIMEOUT_S = 5    # TCP connect budget - the phase that hangs offline


def _build_client(api_key, base_url, extra_headers=None):
    """Build an OpenAI-compatible client, or return None when unusable."""
    if not api_key:
        return None
    if OpenAI is None:
        log.error("OpenAI package is not installed; cannot initialise LLM client.")
        return None
    try:
        # CRITICAL for the offline case: the OpenAI client silently retries
        # connection errors twice by default (3 attempts total) and applies
        # the full timeout to the TCP connect phase too. With WiFi up but no
        # internet, connect() waits out the whole budget - 45s x 3 attempts
        # per provider is exactly what made offline replies take minutes.
        # So: zero retries + a short connect timeout. The generous total
        # timeout is kept for streaming a long answer once connected.
        try:
            import httpx
            timeout = httpx.Timeout(_CLIENT_TIMEOUT_S, connect=_CONNECT_TIMEOUT_S)
        except Exception:
            timeout = _CLIENT_TIMEOUT_S
        kwargs = {
            "api_key": api_key,
            "base_url": base_url,
            "timeout": timeout,
            "max_retries": 0,
        }
        if extra_headers:
            kwargs["default_headers"] = extra_headers
        return OpenAI(**kwargs)
    except Exception as exc:
        log.error("LLM client init failed (%s): %s", base_url, exc)
        return None


client = _build_client(GROQ_API_KEY, "https://api.groq.com/openai/v1")
_fallback_client = _build_client(
    OPENROUTER_API_KEY,
    "https://openrouter.ai/api/v1",
    extra_headers={"X-Title": "Nova AI"},
)

# Ordered failover chain: Groq primary, OpenRouter backup.
_PROVIDERS = []
if client is not None:
    _PROVIDERS.append({
        "name": "Groq",
        "client": client,
        "model": MODEL,
        "cooldown_until": 0.0,
    })
if _fallback_client is not None:
    _PROVIDERS.append({
        "name": "OpenRouter",
        "client": _fallback_client,
        "model": OPENROUTER_MODEL,
        # gpt-oss spends tokens on hidden reasoning before answering, so the
        # backup needs extra headroom or it can return empty content.
        "min_max_tokens": 600,
        "cooldown_until": 0.0,
    })
_PROVIDER_COOLDOWN_S = 30    # deprioritise a provider that just errored
_RATE_LIMIT_COOLDOWN_S = 60  # rate-limited providers wait a full minute

# ---------------------------------------------------------------------------
# Local LLM fallback (Ollama) - last link in the failover chain.
# Enabled via .env:  OLLAMA_ENABLED=1   (+ optional OLLAMA_HOST/MODEL).
# When Groq AND OpenRouter are both unreachable (no internet), Nova can
# still think locally through Ollama's OpenAI-compatible endpoint.
# ---------------------------------------------------------------------------
def _ollama_reachable(host):
    """Quick <1s probe of the Ollama server; stdlib only."""
    import urllib.request
    try:
        req = urllib.request.Request(f"{host.rstrip('/')}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            return resp.status == 200
    except Exception:
        return False


OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", "").strip().lower() in ("1", "true", "yes")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
# Ollama unloads an idle model after ~5 minutes, so the next offline message
# pays the full model-load time (often 10-30s on CPU). The keep-warm thread
# (started automatically after the first Ollama reply) pokes the model every
# few minutes so it never unloads. Disable with .env:  OLLAMA_KEEP_WARM=0
OLLAMA_KEEP_WARM = os.getenv("OLLAMA_KEEP_WARM", "1").strip().lower() not in (
    "0", "false", "no")

_OLLAMA_PROBE_TTL_S = 30
_ollama_client = None
_ollama_probe_state = {"reachable": False, "at": 0.0}
_ollama_attach_lock = threading.Lock()


def _attach_ollama_provider():
    """Attach the Ollama provider to the chain if the server is reachable.

    Runs once at import AND lazily before every request (the probe result is
    cached for _OLLAMA_PROBE_TTL_S) so Nova also finds Ollama when it is
    started AFTER Nova launches.
    """
    global _ollama_client
    if not OLLAMA_ENABLED or OpenAI is None:
        return False
    if any(p.get("name") == "Ollama" for p in _PROVIDERS):
        return True
    with _ollama_attach_lock:
        if any(p.get("name") == "Ollama" for p in _PROVIDERS):
            return True
        now = time.monotonic()
        if (now - _ollama_probe_state["at"]) >= _OLLAMA_PROBE_TTL_S:
            _ollama_probe_state["reachable"] = _ollama_reachable(OLLAMA_HOST)
            _ollama_probe_state["at"] = now
        if not _ollama_probe_state["reachable"]:
            return False
        if _ollama_client is None:
            # api_key is required by the OpenAI client but ignored by Ollama.
            _ollama_client = _build_client("ollama", f"{OLLAMA_HOST.rstrip('/')}/v1")
        if _ollama_client is not None:
            _PROVIDERS.append({
                "name": "Ollama",
                "client": _ollama_client,
                "model": OLLAMA_MODEL,
                "cooldown_until": 0.0,
            })
            log.info("LLM provider attached: Ollama (model=%s)", OLLAMA_MODEL)
            return True
        return False


def _ensure_ollama_provider():
    """Request-path hook; tests stub this out to stay hermetic."""
    try:
        return _attach_ollama_provider()
    except Exception:
        return any(p.get("name") == "Ollama" for p in _PROVIDERS)

# ---------------------------------------------------------------------------
# Fast offline detection. With WiFi up but no internet, TCP connects to the
# cloud APIs hang until timeout (packets go nowhere) - that is what made
# offline replies take 40+ seconds: Groq, then OpenRouter, each burned its
# whole connect budget before Ollama was finally asked. A ~1s cached socket
# probe lets the request path skip cloud providers entirely and answer
# locally straight away.
# ---------------------------------------------------------------------------
_INTERNET_PROBE_HOSTS = (("1.1.1.1", 443), ("8.8.8.8", 53))
_INTERNET_TTL_OK_S = 60.0    # trust a successful probe for a minute
_INTERNET_TTL_DOWN_S = 10.0  # re-check soon so Nova recovers when net returns
_internet_state = {"ok": None, "at": 0.0}


def _internet_ok(force=False):
    """Cheap cached 'is the internet reachable?' check (stdlib only)."""
    now = time.monotonic()
    st = _internet_state
    if not force and st["ok"] is not None:
        ttl = _INTERNET_TTL_OK_S if st["ok"] else _INTERNET_TTL_DOWN_S
        if (now - st["at"]) < ttl:
            return st["ok"]
    ok = False
    for host, port in _INTERNET_PROBE_HOSTS:
        try:
            socket.create_connection((host, port), timeout=1.2).close()
            ok = True
            break
        except OSError:
            continue
    st["ok"] = ok
    st["at"] = now
    return ok


_keep_warm_started = False
_KEEP_WARM_INTERVAL_S = 240  # safely below Ollama's ~5-minute idle unload


def _start_keep_warm():
    """Keep the Ollama model loaded so replies never start with a cold load.

    Called after the first successful Ollama reply (the model is definitely
    in memory at that point). A daemon thread sends an empty 1-token
    generate request with a long keep_alive every few minutes.
    """
    global _keep_warm_started
    if _keep_warm_started or not OLLAMA_KEEP_WARM:
        return
    _keep_warm_started = True

    def _loop():
        import urllib.request
        payload = json.dumps({
            "model": OLLAMA_MODEL,
            "prompt": "",
            "num_predict": 1,
            "keep_alive": "30m",
            "stream": False,
        }).encode("utf-8")
        while True:
            time.sleep(_KEEP_WARM_INTERVAL_S)
            try:
                req = urllib.request.Request(
                    f"{OLLAMA_HOST.rstrip('/')}/api/generate",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=90).read()
            except Exception as exc:
                log.debug("ollama keep-warm ping failed: %s", exc)

    threading.Thread(target=_loop, daemon=True,
                     name="ollama-keep-warm").start()


_attach_ollama_provider()  # attach now if Ollama is already running

for _p in _PROVIDERS:
    log.info("LLM provider ready: %s (model=%s)", _p["name"], _p["model"])

# ---------------------------------------------------------------------------
# Simple in-memory rate-limit (survives within a single app session)
# ---------------------------------------------------------------------------
_RATE_LIMITED_UNTIL = 0.0
_RATE_LIMIT_MESSAGE = ""


def _is_rate_limited() -> bool:
    return time.monotonic() < _RATE_LIMITED_UNTIL


def _rate_limit_message() -> str:
    return _RATE_LIMIT_MESSAGE or "Rate limit hit. Please wait a moment and try again."


def _mark_rate_limited(msg: str, seconds: int = 60):
    global _RATE_LIMITED_UNTIL, _RATE_LIMIT_MESSAGE
    _RATE_LIMITED_UNTIL = time.monotonic() + seconds
    _RATE_LIMIT_MESSAGE = msg


def _short_exc(exc) -> str:
    return f"{type(exc).__name__}: {exc}"


def _redact(text: str) -> str:
    """Remove API keys from error messages before showing them to the user."""
    text = re.sub(r"sk-or-v1-[a-zA-Z0-9\-]+", "sk-or-v1-***", text)
    text = re.sub(r"sk-[a-zA-Z0-9\-]+", "sk-***", text)
    text = re.sub(r"gsk_[a-zA-Z0-9]+", "gsk_***", text)
    return text


# ---------------------------------------------------------------------------
# Multi-provider chat helper (Groq -> OpenRouter automatic failover)
# ---------------------------------------------------------------------------
def _extract_json_object(text):
    """Best-effort JSON object extraction from an LLM reply."""
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return None
    return None


def _ordered_providers():
    """Provider chain for one request: cooldown-aware order + offline fast-path.

    Returns (order, skipped_cloud). When the internet is down and a local
    Ollama provider exists, cloud providers are skipped completely (and put
    on cooldown) so the reply goes straight to the local model instead of
    burning two cloud connect-timeouts first. skipped_cloud lets the caller
    retry them once if the offline verdict turns out to be wrong.
    """
    _ensure_ollama_provider()
    now = time.monotonic()
    healthy = [p for p in _PROVIDERS if p.get("cooldown_until", 0.0) <= now]
    order = healthy + [p for p in _PROVIDERS if p not in healthy]

    skipped_cloud = []
    has_local = any(p.get("name") == "Ollama" for p in order)
    if has_local and not _internet_ok():
        for p in order:
            if p.get("name") != "Ollama":
                skipped_cloud.append(p)
                p["cooldown_until"] = max(p.get("cooldown_until", 0.0),
                                          now + _PROVIDER_COOLDOWN_S)
        order = [p for p in order if p.get("name") == "Ollama"]
        log.info("offline mode: skipping cloud providers, answering locally")
    return order, skipped_cloud


def llm_chat(messages, max_tokens=800, temperature=0.7, response_format=None):
    """Send *messages* through the provider chain until one replies.

    Tries Groq first; if it fails (rate limit / network / retired model /
    auth), automatically retries on the OpenRouter backup so Nova never
    stops answering. Providers that just failed get a short cooldown so
    the next request starts on the healthy one instead of timing out twice.

    Returns (text, provider_name) on success, or (None, last_error_string)
    when every configured provider failed.
    """
    if not _PROVIDERS:
        return None, "no LLM provider configured"

    order, skipped_cloud = _ordered_providers()

    def _try_chain(provs):
        errors = []
        for prov in provs:
            budget = max(max_tokens, prov.get("min_max_tokens", 0))
            # Some providers/models reject response_format - one plain retry.
            formats = [response_format]
            if response_format is not None:
                formats.append(None)
            for fmt in formats:
                try:
                    kwargs = {
                        "model": prov["model"],
                        "messages": messages,
                        "max_tokens": budget,
                        "temperature": temperature,
                    }
                    if fmt is not None:
                        kwargs["response_format"] = fmt
                    resp = prov["client"].chat.completions.create(**kwargs)
                    text = (resp.choices[0].message.content or "").strip()
                    if not text:
                        raise ValueError("empty completion")
                    prov["cooldown_until"] = 0.0
                    if prov.get("name") == "Ollama":
                        _start_keep_warm()
                    return text, prov["name"], errors
                except Exception as exc:
                    err = _redact(str(exc))
                    errors.append(f"{prov['name']}: {type(exc).__name__}: {err}")
                    log.error("llm_chat via %s failed: %s",
                              prov["name"], _short_exc(exc))
                    lowered_err = err.lower()
                    if "429" in err or "rate" in lowered_err:
                        cooldown = _RATE_LIMIT_COOLDOWN_S
                    else:
                        cooldown = _PROVIDER_COOLDOWN_S
                    prov["cooldown_until"] = time.monotonic() + cooldown
        return None, None, errors

    text, name, errors = _try_chain(order)
    if text is None and skipped_cloud and _internet_ok(force=True):
        # Rare: the offline verdict was wrong (the network came back between
        # probes). Retry the cloud providers once - bounded by max_retries=0
        # and the 5s connect timeout, so this can never reintroduce
        # minute-long stalls.
        log.info("offline verdict was wrong; retrying cloud providers")
        text, name, extra = _try_chain(skipped_cloud)
        errors = errors + extra

    if text is not None:
        return text, name
    return None, " | ".join(errors) if errors else ""


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are Nova, a helpful AI assistant. You speak in a friendly mix of "
    "English and Hindi (Hinglish) when appropriate. You are knowledgeable, "
    "concise, and supportive. Keep answers short unless asked for detail. "
    "You are helping a student who is preparing for the Merchant Navy. "
    "Use colorful, expressive emojis in your replies to keep the chat lively "
    "and engaging. Sprinkle relevant emojis naturally — don't overdo it. "
    "When explaining concepts (especially maths, science, or study topics), "
    "follow this study-friendly structure so students retain faster:\n\n"
    "1. Open with praise + emoji, e.g. \"This is **excellent** breakdown! 🎯\"\n"
    "2. Give a super-simplified \"Even MORE for quick retention\" version\n"
    "3. Add \"## **Real-world analogy** 🎯\" — use a vivid, relatable analogy\n"
    "4. Add \"## **For your error journal** 📔\" — list common mistakes, "
    "root causes, and remedies\n"
    "5. Add \"## **Quick CBSE practice drill** 🎓\" — 2-3 practice problems "
    "with answers\n"
    "6. End with a friendly call-to-action encouraging more practice\n\n"
    "Use Markdown bold (**text**) and headers (##). Keep each section tight "
    "and scannable. For short questions or non-study topics, reply normally "
    "without forcing the full structure."
)


# ---------------------------------------------------------------------------
# Emoji utilities — strip emojis from text so the LLM never "reads" them.
# Emojis are display-only for the user; they carry no semantic meaning for
# the model and can confuse keyword matching / routing.
# ---------------------------------------------------------------------------
_EMOJI_PATTERN = re.compile(
    r"["
    r"\U0001F600-\U0001F64F"  # Emoticons
    r"\U0001F300-\U0001F5FF"  # Misc Symbols and Pictographs
    r"\U0001F680-\U0001F6FF"  # Transport and Map Symbols
    r"\U0001F1E0-\U0001F1FF"  # Flags
    r"\U00002700-\U000027BF"  # Dingbats
    r"\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
    r"\U0001FA00-\U0001FA6F"  # Chess Symbols
    r"\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
    r"\U00002600-\U000026FF"  # Misc Symbols
    r"\U00002B00-\U00002BFF"  # Misc Symbols and Arrows
    r"]+",
    flags=re.UNICODE,
)
# Variation selectors & zero-width joiners that combine emoji sequences
_VARIATION_SELECTOR_PATTERN = re.compile(r"[\uFE0F\u200B\u200C\u200D\u20E3]")


def _strip_emojis(text: str) -> str:
    """Remove every emoji character from *text*.

    This is called before any prompt or user message is handed to the LLM
    so that emojis — which the user wants to be 'read' visually but never
    semantically — never reach the model.
    """
    if text is None:
        return ""
    text = _EMOJI_PATTERN.sub("", text)
    text = _VARIATION_SELECTOR_PATTERN.sub("", text)
    return text.strip()

AGENT_SCHEMA_PROMPT = """You are Nova's action router. Decide if the user's request is a system/file action.

If it IS a system action, respond with ONLY a JSON object:
{
  "action": "list_dir" | "open_file" | "search_file" | "read_file_summary" | "create_folder" | "move_file" | "rename_file" | "delete_file" | "run_app" | "system_info" | "disk_usage" | "empty_recycle_bin",
  "args": { "path": "...", "query": "...", "destination": "...", "new_name": "...", "exe": "..." },
  "confidence": 0.0 to 1.0
}

If the request is NOT a system action (it's a question, chat, or needs clarification), respond with:
{
  "action": "chat",
  "ask": "your clarification question here"
}

Rules:
- Only include args fields that are relevant to the action.
- confidence must reflect how sure you are (0.0-1.0).
- For "chat" action, put your clarification or response in "ask".
- Respond with ONLY the JSON object, no other text, no markdown fences.
"""


# ---------------------------------------------------------------------------
# 1. Free-form chat
# ---------------------------------------------------------------------------
def _retrieve_knowledge(prompt: str) -> str:
    """Auto-retrieve relevant personal knowledge for *prompt* (RAG).

    Uses a lazy import so brain.py stays importable even when the optional
    nova_knowledge module is unavailable (e.g. during certain builds).
    Returns an empty string when there is nothing relevant or no KB exists.
    """
    try:
        import nova_knowledge  # type: ignore  # local module, lazy
    except Exception:
        return ""
    try:
        # The user's current question sits at the END of the prompt (the
        # rest is memory facts + recent chat history). Using the tail keeps
        # retrieval focused on the live question instead of old turns.
        query = prompt[-600:] if len(prompt) > 600 else prompt
        return nova_knowledge.knowledge_context(query)
    except Exception:
        return ""


def ask_nova(prompt: str, knowledge_context: str = "") -> str:
    """Free-form LLM chat. Always returns a text response string: if the
    primary LLM fails the backup takes over automatically, and only when
    EVERY provider fails does this return an error message."""
    if not _PROVIDERS:
        return (
            "LLM brain is not configured. Check GROQ_API_KEY (and the "
            "OPENROUTER_API_KEY backup) in the .env file next to brain.py."
        )
    if _is_rate_limited():
        return _rate_limit_message()

    # Strip emojis so the LLM never "reads" them — they are display-only.
    clean_prompt = _strip_emojis(prompt)

    # Inject personal knowledge trained from the user's data (RAG). Auto-
    # retrieve relevant chunks unless a caller passed an explicit context.
    if not knowledge_context:
        knowledge_context = _retrieve_knowledge(clean_prompt)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if knowledge_context:
        # Personal knowledge is injected as a system message so the model
        # treats it as reliable context to apply when answering.
        messages.append({"role": "system", "content": knowledge_context})
    messages.append({"role": "user", "content": clean_prompt})

    text, info = llm_chat(messages, max_tokens=800, temperature=0.7)
    if text is not None:
        return text

    # Every provider failed — explain instead of going silent.
    log.error("ask_nova failed on all providers: %s", info)
    err = info or ""
    lowered_err = err.lower()
    if "429" in err or "rate" in lowered_err:
        _mark_rate_limited(
            "Rate limit hit. Please wait a minute and try again.",
            seconds=60,
        )
        return _rate_limit_message()
    if "404" in err or "not_found" in lowered_err or "not found" in lowered_err:
        return (
            f"Model '{MODEL}' / '{OPENROUTER_MODEL}' is not available right "
            "now. Update MODEL (or OPENROUTER_MODEL) in brain.py / .env to "
            "a current model. (NotFoundError)"
        )
    match_exc = re.search(r"[A-Za-z]+(?:Error|Exception|Timeout)", err)
    exc_name = match_exc.group(0) if match_exc else "LLMUnavailable"
    return f"Sorry, I couldn't process that right now. ({exc_name})"



# ---------------------------------------------------------------------------
# 2. Agent router — LLM decides if the request is a system action
# ---------------------------------------------------------------------------
def route_to_agent(command: str, confirm_callback=None) -> str:
    """
    Call the LLM with a forced-JSON system prompt, then forward the
    validated action to `agent.handle()`. `confirm_callback(msg) -> bool`
    is required for destructive actions.
    """
    # Lazy import — agent.py may not be present in older builds
    try:
        import agent  # type: ignore
    except ImportError:
        log.error("agent.py not available; cannot route system actions")
        return "System-agent module is not installed. Run `pip install -e .` or copy agent.py next to brain.py."

    if not _PROVIDERS:
        return "LLM brain is not configured. Check GROQ_API_KEY in .env."

    if _is_rate_limited():
        return _rate_limit_message()

    messages = [
        {"role": "system", "content": AGENT_SCHEMA_PROMPT},
        {"role": "user", "content": _strip_emojis(command)},
    ]
    raw, info = llm_chat(
        messages,
        max_tokens=200,
        temperature=0,
        response_format={"type": "json_object"},
    )
    if raw is None:
        log.error("route_to_agent: all providers failed: %s", info)
        err = info or ""
        if "429" in err or "rate" in err.lower():
            _mark_rate_limited(err)
        return "Sorry, I couldn't decide what to do. Try again or be more specific."

    # Tolerant parse - some providers wrap JSON in prose despite
    # response_format, so fall back to brace extraction.
    action_json = _extract_json_object(raw)
    if not isinstance(action_json, dict):
        log.error("route_to_agent: unparseable reply via %s", info)
        return "Sorry, I couldn't decide what to do. Try again or be more specific."

    # If the model asked for clarification, return that instead of
    # calling agent.handle().
    if action_json.get("action") == "chat":
        ask = action_json.get("ask", "").strip()
        if ask:
            return ask
        return "Thoda aur detail do please — kya karna hai exactly?"

    # Defensive: the schema prompt forbids unknown actions, but verify.
    if action_json.get("action") not in agent.ALLOWED_ACTIONS:
        log.warning("LLM proposed unknown action %r", action_json.get("action"))
        return f"Sorry, I can't do '{action_json.get('action')}'."

    return agent.handle(action_json, confirm_callback=confirm_callback)


# ---------------------------------------------------------------------------
# 3. Structured-JSON helper - one call, tolerant parse (intents/quizzes/SRS)
# ---------------------------------------------------------------------------
def llm_json(system_prompt, user_prompt, max_tokens=600, temperature=0.3):
    """Ask the LLM for a JSON object and return it as a dict.

    Combines a single provider round-trip with _extract_json_object()'s
    tolerant parsing (handles prose-wrapped / fenced JSON). Returns
    None when every provider fails or nothing parseable comes back -
    callers are expected to degrade gracefully.
    """
    if not _PROVIDERS:
        return None
    raw, info = llm_chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    if raw is None:
        log.debug("llm_json: providers failed: %s", info)
        return None
    parsed = _extract_json_object(raw)
    return parsed if isinstance(parsed, dict) else None

# ---------------------------------------------------------------------------
# 4. Streaming chat - same failover chain, but tokens arrive live
# ---------------------------------------------------------------------------
def llm_chat_stream(messages, max_tokens=800, temperature=0.7, on_delta=None):
    """Streaming variant of llm_chat().

    Iterates the same provider chain; for each provider opens a
    stream=True completion and forwards content deltas to
    on_delta(chunk_text) as they arrive. If a provider fails BEFORE any
    token was emitted, the next provider is tried seamlessly. If it dies
    mid-stream, whatever was accumulated so far is returned - restarting
    would visibly delete text the user already saw.

    Returns (full_text, provider_name_or_error).
    """
    if not _PROVIDERS:
        return None, "no LLM provider configured"

    order, skipped_cloud = _ordered_providers()

    def _try_stream_chain(provs):
        errors = []
        for prov in provs:
            budget = max(max_tokens, prov.get("min_max_tokens", 0))
            chunks = []
            try:
                stream = prov["client"].chat.completions.create(
                    model=prov["model"],
                    messages=messages,
                    max_tokens=budget,
                    temperature=temperature,
                    stream=True,
                )
                for event in stream:
                    choices = getattr(event, "choices", None)
                    delta = getattr(choices[0], "delta", None) if choices else None
                    piece = (getattr(delta, "content", None) or "") if delta else ""
                    if not piece:
                        continue
                    chunks.append(piece)
                    if on_delta is not None:
                        try:
                            on_delta(piece)
                        except Exception:
                            pass   # a UI hiccup must never kill the stream
                text = "".join(chunks).strip()
                if not text:
                    raise ValueError("empty streamed completion")
                prov["cooldown_until"] = 0.0
                if prov.get("name") == "Ollama":
                    _start_keep_warm()
                return text, prov["name"], errors
            except Exception as exc:
                partial = "".join(chunks).strip()
                err = _redact(str(exc))
                errors.append(f"{prov['name']}: {type(exc).__name__}: {err}")
                log.error("llm_chat_stream via %s failed: %s",
                          prov["name"], _short_exc(exc))
                lowered_err = err.lower()
                cooldown = (_RATE_LIMIT_COOLDOWN_S if "429" in err or "rate" in lowered_err
                            else _PROVIDER_COOLDOWN_S)
                prov["cooldown_until"] = time.monotonic() + cooldown
                if partial:
                    # Tokens already shown to the user - better to deliver them.
                    return partial, f"{prov['name']} (partial)", errors
                continue
        return None, None, errors

    text, name, errors = _try_stream_chain(order)
    if text is None and skipped_cloud and _internet_ok(force=True):
        # Rare: the offline verdict was wrong - bounded retry, see llm_chat.
        log.info("offline verdict was wrong; retrying cloud providers")
        text, name, extra = _try_stream_chain(skipped_cloud)
        errors = errors + extra

    if text is not None:
        return text, name
    return None, " | ".join(errors) if errors else ""


def ask_nova_stream(prompt: str, knowledge_context: str = "", on_delta=None):
    """Streaming twin of ask_nova(): identical prompt assembly and
    failover behaviour, but reply text arrives chunk-by-chunk through
    on_delta(chunk). Returns the final full text (always a str)."""
    if not _PROVIDERS:
        return (
            "LLM brain is not configured. Check GROQ_API_KEY (and the "
            "OPENROUTER_API_KEY backup) in the .env file next to brain.py."
        )
    if _is_rate_limited():
        return _rate_limit_message()

    clean_prompt = _strip_emojis(prompt)
    if not knowledge_context:
        knowledge_context = _retrieve_knowledge(clean_prompt)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if knowledge_context:
        messages.append({"role": "system", "content": knowledge_context})
    messages.append({"role": "user", "content": clean_prompt})

    text, info = llm_chat_stream(messages, max_tokens=800, temperature=0.7,
                                 on_delta=on_delta)
    if text is not None:
        return text

    log.error("ask_nova_stream failed on all providers: %s", info)
    err = info or ""
    if "429" in err or "rate" in err.lower():
        _mark_rate_limited(
            "Rate limit hit. Please wait a minute and try again.", seconds=60)
        return _rate_limit_message()
    match_exc = re.search(r"[A-Za-z]+(?:Error|Exception|Timeout)", err)
    exc_name = match_exc.group(0) if match_exc else "LLMUnavailable"
    return f"Sorry, I couldn't process that right now. ({exc_name})"