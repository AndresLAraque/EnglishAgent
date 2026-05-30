# EnglishAgent — Handoff Document

## Goal

Build a personal English vocabulary learning assistant where **OpenClaw** (Ollama + qwen2.5:1.5b) is the AI brain, **Notion** is the database, and a Python CLI (`english-agent`) exposes tools for OpenClaw to call. The user learns Spanish→English, receives Telegram reminders, stores full reading texts for automatic vocabulary extraction, and gets analytics on best training times and weak words.

## Current State — 2026-05-29

**All code is written, installed, and verified.** The `english-agent` CLI compiles, all subcommands parse correctly, and imports resolve. The project has NOT been connected to real Notion/Telegram credentials yet — those require user setup steps.

### What works (verified)
- `english-agent --help` — CLI dispatches all 6 command groups
- `english-agent word add/list/get/delete --help` — all parse
- `english-agent quiz generate/evaluate --help` — all parse
- `english-agent reading add/list/extract --help` — all parse
- `english-agent stats` — runs (fails with "Invalid request URL" since no Notion token configured, expected)
- `english-agent analyze time/weak` — run (same expected failure)
- `english-agent notify send` — runs (fails if no Telegram token)
- `pip install .` succeeds, `english-agent` is on PATH
- `notion-client==1.0.1` pinned — this version has `databases.query()` which the code depends on; v2.x and v3.x removed that method

### What does NOT work yet (by design)
- No Notion databases exist (user must run `setup_notion.py`)
- No `.env` configured with real tokens
- OpenClaw not yet configured to use the tools

---

## Files in Project

```
EnglishAgent/
├── HANDOFF.md                          ← this file
├── README.md                           # Full setup guide for user
├── pyproject.toml                      # Build metadata
├── setup.py                            # Package installation
├── requirements.txt                    # Pinned deps
├── .env.example                        # Template for secrets
├── .gitignore
├── setup_notion.py                     # Auto-creates 3 Notion databases
│
├── src/english_agent/
│   ├── __init__.py                     # Package marker
│   ├── __main__.py                     # CLI dispatcher (argparse, 15 subcommands)
│   ├── notion_db.py                    # Core: Notion CRUD for words, readings, activity_log
│   ├── quiz_engine.py                  # Quiz generation + evaluation + status auto-promotion
│   ├── analyzer.py                     # Best-hour time analysis + weak word detection
│   ├── vocab_extractor.py              # Extract unknown words from reading texts
│   └── notify.py                       # Telegram HTTP sender
│
└── openclaw/
    ├── SKILL.md                        # OpenClaw personality + instructions
    ├── tools.yaml                      # 11 tool definitions for OpenClaw to call
    └── cron.yaml                       # Schedule: daily quiz, afternoon reminder, weekly analysis
```

---

## File-by-File Details

### `src/english_agent/notion_db.py` (273 lines)
- **Purpose**: All database operations via Notion API
- **3 databases**: `NOTION_WORDS_DB`, `NOTION_READINGS_DB`, `NOTION_ACTIVITY_DB`
- **Words**: `word_add`, `word_get`, `word_list`, `word_update_result`, `word_delete`
- **Readings**: `reading_add`, `reading_list`, `reading_get`
- **Activity**: `activity_log`, `activity_get_logs`
- **Stats**: `stats()` — aggregated counts by status + accuracy
- **Status auto-promotion**: After 3+ attempts, promotes to `mastered` (≥80%), `reviewing` (≥50%), or `forgotten` (on wrong)
- **Key dependency**: Relies on `notion-client==1.0.1` — this version has `databases.query()`; newer versions (2.x, 3.x) removed it

### `src/english_agent/quiz_engine.py` (107 lines)
- **`generate(count=10)`**: Picks words biased toward `learning`/`forgotten` statuses, generates mix of 35% type-answer, 30% mc_word (English→Spanish), 35% mc_translation (Spanish→English)
- **`evaluate(word_id, correct)`**: Updates word result in Notion + logs to activity DB
- **Distractors**: Picks 3 random wrong answers from existing vocabulary

### `src/english_agent/analyzer.py` (46 lines)
- **`best_training_hours(days=30)`**: Aggregates activity logs by hour, returns accuracy per hour
- **`weak_words(min_attempts=2)`**: Finds words with <50% accuracy, sorted worst-first

### `src/english_agent/vocab_extractor.py` (75 lines)
- **`extract_candidates(text, max=20)`**: Tokenizes, removes common English words + existing vocab, returns frequency-sorted unknown candidates
- **`extract_and_save(reading_id)`**: Gets reading from Notion, extracts candidates, adds each as a word entry with `source=extracted`

### `src/english_agent/notify.py` (19 lines)
- Simple `requests.post` to Telegram Bot API `sendMessage` endpoint

### `src/english_agent/__main__.py` (189 lines)
- 6 command groups via argparse: `word`, `quiz`, `reading`, `stats`, `analyze`, `notify`
- All output JSON via `json.dumps` for OpenClaw consumption

### `openclaw/SKILL.md` (56 lines)
- Tells OpenClaw: "You are an English vocabulary tutor for a Spanish speaker"
- Instructs on adding words, running quizzes, extracting readings, analyzing

### `openclaw/tools.yaml` (75 lines)
- 11 tool definitions mapping OpenClaw tool calls to `english-agent` shell commands

### `openclaw/cron.yaml` (38 lines)
- 4 scheduled jobs: 9AM quiz reminder, 1PM follow-up, 8PM daily review, Sunday weekly analysis

### `setup_notion.py` (113 lines)
- Creates the 3 Notion databases with correct schema
- Requires parent page ID (user prompt) + `NOTION_TOKEN` in `.env`

---

## Failed Attempts / Decisions

1. **`notion-client` version hell**: v3.1.0 and v2.x removed `databases.query()`. The code was originally written for the v1.x API. Pinned to `notion-client==1.0.1` which has the classic `databases.query(database_id, filter=..., sorts=...)` method. If upgrading in future, would need to migrate to `data_sources.query(data_source_id, ...)` from v3.x.
2. **`build-backend` in pyproject.toml**: First attempt used `setuptools.backends._legacy:_Backend` which doesn't exist → changed to `setuptools.build_meta`.
3. **Editable install failed**: `pip install -e .` didn't work because the setuptools version doesn't support PEP 660 for editable installs with pyproject.toml-only setup. Added `setup.py` as fallback → regular `pip install .` works fine.
4. **`venv` on external drive**: Initial attempt to create `.venv` on `/media/andres/DataMac1/Linux/` failed with "Operation not permitted" (likely filesystem mount restrictions). Used `pip install --user` instead.
5. **Real secrets in `.env.example`**: Found real-looking Telegram bot token and gateway token in `.env.example` — redacted them.

---

## Next Steps (for user to complete)

### 1. Set up Notion
```bash
cp .env.example .env
# Edit .env with your NOTION_TOKEN
python setup_notion.py       # Creates 3 databases, prints their IDs
# Copy the IDs into .env
```

### 2. Set up Telegram
- Talk to [@BotFather](https://t.me/botfather) to create a bot → get token
- Find your chat ID (send a message to the bot, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates`)
- Fill `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`

### 3. Configure OpenClaw
- Copy `openclaw/SKILL.md`, `openclaw/tools.yaml`, `openclaw/cron.yaml` into OpenClaw workspace
- Or configure via OpenClaw's UI
- Ensure `english-agent` is on PATH that OpenClaw can see

### 4. Pull Ollama model
```bash
ollama pull qwen2.5:1.5b
```

### 5. Verify end-to-end
```bash
english-agent word add "hello" "hola"
english-agent stats
english-agent quiz generate --count 5
english-agent analyze time
english-agent notify send "✅ EnglishAgent is working!"
```

### Potential improvements for future sessions
- Add spaced repetition (SM-2 algorithm) instead of simple status promotion
- Add batch import via CSV file upload
- Add pronunciation links (Forvo API)
- Add offline SQLite cache layer for Raspberry Pi resilience
- Migrate from `notion-client==1.0.1` to v3.x if Notion API changes require it
