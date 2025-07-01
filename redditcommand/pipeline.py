# Updated pipeline.py to use PipelineHelper class

import random
import asyncio
import logging

from redditcommand.config import RedditClientManager, MediaConfig, RetryConfig
from redditcommand.utils.pipeline_utils import PipelineHelper

from .fetch import fetch_posts_to_list
from .media_handler import process_media_batch

logger = logging.getLogger(__name__)


async def pipeline(
    update,
    subreddit_names: list[str],
    search_terms: list[str],
    sort: str = "hot",
    time_filter: str = None,
    media_count: int = 1,
    media_type: str = None,
    include_comments: bool = False,
    include_flair: bool = False,
    include_title: bool = False,
    fetch_semaphore_limit: int = MediaConfig.DEFAULT_SEMAPHORE_LIMIT,
):
    logger.info(f"Starting pipeline for subreddits: {', '.join(subreddit_names)}")
    fetch_semaphore = asyncio.Semaphore(fetch_semaphore_limit)
    processed_urls = set()
    successfully_sent_posts = []
    total_processed = 0
    backoff = 1.0

    try:
        reddit = await PipelineHelper.initialize_client(RedditClientManager.get_client)
        valid_subreddits = await PipelineHelper.validate_subreddits(update, reddit, subreddit_names)

        if not valid_subreddits and "random" not in subreddit_names:
            await PipelineHelper.notify_user(update, "No valid or accessible subreddits provided.")
            logger.warning("No valid subreddits to proceed with.")
            return

        for attempt in range(1, RetryConfig.RETRY_ATTEMPTS + 1):
            remaining = media_count - total_processed
            if remaining <= 0:
                break

            logger.info(f"Attempt {attempt}: fetching {remaining} post(s)")
            filtered = await fetch_posts_to_list(
                subreddit_names=valid_subreddits,
                search_terms=search_terms,
                sort=sort,
                time_filter=time_filter,
                media_type=media_type,
                media_count=remaining,
                semaphore=fetch_semaphore,
                update=update,
                processed_urls=processed_urls,
                include_comments=include_comments,
            )

            if not filtered:
                sleep_duration = backoff * random.uniform(0.5, 1.5)
                logger.warning(f"No new media found. Retrying after {sleep_duration:.2f}s.")
                await asyncio.sleep(sleep_duration)
                backoff = min(backoff * 1.5, 30.0)
                continue

            processed_urls.update(post.url for post in filtered)
            if len(processed_urls) > 10_000:
                logger.warning("Processed URL cache exceeded 10k entries. Resetting.")
                processed_urls.clear()

            sent = await process_media_batch(
                filtered, reddit, update,
                include_comments=include_comments,
                include_flair=include_flair,
                include_title=include_title
            )
            successfully_sent_posts.extend(sent)
            total_processed += len(sent)

        await PipelineHelper.notify_completion(update, total_processed, media_count, successfully_sent_posts)

    except RuntimeError as e:
        logger.error(f"Pipeline error: {e}")
        await PipelineHelper.notify_user(update, str(e))

    except Exception as e:
        logger.error("Unexpected pipeline error", exc_info=True)
        await PipelineHelper.notify_user(update, "An unexpected error occurred.")