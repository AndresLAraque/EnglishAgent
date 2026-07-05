# EnglishAgent

Personal English learning assistant powered by **AI (DeepSeek / Ollama)** + **Notion** + **Telegram**.

## Features

- 🤖 **Dual AI provider**: DeepSeek (cloud) with auto-fallback to Ollama (local) when quota runs out
- 📚 **Vocabulary**: Send any English word → auto-saves with AI translation, explanation, examples, synonyms
- ✍️ **Writing practice**: 5-week curriculum with topics, AI grading (score/100), mistake-by-mistake feedback, corrected version
- 🔁 **Mistake review**: Spaced-repetition flashcards from your writing mistakes
- 📊 **Progress tracking**: Stats on words mastered, accuracy, writing topics completed
- ⏰ **Daily reminders**: Scheduled study reminders and weekly writing challenges via Telegram
- 🔄 **Multi-user**: No user restrictions — anyone who finds the bot can use it

## Architecture

```
Telegram Bot ←→ Python (python-telegram-bot)
                    ├── DeepSeek API (primary AI) ──→ fallback ──→ Ollama (local)
                    ├── Notion API (all data storage)
                    └── JobQueue (daily/weekly reminders)
```

## Setup

### 1. Install

```bash
git clone <repo> && cd EnglishAgent
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

### 2. Configure `.env`

```bash
cp .env.example .env
# Edit with your tokens
```

| Variable | Required | Description |
|----------|----------|-------------|
| `NOTION_TOKEN` | ✅ | Notion integration token (starts with `ntn_`) |
| `NOTION_WORDS_DB` | ✅ | Vocabulary database ID |
| `NOTION_READINGS_DB` | ✅ | Readings database ID |
| `NOTION_ACTIVITY_DB` | ✅ | Quiz activity log database ID |
| `NOTION_TOPICS_DB` | ✅ | Writing topics database ID |
| `NOTION_SUBMISSIONS_DB` | ✅ | Writing submissions database ID |
| `NOTION_MISTAKES_DB` | ✅ | Mistakes bank database ID |
| `TELEGRAM_BOT_TOKEN` | ✅ | From [@BotFather](https://t.me/botfather) |
| `TELEGRAM_CHAT_ID` | ✅ | Your Telegram numeric user ID |
| `DEEPSEEK_API_KEY` | ❌ | DeepSeek API key (sk-...) |
| `OLLAMA_BASE_URL` | ❌ | `http://127.0.0.1:11434` (default) |
| `OLLAMA_MODEL` | ❌ | `qwen2.5:0.5b` (default) |

### 3. Create Notion databases

```bash
python setup_notion.py
```

Paste a parent page ID shared with your integration → creates 6 databases.

### 4. (Optional) Pull Ollama model

```bash
ollama pull qwen2.5:0.5b
ollama serve
```

## CLI Reference

All commands output JSON. Useful for scripting or testing.

```bash
# AI
english-agent correct "She go to school every day"
english-agent explain "perseverance"
english-agent recommend

# Words
english-agent word add "ubiquitous" "omnipresente"
english-agent word list --status learning
english-agent word get "ubiquitous"
english-agent word delete "ubiquitous"

# Quiz
english-agent quiz generate --count 10
english-agent quiz evaluate <word_id> --correct true

# Readings
english-agent reading add "Title" "Full text..."
english-agent reading list
english-agent reading extract <reading_id> --max 20

# Stats & Analysis
english-agent stats
english-agent analyze time --days 30
english-agent analyze weak --min-attempts 2

# Notify
english-agent notify "Time to study!"
```

## Telegram Bot Commands

Talk to the bot on Telegram:

| Command | Description |
|---------|-------------|
| `/start` or `/help` | Show help with current AI model |
| `/menu` | Choose study mode: Vocabulary, Writing, Mistake Review, Stats |
| Send any English word | Auto-saves with AI translation + explanation |
| `/add <word> [translation]` | Manually add a word |
| `/quiz` | 5-question vocabulary test |
| `/correct <sentence>` | Fix grammar mistakes |
| `/explain <word>` | AI explanation of a saved word |
| `/stats` | Your learning progress |
| `/recommend` | AI study tips based on weak words |
| `/mistakes` | Flashcard review of writing mistakes |
| `/model` | Switch between DeepSeek and Ollama |
| `/reminder [HH:MM]` | View/set daily reminder time |
| `/resettopics` | Reset all writing topics for a new cycle |

### Writing Practice Flow

1. `/menu` → **✍️ Writing** → pick a week → pick a topic
2. Bot suggests connectors (Nevertheless, Moreover...) and you write a text
3. Send your text → AI grades it: score/100, each mistake shown as ❌ → ✅ → 💡, corrected version, overall feedback
4. Everything saved to Notion: original text, corrected text, score, mistakes, strengths, AI model used, hour, user ID
5. All topics done? Use `/resettopics` or tap "🔄 Reset cycle"

### Mistake Review Flow

1. `/menu` → **🔁 Mistake Review** (or `/mistakes`)
2. Bot shows ❌ wrong phrase → tap "🔍 Show answer" → reveals ✅ correction
3. Tap "✅ I knew it" or "❌ I didn't know" → updates spaced-repetition stats
4. After 3 correct reviews → mistake promoted to `mastered`

### Model Selection

Use `/model` to switch between providers:

- **DeepSeek** (cloud): Faster, smarter — needs `DEEPSEEK_API_KEY` in `.env`
- **Ollama** (local): Runs locally, no API costs — needs Ollama running

If DeepSeek quota is exhausted, the bot **automatically falls back** to Ollama.

### Daily Reminders

Set a daily reminder with `/reminder 20:00` (or any HH:MM). The bot will send:
- Daily study reminder at your chosen time
- Weekly writing topic suggestion every Monday at 9:00

## Notion Database Schema

Each database is documented below. Create them via `python setup_notion.py`.

### English Vocabulary
`Word` (title), `Translation`, `Definition`, `Example`, `Status` (learning/reviewing/mastered/forgotten), `Tags`, `Times Correct`, `Times Wrong`, `Date Added`, `Last Reviewed`, `Source` (manual/extracted)

### Writing Submissions
`Name` (title), `Week`, `Topic` (relation), `Original Text`, `Corrected Text`, `Feedback`, `Score`, `Mistake Count`, `Strengths`, `Hour`, `Provider`, `AI Model`, `User ID`, `Date`

### Mistakes Bank
`Name` (title), `Wrong`, `Correct`, `Explanation`, `Category` (grammar/vocabulary/word-order/...), `Status` (new/reviewing/mastered), `Times Reviewed`, `Times Correct`, `Date Added`, `Last Reviewed`, `Source Submission` (relation)

Also: **Readings**, **Activity Log**, **Writing Topics** (auto-seeded with 5-week curriculum).

## Docker

```bash
docker compose up -d
docker exec english-ollama ollama pull qwen2.5:0.5b
```

Works on Raspberry Pi (ARM64).

## Portability

Data stays in Notion. To move to a new device:
1. Copy `.env`
2. Install Ollama or configure DeepSeek
3. Run the bot
