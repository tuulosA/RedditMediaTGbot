import logging
from telegram import Update
from telegram.ext import CallbackContext
from reddit.config import Messages, MediaConfig
from typing import List

logger = logging.getLogger(__name__)


async def parse_command_args(update: Update, context: CallbackContext) -> tuple:
    """
    Parse command arguments and validate them.
    """
    logger.info(f"Parsing command arguments for user: {update.message.from_user.username}")

    if len(context.args) < 1:
        raise ValueError(Messages.INVALID_FORMAT_MESSAGE)

    # Extract time filter if present
    time_filter = None
    first_arg = context.args[0].lower()
    if first_arg in ["all", "year", "month", "week"]:
        time_filter = first_arg
        context.args.pop(0)

    if len(context.args) < 1:
        raise ValueError("Please specify at least one subreddit.")

    subreddit_names = parse_subreddits(context.args[0])
    media_count, media_type, search_terms, include_comments = parse_other_args(context.args[1:])

    return time_filter, subreddit_names, search_terms, media_count, media_type, include_comments


def parse_subreddits(arg: str) -> List[str]:
    """
    Parse and validate subreddit names.
    """
    subreddits = arg.split(",")
    if not all(subreddits):
        raise ValueError("Invalid subreddit format. Ensure names are comma-separated.")
    return subreddits


def parse_other_args(args: List[str]) -> tuple:
    """
    Parse search terms, media type, media count, and the include_comments flag.
    """
    media_count = 1
    media_type = None
    search_terms = []
    include_comments = False

    for arg in args:
        # Check for the `-c` flag
        if arg.lower() == "-c":
            include_comments = True
            continue

        # Check for media count
        try:
            count = int(arg)
            if 1 <= count <= MediaConfig.MAX_MEDIA_COUNT:
                media_count = count
            elif count > MediaConfig.MAX_MEDIA_COUNT:
                raise ValueError(f"Only up to {MediaConfig.MAX_MEDIA_COUNT} posts can be fetched at once.")
            continue
        except ValueError as e:
            # If a number is greater than MAX_MEDIA_COUNT, raise an error
            if str(e).startswith("Only up to"):
                raise e
            pass

        # Check for media type
        if arg.lower() in ["image", "video"]:
            media_type = arg.lower()
            continue

        # Treat everything else as a search term
        search_terms.append(arg.lower())

    return media_count, media_type, search_terms, include_comments
