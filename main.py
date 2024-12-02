import logging
import os
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler
from bot.commands import reddit_media_command

# Load environment variables
load_dotenv()

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler()
        ],
    )
    logging.getLogger("telegram").setLevel(logging.WARNING)

def main():
    setup_logging()
    logger = logging.getLogger(__name__)
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
        logging.getLogger(__name__).critical(f"Error starting the bot: {e}", exc_info=True)
