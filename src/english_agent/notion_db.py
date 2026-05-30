import os
from datetime import date, datetime, timezone
from typing import Optional
from notion_client import Client

from dotenv import load_dotenv

load_dotenv()

_NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
_WORDS_DB = os.getenv("NOTION_WORDS_DB", "")
_READINGS_DB = os.getenv("NOTION_READINGS_DB", "")
_ACTIVITY_DB = os.getenv("NOTION_ACTIVITY_DB", "")


def _client() -> Client:
    return Client(auth=_NOTION_TOKEN)


# ─── helpers ───────────────────────────────────────────────────────


def _rich_text(text: str) -> list:
    return [{"type": "text", "text": {"content": text}}]


def _text_prop(props: dict, key: str, default: str = "") -> str:
    items = props.get(key, {}).get("rich_text", [])
    return items[0]["text"]["content"] if items else default


def _title_prop(props: dict, key: str = "Name", default: str = "") -> str:
    items = props.get(key, {}).get("title", [])
    return items[0]["text"]["content"] if items else default


def _num_prop(props: dict, key: str, default: int = 0) -> int:
    v = props.get(key, {}).get("number")
    return v if v is not None else default


def _select_prop(props: dict, key: str) -> str:
    s = props.get(key, {}).get("select")
    return s["name"] if s else ""


def _multi_select_prop(props: dict, key: str) -> list[str]:
    return [t["name"] for t in props.get(key, {}).get("multi_select", [])]


def _date_prop(props: dict, key: str) -> Optional[str]:
    d = props.get(key, {}).get("date")
    return d["start"] if d else None


# ─── WORDS ─────────────────────────────────────────────────────────


def word_add(
    word: str,
    translation: str,
    definition: str = "",
    example: str = "",
    tags: Optional[list[str]] = None,
    source: str = "manual",
    source_text_id: Optional[str] = None,
) -> dict:
    c = _client()
    today = date.today().isoformat()
    props = {
        "Word": {"title": [{"text": {"content": word}}]},
        "Translation": {"rich_text": _rich_text(translation)},
        "Status": {"select": {"name": "learning"}},
        "Date Added": {"date": {"start": today}},
        "Times Correct": {"number": 0},
        "Times Wrong": {"number": 0},
        "Source": {"select": {"name": source}},
    }
    if definition:
        props["Definition"] = {"rich_text": _rich_text(definition)}
    if example:
        props["Example"] = {"rich_text": _rich_text(example)}
    if tags:
        props["Tags"] = {"multi_select": [{"name": t} for t in tags]}
    if source_text_id:
        props["Source Text"] = {"relation": [{"id": source_text_id}]}

    page = c.pages.create(parent={"database_id": _WORDS_DB}, properties=props)
    return _word_from_page(page)


def _word_from_page(page: dict) -> dict:
    p = page["properties"]
    w = {
        "id": page["id"],
        "word": _title_prop(p, "Word"),
        "translation": _text_prop(p, "Translation"),
        "definition": _text_prop(p, "Definition"),
        "example": _text_prop(p, "Example"),
        "status": _select_prop(p, "Status"),
        "tags": _multi_select_prop(p, "Tags"),
        "times_correct": _num_prop(p, "Times Correct"),
        "times_wrong": _num_prop(p, "Times Wrong"),
        "date_added": _date_prop(p, "Date Added"),
        "last_reviewed": _date_prop(p, "Last Reviewed"),
        "source": _select_prop(p, "Source"),
    }
    return w


def word_get(word: str) -> Optional[dict]:
    c = _client()
    res = c.databases.query(
        database_id=_WORDS_DB,
        filter={"property": "Word", "title": {"equals": word}},
    )
    if res["results"]:
        return _word_from_page(res["results"][0])
    return None


def word_list(status: Optional[str] = None, source: Optional[str] = None) -> list[dict]:
    c = _client()
    filters = []
    if status:
        filters.append({"property": "Status", "select": {"equals": status}})
    if source:
        filters.append({"property": "Source", "select": {"equals": source}})
    filter_obj = {"and": filters} if filters else None

    res = c.databases.query(database_id=_WORDS_DB, filter=filter_obj)
    return [_word_from_page(p) for p in res["results"]]


def word_update_result(page_id: str, correct: bool):
    c = _client()
    page = c.pages.retrieve(page_id)
    p = page["properties"]
    cur_correct = _num_prop(p, "Times Correct")
    cur_wrong = _num_prop(p, "Times Wrong")
    today = date.today().isoformat()

    props = {"Last Reviewed": {"date": {"start": today}}}
    if correct:
        props["Times Correct"] = {"number": cur_correct + 1}
    else:
        props["Times Wrong"] = {"number": cur_wrong + 1}
        props["Status"] = {"select": {"name": "forgotten"}}

    total = cur_correct + cur_wrong + (1 if correct else 0)
    if total >= 3:
        ratio = (cur_correct + (1 if correct else 0)) / total
        if ratio >= 0.8:
            props["Status"] = {"select": {"name": "mastered"}}
        elif ratio >= 0.5:
            props["Status"] = {"select": {"name": "reviewing"}}

    c.pages.update(page_id=page_id, properties=props)


def word_delete(word: str) -> bool:
    c = _client()
    entry = word_get(word)
    if not entry:
        return False
    c.pages.update(page_id=entry["id"], archived=True)
    return True


# ─── READINGS ──────────────────────────────────────────────────────


def reading_add(title: str, content: str, difficulty: str = "intermediate", tags: Optional[list[str]] = None) -> dict:
    c = _client()
    today = date.today().isoformat()
    props = {
        "Title": {"title": [{"text": {"content": title}}]},
        "Content": {"rich_text": _rich_text(content)},
        "Date Added": {"date": {"start": today}},
        "Difficulty": {"select": {"name": difficulty}},
    }
    if tags:
        props["Tags"] = {"multi_select": [{"name": t} for t in tags]}
    page = c.pages.create(parent={"database_id": _READINGS_DB}, properties=props)
    return _reading_from_page(page)


def _reading_from_page(page: dict) -> dict:
    p = page["properties"]
    return {
        "id": page["id"],
        "title": _title_prop(p, "Title"),
        "content": _text_prop(p, "Content"),
        "difficulty": _select_prop(p, "Difficulty"),
        "tags": _multi_select_prop(p, "Tags"),
        "date_added": _date_prop(p, "Date Added"),
    }


def reading_list() -> list[dict]:
    c = _client()
    res = c.databases.query(database_id=_READINGS_DB)
    return [_reading_from_page(p) for p in res["results"]]


def reading_get(reading_id: str) -> Optional[dict]:
    c = _client()
    page = c.pages.retrieve(reading_id)
    return _reading_from_page(page)


# ─── ACTIVITY LOG ──────────────────────────────────────────────────


def activity_log(word_id: str, correct: bool):
    c = _client()
    now = datetime.now(timezone.utc)
    props = {
        "Name": {"title": [{"text": {"content": f"Quiz #{word_id[:8]} {now.hour}:{now.minute}"}}]},
        "Timestamp": {"date": {"start": now.isoformat()}},
        "Word": {"relation": [{"id": word_id}]},
        "Correct": {"checkbox": correct},
        "Hour": {"number": now.hour},
    }
    c.pages.create(parent={"database_id": _ACTIVITY_DB}, properties=props)


def activity_get_logs(days: int = 30) -> list[dict]:
    c = _client()
    from datetime import timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    res = c.databases.query(
        database_id=_ACTIVITY_DB,
        filter={"property": "Timestamp", "date": {"on_or_after": cutoff}},
    )
    out = []
    for p in res["results"]:
        pr = p["properties"]
        out.append({
            "id": p["id"],
            "timestamp": _date_prop(pr, "Timestamp"),
            "correct": pr.get("Correct", {}).get("checkbox", False),
            "hour": _num_prop(pr, "Hour"),
            "word_id": (pr.get("Word", {}).get("relation") or [{}])[0].get("id", ""),
        })
    return out


# ─── STATS ─────────────────────────────────────────────────────────


def stats() -> dict:
    words = word_list()
    total = len(words)
    mastered = sum(1 for w in words if w["status"] == "mastered")
    learning = sum(1 for w in words if w["status"] == "learning")
    reviewing = sum(1 for w in words if w["status"] == "reviewing")
    forgotten = sum(1 for w in words if w["status"] == "forgotten")
    total_correct = sum(w["times_correct"] for w in words)
    total_wrong = sum(w["times_wrong"] for w in words)
    attempts = total_correct + total_wrong
    accuracy = round(total_correct / attempts * 100, 1) if attempts else 0

    return {
        "total": total,
        "mastered": mastered,
        "learning": learning,
        "reviewing": reviewing,
        "forgotten": forgotten,
        "total_correct": total_correct,
        "total_wrong": total_wrong,
        "accuracy": accuracy,
    }
