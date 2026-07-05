import random

from . import notion_db, llm, topics


def available_weeks() -> list[int]:
    return sorted(topics.WEEKS.keys())


def random_connectors(count: int = 3) -> list[str]:
    return random.sample(topics.CONNECTORS, min(count, len(topics.CONNECTORS)))


def grade_and_save(topic: dict, text: str, user_id: int = 0) -> dict:
    result = llm.grade_writing(topic["name"], text)

    score = result.get("score", 0)
    corrected_text = result.get("corrected_text", text)
    feedback = result.get("feedback", "")
    mistakes = result.get("mistakes", []) or []
    strengths = result.get("strengths", []) or []

    submission = notion_db.submission_add(
        topic=topic,
        original_text=text,
        corrected_text=corrected_text,
        score=score,
        feedback=feedback,
        mistake_count=len(mistakes),
        strengths=strengths,
        user_id=user_id,
    )

    for m in mistakes:
        notion_db.mistake_add(
            wrong=m.get("wrong", ""),
            correct=m.get("correct", ""),
            explanation=m.get("explanation", ""),
            category=m.get("category", "other"),
            submission_id=submission["id"],
        )

    notion_db.topic_mark_used(topic["id"])

    return {
        "score": score,
        "corrected_text": corrected_text,
        "feedback": feedback,
        "mistakes": mistakes,
        "strengths": strengths,
        "submission": submission,
    }


def next_review_batch(limit: int = 5) -> list[dict]:
    candidates = notion_db.mistake_list(status="new") + notion_db.mistake_list(status="reviewing")
    candidates.sort(key=lambda m: m["last_reviewed"] or m["date_added"] or "")
    batch = candidates[:limit * 2]
    random.shuffle(batch)
    return batch[:limit]


def reset_cycle():
    notion_db.topic_reset_all()
