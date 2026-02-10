# Kiroku Discord Command Bridge

## Purpose
Enable Kiroku operations from Discord with strict controls:
- Human approval still required for email sends
- Pilot lock (`send_lock`) still enforced
- Only approved Discord users can run mutating commands

## Script location
`/Users/kiroku/Desktop/website /kiroku_outreach_automation.gs`

## Required script properties
- `DISCORD_BOT_TOKEN`
- `DISCORD_COMMAND_CHANNEL_IDS` (comma-separated channel IDs)
- `DISCORD_ALLOWED_USER_IDS` (comma-separated user IDs)
- Optional: `DISCORD_WEBHOOK_URL` for ops alerts
- Optional: `DISCORD_MARIAM_ROLE_ID` for mention on failures/replies

## Setup commands (Apps Script console)
- `setDiscordBotToken('DISCORD_BOT_TOKEN')`
- `setDiscordCommandChannelIds('CHANNEL_ID_1,CHANNEL_ID_2')`
- `setDiscordAllowedUserIds('OWNER_USER_ID,MARIAM_USER_ID')`
- `testDiscordBotMessage()`
- `bootstrapDiscordCommandCursor()`

## Trigger
Create time-driven trigger:
- Function: `pollDiscordCommands`
- Frequency: every 1 to 5 minutes

## Command reference
Use prefix: `!kiroku`

Read commands:
- `!kiroku help`
- `!kiroku status`
- `!kiroku queue [N]`
- `!kiroku row <sequence>`
- `!kiroku next`

Mutating commands (allowed users only):
- `!kiroku approve <seq_csv>`
- `!kiroku reject <seq_csv>`
- `!kiroku unlock <seq_csv>`
- `!kiroku lock <seq_csv>`
- `!kiroku run-send`
- `!kiroku run-replies`

Examples:
- `!kiroku status`
- `!kiroku queue 10`
- `!kiroku approve 1,2`
- `!kiroku unlock 1,2`
- `!kiroku run-send`

## Guardrails that still apply
- Send requires `approval_status = APPROVED`
- Send requires `send_lock = UNLOCKED`
- Send requires non-empty `recipient_email`
- Row already marked sent for current touch is skipped
- Unauthorized Discord users cannot run mutating commands

## Recommended bot permissions
Channel-level minimum:
- View Channels
- Read Message History
- Send Messages

No admin role needed for the bot.

## Operational notes
- Run `bootstrapDiscordCommandCursor()` once when enabling to avoid replaying old messages.
- Rotate Discord bot token and webhook immediately if leaked.
- Keep `DISCORD_ALLOWED_USER_IDS` limited to you and Mariam.
