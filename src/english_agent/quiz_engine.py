import random
from typing import Optional

from . import notion_db


class Question:
    def __init__(self, word_entry: dict, q_type: str):
        self.word_entry = word_entry
        self.q_type = q_type

    @property
    def correct_answer(self) -> str:
        return self.word_entry["word"] if self.q_type in ("mc_word", "type_answer") else self.word_entry["translation"]

    @property
    def prompt(self) -> str:
        w = self.word_entry
        if self.q_type == "mc_word":
            return f"What is the English word for «{w['translation']}»?"
        elif self.q_type == "mc_translation":
            return f"What is the translation of «{w['word']}»?"
        else:
            return f"Type the English word for «{w['translation']}»"

    @property
    def help_text(self) -> str:
        w = self.word_entry
        parts = []
        if w.get("definition"):
            parts.append(f"Definición: {w['definition']}")
        if w.get("example"):
            parts.append(f"Ejemplo: {w['example']}")
        return "\n".join(parts)


def _distractors(correct: str, all_words: list[dict], key: str = "word", count: int = 3) -> list[str]:
    candidates = [w[key] for w in all_words if w[key].lower() != correct.lower() and w[key]]
    if len(candidates) < count:
        return candidates
    return random.sample(candidates, count)


def build_options(question: Question, all_words: list[dict]) -> Optional[list[str]]:
    correct = question.correct_answer
    if question.q_type == "mc_word":
        dist = _distractors(correct, all_words, key="word")
    elif question.q_type == "mc_translation":
        dist = _distractors(correct, all_words, key="translation")
    else:
        return None
    if len(dist) < 3:
        return None
    opts = dist + [correct]
    random.shuffle(opts)
    return opts


def generate(count: int = 10) -> list[dict]:
    all_words = notion_db.word_list()
    if not all_words:
        return []

    learning = [w for w in all_words if w["status"] in ("learning", "forgotten")]
    reviewing = [w for w in all_words if w["status"] == "reviewing"]
    mastered = [w for w in all_words if w["status"] == "mastered"]

    pool = learning + reviewing * 2 + mastered
    if not pool:
        pool = all_words

    selected = random.sample(pool, min(count, len(pool)))
    questions = []

    for w in selected:
        r = random.random()
        if r < 0.35:
            questions.append(Question(w, "type_answer"))
        elif r < 0.65:
            questions.append(Question(w, "mc_word"))
        else:
            questions.append(Question(w, "mc_translation"))

    random.shuffle(questions)

    out = []
    for q in questions:
        opts = build_options(q, all_words)
        item = {
            "word_id": q.word_entry["id"],
            "word": q.word_entry["word"],
            "translation": q.word_entry["translation"],
            "type": q.q_type,
            "prompt": q.prompt,
            "correct_answer": q.correct_answer,
            "help_text": q.help_text,
        }
        if opts:
            item["options"] = opts
        out.append(item)
    return out


def evaluate(word_id: str, correct: bool) -> dict:
    notion_db.word_update_result(word_id, correct)
    notion_db.activity_log(word_id, correct)
    return {"word_id": word_id, "correct": correct}
