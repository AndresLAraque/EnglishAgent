import json
import random
from datetime import datetime, timezone
from typing import Optional

from . import notion_db, llm, topics


class ReadingGame:
    def __init__(self, game_data: dict):
        self.id = game_data["id"]
        self.name = game_data["name"]
        self.content = game_data["content"]
        self.level = game_data["level"]
        self.topic = game_data["topic"]
        self.key_words = game_data["key_words"]
        self.times_played = game_data["times_played"]
        self.best_score = game_data["best_score"]
        self.best_time = game_data["best_time"]
        self.date_added = game_data["date_added"]
        self.last_played = game_data["last_played"]
        self.source = game_data["source"]

        questions_raw = game_data.get("questions_json", "[]")
        try:
            self.questions = json.loads(questions_raw) if questions_raw else []
        except (json.JSONDecodeError, TypeError):
            self.questions = []

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "content": self.content,
            "level": self.level,
            "topic": self.topic,
            "key_words": self.key_words,
            "times_played": self.times_played,
            "best_score": self.best_score,
            "best_time": self.best_time,
            "date_added": self.date_added,
            "last_played": self.last_played,
            "source": self.source,
            "questions_count": len(self.questions),
        }

    def score_answers(self, user_answers: list[str]) -> dict:
        correct = 0
        total = len(self.questions)
        details = []
        for i, q in enumerate(self.questions):
            answer = user_answers[i] if i < len(user_answers) else ""
            is_correct = answer.strip().lower() == q.get("answer", "").strip().lower()
            if is_correct:
                correct += 1
            details.append({
                "question": q.get("question", ""),
                "options": q.get("options", []),
                "correct_answer": q.get("answer", ""),
                "user_answer": answer,
                "is_correct": is_correct,
            })
        percentage = round(correct / total * 100, 1) if total else 0
        return {
            "score": correct,
            "total": total,
            "percentage": percentage,
            "details": details,
        }


def _today_topic() -> str:
    weekday = datetime.now(timezone.utc).weekday()
    all_topics = [t for week in topics.READING_WEEKS.values() for t in week]
    if not all_topics:
        return "General Interest"
    return all_topics[weekday % len(all_topics)]


def fetch_or_create_game(topic: Optional[str] = None, level: Optional[str] = None) -> Optional[ReadingGame]:
    topic = topic or _today_topic()
    level = level or "IELTS (6.5-7.0)"

    existing = notion_db.reading_game_list(topic=topic, level=level)
    if existing:
        newest = existing[0]
        return ReadingGame(newest)

    if llm.engine_available():
        result = llm.generate_reading(topic, level)
        questions = llm.generate_questions(result["content"], topics.QUESTIONS_PER_GAME)
        key_words = llm.extract_key_words(result["content"])[:6]
        key_words = [kw.strip().rstrip(".,!?") for kw in key_words]

        game_data = notion_db.reading_game_add(
            name=result["title"],
            content=result["content"],
            level=level,
            topic=topic,
            questions=questions,
            key_words=key_words,
            source="ai_generated",
        )
        return ReadingGame(game_data)

    return None


READING_WPM = 180
ANSWER_SECONDS_PER_QUESTION = 45


def reading_time_seconds(content: str) -> int:
    word_count = len(content.split())
    return max(60, (word_count // READING_WPM) * 60)


def answer_time_seconds(question_count: int) -> int:
    return question_count * ANSWER_SECONDS_PER_QUESTION


def fetch_by_id(game_id: str) -> Optional[ReadingGame]:
    data = notion_db.reading_game_get(game_id)
    if data:
        return ReadingGame(data)
    return None


def update_play_stats(game_id: str, score: int, time_seconds: int):
    notion_db.reading_game_update_play(game_id, score, time_seconds)


def import_reading(name: str, content: str, topic: str, level: str = "General") -> Optional[ReadingGame]:
    questions = llm.generate_questions(content, topics.QUESTIONS_PER_GAME)
    key_words = llm.extract_key_words(content)[:6]
    key_words = [kw.strip().rstrip(".,!?") for kw in key_words]

    game_data = notion_db.reading_game_add(
        name=name,
        content=content,
        level=level,
        topic=topic,
        questions=questions,
        key_words=key_words,
        source="imported",
    )
    return ReadingGame(game_data)
