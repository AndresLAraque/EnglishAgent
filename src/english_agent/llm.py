import os
import json
import requests

from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")


SYSTEM_PROMPT = "You are an English tutor for Spanish speakers. Only use English and Spanish. Never use Chinese or any other language."


def _chat(messages: list[dict], **kwargs) -> str:
    url = f"{OLLAMA_BASE_URL}/api/chat"
    full = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    payload = {
        "model": OLLAMA_MODEL,
        "messages": full,
        "stream": False,
        "options": {"num_predict": kwargs.get("max_tokens", 300)},
    }
    resp = requests.post(url, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


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


def explain_word(word: str, translation: str) -> dict:
    prompt = (
        f"Explain the word '{word}' ({translation} in Spanish). "
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
