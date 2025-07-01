# Refactored pipeline_utils.py using PipelineHelper class for better structure

import logging
import asyncio

from typing import List
from asyncpraw.models import Submission

logger = logging.getLogger(__name__)


class PipelineHelper:
    @staticmethod
    async def initialize_client(client_initializer):
        try:
            return await asyncio.wait_for(client_initializer(), timeout=30)
        except asyncio.TimeoutError:
            raise RuntimeError("Reddit client initialization timed out.")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Reddit client: {e}")

    @staticmethod
    async def notify_user(update, message: str):
        logger.info(f"Notifying user: {message}")
        await update.message.reply_text(message)

    @staticmethod
    async def validate_subreddits(update, reddit_instance, subreddit_names: List[str]) -> List[str]:
        valid, invalid = [], []

        for name in subreddit_names:
            if name.lower() == "random":
                valid.append(name)
                continue
            try:
                subreddit = await reddit_instance.subreddit(name)
                await subreddit.load()
                valid.append(name)
            except Exception as e:
                logger.warning(f"Subreddit {name} is invalid or inaccessible: {e}")
                invalid.append(name)

        if invalid and not valid:
            await PipelineHelper.notify_user(update, "No valid or accessible subreddits provided.")
            logger.warning(f"All subreddits invalid: {', '.join(invalid)}")
        else:
            logger.info(f"Valid subreddits: {', '.join(valid)}")

        return valid

    @staticmethod
    def log_post_summary(posts: List[Submission]):
        if posts:
            logger.info("Pipeline Summary:")
            for post in posts:
                logger.info(f"Title: {post.title}, URL: {post.url}")
        else:
            logger.info("No posts were processed.")

    @staticmethod
    async def notify_completion(update, total_processed: int, media_count: int, posts: List[Submission]):
        if total_processed == 0:
            await PipelineHelper.notify_user(update, "No posts found.")
        elif total_processed < media_count:
            await PipelineHelper.notify_user(update, f"Only {total_processed}/{media_count} posts found.")

        PipelineHelper.log_post_summary(posts)
        logger.info("Pipeline completed successfully.")