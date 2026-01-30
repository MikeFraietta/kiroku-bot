# Kiroku Bot - Mac Mini Deployment Guide

This guide covers setting up Kiroku bot on a Mac mini for continuous operation.

## Step 1: Prerequisites

Make sure you have:
- Git installed (comes with Xcode Command Line Tools)
- - Python 3.8+ installed (use Homebrew: `brew install python3`)
  - - Your Discord bot token (from Developer Portal)
    - - Your test Discord server channel ID
     
      - ## Step 2: Clone the Repository
     
      - Open Terminal and run:
     
      - ```bash
        cd ~
        git clone https://github.com/MikeFraietta/kiroku-bot.git
        cd kiroku-bot
        ```

        ## Step 3: Set Up Python Virtual Environment

        Create a virtual environment to keep dependencies isolated:

        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```

        You should see `(venv)` at the beginning of your terminal prompt.

        ## Step 4: Install Dependencies

        ```bash
        pip install -r requirements.txt
        ```

        ## Step 5: Configure Environment Variables

        Copy the example file and edit it:

        ```bash
        cp .env.example .env
        nano .env
        ```

        Edit the file with:
        - Your DISCORD_TOKEN (from Discord Developer Portal)
        - - Your test CHANNEL_ID (from your personal Discord server)
         
          - To get Channel ID:
          - 1. Enable Developer Mode in Discord (Settings > Advanced > Developer Mode)
            2. 2. Right-click the channel
               3. 3. Click "Copy Channel ID"
                 
                  4. Press `Ctrl+O`, then `Enter` to save, then `Ctrl+X` to exit nano.
                 
                  5. ## Step 6: Test the Bot
                 
                  6. Run the bot:
                 
                  7. ```bash
                     python bot.py
                     ```

                     You should see:
                     ```
                     INFO:__main__:your_bot_name has connected to Discord!
                     INFO:__main__:Scheduler started - weekly event posts enabled
                     INFO:__main__:Weekly event job scheduled
                     ```

                     If you see these messages, the bot is working! Keep it running for a few moments to confirm, then press `Ctrl+C` to stop.

                     ## Step 7: Set Up for Continuous Operation (LaunchAgent)

                     To run the bot automatically on Mac startup, create a LaunchAgent:

                     1. Create a plist file:
                    
                     2. ```bash
                        nano ~/Library/LaunchAgents/com.kiroku.bot.plist
                        ```

                        2. Paste this content (update paths if needed):
                       
                        3. ```xml
                           <?xml version="1.0" encoding="UTF-8"?>
                           <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
                           <plist version="1.0">
                           <dict>
                               <key>Label</key>
                               <string>com.kiroku.bot</string>
                               <key>ProgramArguments</key>
                               <array>
                                   <string>/usr/local/bin/python3</string>
                                   <string>/Users/YOUR_USERNAME/kiroku-bot/bot.py</string>
                               </array>
                               <key>WorkingDirectory</key>
                               <string>/Users/YOUR_USERNAME/kiroku-bot</string>
                               <key>StandardOutPath</key>
                               <string>/Users/YOUR_USERNAME/kiroku-bot/bot.log</string>
                               <key>StandardErrorPath</key>
                               <string>/Users/YOUR_USERNAME/kiroku-bot/bot_error.log</string>
                               <key>EnvironmentVariables</key>
                               <dict>
                                   <key>PATH</key>
                                   <string>/Users/YOUR_USERNAME/kiroku-bot/venv/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
                               </dict>
                               <key>RunAtLoad</key>
                               <true/>
                               <key>KeepAlive</key>
                               <true/>
                           </dict>
                           </plist>
                           ```

                           Replace `YOUR_USERNAME` with your actual Mac username (find it with `whoami` in Terminal).

                           3. Save and enable it:
                          
                           4. ```bash
                              launchctl load ~/Library/LaunchAgents/com.kiroku.bot.plist
                              ```

                              ## Step 8: Verify Setup

                              Check if the bot is running:

                              ```bash
                              launchctl list | grep kiroku
                              ```

                              Check logs:

                              ```bash
                              tail -f ~/kiroku-bot/bot.log
                              ```

                              ## Testing the Schedule

                              To test before Monday, you can temporarily modify `bot.py` line 64 to post daily:

                              ```python
                              CronTrigger(day_of_week=0, hour=9, minute=0)  # Monday 9 AM UTC
                              ```

                              Change to:

                              ```python
                              CronTrigger(hour=9, minute=0)  # Every day at 9 AM UTC
                              ```

                              Or test immediately:

                              ```python
                              CronTrigger(hour='*', minute='*/5')  # Every 5 minutes for testing
                              ```

                              After testing, change it back to Monday schedule.

                              ## Troubleshooting

                              **Bot won't start:**
                              - Check DISCORD_TOKEN is correct
                              - - Check CHANNEL_ID exists and bot has access
                                - - Run `python bot.py` directly to see error messages
                                 
                                  - **LaunchAgent not working:**
                                  - - Check paths in plist file match your system
                                    - - Verify Python path: `which python3`
                                      - - Check logs: `cat ~/kiroku-bot/bot_error.log`
                                       
                                        - **Bot keeps stopping:**
                                        - - Check disk space: `df -h`
                                          - - Check bot logs for errors
                                            - - Make sure Mac doesn't sleep (Energy Saver settings)
                                             
                                              - ## Updating the Bot
                                             
                                              - To pull new changes:
                                             
                                              - ```bash
                                                cd ~/kiroku-bot
                                                git pull
                                                source venv/bin/activate
                                                pip install -r requirements.txt
                                                launchctl stop com.kiroku.bot
                                                launchctl start com.kiroku.bot
                                                ```

                                                ## Monday Morning Configuration

                                                The default schedule posts every Monday at 9 AM UTC.

                                                To change the time, edit `bot.py` line 64:
                                                - `day_of_week=0` means Monday (0=Monday, 1=Tuesday, etc.)
                                                - - `hour=9` is the hour in UTC
                                                  - - `minute=0` is the minute
                                                   
                                                    - Example for 8 AM EST (1 PM UTC):
                                                    - ```python
                                                      CronTrigger(day_of_week=0, hour=13, minute=0)
                                                      ```
