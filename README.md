# EnglishAgent

Personal English vocabulary learning assistant powered by **Ollama** + **Notion** + **Telegram**.

Uses `qwen2.5:0.5b` locally via Ollama for AI features (sentence correction, word explanations, study recommendations). Vocabulary, readings, and progress are stored in Notion. Telegram delivers notifications.

## Architecture

```
You (CLI or Telegram)
  │
  ├─▶ english-agent correct "I go to school yesterday"
  ├─▶ english-agent explain "perseverance"
  ├─▶ english-agent word add "hello" "hola"
  ├─▶ english-agent quiz generate --count 10
  └─▶ english-agent notify send "Study time!"
          │
          ├─▶ Ollama + qwen2.5:0.5b (AI commands)
          └─▶ Notion API (words, readings, activity logs)
```

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) + `qwen2.5:0.5b` model
- Notion integration token
- Telegram bot token (for notifications)

## Setup

### 1. Install the Python package

```bash
cd EnglishAgent
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configure .env

```bash
cp .env.example .env
```

Edit `.env` with your tokens. It should look like:

```env
# Notion
NOTION_TOKEN=ntn_your_integration_token
NOTION_WORDS_DB=your_words_database_id
NOTION_READINGS_DB=your_readings_database_id
NOTION_ACTIVITY_DB=your_activity_database_id
NOTION_TOPICS_DB=your_writing_topics_database_id
NOTION_SUBMISSIONS_DB=your_writing_submissions_database_id
NOTION_MISTAKES_DB=your_mistakes_bank_database_id

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_CHAT_ID=your_telegram_user_id

# Ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:0.5b
# Optional — use a different/bigger model just for grading writing submissions
OLLAMA_WRITING_MODEL=qwen2.5:0.5b
```

| Variable | Description |
|----------|-------------|
| `NOTION_TOKEN` | Notion integration token (starts with `ntn_`) |
| `NOTION_WORDS_DB` | Created by `setup_notion.py` |
| `NOTION_READINGS_DB` | Created by `setup_notion.py` |
| `NOTION_ACTIVITY_DB` | Created by `setup_notion.py` |
| `NOTION_TOPICS_DB` | Created by `setup_notion.py` — writing curriculum topics |
| `NOTION_SUBMISSIONS_DB` | Created by `setup_notion.py` — graded writing texts |
| `NOTION_MISTAKES_DB` | Created by `setup_notion.py` — mistake review bank |
| `TELEGRAM_BOT_TOKEN` | From [@BotFather](https://t.me/botfather) |
| `TELEGRAM_CHAT_ID` | Your Telegram user ID (numeric) |
| `OLLAMA_BASE_URL` | Ollama API endpoint (default: `http://127.0.0.1:11434`) |
| `OLLAMA_MODEL` | Ollama model to use (default: `qwen2.5:0.5b`) |
| `OLLAMA_WRITING_MODEL` | Model used to grade writing submissions (default: same as `OLLAMA_MODEL`) |

### 3. Create Notion databases

```bash
python setup_notion.py
```

Paste a parent page ID (a Notion page shared with your integration). This creates 6 databases:
- **English Vocabulary** — words, translations, status, stats
- **Readings** — reading texts for vocabulary extraction
- **Activity Log** — quiz results and timestamps
- **Writing Topics** — the 5-week writing curriculum (seeded automatically)
- **Writing Submissions** — your graded texts (score, corrections, feedback)
- **Mistakes Bank** — individual mistakes pulled from graded texts, for spaced review

### 4. Pull the Ollama model

```bash
ollama pull qwen2.5:0.5b
```

Make sure Ollama is running:
```bash
ollama serve
```

## CLI Reference

All commands output JSON.

### AI Commands (powered by Ollama)

```bash
# Correct a sentence with grammar explanation
english-agent correct "She go to school every day"

# Explain a word from your vocabulary
english-agent explain "perseverance"

# Get AI study recommendations (based on weak words)
english-agent recommend
```

### Words

```bash
english-agent word add "ubiquitous" "omnipresente" --definition "present everywhere"
english-agent word list --status learning
english-agent word get "ubiquitous"
english-agent word delete "ubiquitous"
```

### Quiz

```bash
english-agent quiz generate --count 10
english-agent quiz evaluate <word_id> --correct true
english-agent quiz evaluate <word_id> --correct false
```

### Readings

```bash
english-agent reading add "Article Title" "Full text content here..."
english-agent reading list
english-agent reading extract <reading_id> --max 20
```

### Analytics

```bash
english-agent stats
english-agent analyze time --days 30
english-agent analyze weak --min-attempts 2
```

### Notifications

```bash
english-agent notify "Time for your daily quiz!"
```

## Telegram Bot (Interactive)

The bot runs as a systemd service and responds to you on Telegram.

### Start the bot — native (systemd)

```bash
systemctl --user start english-bot
systemctl --user enable english-bot  # auto-start on boot
```

### Start the bot — Docker (Raspberry Pi / ARM)

```bash
# Build and run both Ollama + bot
docker compose up -d

# Pull the model inside the container
docker exec english-ollama ollama pull qwen2.5:0.5b

# View logs
docker compose logs -f bot
```

For Raspberry Pi (ARM64), the compose file uses the official `ollama/ollama` image which supports ARM natively. The bot container builds from `python:3.11-slim-bookworm` (multi-arch).

### Bot Commands

Talk to your bot on Telegram (@ImprovemyEnglish_bot):

| Action | What happens |
|--------|-------------|
| `/menu` | Choose a study mode: vocabulary, writing practice, mistake review, or stats |
| Send any English word | Bot saves it to Notion, asks AI for translation, replies with meaning |
| `/quiz` | Generates 5 questions from your vocabulary with multiple choice |
| `/correct <sentence>` | Fixes grammar mistakes |
| `/explain <word>` | Shows AI explanation for a saved word |
| `/stats` | Shows your progress (mastered, learning, accuracy) |
| `/recommend` | AI study recommendations based on weak words |
| `/add <word>` | Manually add a word |
| `/mistakes` | Review your writing mistakes as flashcards |
| `/resettopics` | Start a new writing cycle once all topics are used |
| `/start` or `/help` | Show help |

### Quiz Flow

1. Send `/quiz` → bot sends question 1/5 with buttons
2. Tap an answer → bot tells you if correct, records the result
3. After question 5 → bot shows your score + overall progress

### Auto Save

Just send any English word like `perseverance` → bot automatically:
- Asks AI for translation and meaning
- Saves to Notion
- Replies with the explanation

### Writing Practice Flow

The curriculum is a 5-week plan (topics like "Mi trabajo", "Tecnología", "Ensayos", "Historias"...) stored in the **Writing Topics** database.

1. `/menu` → **✍️ Escritura** → pick a week → pick a topic
2. Bot suggests a few connectors (Nevertheless, Moreover, Although...) and asks you to write about the topic
3. Send your text as a message → the bot grades it with Ollama: score /100, each mistake shown as ❌ wrong → ✅ correct → 💡 explanation, the fully corrected text, and overall feedback
4. The graded submission is saved to **Writing Submissions**, each mistake is saved to the **Mistakes Bank**, and the topic is marked as used
5. Once every topic across all 5 weeks has been used, `/resettopics` (or the "🔄 Reiniciar ciclo" button) marks them all available again so you can repeat the plan

### Mistake Review Flow

`/menu` → **🔁 Repasar errores** (or `/mistakes` directly) pulls up to 5 not-yet-mastered mistakes from the **Mistakes Bank** as flashcards:

1. Bot shows the ❌ wrong phrase
2. Tap "🔍 Mostrar respuesta" → reveals ✅ the correction + explanation
3. Tap "✅ Lo sabía" / "❌ No lo sabía" → updates that mistake's review stats in Notion (promoted to `mastered` after enough correct reviews)
4. After the batch, the bot shows how many you remembered

## Docker Deployment (Raspberry Pi / ARM)

The project includes a `docker-compose.yml` with two services:

| Service | Image | Role |
|---------|-------|------|
| `ollama` | `ollama/ollama:latest` | Runs `qwen2.5:0.5b` on ARM64 natively |
| `bot` | built from `Dockerfile` | Python bot + Notion client |

```bash
# On your Raspberry Pi (64-bit OS required):
git clone https://github.com/AiLinknfc/learning-english-agent.git
cd learning-english-agent

# Configure secrets
cp .env.example .env
# Edit .env with your Notion + Telegram tokens

# Start everything
docker compose up -d

# Pull the model (one-time)
docker exec english-ollama ollama pull qwen2.5:0.5b

# Check logs
docker compose logs -f bot
```

> **Note:** Ollama runs *inside* the container, so model inference shares resources with the container. For better performance on RPi, run Ollama natively and only containerize the bot.

## Portability

This runs on low-power devices (Raspberry Pi, old laptops) with:
- `qwen2.5:0.5b` (~400MB RAM, ~400MB disk)
- Python + notion-client (~50MB)
- Total footprint ~1GB

To move to a new device:
1. Copy `.env` — your data stays in Notion
2. Install Ollama + pull the model (or use Docker)
3. Run the bot (native or container)

## Repository

Source code: https://github.com/AiLinknfc/learning-english-agent
