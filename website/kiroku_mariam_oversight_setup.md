# Setup: Mariam Oversees, Kiroku Executes Outreach (via Kiroku Email)

## Recommended architecture
- Sending identity: `kiroku@[your-domain]`
- Human approver: Mariam
- System of record: Google Sheet based on `/Users/kiroku/Desktop/website /mariam_3_week_cadence_tracker_pilot2.csv`
- Automation: Google Apps Script running under Kiroku mailbox
- Ops communication: private Discord server (`Kiroku Admin`) with webhook alerts from Apps Script
- Command bridge: Discord bot commands (`!kiroku ...`) processed by Apps Script

## Why this model works
- Kiroku can execute at speed.
- Mariam has hard approval control before any send.
- Every action is logged in one tracker (approval, send, reply, follow-up timing).

## Files prepared
- Controlled tracker (pilot-safe): `/Users/kiroku/Desktop/website /mariam_3_week_cadence_tracker_pilot2.csv`
- Automation script: `/Users/kiroku/Desktop/website /kiroku_outreach_automation.gs`

## One-time setup (30-45 min)
1. Create a Google Sheet named `Kiroku APAC Outreach`.
2. Import `/Users/kiroku/Desktop/website /mariam_3_week_cadence_tracker_pilot2.csv` into tab `Cadence`.
3. Share the sheet with Mariam (Editor) and Kiroku account (Editor).
4. In Kiroku Google account, open Apps Script and paste `/Users/kiroku/Desktop/website /kiroku_outreach_automation.gs`.
5. In Apps Script, set `SHEET_NAME = 'Cadence'`.
6. Run `validateConfiguration()` once and grant permissions.
7. Create time trigger for `sendApprovedDueEmails` to run hourly.
8. Create time trigger for `syncRepliesByThread` to run every 4 hours.
9. In Discord, create private server `Kiroku Admin` and channel `#outreach-ops`.
10. Create a Discord webhook for `#outreach-ops`.
11. In Apps Script, run:
- `setDiscordWebhookUrl('https://discord.com/api/webhooks/...')`
- optional: `setDiscordMariamRoleId('ROLE_ID')` to @mention Mariam on failures/replies
12. Run `testDiscordNotification()` and confirm message appears in Discord.
13. To get `ROLE_ID`: enable Discord Developer Mode, right-click Mariam role, copy ID.
14. Create a Discord bot application, invite it to `Kiroku Admin`, and grant:
- `View Channels`
- `Read Message History`
- `Send Messages`
15. In Apps Script, run:
- `setDiscordBotToken('DISCORD_BOT_TOKEN')`
- `setDiscordCommandChannelIds('ADMIN_CHAT_CHANNEL_ID,OUTREACH_OPS_CHANNEL_ID')`
- `setDiscordAllowedUserIds('YOUR_USER_ID,MARIAM_USER_ID')`
16. Run `testDiscordBotMessage()` and confirm bot can post in command channel.
17. Run `bootstrapDiscordCommandCursor()` once to avoid replaying old messages.
18. Create time trigger for `pollDiscordCommands` every 1-5 minutes.

## Daily operating workflow
1. Kiroku prepares recipient emails and leaves `approval_status = PENDING_REVIEW`.
2. Mariam reviews row-level content and sets:
- `approval_status = APPROVED`
- `approved_by = Mariam`
- `approved_at = YYYY-MM-DD HH:MM`
3. Script sends only rows where:
- `approval_status = APPROVED`
- `send_lock = UNLOCKED`
- touch date is due
4. Pilot mode default:
- Sequence 1-2 are `UNLOCKED` (`WAVE_1`)
- Sequence 3-12 are `LOCKED` (`WAVE_2`)
5. To expand after pilot:
- switch additional rows from `send_lock = LOCKED` to `UNLOCKED`
- keep Mariam approval required row by row
6. Script writes back `send_status`, `sent_at`, Gmail IDs, and next follow-up date.
7. Script posts send/reply/failure summaries into Discord `#outreach-ops`.
8. Mariam checks replies and sets escalation where needed.
9. You or Mariam can use Discord commands to operate without NoMachine:
- `!kiroku status`
- `!kiroku queue 5`
- `!kiroku row 1`
- `!kiroku approve 1,2`
- `!kiroku unlock 1,2`
- `!kiroku run-send`

## Hard guardrails
- No send if `approval_status != APPROVED`.
- No send if `send_lock != UNLOCKED`.
- No send if `recipient_email` is blank.
- No send if row already marked `send_status = SENT` for that active touch.
- Recommended send cap: 25/day during warm-up.
- Mutating Discord commands require caller ID to be in `DISCORD_ALLOWED_USER_IDS`.

## Approval SLA
- Mariam review window: same business day.
- Kiroku execution window: next available APAC morning send slot.

## Suggested status values
- `approval_status`: `PENDING_REVIEW`, `APPROVED`, `REJECTED`
- `send_status`: `NOT_SENT`, `SENT`, `FAILED`
- `reply_status`: `NO_REPLY`, `REPLIED_POSITIVE`, `REPLIED_NEUTRAL`, `REPLIED_NOT_NOW`, `BOUNCED`
- `escalation_flag`: `NO`, `YES`

## Weekly reporting (to leadership)
- Sent this week
- Replies this week
- Meetings booked
- Qualified opportunities
- Blockers and ownership

## Important prerequisites
- Kiroku email must be a Google Workspace mailbox with Gmail enabled.
- SPF, DKIM, and DMARC should be configured for sending domain.
- Keep first week volume conservative (domain warm-up and deliverability).
- Store webhook URL only in Apps Script properties (never in the sheet).
