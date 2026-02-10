# Kiroku Bot Deployment on Mac Mini

## 1. Clone and prepare

```bash
cd ~/Desktop
# SSH remote recommended
git clone git@github.com:MikeFraietta/kiroku-bot.git
cd kiroku-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 2. Configure .env

Set at minimum:

- `DISCORD_TOKEN`
- `ADMIN_CHANNEL_IDS`
- `ALLOWED_USER_IDS`
- `REPO_PATH` (usually `.`)
- `BASE_BRANCH` (usually `main`)
- `GIT_REMOTE` (usually `origin`)
- `OPENAI_API_KEY` (needed for `!kiroku diff` and `!kiroku run`)

Optional:

- `VERIFY_COMMAND`
- `WEEKLY_POST_CHANNEL_ID`
- `ENABLE_WEEKLY_EVENTS`

## 3. Test run

```bash
source venv/bin/activate
python bot.py
```

In Discord admin channel:

- `!kiroku help`
- `!kiroku status`

## 4. LaunchAgent (auto-start)

Create `~/Library/LaunchAgents/com.kiroku.bot.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.kiroku.bot</string>

  <key>ProgramArguments</key>
  <array>
    <string>/Users/YOUR_USERNAME/Desktop/kiroku-bot/venv/bin/python</string>
    <string>/Users/YOUR_USERNAME/Desktop/kiroku-bot/bot.py</string>
  </array>

  <key>WorkingDirectory</key>
  <string>/Users/YOUR_USERNAME/Desktop/kiroku-bot</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin</string>
  </dict>

  <key>StandardOutPath</key>
  <string>/Users/YOUR_USERNAME/Desktop/kiroku-bot/bot.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/YOUR_USERNAME/Desktop/kiroku-bot/bot_error.log</string>

  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
</dict>
</plist>
```

Enable:

```bash
launchctl unload ~/Library/LaunchAgents/com.kiroku.bot.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.kiroku.bot.plist
launchctl list | rg kiroku
```

## 5. Ops checks

- Tail logs:

```bash
tail -f ~/Desktop/kiroku-bot/bot.log
```

- Validate git auth from the same runtime user:

```bash
cd ~/Desktop/kiroku-bot
git push --dry-run origin main
```

If dry-run push fails, fix SSH/PAT before enabling code-change commands.
