import logging
import os
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler
from reddit.commands import reddit_media_command

# Load environment variables
load_dotenv()

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
    logger = setup_logging()
    logger.info("Bot is starting...")

    # Telegram API key from environment variables
    telegram_api_key = os.getenv('TELEGRAM_API_KEY')
    if not telegram_api_key:
        raise ValueError("TELEGRAM_API_KEY environment variable is not set. Please add it to your .env file.")

    application = Application.builder().token(telegram_api_key).build()

    application.add_handler(CommandHandler('r', reddit_media_command))

    application.run_polling()

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"Error starting the bot: {e}")