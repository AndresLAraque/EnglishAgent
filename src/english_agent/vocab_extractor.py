import re

from . import notion_db


_COMMON_WORDS = {
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i",
    "it", "for", "not", "on", "with", "he", "as", "you", "do", "at",
    "this", "but", "his", "by", "from", "they", "we", "say", "her", "she",
    "or", "an", "will", "my", "one", "all", "would", "there", "their", "what",
    "so", "up", "out", "if", "about", "who", "get", "which", "go", "me",
    "when", "make", "can", "like", "time", "no", "just", "him", "know", "take",
    "people", "into", "year", "your", "good", "some", "could", "them", "see", "other",
    "than", "then", "now", "look", "only", "come", "its", "over", "think", "also",
    "back", "after", "use", "two", "how", "our", "work", "first", "well", "way",
    "even", "new", "want", "because", "any", "these", "give", "day", "most", "us",
    "every", "much", "may", "very", "here", "thing", "many", "has", "been", "were",
    "am", "are", "is", "was", "were", "been", "being", "have", "has", "had",
    "do", "does", "did", "doing", "shall", "will", "would", "should", "can", "could",
    "may", "might", "must", "need", "dare", "ought", "used", "this", "that", "these",
    "those", "each", "every", "all", "both", "few", "several", "some", "any", "no",
    "none", "nothing", "everything", "something", "anything", "here", "there", "where",
    "before", "after", "above", "below", "between", "through", "during", "without",
    "against", "within", "along", "among", "around", "about", "across", "behind",
    "beneath", "beside", "beyond", "down", "inside", "near", "off", "outside", "over",
    "past", "through", "throughout", "toward", "towards", "under", "underneath", "up",
    "upon", "with", "within", "without",
}


def extract_candidates(text: str, max_candidates: int = 20) -> list[dict]:
    cleaned = re.sub(r"[^a-zA-ZáéíóúñüÁÉÍÓÚÑÜ\s]", " ", text.lower())
    words = cleaned.split()
    word_counts: dict[str, int] = {}
    for w in words:
        if len(w) <= 2:
            continue
        if w in _COMMON_WORDS:
            continue
        word_counts[w] = word_counts.get(w, 0) + 1

    sorted_words = sorted(word_counts.items(), key=lambda x: -x[1])

    existing = {w["word"].lower() for w in notion_db.word_list()}

    candidates = []
    for w, count in sorted_words:
        if len(candidates) >= max_candidates:
            break
        if w in existing:
            continue
        candidates.append({"word": w, "count": count})

    return candidates


def extract_and_save(reading_id: str, max_candidates: int = 20) -> dict:
    reading = notion_db.reading_get(reading_id)
    if not reading:
        return {"error": f"Reading {reading_id} not found"}

    candidates = extract_candidates(reading["content"], max_candidates=max_candidates)
    added = []
    for c in candidates:
        entry = notion_db.word_add(
            word=c["word"],
            translation="",
            source="extracted",
            source_text_id=reading_id,
            tags=["auto-extracted"],
        )
        added.append({"word": c["word"], "id": entry["id"]})

    return {"reading_title": reading["title"], "candidates_found": len(candidates), "added": added}
