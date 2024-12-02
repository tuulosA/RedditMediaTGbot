from telegram import Update
from telegram.ext import CallbackContext
import logging
from bot.pipeline import pipeline
from bot.utils.command_utils import parse_command_args
from bot.config import Messages

logger = logging.getLogger(__name__)


async def reddit_media_command(update: Update, context: CallbackContext) -> None:
    logger.info(f"Received /r command from {update.message.from_user.username}")

    if not context.args:
        await update.message.reply_text(Messages.USAGE_MESSAGE)
        logger.warning("No arguments provided.")
        return

    try:
        parsed_args = await parse_command_args(update, context)
        time_filter, subreddit_names, search_terms, media_count, media_type, include_comments = parsed_args

        if not subreddit_names:
            await update.message.reply_text("Please specify at least one valid subreddit.")
            logger.warning("No valid subreddit names provided.")
            return

        logger.info(f"Parsed command arguments: {parsed_args}")
        await pipeline(
            update,
            subreddit_names,
            search_terms,
            sort="top" if time_filter else "hot",
            time_filter=time_filter,
            media_count=media_count,
            media_type=media_type,
            include_comments=include_comments
        )

    except ValueError as e:
        await update.message.reply_text(str(e))
        logger.error(f"Argument parsing failed: {e}")
    except Exception as e:
        await update.message.reply_text("An unexpected error occurred. Please try again.")
        logger.error(f"Unexpected error: {e}", exc_info=True)
