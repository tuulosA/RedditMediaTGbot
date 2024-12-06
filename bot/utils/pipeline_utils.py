#pipeline_utils.py
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


async def validate_and_notify_subreddits(update, reddit_instance, subreddit_names):
    """
    Validate subreddit accessibility and notify the user if none are valid.
    """
    valid_subreddits = []
    for subreddit_name in subreddit_names:
        try:
            subreddit = await reddit_instance.subreddit(subreddit_name)
            await subreddit.load()
            valid_subreddits.append(subreddit_name)
        except Exception:
            logger.warning(f"Subreddit {subreddit_name} is invalid or inaccessible.")

    if not valid_subreddits:
        await notify_user(update, "No valid or accessible subreddits provided.")
        logger.warning("All provided subreddits were invalid.")
    else:
        logger.info(f"Valid subreddits: {', '.join(valid_subreddits)}")

    return valid_subreddits


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


async def notify_completion(update, total_processed, media_count, successfully_sent_posts):
    """
    Notifies the user about the completion of the pipeline.
    """
    if total_processed < media_count:
        await notify_user(update, f"Only {total_processed}/{media_count} posts found.")
    log_summary(successfully_sent_posts)
    logger.info("Pipeline completed successfully.")
