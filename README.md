# Kiroku Bot

Kiroku is a Discord-first operations bot that can:

- receive admin tasks from Discord
- generate a coding plan
- generate a git patch (LLM-backed)
- apply patch in a task branch
- commit and push branch
- return a PR compare URL

It is designed for controlled operation by a small admin group (you + Mariam).

## Core flow

1. `!kiroku task <title> || <instructions>`
2. `!kiroku plan <id>`
3. `!kiroku diff <id>`
4. `!kiroku apply <id>`
5. `!kiroku commit <id> [message]`
6. `!kiroku pr <id>`

One-shot option:
- `!kiroku run <id>` (plan + diff + apply + commit + pr)

## Safety model

- Commands are only accepted in `ADMIN_CHANNEL_IDS`.
- Mutating commands require caller to be in `ALLOWED_USER_IDS`.
- If `ALLOWED_USER_IDS` is empty, mutating commands are allowed for anyone in admin channels (bootstrap mode).
- Git work is isolated per task branch (`codex/task-<id>`).
- Task state is persisted in `.kiroku/tasks.json`.

## Requirements

- Python 3.9+
- Git with push access to the target repo
- Discord bot token and invited bot
- Optional: OpenAI-compatible API key for patch generation

## Setup

```bash
cd kiroku-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

- `DISCORD_TOKEN`
- `ADMIN_CHANNEL_IDS`
- `ALLOWED_USER_IDS` (optional in bootstrap mode)
- `REPO_PATH`
- `BASE_BRANCH`
- `GIT_REMOTE`
- `OPENAI_API_KEY` (required for `diff` and `run`)

## Run

```bash
source venv/bin/activate
python bot.py
```

## Commands

Read commands:

- `!kiroku help`
- `!kiroku status`
- `!kiroku id`
- `!kiroku repo`
- `!kiroku tasks [all]`
- `!kiroku show <id>`
- `!kiroku preview <id>`

Mutating commands (allowed users only):

- `!kiroku task <title> || <instructions>`
- `!kiroku plan <id>`
- `!kiroku diff <id>`
- `!kiroku apply <id>`
- `!kiroku commit <id> [message]`
- `!kiroku pr <id>`
- `!kiroku run <id>`

## Notes

- `diff` and `run` require `OPENAI_API_KEY`.
- Use `!kiroku id` to copy your `user_id`, `channel_id`, and `guild_id` directly from Discord.
- `apply` can optionally run `VERIFY_COMMAND` from `.env`.
- Compare URLs are generated from your git remote URL.
