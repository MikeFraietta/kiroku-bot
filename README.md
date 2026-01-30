# Kiroku Discord Bot

🤖 An autonomous Discord bot for enXross DAO that posts weekly event updates and meeting reminders.

## Features

- **Weekly Event Posts**: Automatically posts event information every Monday at 9 AM UTC
- - **Event Tracking**: Keeps the community informed about upcoming events
  - - **Reliable Scheduling**: Uses APScheduler for precise, recurring notifications
    - - **Easy Configuration**: Simple environment variable setup
     
      - ## Requirements
     
      - - Python 3.8+
        - - Discord.py 2.3.2
          - - APScheduler 3.10.4
           
            - ## Installation
           
            - 1. Clone this repository:
              2. ```bash
                 git clone https://github.com/MikeFraietta/kiroku-bot.git
                 cd kiroku-bot
                 ```

                 2. Install dependencies:
                 3. ```bash
                    pip install -r requirements.txt
                    ```

                    3. Set up environment variables:
                    4. ```bash
                       cp .env.example .env
                       ```

                       4. Edit `.env` and add your values:
                       5.    - `DISCORD_TOKEN`: Your Discord bot token from the Developer Portal
                             -    - `CHANNEL_ID`: The ID of the channel where events will be posted
                              
                                  - ## Getting Your Discord Token
                              
                                  - 1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
                                    2. 2. Click "New Application" and name it "Kiroku"
                                       3. 3. Go to the "Bot" section and click "Add Bot"
                                          4. 4. Copy the token and paste it in your `.env` file
                                             5. 5. Under "TOKEN", click "Copy"
                                               
                                                6. ## Getting Your Channel ID
                                               
                                                7. 1. In Discord, enable Developer Mode (User Settings > Advanced > Developer Mode)
                                                   2. 2. Right-click the channel where you want events posted
                                                      3. 3. Click "Copy Channel ID"
                                                         4. 4. Paste it in your `.env` file as `CHANNEL_ID`
                                                           
                                                            5. ## Running the Bot
                                                           
                                                            6. ```bash
                                                               python bot.py
                                                               ```

                                                               The bot will connect to Discord and start posting events weekly at 9 AM UTC every Monday.

                                                               ## Customization

                                                               To change the posting schedule, edit the `bot.py` file and modify the CronTrigger:

                                                               ```python
                                                               CronTrigger(day_of_week=0, hour=9, minute=0)
                                                               ```

                                                               - `day_of_week`: 0 = Monday, 1 = Tuesday, etc.
                                                               - - `hour`: Hour in UTC (24-hour format)
                                                                 - - `minute`: Minute (0-59)
                                                                  
                                                                   - ## Deployment
                                                                  
                                                                   - For production use, consider deploying to:
                                                                   - - **Heroku** (with Procfile)
                                                                     - - **Railway**
                                                                       - - **Replit**
                                                                         - - **Your own server**
                                                                          
                                                                           - ## Contributing
                                                                          
                                                                           - Contributions are welcome! Please feel free to submit a Pull Request.
                                                                          
                                                                           - ## License
                                                                          
                                                                           - This project is open source and available under the MIT License.
                                                                          
                                                                           - ## Support
                                                                          
                                                                           - For issues or questions, please open an issue on GitHub.
