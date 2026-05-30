import os
import requests
from dotenv import load_dotenv

load_dotenv()

_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def send_message(text: str, parse_mode: str = "Markdown") -> dict:
    if not _TOKEN or not _CHAT_ID:
        return {"error": "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env"}
    url = f"https://api.telegram.org/bot{_TOKEN}/sendMessage"
    payload = {"chat_id": _CHAT_ID, "text": text, "parse_mode": parse_mode}
    resp = requests.post(url, json=payload, timeout=10)
    if resp.status_code != 200:
        return {"error": resp.text}
    return {"ok": True, "result": resp.json()}
