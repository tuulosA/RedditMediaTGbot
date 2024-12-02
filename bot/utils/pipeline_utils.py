import logging
import asyncio
from typing import List
from asyncpraw.models import Submission

logger = logging.getLogger(__name__)


async def initialize_client(client_initializer):
    """
    Initialize a Reddit client with error handling.
    """
    try:
        return await asyncio.wait_for(client_initializer(), timeout=30)
    except asyncio.TimeoutError:
        raise RuntimeError("Reddit client initialization timed out.")
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Reddit client: {e}")


async def notify_user(update, message):
    """
    Send a notification to the user via Telegram.
    """
    logger.info(f"Notifying user: {message}")
    await update.message.reply_text(message)


def log_summary(posts: List[Submission]):
    """
    Log a summary of successfully sent posts.
    """
    if posts:
        logger.info("Pipeline Summary:")
        for post in posts:
            logger.info(f"Title: {post.title}, URL: {post.url}")
    else:
        logger.info("No posts were processed.")


async def validate_subreddits(reddit_instance, subreddit_names):
    """
    Validate subreddit accessibility.
    """
    valid_subreddits = []
    for subreddit_name in subreddit_names:
        try:
            subreddit = await reddit_instance.subreddit(subreddit_name)
            await subreddit.load()
            valid_subreddits.append(subreddit_name)
        except Exception:
            logger.warning(f"Subreddit {subreddit_name} is invalid or inaccessible.")
    return valid_subreddits
