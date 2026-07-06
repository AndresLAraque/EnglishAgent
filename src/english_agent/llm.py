import os
import json
import requests
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# ─── providers ──────────────────────────────────────────────────────

PROVIDER_DEEPSEEK = "deepseek"
PROVIDER_OLLAMA = "ollama"

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
WRITING_MODEL = os.getenv("OLLAMA_WRITING_MODEL", OLLAMA_MODEL)

# Which provider to prefer ("deepseek" or "ollama")
_ACTIVE_PROVIDER: str = os.getenv("LLM_PROVIDER", PROVIDER_DEEPSEEK if DEEPSEEK_API_KEY else PROVIDER_OLLAMA)
_ACTIVE_MODEL: str = ""

SYSTEM_PROMPT = "You are an English tutor. Respond exclusively in English. Never use Spanish or any other language."


def get_active_provider() -> str:
    return _ACTIVE_PROVIDER


def get_active_model() -> str:
    if _ACTIVE_MODEL:
        return _ACTIVE_MODEL
    if _ACTIVE_PROVIDER == PROVIDER_DEEPSEEK:
        return DEEPSEEK_MODEL
    return OLLAMA_MODEL


def set_provider(provider: str) -> bool:
    global _ACTIVE_PROVIDER, _ACTIVE_MODEL
    provider = provider.lower()
    if provider == PROVIDER_DEEPSEEK:
        if not DEEPSEEK_API_KEY:
            return False
        _ACTIVE_PROVIDER = PROVIDER_DEEPSEEK
        _ACTIVE_MODEL = ""
        return True
    if provider == PROVIDER_OLLAMA:
        _ACTIVE_PROVIDER = PROVIDER_OLLAMA
        _ACTIVE_MODEL = ""
        return True
    return False


def list_models() -> list[dict]:
    models = []
    if DEEPSEEK_API_KEY:
        models.append({"id": PROVIDER_DEEPSEEK, "name": f"DeepSeek ({DEEPSEEK_MODEL})", "available": True})
    models.append({"id": PROVIDER_OLLAMA, "name": f"Ollama ({OLLAMA_MODEL})", "available": True})
    return models


# ─── internal chat functions ────────────────────────────────────────


def _chat_ollama(messages: list[dict], model: Optional[str] = None, **kwargs) -> str:
    url = f"{OLLAMA_BASE_URL}/api/chat"
    full = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    payload = {
        "model": model or OLLAMA_MODEL,
        "messages": full,
        "stream": False,
        "options": {"num_predict": kwargs.get("max_tokens", 300)},
    }
    resp = requests.post(url, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def _chat_deepseek(messages: list[dict], model: Optional[str] = None, **kwargs) -> str:
    url = f"{DEEPSEEK_BASE_URL}/chat/completions"
    full = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    payload = {
        "model": model or DEEPSEEK_MODEL,
        "messages": full,
        "stream": False,
        "max_tokens": kwargs.get("max_tokens", 300),
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    if resp.status_code in (401, 402, 403, 429):
        error_body = resp.json()
        error_msg = error_body.get("error", {}).get("message", resp.text)
        raise RuntimeError(f"deepseek_quota_exceeded|{error_msg}")
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _chat(messages: list[dict], model: Optional[str] = None, **kwargs) -> str:
    if _ACTIVE_PROVIDER == PROVIDER_DEEPSEEK:
        try:
            return _chat_deepseek(messages, model=model, **kwargs)
        except RuntimeError as e:
            err_str = str(e)
            if err_str.startswith("deepseek_quota_exceeded"):
                print(f"[llm] DeepSeek quota exhausted, falling back to Ollama: {err_str}")
                return _chat_ollama(messages, model=model, **kwargs)
            raise
        except requests.RequestException as e:
            print(f"[llm] DeepSeek request failed, falling back to Ollama: {e}")
            return _chat_ollama(messages, model=model, **kwargs)
    return _chat_ollama(messages, model=model, **kwargs)


# ─── parsing ────────────────────────────────────────────────────────


def _parse(content: str) -> dict:
    import re
    block = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
    if block:
        content = block.group(1).strip()
    content = re.sub(r',\s*([}\]])', r'\1', content)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"raw": content}


# ─── public API ─────────────────────────────────────────────────────


def explain_word(word: str, translation: str) -> dict:
    prompt = (
        f"Explain the English word '{word}' (translation: {translation}). "
        f"Return ONLY valid JSON with these exact keys: "
        f"explanation, translation, example, synonyms. "
        f"No other text."
    )
    return _parse(_chat([{"role": "user", "content": prompt}], max_tokens=300))


def correct_sentence(sentence: str) -> dict:
    prompt = (
        f"Correct this English sentence: '{sentence}'. "
        f"Return ONLY valid JSON with these exact keys: "
        f"corrected, explanation, mistake_type. "
        f"No other text."
    )
    return _parse(_chat([{"role": "user", "content": prompt}], max_tokens=250))


def recommend_study(weak_words: list[dict], stats: dict) -> dict:
    words_text = "\n".join(
        f"- {w['word']} ({w['translation']})"
        for w in weak_words[:10])
    prompt = (
        f"Weak words:\n{words_text}\n\nStats: {json.dumps(stats)}\n\n"
        f"Return ONLY valid JSON with these exact keys: "
        f"tip, focus_words, encouragement. "
        f"No other text."
    )
    return _parse(_chat([{"role": "user", "content": prompt}], max_tokens=250))


def grade_writing(topic: str, text: str) -> dict:
    prompt = (
        f"A Spanish-speaking student wrote this text about the topic '{topic}':\n\n"
        f"\"{text}\"\n\n"
        f"Grade it as an English writing tutor. Find every grammar, vocabulary, and word-order mistake. "
        f"Return ONLY valid JSON with these exact keys:\n"
        f"score (integer 0-100), "
        f"corrected_text (the full text rewritten correctly), "
        f"mistakes (a list of objects, each with keys: wrong, correct, explanation, category — "
        f"category is one of grammar, vocabulary, word-order, preposition, verb-tense, other), "
        f"feedback (2-3 sentences of overall feedback), "
        f"strengths (a list of short strings about what the student did well). "
        f"If there are no mistakes, return an empty list for mistakes. "
        f"No other text."
    )
    return _parse(_chat([{"role": "user", "content": prompt}], model=WRITING_MODEL, max_tokens=900))


def engine_available() -> bool:
    return bool(_ACTIVE_PROVIDER)


def generate_reading(topic: str, level: str) -> dict:
    prompt = (
        f"Write a high-quality English reading text on the topic '{topic}' "
        f"suitable for level '{level}'. The text must be 250-350 words long, "
        f"simulate a Cambridge/IELTS/TOEFL exam passage, and have sophisticated yet natural syntax. "
        f"Return ONLY valid JSON with these exact keys: "
        f"title (a concise heading), content (the full reading text). "
        f"No other text."
    )
    return _parse(_chat([{"role": "user", "content": prompt}], max_tokens=1200))


def generate_questions(text: str, count: int = 6) -> list[dict]:
    prompt = (
        f"Based on the following reading text, create {count} multiple-choice questions "
        f"to test reading comprehension. Each question must have exactly 4 options (A, B, C, D) "
        f"with exactly one correct answer. The incorrect options must be plausible but wrong. "
        f"Return ONLY valid JSON as a list of objects, each with keys: "
        f"question (string), options (list of 4 strings), answer (string, the exact correct option text). "
        f"No other text.\n\n"
        f"--- TEXT ---\n{text}"
    )
    result = _parse(_chat([{"role": "user", "content": prompt}], max_tokens=2000))
    if isinstance(result, list):
        return result
    if isinstance(result, dict) and "questions" in result:
        return result["questions"]
    return []


def extract_key_words(text: str) -> list[str]:
    prompt = (
        f"From the following reading text, extract exactly 6 key words that are "
        f"most important for understanding the passage. These should be words that an "
        f"English learner should learn. "
        f"Return ONLY valid JSON as a list of strings. "
        f"No other text.\n\n"
        f"--- TEXT ---\n{text}"
    )
    result = _parse(_chat([{"role": "user", "content": prompt}], max_tokens=300))
    if isinstance(result, list):
        return result
    return []
