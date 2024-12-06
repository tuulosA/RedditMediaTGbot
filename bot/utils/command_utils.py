#command_utils.py
import logging
from telegram import Update
from telegram.ext import CallbackContext
from bot.config import Messages, MediaConfig
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


async def parse_command_args(update: Update, context: CallbackContext) -> Tuple:
    """
    Parse and validate command arguments.
    """
    if not context.args:
        raise ValueError(Messages.INVALID_FORMAT_MESSAGE)

    time_filter, args = extract_time_filter(context.args)
    if not args:
        raise ValueError("Please specify at least one subreddit.")

    subreddit_names = parse_subreddits(args[0])
    media_count, media_type, search_terms, include_comments = parse_other_args(args[1:])

    if media_count > MediaConfig.MAX_MEDIA_COUNT:
        raise ValueError(Messages.MAX_COUNT_EXCEEDED_MESSAGE)

    logger.info(f"Command parsed for {update.message.from_user.username}: {locals()}")
    return time_filter, subreddit_names, search_terms, media_count, media_type, include_comments


def extract_time_filter(args: List[str]) -> Tuple[Optional[str], List[str]]:
    """
    Extracts the time filter if present and returns the remaining arguments.
    """
    time_filter = args[0].lower() if args[0].lower() in ["all", "year", "month", "week"] else None
    return time_filter, args[1:] if time_filter else args


def parse_subreddits(arg: str) -> List[str]:
    """
    Validates and splits subreddit names.
    """
    subreddits = [sub.strip() for sub in arg.split(",") if sub.strip()]
    if not subreddits:
        raise ValueError("Invalid subreddit format. Ensure names are comma-separated.")
    return subreddits


def parse_other_args(args: List[str]) -> Tuple[int, Optional[str], List[str], bool]:
    """
    Parses media count, type, search terms, and include_comments flag.
    """
    media_count = 1
    media_type = None
    search_terms = []
    include_comments = False

    for arg in args:
        if arg.lower() == "-c":
            include_comments = True
        elif arg.isdigit():
            count = int(arg)
            if count <= MediaConfig.MAX_MEDIA_COUNT:
                media_count = count
            else:
                raise ValueError(Messages.MAX_COUNT_EXCEEDED_MESSAGE)
        elif arg.lower() in ["image", "video"]:
            media_type = arg.lower()
        else:
            search_terms.append(arg.lower())

    return media_count, media_type, search_terms, include_comments
