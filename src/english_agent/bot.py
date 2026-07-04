import os
import logging

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes,
)

from . import notion_db, llm, quiz_engine, analyzer, writing_engine

load_dotenv()

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

QUIZ_STATE: dict[int, list[dict]] = {}
QUIZ_INDEX: dict[int, int] = {}
QUIZ_RESULTS: dict[int, list[bool]] = {}

WRITING_STATE: dict[int, dict] = {}
REVIEW_STATE: dict[int, dict] = {}


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! I'm your English tutor. Here's what I can do:\n\n"
        "• /menu — Choose a study mode (vocabulary, writing, mistake review)\n"
        "• Send any English word → I save it and explain it\n"
        "• /quiz — Test your vocabulary\n"
        "• /correct <sentence> — Fix grammar\n"
        "• /stats — Your progress\n"
        "• /recommend — Study tips\n"
        "• /explain <word> — Explain a saved word\n"
        "• /mistakes — Review your writing mistakes\n"
        "• /help — Show this message"
    )


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id

    if uid in QUIZ_STATE:
        await handle_quiz_answer(update, ctx, text)
        return

    if uid in WRITING_STATE:
        await handle_writing_submission(update, ctx, text)
        return

    existing = notion_db.word_get(text)
    if existing:
        msg = (
            f"Already in your vocabulary: *{existing['word']}*\n"
            f"Translation: {existing['translation']}\n"
            f"Status: {existing['status']}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    await update.message.reply_text(f"Learning \"{text}\" — asking AI for translation...")
    try:
        result = llm.explain_word(text, "")
        translation = result.get("translation", result.get("explanation", text))
        explanation = result.get("explanation", "")
        example = result.get("example", "")
        synonyms = result.get("synonyms", [])

        notion_db.word_add(text, translation, definition=explanation, example=example)

        msg = f"✅ Saved: *{text}* → {translation}"
        if explanation:
            msg += f"\n📖 {explanation}"
        if example:
            msg += f"\n💬 _{example}_"
        if synonyms:
            msg += f"\n🔗 Synonyms: {', '.join(synonyms[:3])}"
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = " ".join(ctx.args)
    if not text:
        await update.message.reply_text("Usage: /add <word> [translation]")
        return

    parts = text.rsplit(" ", 1)
    word = parts[0]
    translation = parts[1] if len(parts) > 1 else ""

    existing = notion_db.word_get(word)
    if existing:
        await update.message.reply_text(f"Already exists: {word} → {existing['translation']}")
        return

    if translation:
        notion_db.word_add(word, translation, source="manual")
        await update.message.reply_text(f"✅ Saved: *{word}* → {translation}", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"Asking AI about \"{word}\"...")
        result = llm.explain_word(word, "")
        t = result.get("translation", "")
        explanation = result.get("explanation", "")
        example = result.get("example", "")
        notion_db.word_add(word, t, definition=explanation, example=example)
        msg = f"✅ Saved: *{word}* → {t}"
        if explanation:
            msg += f"\n📖 {explanation}"
        if example:
            msg += f"\n💬 _{example}_"
        await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_quiz(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    questions = quiz_engine.generate(count=5)
    if not questions:
        await update.message.reply_text("No words in your vocabulary yet. Add some first!")
        return

    QUIZ_STATE[uid] = questions
    QUIZ_INDEX[uid] = 0
    QUIZ_RESULTS[uid] = []
    await send_question(update, ctx, uid)


async def send_question(update: Update, ctx: ContextTypes.DEFAULT_TYPE, uid: int):
    questions = QUIZ_STATE[uid]
    idx = QUIZ_INDEX[uid]
    if idx >= len(questions):
        await finish_quiz(update, ctx, uid)
        return

    q = questions[idx]
    total = len(questions)
    text = f"*Question {idx + 1}/{total}*\n{q['prompt']}"

    keyboard = None
    if q.get("options"):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(opt, callback_data=f"quiz_{opt}")]
            for opt in q["options"]
        ])

    msg = await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
    ctx.user_data["last_quiz_msg_id"] = msg.message_id


async def handle_quiz_answer(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str):
    uid = update.effective_user.id
    questions = QUIZ_STATE[uid]
    idx = QUIZ_INDEX[uid]
    q = questions[idx]

    correct = text.strip().lower() == q["correct_answer"].lower()
    QUIZ_RESULTS[uid].append(correct)

    quiz_engine.evaluate(q["word_id"], correct)

    if correct:
        await update.message.reply_text("✅ Correct!")
    else:
        await update.message.reply_text(f"❌ The answer was: *{q['correct_answer']}*", parse_mode="Markdown")

    QUIZ_INDEX[uid] += 1
    await send_question(update, ctx, uid)


async def quiz_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    data = query.data

    if not data.startswith("quiz_"):
        return

    answer = data[5:]
    questions = QUIZ_STATE.get(uid, [])
    idx = QUIZ_INDEX.get(uid, 0)
    if idx >= len(questions):
        return

    q = questions[idx]
    correct = answer.strip().lower() == q["correct_answer"].lower()
    QUIZ_RESULTS.setdefault(uid, []).append(correct)

    quiz_engine.evaluate(q["word_id"], correct)

    if correct:
        await query.edit_message_text(f"✅ Correct!\n\n{q['prompt']}\n→ *{q['correct_answer']}*", parse_mode="Markdown")
    else:
        await query.edit_message_text(f"❌ The answer was: *{q['correct_answer']}*\n\n{q['prompt']}", parse_mode="Markdown")

    QUIZ_INDEX[uid] = idx + 1
    await send_question_callback(query, ctx, uid)


async def send_question_callback(query, ctx: ContextTypes.DEFAULT_TYPE, uid: int):
    questions = QUIZ_STATE[uid]
    idx = QUIZ_INDEX[uid]
    if idx >= len(questions):
        await finish_quiz_callback(query, ctx, uid)
        return

    q = questions[idx]
    total = len(questions)
    text = f"*Question {idx + 1}/{total}*\n{q['prompt']}"

    keyboard = None
    if q.get("options"):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(opt, callback_data=f"quiz_{opt}")]
            for opt in q["options"]
        ])

    await query.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def finish_quiz(update: Update, ctx: ContextTypes.DEFAULT_TYPE, uid: int):
    results = QUIZ_RESULTS.get(uid, [])
    total = len(results)
    correct = sum(results)
    pct = round(correct / total * 100) if total else 0

    stats = notion_db.stats()
    msg = (
        f"🏁 *Quiz Complete!*\n"
        f"Score: {correct}/{total} ({pct}%)\n\n"
        f"📊 *Overall Progress:*\n"
        f"Total words: {stats['total']}\n"
        f"Mastered: {stats['mastered']}\n"
        f"Learning: {stats['learning']}\n"
        f"Accuracy: {stats['accuracy']}%"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

    del QUIZ_STATE[uid]
    del QUIZ_INDEX[uid]
    del QUIZ_RESULTS[uid]


async def finish_quiz_callback(query, ctx: ContextTypes.DEFAULT_TYPE, uid: int):
    results = QUIZ_RESULTS.get(uid, [])
    total = len(results)
    correct = sum(results)
    pct = round(correct / total * 100) if total else 0

    stats = notion_db.stats()
    msg = (
        f"🏁 *Quiz Complete!*\n"
        f"Score: {correct}/{total} ({pct}%)\n\n"
        f"📊 *Overall Progress:*\n"
        f"Total words: {stats['total']}\n"
        f"Mastered: {stats['mastered']}\n"
        f"Learning: {stats['learning']}\n"
        f"Accuracy: {stats['accuracy']}%"
    )
    await query.message.reply_text(msg, parse_mode="Markdown")

    del QUIZ_STATE[uid]
    del QUIZ_INDEX[uid]
    del QUIZ_RESULTS[uid]


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    s = notion_db.stats()
    msg = (
        f"📊 *Your Progress*\n"
        f"Total words: {s['total']}\n"
        f"Mastered: {s['mastered']}\n"
        f"Reviewing: {s['reviewing']}\n"
        f"Learning: {s['learning']}\n"
        f"Forgotten: {s['forgotten']}\n"
        f"Accuracy: {s['accuracy']}%"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_explain(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    word = " ".join(ctx.args)
    if not word:
        await update.message.reply_text("Usage: /explain <word>")
        return
    entry = notion_db.word_get(word)
    if not entry:
        await update.message.reply_text(f"'{word}' not found in your vocabulary.")
        return
    result = llm.explain_word(entry["word"], entry["translation"])
    msg = f"*{result.get('word', entry['word'])}*\n"
    if "explanation" in result:
        msg += f"📖 {result['explanation']}\n"
    if "example" in result:
        msg += f"💬 _{result['example']}_\n"
    if "synonyms" in result:
        msg += f"🔗 {', '.join(result['synonyms'][:3])}"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_correct(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    sentence = " ".join(ctx.args)
    if not sentence:
        await update.message.reply_text("Usage: /correct <sentence>")
        return
    result = llm.correct_sentence(sentence)
    corrected = result.get("corrected", "")
    explanation = result.get("explanation", "")
    msg = f"✏️ *Correction:* {corrected}"
    if explanation:
        msg += f"\n📝 {explanation}"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_recommend(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    weak = analyzer.weak_words(min_attempts=1)
    s = notion_db.stats()
    if not weak:
        await update.message.reply_text("Keep studying! Take some quizzes first to get personalized tips.")
        return
    result = llm.recommend_study(weak, s)
    msg = ""
    if "tip" in result:
        msg += f"💡 *Tip:* {result['tip']}\n\n"
    if "focus_words" in result:
        words = "\n".join(f"• {w}" for w in result["focus_words"])
        msg += f"🎯 *Focus on:*\n{words}\n\n"
    if "encouragement" in result:
        msg += f"🔥 {result['encouragement']}"
    await update.message.reply_text(msg, parse_mode="Markdown")


def _chunk_text(text: str, size: int = 3500) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


# ─── STUDY MENU ────────────────────────────────────────────────────


async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Vocabulario", callback_data="mode_vocab")],
        [InlineKeyboardButton("✍️ Escritura", callback_data="mode_write")],
        [InlineKeyboardButton("🔁 Repasar errores", callback_data="mode_review")],
        [InlineKeyboardButton("📊 Stats", callback_data="mode_stats")],
    ])
    await update.message.reply_text("¿Cómo quieres estudiar hoy?", reply_markup=keyboard)


async def show_week_menu(query):
    weeks = writing_engine.available_weeks()
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"Week {w}", callback_data=f"week_{w}")] for w in weeks]
    )
    await query.edit_message_text("✍️ Elige una semana:", reply_markup=keyboard)


async def send_combined_stats(query):
    s = notion_db.stats()
    writing_line = ""
    try:
        all_topics = notion_db.topic_list()
        used = sum(1 for t in all_topics if t["status"] == "used")
        all_mistakes = notion_db.mistake_list()
        mastered = sum(1 for m in all_mistakes if m["status"] == "mastered")
        writing_line = (
            f"\n*Escritura:*\n"
            f"Temas completados: {used}/{len(all_topics)}\n"
            f"Errores dominados: {mastered}/{len(all_mistakes)}\n"
        )
    except Exception:
        pass

    msg = (
        f"📊 *Tu Progreso*\n\n"
        f"*Vocabulario:*\n"
        f"Total: {s['total']} | Mastered: {s['mastered']} | Accuracy: {s['accuracy']}%\n"
        f"{writing_line}"
    )
    await query.edit_message_text(msg, parse_mode="Markdown")


async def menu_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    mode = query.data

    if mode == "mode_vocab":
        await query.edit_message_text(
            "📚 *Modo Vocabulario*\n\n"
            "• Envía cualquier palabra en inglés para guardarla\n"
            "• /quiz — Pon a prueba tu vocabulario\n"
            "• /correct <frase> — Corrige gramática\n"
            "• /explain <palabra> — Explica una palabra guardada\n"
            "• /recommend — Consejos de estudio\n"
            "• /add <palabra> — Agrega manualmente",
            parse_mode="Markdown",
        )
    elif mode == "mode_write":
        await show_week_menu(query)
    elif mode == "mode_review":
        await start_review(update.effective_user.id, query.edit_message_text)
    elif mode == "mode_stats":
        await send_combined_stats(query)


# ─── WRITING PRACTICE ──────────────────────────────────────────────


async def week_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    week = int(query.data.split("_", 1)[1])

    try:
        entries = notion_db.topic_list(week=week)
        all_topics = notion_db.topic_list()
    except Exception as e:
        await query.edit_message_text(f"Error loading topics: {e}")
        return

    if not entries:
        await query.edit_message_text(f"No hay temas para la Week {week} todavía.")
        return

    buttons = [
        [InlineKeyboardButton(
            f"✅ {t['name']}" if t["status"] == "used" else t["name"],
            callback_data=f"topic_{t['id']}",
        )]
        for t in entries
    ]

    if all_topics and all(t["status"] == "used" for t in all_topics):
        buttons.append([InlineKeyboardButton("🔄 Reiniciar ciclo", callback_data="resettopics")])

    await query.edit_message_text(
        f"✍️ *Week {week}* — elige un tema:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


async def topic_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    topic_id = query.data.split("_", 1)[1]

    topic = notion_db.topic_get(topic_id)
    if not topic:
        await query.edit_message_text("Topic not found.")
        return

    WRITING_STATE[uid] = {"topic": topic}
    connectors = writing_engine.random_connectors(3)

    msg = (
        f"✍️ *{topic['name']}*\n\n"
        f"Escribe tu texto sobre este tema y envíalo como mensaje.\n\n"
        f"💡 Intenta usar: {', '.join(connectors)}"
    )
    await query.edit_message_text(msg, parse_mode="Markdown")


async def reset_topics_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        writing_engine.reset_cycle()
        await query.edit_message_text("🔄 Ciclo reiniciado. Todos los temas están disponibles de nuevo. Usa /menu para empezar.")
    except Exception as e:
        await query.edit_message_text(f"Error: {e}")


async def cmd_reset_topics(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        writing_engine.reset_cycle()
        await update.message.reply_text("🔄 Ciclo reiniciado. Todos los temas están disponibles de nuevo.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def handle_writing_submission(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str):
    uid = update.effective_user.id
    topic = WRITING_STATE.pop(uid)["topic"]

    await update.message.reply_text("⏳ Calificando tu texto...")
    try:
        result = writing_engine.grade_and_save(topic, text)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
        return

    mistakes = result["mistakes"]
    msg = f"📊 *Score: {result['score']}/100*\n\n"

    if mistakes:
        msg += "*Errores encontrados:*\n\n"
        for m in mistakes[:8]:
            msg += (
                f"❌ {m.get('wrong', '')}\n"
                f"✅ {m.get('correct', '')}\n"
                f"💡 {m.get('explanation', '')}\n\n"
            )
        if len(mistakes) > 8:
            msg += f"_+{len(mistakes) - 8} más guardados en tu banco de errores_\n\n"
    else:
        msg += "🎉 ¡No se encontraron errores!\n\n"

    if result.get("feedback"):
        msg += f"💬 *Feedback:* {result['feedback']}"

    await update.message.reply_text(msg, parse_mode="Markdown")

    corrected = result.get("corrected_text", "")
    if corrected:
        for i, chunk in enumerate(_chunk_text(corrected)):
            title = "📝 *Texto corregido:*\n" if i == 0 else ""
            await update.message.reply_text(f"{title}{chunk}", parse_mode="Markdown")


# ─── MISTAKE REVIEW (flashcards) ────────────────────────────────────


async def cmd_mistakes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await start_review(uid, update.message.reply_text)


async def start_review(uid: int, send):
    try:
        queue = writing_engine.next_review_batch(limit=5)
    except Exception as e:
        await send(f"Error: {e}")
        return

    if not queue:
        await send("🎉 ¡No hay errores pendientes para repasar! Sigue escribiendo 💪")
        return

    REVIEW_STATE[uid] = {"queue": queue, "index": 0, "remembered": 0}
    await send_flashcard(uid, send)


async def send_flashcard(uid: int, send):
    state = REVIEW_STATE[uid]
    idx = state["index"]
    queue = state["queue"]
    if idx >= len(queue):
        await finish_review(uid, send)
        return

    m = queue[idx]
    total = len(queue)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔍 Mostrar respuesta", callback_data=f"reveal_{idx}")]])
    await send(f"*Card {idx + 1}/{total}*\n❌ {m['wrong']}", parse_mode="Markdown", reply_markup=keyboard)


async def finish_review(uid: int, send):
    state = REVIEW_STATE.pop(uid, {})
    total = len(state.get("queue", []))
    remembered = state.get("remembered", 0)
    await send(f"🏁 *Repaso completo!*\nRecordaste {remembered}/{total}", parse_mode="Markdown")


async def reveal_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    idx = int(query.data.split("_", 1)[1])

    state = REVIEW_STATE.get(uid)
    if not state or idx != state["index"]:
        return

    m = state["queue"][idx]
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Lo sabía", callback_data=f"knew_{idx}_1"),
        InlineKeyboardButton("❌ No lo sabía", callback_data=f"knew_{idx}_0"),
    ]])
    msg = f"✅ {m['correct']}\n💡 {m.get('explanation', '')}"
    await query.edit_message_text(msg, reply_markup=keyboard)


async def knew_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    _, idx_str, remembered_str = query.data.split("_")
    idx = int(idx_str)
    remembered = remembered_str == "1"

    state = REVIEW_STATE.get(uid)
    if not state or idx != state["index"]:
        return

    m = state["queue"][idx]
    try:
        notion_db.mistake_update_review(m["id"], remembered)
    except Exception:
        pass

    if remembered:
        state["remembered"] += 1
        await query.edit_message_text(f"✅ {m['correct']}\n💡 {m.get('explanation', '')}\n\n👍 ¡Bien hecho!")
    else:
        await query.edit_message_text(f"✅ {m['correct']}\n💡 {m.get('explanation', '')}\n\n📌 Sigue practicando esta.")

    state["index"] += 1
    await send_flashcard(uid, query.message.reply_text)


def main():
    if not TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not set in .env")
        return

    auth = filters.User(user_id=int(CHAT_ID)) if CHAT_ID and CHAT_ID.isdigit() else None

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start, filters=auth))
    app.add_handler(CommandHandler("help", start, filters=auth))
    app.add_handler(CommandHandler("add", cmd_add, filters=auth))
    app.add_handler(CommandHandler("quiz", cmd_quiz, filters=auth))
    app.add_handler(CommandHandler("stats", cmd_stats, filters=auth))
    app.add_handler(CommandHandler("explain", cmd_explain, filters=auth))
    app.add_handler(CommandHandler("correct", cmd_correct, filters=auth))
    app.add_handler(CommandHandler("recommend", cmd_recommend, filters=auth))
    app.add_handler(CommandHandler("menu", cmd_menu, filters=auth))
    app.add_handler(CommandHandler("mistakes", cmd_mistakes, filters=auth))
    app.add_handler(CommandHandler("resettopics", cmd_reset_topics, filters=auth))
    app.add_handler(CallbackQueryHandler(quiz_callback, pattern="^quiz_"))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^mode_"))
    app.add_handler(CallbackQueryHandler(week_callback, pattern="^week_"))
    app.add_handler(CallbackQueryHandler(topic_callback, pattern="^topic_"))
    app.add_handler(CallbackQueryHandler(reset_topics_callback, pattern="^resettopics$"))
    app.add_handler(CallbackQueryHandler(reveal_callback, pattern="^reveal_"))
    app.add_handler(CallbackQueryHandler(knew_callback, pattern="^knew_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print(f"Bot started for user {CHAT_ID}. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
