# inbox-agent

Personal email knowledge pipeline. Fetches email metadata from Fastmail, stores it locally as JSONL, and answers questions about your email using a local LLM.

No pre-classification, no rigid schema. Raw emails go in, you ask questions, answers come out.

## Architecture

```
Fastmail (JMAP)
  ↓ fetch
Raw email metadata (JSONL)
  ↓ ask / briefing
LLM answers (Ollama)
```

- **fetch** — pulls email metadata (sender, subject, preview, date) from Fastmail via JMAP, appends to a local JSONL file. No LLM involved. Idempotent.
- **ask** — sends your question + stored emails to a local Ollama instance, returns an answer.
- **briefing** — runs a set of known questions (action items, travel, money, people, alerts) and prints a grouped summary.

## Setup

Requires [Ollama](https://ollama.ai) running locally and a [Fastmail](https://www.fastmail.com) account with an API token.

```bash
cp .env.example .env
# edit .env with your Fastmail credentials

uv sync
```

## Usage

```bash
# Fetch emails from inbox
inbox-agent fetch

# Ask a question
inbox-agent ask "Do I have any upcoming flights?"
inbox-agent ask "Who emailed me this week?"
inbox-agent ask "What bills are due?"

# Run a daily briefing (action items, travel, money, people, alerts)
inbox-agent briefing
inbox-agent briefing --days 3
```

## Storage

Emails are stored as append-only JSONL at `~/.local/share/inbox-agent/emails.jsonl` (respects `XDG_DATA_HOME`). One line per email, no deletions.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `FASTMAIL_USER` | — | Fastmail email address |
| `FASTMAIL_TOKEN` | — | Fastmail API token |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3.1:latest` | Model for queries |

## License

AGPL-3.0-or-later
