import discord
from discord.ext import commands, tasks
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import os
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0))

# Create bot instance with intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Initialize scheduler
scheduler = AsyncIOScheduler()

@bot.event
async def on_ready():
      logger.info(f'{bot.user} has connected to Discord!')
      if not scheduler.running:
                scheduler.start()
            logger.info('Scheduler started - weekly event posts enabled')

async def post_events():
      """Post weekly events to the configured channel"""
    try:
              channel = bot.get_channel(CHANNEL_ID)
              if channel is None:
                            logger.error(f'Channel {CHANNEL_ID} not found!')
                            return

              # Create event embed
              embed = discord.Embed(
                  title='📅 Weekly Event Update',
                  description='Here are this week\'s events for enXross DAO:',
                  color=discord.Color.gold()
              )

        embed.add_field(
                      name='Coming Soon',
                      value='Event information will be posted here weekly.',
                      inline=False
        )

        embed.set_footer(text='Posted by Kiroku Bot')

        await channel.send(embed=embed)
        logger.info('Weekly events posted successfully')
except Exception as e:
        logger.error(f'Error posting events: {e}')

@bot.event
async def on_ready_scheduler():
      """Called when bot is ready to start scheduling"""
    # Schedule weekly event posts for Monday at 9 AM UTC
    scheduler.add_job(
              post_events,
              CronTrigger(day_of_week=0, hour=9, minute=0),
              id='weekly_events',
              replace_existing=True
    )
    logger.info('Weekly event job scheduled')

def run_bot():
      """Start the bot"""
    if not DISCORD_TOKEN:
              raise ValueError('DISCORD_TOKEN environment variable not set!')
          if not CHANNEL_ID:
                    raise ValueError('CHANNEL_ID environment variable not set!')

    bot.run(DISCORD_TOKEN)

if __name__ == '__main__':
      run_bot()
