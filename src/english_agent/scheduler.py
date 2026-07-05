import logging
from datetime import time
from typing import Optional

from telegram.ext import ContextTypes, Application

from . import notify as notify_mod

logger = logging.getLogger(__name__)

_REMINDER_HOUR = 8
_REMINDER_MINUTE = 0

_REMINDER_MESSAGE = (
    "☀️ *Daily Study Reminder*\n\n"
    "Time for your English practice! Here's what you can do:\n\n"
    "📚 *Vocabulary* — Send /quiz to test your words\n"
    "✍️ *Writing* — Send /menu → Writing, pick a topic\n"
    "🔁 *Mistake Review* — Send /mistakes to review errors\n"
    "📰 *Reading* — Find an article in English and send new words to me\n\n"
    "💡 _Tip: Read a short news article today and save 3 new words._\n"
    "_Consistency beats intensity — 15 minutes daily is enough._"
)


def get_reminder_time() -> tuple[int, int]:
    return _REMINDER_HOUR, _REMINDER_MINUTE


def set_reminder_time(hour: int, minute: int = 0):
    global _REMINDER_HOUR, _REMINDER_MINUTE
    _REMINDER_HOUR = max(0, min(23, hour))
    _REMINDER_MINUTE = max(0, min(59, minute))


async def _send_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = ctx.job.chat_id
    try:
        await ctx.bot.send_message(chat_id=chat_id, text=_REMINDER_MESSAGE, parse_mode="Markdown")
        logger.info(f"Reminder sent to chat {chat_id}")
    except Exception as e:
        logger.error(f"Failed to send reminder to {chat_id}: {e}")


def setup_daily_reminder(app: Application, chat_id: Optional[int] = None):
    if chat_id is None:
        import os
        from dotenv import load_dotenv
        load_dotenv()
        cid = os.getenv("TELEGRAM_CHAT_ID", "")
        chat_id = int(cid) if cid and cid.isdigit() else None

    if not chat_id:
        logger.warning("No TELEGRAM_CHAT_ID set. Daily reminder not scheduled.")
        return

    app.job_queue.run_daily(
        _send_reminder,
        time=time(hour=_REMINDER_HOUR, minute=_REMINDER_MINUTE),
        chat_id=chat_id,
        name="daily_reminder",
    )
    logger.info(f"Daily reminder scheduled at {_REMINDER_HOUR:02d}:{_REMINDER_MINUTE:02d} for chat {chat_id}")


def setup_writing_topic_reminder(app: Application, chat_id: Optional[int] = None):
    """Sends a weekly writing topic suggestion every Monday at 9:00."""
    if chat_id is None:
        import os
        from dotenv import load_dotenv
        load_dotenv()
        cid = os.getenv("TELEGRAM_CHAT_ID", "")
        chat_id = int(cid) if cid and cid.isdigit() else None

    if not chat_id:
        return

    from . import notion_db, topics

    async def _send_topic(ctx: ContextTypes.DEFAULT_TYPE):
        all_topics = notion_db.topic_list(status="available")
        if not all_topics:
            await ctx.bot.send_message(
                chat_id=chat_id,
                text="🎉 All writing topics are done! Use /resettopics to start a new cycle.",
            )
            return
        topic = all_topics[0]
        await ctx.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🗓️ *Weekly Writing Challenge*\n\n"
                f"This week's topic: *{topic['name']}* (Week {topic['week']})\n\n"
                f"Try writing a short paragraph and send /menu to start.\n"
                f"Consistency is key! 💪"
            ),
            parse_mode="Markdown",
        )

    app.job_queue.run_daily(
        _send_topic,
        time=time(hour=9, minute=0),
        days=(0,),
        chat_id=chat_id,
        name="weekly_topic_reminder",
    )
    logger.info("Weekly topic reminder scheduled for Mondays at 09:00")
