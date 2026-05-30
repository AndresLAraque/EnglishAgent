from collections import defaultdict
from . import notion_db


def best_training_hours(days: int = 30) -> list[dict]:
    logs = notion_db.activity_get_logs(days=days)
    if not logs:
        return []

    by_hour: dict[int, dict] = defaultdict(lambda: {"correct": 0, "total": 0})
    for entry in logs:
        h = entry["hour"]
        by_hour[h]["total"] += 1
        if entry["correct"]:
            by_hour[h]["correct"] += 1

    results = []
    for hour, data in sorted(by_hour.items()):
        acc = round(data["correct"] / data["total"] * 100, 1) if data["total"] else 0
        results.append({
            "hour": hour,
            "total": data["total"],
            "correct": data["correct"],
            "accuracy": acc,
        })
    return results


def weak_words(min_attempts: int = 2) -> list[dict]:
    words = notion_db.word_list()
    weak = []
    for w in words:
        total = w["times_correct"] + w["times_wrong"]
        if total >= min_attempts:
            ratio = w["times_correct"] / total if total else 0
            if ratio < 0.5:
                weak.append({
                    "word": w["word"],
                    "translation": w["translation"],
                    "correct": w["times_correct"],
                    "wrong": w["times_wrong"],
                    "accuracy": round(ratio * 100, 1),
                    "status": w["status"],
                })
    weak.sort(key=lambda x: x["accuracy"])
    return weak
