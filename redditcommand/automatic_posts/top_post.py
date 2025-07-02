# redditcommand/automatic_posts/top_post.py

import os
import logging
from shutil import copy2
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Union

from telegram import Update, Bot
from asyncpraw.models import Submission

from redditcommand.config import RedditClientManager
from redditcommand.utils.filter_utils import FilterUtils
from redditcommand.utils.media_utils import MediaUtils
from redditcommand.media_handler import MediaProcessor

logger = logging.getLogger(__name__)
SubredditTarget = Union[Update, Tuple[Bot, int]]


class TopPostManager:
    def __init__(self, subreddit: str = "kpopfap"):
        self.subreddit = subreddit
        self.reddit = None
        self.timezone = timezone(timedelta(hours=3))
        self.base_dir = "auto_posts"

    async def init_client(self):
        self.reddit = await RedditClientManager.get_client()

    async def fetch_top_post(self, time_filter: str) -> Optional[Submission]:
        try:
            subreddit = await self.reddit.subreddit(self.subreddit)
            posts = [post async for post in subreddit.top(time_filter=time_filter, limit=50)]

            async with MediaProcessor(self.reddit, update=None) as processor:
                for post in posts:
                    if FilterUtils.should_skip(post, set(), None):
                        continue
                    await FilterUtils.attach_metadata(post)

                    resolved_url = await processor.resolve_media_url(post)
                    if not resolved_url:
                        continue

                    file_path = await processor.download_and_validate_media(resolved_url, post.id)
                    if not file_path:
                        continue

                    post.metadata["file_path"] = file_path
                    top_comment = await MediaUtils.fetch_top_comment(post, return_author=True)
                    post.metadata["top_comment"] = top_comment
                    if top_comment and not isinstance(top_comment, str):
                        post.metadata["top_comment_author"] = (
                            top_comment.author.name if top_comment.author else "[deleted]"
                        )
                    return post
            return None
        except Exception as e:
            logger.error(f"Error in fetch_top_post({time_filter}): {e}", exc_info=True)
            return None

    def build_caption(self, post: Submission, label: str) -> str:
        title = post.metadata.get("title", "No title")
        author = post.metadata.get("author", "[deleted]")
        flair = post.metadata.get("link_flair_text")
        upvotes = post.metadata.get("upvotes", 0)
        top_comment = post.metadata.get("top_comment")

        flair_text = f" [{flair}]" if flair and flair.lower() != "none" else ""
        caption = f"{label} ({upvotes} upvotes)\n\n{title}{flair_text} by u/{author}"

        if top_comment:
            if isinstance(top_comment, str):
                caption += f"\n\n💬 Top comment:\n{top_comment[:500]}"
            else:
                comment_author = post.metadata.get("top_comment_author", "[deleted]")
                caption += f"\n\n💬 Top comment by u/{comment_author}:\n{top_comment.body[:500]}"
        return caption

    def archive_post(self, post: Submission, file_path: str, time_filter: str):
        now = datetime.now(tz=self.timezone)
        subfolder = {
            "day": "daily",
            "week": "weekly",
            "month": "monthly",
            "year": "yearly"
        }.get(time_filter, "misc")

        suffix = now.strftime({
            "day": "_%Y-%m-%d",
            "week": "_week_%W_%Y",
            "month": "_month_%m_%Y",
            "year": "_year_%Y"
        }.get(time_filter, ""))

        save_dir = os.path.join(self.base_dir, subfolder)
        os.makedirs(save_dir, exist_ok=True)

        name_root, ext = os.path.splitext(os.path.basename(file_path))
        new_name = f"{name_root}{suffix}{ext}"
        dest_path = os.path.join(save_dir, new_name)
        metadata_path = os.path.join(save_dir, f"{name_root}{suffix}.txt")

        copy2(file_path, dest_path)
        logger.info(f"Saved media copy to {dest_path}")

        with open(metadata_path, "w", encoding="utf-8") as f:
            f.write(f"Title: {post.metadata.get('title', 'N/A')}\n")
            f.write(f"Author: {post.metadata.get('author', '[deleted]')}\n")
            f.write(f"Upvotes: {post.metadata.get('upvotes', 0)}\n")
            if post.metadata.get("link_flair_text"):
                f.write(f"Flair: {post.metadata['link_flair_text']}\n")
            top_comment = post.metadata.get("top_comment")
            author = post.metadata.get("top_comment_author", "[deleted]")
            if top_comment:
                if isinstance(top_comment, str):
                    f.write("\nTop comment:\n" + top_comment.strip()[:1000] + "\n")
                else:
                    f.write(f"\nTop comment by u/{author}:\n{top_comment.body.strip()[:1000]}\n")
            f.write(f"\nReddit URL: https://reddit.com/comments/{post.id}\n")
        logger.info(f"Saved metadata to {metadata_path}")