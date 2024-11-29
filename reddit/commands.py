from telegram import Update
from telegram.ext import CallbackContext
import logging
from reddit.pipeline import pipeline
from reddit.utils.command_utils import parse_command_args
from reddit.config import Messages

logger = logging.getLogger(__name__)


async def reddit_media_command(update: Update, context: CallbackContext) -> None:
    logger.info(f"Received /r command from user: {update.message.from_user.username}")

    if not context.args:
        await update.message.reply_text(Messages.USAGE_MESSAGE)
        logger.warning("No arguments provided in /r command")
        return

    try:
        # Updated to include `include_comments`
        time_filter, subreddit_names, search_terms, media_count, media_type, include_comments = await parse_command_args(update, context)

        if not subreddit_names:
            logger.warning("Subreddit names not provided or invalid")
            await update.message.reply_text("Please specify at least one valid subreddit.")
            return

        logger.info(
            f"Parsed command: time_filter={time_filter}, subreddits={subreddit_names}, "
            f"search_terms={search_terms}, media_count={media_count}, media_type={media_type}, "
            f"include_comments={include_comments}"
        )

        # Start the pipeline
        await pipeline(
            update,
            subreddit_names,
            search_terms,
            sort="top" if time_filter else "hot",
            time_filter=time_filter,
            media_count=media_count,
            media_type=media_type,
            include_comments=include_comments,  # Pass the include_comments flag
        )

    except ValueError as e:
        logger.error(f"Argument parsing failed: {e}")
        await update.message.reply_text(str(e))
    except Exception as e:
        logger.error(f"Unexpected error in reddit_media_command: {e}", exc_info=True)
        await update.message.reply_text("An unexpected error occurred. Please try again.")