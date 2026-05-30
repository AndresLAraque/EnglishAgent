import os
import logging

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes,
)

from . import notion_db, llm, quiz_engine, analyzer

load_dotenv()

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

QUIZ_STATE: dict[int, list[dict]] = {}
QUIZ_INDEX: dict[int, int] = {}
QUIZ_RESULTS: dict[int, list[bool]] = {}


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! I'm your English tutor. Here's what I can do:\n\n"
        "• Send any English word → I save it and explain it\n"
        "• /quiz — Test your vocabulary\n"
        "• /correct <sentence> — Fix grammar\n"
        "• /stats — Your progress\n"
        "• /recommend — Study tips\n"
        "• /explain <word> — Explain a saved word\n"
        "• /help — Show this message"
    )


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id

    if uid in QUIZ_STATE:
        await handle_quiz_answer(update, ctx, text)
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
    app.add_handler(CallbackQueryHandler(quiz_callback, pattern="^quiz_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print(f"Bot started for user {CHAT_ID}. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
