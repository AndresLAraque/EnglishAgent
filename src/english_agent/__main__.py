import sys
import json
import argparse

from . import notion_db, quiz_engine, analyzer, vocab_extractor, notify, llm, reading_game


def _print(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_word_add(args):
    existing = notion_db.word_get(args.word)
    if existing:
        _print({"error": f"'{args.word}' already exists", "existing": existing})
        return
    entry = notion_db.word_add(
        word=args.word,
        translation=args.translation,
        definition=args.definition or "",
        example=args.example or "",
        tags=args.tags,
    )
    _print({"ok": True, "word": entry})


def cmd_word_list(args):
    words = notion_db.word_list(status=args.status, source=args.source)
    _print({"count": len(words), "words": words})


def cmd_word_get(args):
    entry = notion_db.word_get(args.word)
    if entry:
        _print(entry)
    else:
        _print({"error": f"'{args.word}' not found"})


def cmd_word_delete(args):
    ok = notion_db.word_delete(args.word)
    _print({"ok": ok, "word": args.word})


def cmd_quiz_generate(args):
    questions = quiz_engine.generate(count=args.count)
    _print({"count": len(questions), "questions": questions})


def cmd_quiz_evaluate(args):
    result = quiz_engine.evaluate(args.word_id, args.correct)
    _print(result)


def cmd_reading_add(args):
    entry = notion_db.reading_add(
        title=args.title,
        content=args.content,
        difficulty=args.difficulty,
        tags=args.tags,
    )
    _print({"ok": True, "reading": entry})


def cmd_reading_list(args):
    readings = notion_db.reading_list()
    _print({"count": len(readings), "readings": readings})


def cmd_reading_extract(args):
    result = vocab_extractor.extract_and_save(args.reading_id, max_candidates=args.max or 20)
    _print(result)


def cmd_stats(args):
    s = notion_db.stats()
    _print(s)


def cmd_analyze_time(args):
    data = analyzer.best_training_hours(days=args.days)
    if not data:
        _print({"info": "No activity data yet. Take some quizzes first!"})
        return
    best = max(data, key=lambda x: (x["accuracy"], x["total"])) if data else None
    _print({"hours": data, "best_hour": best})


def cmd_analyze_weak(args):
    words = analyzer.weak_words(min_attempts=args.min_attempts)
    _print({"count": len(words), "weak_words": words})


def cmd_notify(args):
    result = notify.send_message(args.message)
    _print(result)


def cmd_explain(args):
    word = notion_db.word_get(args.word)
    if not word:
        _print({"error": f"'{args.word}' not found in vocabulary"})
        return
    result = llm.explain_word(word["word"], word["translation"])
    _print({"word": word["word"], "translation": word["translation"], **result})


def cmd_correct(args):
    result = llm.correct_sentence(args.sentence)
    _print(result)


def cmd_recommend(args):
    weak = analyzer.weak_words(min_attempts=args.min_attempts)
    s = notion_db.stats()
    result = llm.recommend_study(weak, s)
    _print(result)


# ─── READING GAME CLI ──────────────────────────────────────────────


def cmd_reading_game_list(args):
    games = notion_db.reading_game_list(topic=args.topic, level=args.level)
    out = []
    for g in games:
        out.append({
            "id": g["id"],
            "name": g["name"],
            "topic": g["topic"],
            "level": g["level"],
            "times_played": g["times_played"],
            "best_score": g["best_score"],
            "source": g["source"],
        })
    _print({"count": len(out), "games": out})


def cmd_reading_game_generate(args):
    topic = args.topic
    level = args.level
    print(f"Generating reading for topic '{topic}' at level '{level}'...")
    try:
        game = reading_game.fetch_or_create_game(topic=topic, level=level)
        if game:
            _print(game.to_dict())
        else:
            _print({"error": "Could not create reading game"})
    except Exception as e:
        _print({"error": str(e)})


def cmd_reading_game_import(args):
    print(f"Importing reading '{args.name}'...")
    try:
        game = reading_game.import_reading(
            name=args.name,
            content=args.content,
            topic=args.topic or "General Interest",
            level=args.level,
        )
        if game:
            _print(game.to_dict())
        else:
            _print({"error": "Could not import reading"})
    except Exception as e:
        _print({"error": str(e)})


def main():
    parser = argparse.ArgumentParser(prog="english-agent", description="English vocabulary learning assistant")
    sub = parser.add_subparsers(dest="command", required=True)

    # word
    wp = sub.add_parser("word", help="Word operations")
    wsub = wp.add_subparsers(dest="action", required=True)

    p = wsub.add_parser("add", help="Add a new word")
    p.add_argument("word", help="The word in English")
    p.add_argument("translation", help="Spanish translation")
    p.add_argument("--definition", "-d", help="English definition")
    p.add_argument("--example", "-e", help="Example sentence")
    p.add_argument("--tags", "-t", nargs="*", default=None, help="Tags")
    p.set_defaults(func=cmd_word_add)

    p = wsub.add_parser("list", help="List words")
    p.add_argument("--status", choices=["learning", "reviewing", "mastered", "forgotten"], help="Filter by status")
    p.add_argument("--source", choices=["manual", "extracted"], help="Filter by source")
    p.set_defaults(func=cmd_word_list)

    p = wsub.add_parser("get", help="Get a word by name")
    p.add_argument("word", help="The word in English")
    p.set_defaults(func=cmd_word_get)

    p = wsub.add_parser("delete", help="Delete a word")
    p.add_argument("word", help="The word in English")
    p.set_defaults(func=cmd_word_delete)

    # quiz
    qp = sub.add_parser("quiz", help="Quiz operations")
    qsub = qp.add_subparsers(dest="action", required=True)

    p = qsub.add_parser("generate", help="Generate quiz questions")
    p.add_argument("--count", "-c", type=int, default=10, help="Number of questions")
    p.set_defaults(func=cmd_quiz_generate)

    p = qsub.add_parser("evaluate", help="Record a quiz result")
    p.add_argument("word_id", help="Word page ID from question")
    p.add_argument("--correct", action=argparse.BooleanOptionalAction, default=True)
    p.set_defaults(func=cmd_quiz_evaluate)

    # reading
    rp = sub.add_parser("reading", help="Reading operations")
    rsub = rp.add_subparsers(dest="action", required=True)

    p = rsub.add_parser("add", help="Save a reading text")
    p.add_argument("title", help="Title or description")
    p.add_argument("content", help="Full text content")
    p.add_argument("--difficulty", choices=["beginner", "intermediate", "advanced"], default="intermediate")
    p.add_argument("--tags", nargs="*", default=None)
    p.set_defaults(func=cmd_reading_add)

    p = rsub.add_parser("list", help="List saved readings")
    p.set_defaults(func=cmd_reading_list)

    p = rsub.add_parser("extract", help="Extract vocabulary from a reading")
    p.add_argument("reading_id", help="Reading page ID")
    p.add_argument("--max", type=int, default=20, help="Max candidates")
    p.set_defaults(func=cmd_reading_extract)

    # stats
    sub.add_parser("stats", help="Show learning statistics").set_defaults(func=cmd_stats)

    # analyze
    ap = sub.add_parser("analyze", help="Analyze learning data")
    asub = ap.add_subparsers(dest="action", required=True)

    p = asub.add_parser("time", help="Best training hours analysis")
    p.add_argument("--days", type=int, default=30)
    p.set_defaults(func=cmd_analyze_time)

    p = asub.add_parser("weak", help="Weak words analysis")
    p.add_argument("--min-attempts", type=int, default=2)
    p.set_defaults(func=cmd_analyze_weak)

    # notify
    p = sub.add_parser("notify", help="Send a Telegram notification")
    p.add_argument("message", help="Message text (Markdown)")
    p.set_defaults(func=cmd_notify)

    # llm
    p = sub.add_parser("explain", help="Explain a word using AI")
    p.add_argument("word", help="Word to explain (must exist in vocabulary)")
    p.set_defaults(func=cmd_explain)

    p = sub.add_parser("correct", help="Correct a sentence using AI")
    p.add_argument("sentence", help="Sentence to correct")
    p.set_defaults(func=cmd_correct)

    p = sub.add_parser("recommend", help="Get AI study recommendations")
    p.add_argument("--min-attempts", type=int, default=2, help="Min attempts for weak word detection")
    p.set_defaults(func=cmd_recommend)

    # reading-game
    rgp = sub.add_parser("reading-game", help="Reading game operations")
    rgsub = rgp.add_subparsers(dest="action", required=True)

    p = rgsub.add_parser("list", help="List reading games")
    p.add_argument("--topic", help="Filter by topic")
    p.add_argument("--level", help="Filter by level")
    p.set_defaults(func=cmd_reading_game_list)

    p = rgsub.add_parser("generate", help="Generate a new AI reading game")
    p.add_argument("topic", help="Topic name")
    p.add_argument("--level", default="IELTS (6.5-7.0)", help="Difficulty level")
    p.set_defaults(func=cmd_reading_game_generate)

    p = rgsub.add_parser("import", help="Import a reading from text")
    p.add_argument("name", help="Name/title of the reading")
    p.add_argument("content", help="Full text content")
    p.add_argument("--topic", help="Topic for the reading")
    p.add_argument("--level", default="General", help="Difficulty level")
    p.set_defaults(func=cmd_reading_game_import)

    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as e:
        _print({"error": str(e)})
        sys.exit(1)


if __name__ == "__main__":
    main()
