# redditcommand/fetch.py

import asyncio
import random
from typing import Optional, List, Set
from asyncpraw.models import Submission

from .config import RedditClientManager, MediaConfig, RedditDefaults
from .filter_posts import MediaPostFilter
from redditcommand.utils.fetch_utils import RedditPostFetcher, FetchOrchestrator
from redditcommand.utils.log_manager import LogManager

logger = LogManager.setup_main_logger()


class MediaPostFetcher:
    def __init__(self, semaphore: Optional[asyncio.Semaphore] = None):
        self.semaphore = semaphore or asyncio.Semaphore(MediaConfig.DEFAULT_SEMAPHORE_LIMIT)
        self.reddit = None

    async def init_client(self):
        if not self.reddit:
            self.reddit = await RedditClientManager.get_client()

    async def fetch_from_subreddits(
        self,
        subreddit_names: List[str],
        search_terms: Optional[List[str]] = None,
        sort: str = RedditDefaults.DEFAULT_SORT_NO_TIME_FILTER,
        time_filter: Optional[str] = None,
        media_type: Optional[str] = None,
        media_count: int = 1,
        update=None,
        invalid_subreddits: Optional[Set[str]] = None,
        include_comments: bool = False,
        processed_urls: Optional[Set[str]] = None,
    ) -> List[Submission]:
        await self.init_client()

        invalid_subreddits = invalid_subreddits or set()
        processed_urls = processed_urls or set()
        processed_post_ids = set()
        media_posts = []

        valid_subreddits = [s for s in subreddit_names if s not in invalid_subreddits]
        random.shuffle(valid_subreddits)

        fetch_tasks = [
            self.fetch_from_single_subreddit(
                subreddit_name=s,
                search_terms=search_terms,
                sort=sort,
                time_filter=time_filter,
                media_type=media_type,
                target_count=max(1, media_count // len(valid_subreddits)),
                processed_post_ids=processed_post_ids,
                update=update,
                processed_urls=processed_urls,
            )
            for s in valid_subreddits
        ]

        results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
        for s_name, result in zip(valid_subreddits, results):
            if isinstance(result, Exception):
                logger.error(f"Subreddit '{s_name}' task failed: {result}", exc_info=True)
            elif isinstance(result, list):
                media_posts.extend(result)
            else:
                logger.warning(f"Unexpected result from subreddit '{s_name}': {type(result)}")

        filtered = [post for post in media_posts if post.url not in processed_urls]
        logger.info(f"Removed {len(media_posts) - len(filtered)} duplicates. Returning {len(filtered)} posts.")
        return filtered[:media_count]

    async def fetch_from_single_subreddit(
        self,
        subreddit_name: str,
        search_terms: Optional[List[str]],
        sort: str,
        time_filter: Optional[str],
        media_type: Optional[str],
        target_count: int,
        processed_post_ids: Set[str],
        update,
        processed_urls: Set[str],
    ) -> List[Submission]:
        async with self.semaphore:
            try:
                posts, display_name = await FetchOrchestrator.get_posts(
                    reddit=self.reddit,
                    subreddit_name=subreddit_name,
                    search_terms=search_terms,
                    sort=sort,
                    time_filter=time_filter,
                    update=update
                )

                if not posts:
                    logger.info(f"No results from r/{display_name or subreddit_name}")
                    return []

                filterer = MediaPostFilter(
                    subreddit_name=display_name or subreddit_name,
                    media_type=media_type,
                    media_count=target_count,
                    processed_urls=processed_urls,
                )
                filtered = await filterer.filter(posts)
                unique = await RedditPostFetcher.filter_duplicates(filtered, processed_post_ids)
                logger.info(f"r/{display_name}: {len(unique)} unique posts")
                return unique

            except Exception as e:
                logger.error(f"Error from subreddit '{subreddit_name}': {e}", exc_info=True)
                return []
