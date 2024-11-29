import logging
import asyncio
from typing import List
from asyncpraw.models import Submission
from reddit.config import Paths

logger = logging.getLogger(__name__)

async def initialize_client(client_initializer):
    """
    Initialize a Reddit client with error handling.
    """
    logger.debug("Initializing Reddit client...")
    try:
        return await asyncio.wait_for(client_initializer(), timeout=30)
    except asyncio.TimeoutError:
        logger.error("Timeout occurred while initializing Reddit client.")
        raise RuntimeError("Failed to initialize the Reddit client. Please try again later.")
    except Exception as e:
        logger.error(f"Error initializing Reddit client: {e}", exc_info=True)
        raise RuntimeError("An unexpected error occurred while initializing the Reddit client.")

async def notify_user(update, message):
    """
    Send a notification message to the user via Telegram.
    """
    logger.info(f"Notifying user: {message}")
    await update.message.reply_text(message)

def log_summary(posts: List[Submission]):
    """
    Log a summary of posts that were successfully sent to the user.
    Handles Submission objects.
    """
    logger.info("Pipeline Summary of Successfully Sent Posts:")
    for post in posts:
        logger.info(f"Title: {post.title}, URL: {post.url}")

def clear_fetched_posts_log():
    """
    Clears the fetched posts log file at the start of a new pipeline run.
    """
    try:
        with open(Paths.FETCHED_POSTS_LOG_PATH, "w") as file:
            file.write("")  # Overwrite the file with an empty string
        logger.info("Cleared the fetched posts log file.")
    except Exception as e:
        logger.error(f"Failed to clear fetched posts log file: {e}", exc_info=True)

async def validate_subreddits(reddit_instance, subreddit_names):
    """
    Validates if the given subreddits exist and are accessible.

    Args:
        reddit_instance: Reddit API client instance.
        subreddit_names (list[str]): List of subreddit names to validate.

    Returns:
        list[str]: List of valid subreddit names.
    """
    valid_subreddits = []
    for subreddit_name in subreddit_names:
        try:
            subreddit = await reddit_instance.subreddit(subreddit_name)
            await subreddit.load()
            valid_subreddits.append(subreddit_name)
        except Exception as e:
            logger.warning(f"Subreddit {subreddit_name} is invalid or inaccessible: {e}")
    return valid_subreddits