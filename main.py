import logging
import os
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler
from datetime import datetime, timezone
from reddit.commands import reddit_media_command

# Load environment variables
load_dotenv()

start_time = datetime.now(timezone.utc)


def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    if not logger.hasHandlers():
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)

        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)

        logger.addHandler(ch)

    return logger


def main():
    # Set up logging
    logger = setup_logging()
    logger.info("Bot is starting...")

    # Get the Telegram API key from environment variables
    telegram_api_key = os.getenv('TELEGRAM_API_KEY')
    if not telegram_api_key:
        raise ValueError("TELEGRAM_API_KEY environment variable is not set. Please add it to your .env file.")

    # Create the bot application
    application = Application.builder().token(telegram_api_key).build()

    # Add the /r command handler
    application.add_handler(CommandHandler('r', reddit_media_command))

    # Start the bot
    application.run_polling()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"Error starting the bot: {e}")