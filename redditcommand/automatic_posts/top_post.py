# top_post.py 

import os
import logging
import aiohttp

from typing import Optional, Tuple, Union
from telegram import Update, Bot
from telegram.ext import ContextTypes
from asyncpraw.models import Submission
from shutil import copy2
from datetime import datetime, timezone, timedelta

from redditcommand.config import RedditClientManager
from redditcommand.utils.filter_utils import FilterUtils
from redditcommand.utils.media_utils import MediaUtils

from redditcommand.media_handler import (
    resolve_media_url,
    download_and_validate_media,
    upload_media_to_telegram,
)

logger = logging.getLogger(__name__)

SubredditTarget = Union[Update, Tuple[Bot, int]]


async def fetch_single_top_media_post(
    subreddit_name: str,
    reddit,
    time_filter: str = "day"
) -> Optional[Submission]:
    try:
        subreddit = await reddit.subreddit(subreddit_name)
        top_posts = [post async for post in subreddit.top(time_filter=time_filter, limit=50)]

        async with aiohttp.ClientSession() as session:
            for post in top_posts:
                if FilterUtils.should_skip(post, set(), None):
                    continue

                await FilterUtils.attach_metadata(post)
                resolved_url = await resolve_media_url(post, reddit, session)
                if not resolved_url:
                    continue

                file_path = await download_and_validate_media(resolved_url, session, post_id=post.id)
                if not file_path:
                    continue

                post.metadata["file_path"] = file_path
                top_comment = await MediaUtils.fetch_top_comment(post, return_author=True)  # returns Comment
                post.metadata["top_comment"] = top_comment
                if top_comment and not isinstance(top_comment, str):
                    post.metadata["top_comment_author"] = top_comment.author.name if top_comment.author else "[deleted]"
                return post
        return None

    except Exception as e:
        logger.error(f"Failed in fetch_single_top_media_post ({time_filter}): {e}", exc_info=True)
        return None
      

def build_caption(post: Submission, label: str) -> str:
    title = post.metadata.get("title", "No title")
    author = post.metadata.get("author", "[deleted]")
    flair = post.metadata.get("link_flair_text")
    upvotes = post.metadata.get("upvotes", 0)
    top_comment = post.metadata.get("top_comment")

    # Move flair inline with title
    flair_text = f" [{flair}]" if flair and flair.lower() != "none" else ""
    caption = f"{label} ({upvotes} upvotes)\n\n{title}{flair_text} by u/{author}"

    if top_comment:
        if isinstance(top_comment, str):
            caption += f"\n\n💬 Top comment:\n{top_comment[:500]}"
        else:
            comment_author = top_comment.author.name if top_comment.author else "[deleted]"
            caption += f"\n\n💬 Top comment by u/{comment_author}:\n{top_comment.body[:500]}"
    return caption


def get_save_paths(file_path: str, time_filter: str) -> Tuple[str, str]:
    now = datetime.now(tz=timezone(timedelta(hours=3)))
    base_dir = "auto_posts"
    suffix = ""
    subfolder = "misc"

    if time_filter == "day":
        suffix = now.strftime("_%Y-%m-%d")
        subfolder = "daily"
    elif time_filter == "week":
        suffix = now.strftime("_week_%W_%Y")
        subfolder = "weekly"
    elif time_filter == "month":
        suffix = now.strftime("_month_%m_%Y")
        subfolder = "monthly"
    elif time_filter == "year":
        suffix = now.strftime("_year_%Y")
        subfolder = "yearly"

    save_dir = os.path.join(base_dir, subfolder)
    os.makedirs(save_dir, exist_ok=True)

    original_name = os.path.basename(file_path)
    name_root, ext = os.path.splitext(original_name)
    new_name = f"{name_root}{suffix}{ext}"
    dest_path = os.path.join(save_dir, new_name)
    metadata_path = os.path.join(save_dir, f"{name_root}{suffix}.txt")

    return dest_path, metadata_path


def archive_post(post: Submission, file_path: str, time_filter: str) -> None:
    dest_path, metadata_path = get_save_paths(file_path, time_filter)

    copy2(file_path, dest_path)
    logger.info(f"Saved media copy to {dest_path}")

    with open(metadata_path, "w", encoding="utf-8") as f:
        f.write(f"Title: {post.metadata.get('title', 'N/A')}\n")
        f.write(f"Author: {post.metadata.get('author', '[deleted]')}\n")
        f.write(f"Upvotes: {post.metadata.get('upvotes', 0)}\n")
        flair = post.metadata.get("link_flair_text")
        if flair and flair != "None":
            f.write(f"Flair: {flair}\n")
        top_comment = post.metadata.get("top_comment")
        top_comment_author = post.metadata.get("top_comment_author", "[deleted]")
        if top_comment:
            if isinstance(top_comment, str):
                f.write("\nTop comment:\n")
                f.write(top_comment.strip()[:1000] + "\n")
            else:
                f.write(f"\nTop comment by u/{top_comment_author}:\n")
                f.write(top_comment.body.strip()[:1000] + "\n")
        f.write(f"\nReddit URL: https://reddit.com/comments/{post.id}\n")
    logger.info(f"Saved metadata to {metadata_path}")


async def send_top_post(
    label: str,
    time_filter: str,
    chat_id: int,
    bot,
    update: Update = None,
    subreddit_name: str = "kpopfap",
    archive: bool = True
) -> None:
    try:
        reddit = await RedditClientManager.get_client()
        post = await fetch_single_top_media_post(subreddit_name, reddit, time_filter=time_filter)

        if not post:
            raise RuntimeError("No suitable media post found.")

        caption = build_caption(post, label)
        file_path = post.metadata["file_path"]
        target: SubredditTarget = update if update else (bot, chat_id)

        if archive:
            archive_post(post, file_path, time_filter)

        logger.info(f"{label} sent: https://reddit.com/comments/{post.id}")

        if not await upload_media_to_telegram(file_path, target, caption):
            raise RuntimeError("Media upload failed.")

    except Exception as e:
        logger.error(f"Failed to send {label.lower()}: {e}", exc_info=True)
        msg = f"Failed to fetch {label.lower()}."
        if update:
            await update.message.reply_text(msg)
        else:
            await bot.send_message(chat_id=chat_id, text=msg)


async def send_daily_top_post_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_top_post("TOP POST OF THE DAY", "day", update.effective_chat.id, context.bot, update, archive=False)

async def send_weekly_top_post_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_top_post("TOP POST OF THE WEEK", "week", update.effective_chat.id, context.bot, update, archive=False)

async def send_monthly_top_post_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_top_post("TOP POST OF THE MONTH", "month", update.effective_chat.id, context.bot, update, archive=False)

async def send_yearly_top_post_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_top_post("TOP POST OF THE YEAR", "year", update.effective_chat.id, context.bot, update, archive=False)

async def send_all_time_top_post_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_top_post("TOP POST OF ALL TIME", "all", update.effective_chat.id, context.bot, update, archive=False)


async def send_daily_top_post_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = int(os.getenv("TELEGRAM_CHAT_ID"))
    await send_top_post("TOP POST OF THE DAY", "day", chat_id, context.bot, archive=True)

async def send_weekly_top_post_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = int(os.getenv("TELEGRAM_CHAT_ID"))
    await send_top_post("TOP POST OF THE WEEK", "week", chat_id, context.bot, archive=True)

async def send_monthly_top_post_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(tz=timezone(timedelta(hours=3)))
    if now.day != 1:
        return
    chat_id = int(os.getenv("TELEGRAM_CHAT_ID"))
    await send_top_post("TOP POST OF THE MONTH", "month", chat_id, context.bot, archive=True)

async def send_yearly_top_post_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(tz=timezone(timedelta(hours=3)))
    if not (now.month == 1 and now.day == 1):
        return
    chat_id = int(os.getenv("TELEGRAM_CHAT_ID"))
    await send_top_post("TOP POST OF THE YEAR", "year", chat_id, context.bot, archive=True)
