import os
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes,
)

from . import notion_db, llm, quiz_engine, analyzer, writing_engine, reading_game
from . import notify as notify_mod
from . import scheduler
from .topics import READING_WEEKS

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

READING_STATE: dict[int, dict] = {}


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    model_name = llm.get_active_model()
    provider = llm.get_active_provider()
    await update.message.reply_text(
        f"Hello! I'm your English tutor.\n"
        f"🤖 Model: {provider} ({model_name})\n\n"
        "• /menu — Choose a study mode (vocabulary, writing, mistake review)\n"
        "• Send any English word → I save it and explain it\n"
        "• /quiz — Test your vocabulary\n"
        "• /read — Timed IELTS reading practice\n"
        "• /correct <sentence> — Fix grammar\n"
        "• /stats — Your progress\n"
        "• /recommend — Study tips\n"
        "• /explain <word> — Explain a saved word\n"
        "• /mistakes — Review your writing mistakes\n"
        "• /model — Switch AI model\n"
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


async def cmd_model(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    models = llm.list_models()
    current = llm.get_active_provider()
    buttons = []
    for m in models:
        label = f"{'✅ ' if m['id'] == current else ''}{m['name']}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"model_{m['id']}")])
    buttons.append([InlineKeyboardButton("❌ Close", callback_data="model_close")])
    await update.message.reply_text(
        f"🤖 *Current model:* {current} ({llm.get_active_model()})\n\nSelect a model:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


async def model_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "model_close":
        await query.edit_message_text("✅ No changes made.")
        return
    provider = data.split("_", 1)[1]
    if llm.set_provider(provider):
        await query.edit_message_text(
            f"✅ Switched to *{provider}* ({llm.get_active_model()}).",
            parse_mode="Markdown",
        )
    else:
        await query.edit_message_text("❌ Could not switch. Did you set the API key in .env?")


async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    provider = llm.get_active_provider()
    model_name = llm.get_active_model()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Vocabulary", callback_data="mode_vocab")],
        [InlineKeyboardButton("✍️ Writing", callback_data="mode_write")],
        [InlineKeyboardButton("📖 Reading", callback_data="mode_read")],
        [InlineKeyboardButton("🔁 Mistake Review", callback_data="mode_review")],
        [InlineKeyboardButton("📊 Stats", callback_data="mode_stats")],
    ])
    await update.message.reply_text(
        f"🤖 *{provider}* — _{model_name}_\n\nHow would you like to study today?",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def show_week_menu(query):
    weeks = writing_engine.available_weeks()
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"Week {w}", callback_data=f"week_{w}")] for w in weeks]
    )
    await query.edit_message_text("✍️ Pick a week:", reply_markup=keyboard)


async def send_combined_stats(query):
    s = notion_db.stats()
    writing_line = ""
    try:
        all_topics = notion_db.topic_list()
        used = sum(1 for t in all_topics if t["status"] == "used")
        all_mistakes = notion_db.mistake_list()
        mastered = sum(1 for m in all_mistakes if m["status"] == "mastered")
        writing_line = (
            f"\n*Writing:*\n"
            f"Topics completed: {used}/{len(all_topics)}\n"
            f"Mistakes mastered: {mastered}/{len(all_mistakes)}\n"
        )
    except Exception:
        pass

    msg = (
        f"📊 *Your Progress*\n\n"
        f"*Vocabulary:*\n"
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
            "📚 *Vocabulary Mode*\n\n"
            "• Send any English word to save it\n"
            "• /quiz — Test your vocabulary\n"
            "• /correct <sentence> — Fix grammar\n"
            "• /explain <word> — Explain a saved word\n"
            "• /recommend — Study tips\n"
            "• /add <word> — Add manually",
            parse_mode="Markdown",
        )
    elif mode == "mode_read":
        await show_reading_weeks(query.edit_message_text)
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
        await query.edit_message_text(f"No topics for Week {week} yet.")
        return

    buttons = [
        [InlineKeyboardButton(
            f"✅ {t['name']}" if t["status"] == "used" else t["name"],
            callback_data=f"topic_{t['id']}",
        )]
        for t in entries
    ]

    if all_topics and all(t["status"] == "used" for t in all_topics):
        buttons.append([InlineKeyboardButton("🔄 Reset cycle", callback_data="resettopics")])

    await query.edit_message_text(
        f"✍️ *Week {week}* — pick a topic:",
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
        f"Write your text about this topic and send it as a message.\n\n"
        f"💡 Try using: {', '.join(connectors)}"
    )
    await query.edit_message_text(msg, parse_mode="Markdown")


async def reset_topics_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        writing_engine.reset_cycle()
        await query.edit_message_text("🔄 Cycle reset. All topics are available again. Use /menu to start.")
    except Exception as e:
        await query.edit_message_text(f"Error: {e}")


async def cmd_reset_topics(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        writing_engine.reset_cycle()
        await update.message.reply_text("🔄 Cycle reset. All topics are available again.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def handle_writing_submission(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str):
    uid = update.effective_user.id
    topic = WRITING_STATE.pop(uid)["topic"]

    await update.message.reply_text("⏳ Grading your text...")
    try:
        result = writing_engine.grade_and_save(topic, text, user_id=uid)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
        return

    mistakes = result["mistakes"]
    msg = f"📊 *Score: {result['score']}/100*\n\n"

    if mistakes:
        msg += "*Mistakes found:*\n\n"
        for m in mistakes[:8]:
            msg += (
                f"❌ {m.get('wrong', '')}\n"
                f"✅ {m.get('correct', '')}\n"
                f"💡 {m.get('explanation', '')}\n\n"
            )
        if len(mistakes) > 8:
            msg += f"_+{len(mistakes) - 8} more saved to your mistake bank_\n\n"
    else:
        msg += "🎉 No mistakes found!\n\n"

    if result.get("feedback"):
        msg += f"💬 *Feedback:* {result['feedback']}"

    await update.message.reply_text(msg, parse_mode="Markdown")

    corrected = result.get("corrected_text", "")
    if corrected:
        for i, chunk in enumerate(_chunk_text(corrected)):
            title = "📝 *Corrected text:*\n" if i == 0 else ""
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
        await send("🎉 No pending mistakes to review! Keep writing 💪")
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
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔍 Show answer", callback_data=f"reveal_{idx}")]])
    await send(f"*Card {idx + 1}/{total}*\n❌ {m['wrong']}", parse_mode="Markdown", reply_markup=keyboard)


async def finish_review(uid: int, send):
    state = REVIEW_STATE.pop(uid, {})
    total = len(state.get("queue", []))
    remembered = state.get("remembered", 0)
    await send(f"🏁 *Review complete!*\nYou remembered {remembered}/{total}", parse_mode="Markdown")


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
        InlineKeyboardButton("✅ I knew it", callback_data=f"knew_{idx}_1"),
        InlineKeyboardButton("❌ I didn't know", callback_data=f"knew_{idx}_0"),
    ]])
    msg = f"✅ {m['correct']}\n💡 {m.get('explanation', '')}"
    await query.edit_message_text(msg, reply_markup=keyboard)


async def cmd_reminder(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    hour, minute = scheduler.get_reminder_time()
    if ctx.args and len(ctx.args) >= 1:
        try:
            parts = ctx.args[0].split(":")
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            scheduler.set_reminder_time(h, m)
            scheduler.setup_daily_reminder(ctx.application)
            await update.message.reply_text(f"✅ Daily reminder set for {h:02d}:{m:02d}.")
            return
        except (ValueError, IndexError):
            await update.message.reply_text("Usage: /reminder [HH:MM]")
            return
    await update.message.reply_text(
        f"⏰ Current reminder time: {hour:02d}:{minute:02d}\n"
        f"Use `/reminder HH:MM` to change it (e.g. `/reminder 20:00`).",
        parse_mode="Markdown",
    )


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
        await query.edit_message_text(f"✅ {m['correct']}\n💡 {m.get('explanation', '')}\n\n👍 Well done!")
    else:
        await query.edit_message_text(f"✅ {m['correct']}\n💡 {m.get('explanation', '')}\n\n📌 Keep practicing this one.")

    state["index"] += 1
    await send_flashcard(uid, query.message.reply_text)


# ─── READING GAME ──────────────────────────────────────────────────


async def cmd_read(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in READING_STATE:
        await update.message.reply_text("You already have a reading session in progress!")
        return
    await show_reading_weeks(update.message.reply_text)


def _reading_week_emoji(week: int) -> str:
    return ["📘", "📗", "📕", "📙", "📓"][(week - 1) % 5]


async def show_reading_weeks(send):
    weeks = sorted(READING_WEEKS.keys())
    buttons = [
        [InlineKeyboardButton(
            f"{_reading_week_emoji(w)} Week {w} — {READING_WEEKS[w][0]}...",
            callback_data=f"rweek_{w}",
        )]
        for w in weeks
    ]
    await send(
        "📖 *Reading Practice*\n\nPick a week to explore Cambridge/IELTS/TOEFL-style readings.\n"
        "Each week has different topics. You will get a timed passage "
        "followed by multiple-choice questions and 6 key words to learn.",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


async def reading_week_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    week = int(query.data.split("_", 1)[1])

    entries = READING_WEEKS.get(week, [])
    if not entries:
        await query.edit_message_text(f"No topics for Week {week}.")
        return

    buttons = [
        [InlineKeyboardButton(topic, callback_data=f"rtopic_{week}_{i}")]
        for i, topic in enumerate(entries)
    ]
    await query.edit_message_text(
        f"{_reading_week_emoji(week)} *Week {week}* — pick a topic:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


async def reading_topic_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    parts = query.data.split("_")
    week = int(parts[1])
    topic_idx = int(parts[2])
    topic_name = READING_WEEKS[week][topic_idx]

    await query.edit_message_text(f"⏳ Generating a Cambridge/IELTS reading on *{topic_name}*...", parse_mode="Markdown")
    try:
        game = reading_game.fetch_or_create_game(topic=topic_name)
    except Exception as e:
        await query.edit_message_text(f"Error: {e}")
        return

    if not game:
        await query.edit_message_text("Could not create a reading game. Is the AI provider available?")
        return

    READING_STATE[uid] = {
        "game": game,
        "start_time": None,
        "reading_shown": False,
        "question_idx": 0,
        "answers": [],
    }

    read_secs = reading_game.reading_time_seconds(game.content)
    read_min = max(1, read_secs // 60)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"▶️ Start Reading ({read_min} min timer)", callback_data="reading_start")],
        [InlineKeyboardButton("❌ Cancel", callback_data="reading_cancel")],
    ])
    await query.edit_message_text(
        f"📖 *{game.name}*\n\n"
        f"Week {week} — {game.topic}\n"
        f"Level: {game.level}\n"
        f"Questions: {len(game.questions)}\n"
        f"Times played: {game.times_played}\n\n"
        f"When you press start, you will have {read_min} minutes to read the passage. "
        f"After the timer expires, {len(game.questions)} multiple-choice questions will follow.",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


def _chunk_long_text(text: str, max_len: int = 3500) -> list[str]:
    return [text[i:i + max_len] for i in range(0, len(text), max_len)]


async def reading_start_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = READING_STATE.get(uid)
    if not state:
        return

    game = state["game"]
    state["start_time"] = datetime.now(timezone.utc)

    chunks = _chunk_long_text(game.content)
    for chunk in chunks:
        await query.message.reply_text(chunk, parse_mode="Markdown")

    read_secs = reading_game.reading_time_seconds(game.content)
    ans_secs = reading_game.answer_time_seconds(len(game.questions))
    await query.message.reply_text(
        f"⏱️ *Reading time: ~{read_secs // 60} min ({read_secs}s)*\n"
        f"⏱️ *Answer time: ~{ans_secs // 60} min ({ans_secs}s)*\n\n"
        f"When you finish reading, click below to start the questions.\n"
        f"Your answers will be timed.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Start Questions", callback_data="reading_questions")],
        ]),
        parse_mode="Markdown",
    )
    try:
        await query.edit_message_reply_markup(None)
    except Exception:
        pass


async def reading_questions_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = READING_STATE.get(uid)
    if not state:
        return

    state["reading_shown"] = True
    await send_reading_question(query, uid)


async def send_reading_question(query, uid: int):
    state = READING_STATE[uid]
    game = state["game"]
    idx = state["question_idx"]

    if idx >= len(game.questions):
        await finish_reading_game(query, uid)
        return

    q = game.questions[idx]
    total = len(game.questions)
    text = f"*Question {idx + 1}/{total}*\n\n{q['question']}"

    options = q.get("options", [])
    if options:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{chr(65 + i)}. {opt}", callback_data=f"rd_ans_{i}")]
            for i, opt in enumerate(options)
        ])
    else:
        keyboard = None

    await query.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def reading_answer_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    state = READING_STATE.get(uid)
    if not state:
        return

    option_idx = int(query.data.split("_")[-1])
    game = state["game"]
    idx = state["question_idx"]
    q = game.questions[idx]

    options = q.get("options", [])
    chosen_answer = options[option_idx] if option_idx < len(options) else ""
    correct_answer = q.get("answer", "")
    is_correct = chosen_answer.strip().lower() == correct_answer.strip().lower()

    state["answers"].append(chosen_answer)
    state["question_idx"] += 1

    if is_correct:
        await query.edit_message_text(f"✅ Correct!\n\n*{q['question']}*\n\n→ {correct_answer}", parse_mode="Markdown")
    else:
        await query.edit_message_text(
            f"❌ Your answer: {chosen_answer}\n"
            f"✅ Correct answer: *{correct_answer}*\n\n"
            f"*{q['question']}*",
            parse_mode="Markdown",
        )

    await send_reading_question(query, uid)


async def finish_reading_game(query, uid: int):
    state = READING_STATE.pop(uid, {})
    game = state.get("game")
    answers = state.get("answers", [])
    start_time = state.get("start_time")

    if not game:
        await query.message.reply_text("Reading session ended.")
        return

    elapsed = 0
    if start_time:
        elapsed = int((datetime.now(timezone.utc) - start_time).total_seconds())

    result = game.score_answers(answers)
    minutes = elapsed // 60
    seconds = elapsed % 60

    try:
        reading_game.update_play_stats(game.id, result["score"], elapsed)
    except Exception as e:
        logger.warning(f"Could not update play stats: {e}")

    msg = (
        f"🏁 *Reading Complete!*\n\n"
        f"📖 *{game.name}*\n"
        f"Score: {result['score']}/{result['total']} ({result['percentage']}%)\n"
        f"Time: {minutes}m {seconds}s\n\n"
    )

    incorrect = [d for d in result["details"] if not d["is_correct"]]
    if incorrect:
        msg += "*Mistakes:*\n\n"
        for d in incorrect[:3]:
            msg += f"❌ {d['question']}\n"
            msg += f"✅ *{d['correct_answer']}*\n\n"
        if len(incorrect) > 3:
            msg += f"_+{len(incorrect) - 3} more_\n\n"

    if game.key_words:
        msg += "*🔑 Key Words:*\n"
        for kw in game.key_words:
            msg += f"`{kw}` "
        msg += "\n\n"

    msg += "🎯 Keep practicing! Try other topics with /read"

    await query.message.reply_text(msg, parse_mode="Markdown")

    wrong_ids = [d for d in result["details"] if not d["is_correct"]]
    for detail in wrong_ids:
        question_text = detail["question"]
        correct_ans = detail["correct_answer"]
        await query.message.reply_text(
            f"📝 *Error Review:*\n\n"
            f"Q: {question_text}\n"
            f"✅ Correct: {correct_ans}\n"
            f"❌ Your answer: {detail['user_answer']}",
            parse_mode="Markdown",
        )


async def reading_cancel_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    READING_STATE.pop(uid, None)
    await query.edit_message_text("❌ Reading cancelled.")


async def _set_bot_commands(app: Application):
    commands = [
        ("start", "Welcome message"),
        ("menu", "Study modes: vocabulary, writing, reading, review"),
        ("read", "Timed reading practice with MCQ"),
        ("quiz", "Test your vocabulary"),
        ("stats", "Your learning progress"),
        ("mistakes", "Review writing mistakes"),
        ("correct", "Fix grammar in a sentence"),
        ("explain", "Explain a saved word"),
        ("recommend", "Personalized study tips"),
        ("add", "Add a word manually"),
        ("model", "Switch AI model"),
        ("reminder", "Set daily reminder time"),
    ]
    try:
        await app.bot.set_my_commands(commands)
    except Exception as e:
        logger.warning(f"Could not set bot commands: {e}")


def main():
    if not TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not set in .env")
        return

    app = Application.builder().token(TOKEN).post_init(_set_bot_commands).build()

    cid = int(CHAT_ID) if CHAT_ID and CHAT_ID.isdigit() else None
    scheduler.setup_daily_reminder(app, chat_id=cid)
    scheduler.setup_writing_topic_reminder(app, chat_id=cid)
    scheduler.setup_reading_reminder(app, chat_id=cid)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("quiz", cmd_quiz))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("explain", cmd_explain))
    app.add_handler(CommandHandler("correct", cmd_correct))
    app.add_handler(CommandHandler("recommend", cmd_recommend))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("mistakes", cmd_mistakes))
    app.add_handler(CommandHandler("resettopics", cmd_reset_topics))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CommandHandler("reminder", cmd_reminder))
    app.add_handler(CommandHandler("read", cmd_read))
    app.add_handler(CallbackQueryHandler(quiz_callback, pattern="^quiz_"))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^mode_"))
    app.add_handler(CallbackQueryHandler(week_callback, pattern="^week_"))
    app.add_handler(CallbackQueryHandler(topic_callback, pattern="^topic_"))
    app.add_handler(CallbackQueryHandler(reset_topics_callback, pattern="^resettopics$"))
    app.add_handler(CallbackQueryHandler(reveal_callback, pattern="^reveal_"))
    app.add_handler(CallbackQueryHandler(knew_callback, pattern="^knew_"))
    app.add_handler(CallbackQueryHandler(model_callback, pattern="^model_"))
    app.add_handler(CallbackQueryHandler(reading_week_callback, pattern="^rweek_"))
    app.add_handler(CallbackQueryHandler(reading_topic_callback, pattern="^rtopic_"))
    app.add_handler(CallbackQueryHandler(reading_start_callback, pattern="^reading_start$"))
    app.add_handler(CallbackQueryHandler(reading_questions_callback, pattern="^reading_questions$"))
    app.add_handler(CallbackQueryHandler(reading_answer_callback, pattern="^rd_ans_"))
    app.add_handler(CallbackQueryHandler(reading_cancel_callback, pattern="^reading_cancel$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot started. No user filter — all users can interact. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
