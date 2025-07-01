# Updated commands.py to use extended CommandParser with title/flair flags

import logging
from telegram import Update
from telegram.ext import CallbackContext

from redditcommand.config import Messages
from redditcommand.utils.command_utils import CommandParser
from redditcommand.pipeline import pipeline
from redditcommand.utils.file_state_utils import FollowedUserStore
from asyncprawcore.exceptions import NotFound, Forbidden
from redditcommand.config import RedditClientManager

logger = logging.getLogger(__name__)


async def reddit_media_command(update: Update, context: CallbackContext) -> None:
    logger.info(f"Received /r command from {update.message.from_user.username}")

    if not context.args:
        await update.message.reply_text(Messages.USAGE_MESSAGE)
        logger.warning("No arguments provided.")
        return

    log_paths = ["logs/skip_debug.log", "logs/accepted_debug.log"]
    for path in log_paths:
        try:
            open(path, "w").close()
        except Exception as e:
            logger.warning(f"Could not clear log file {path}: {e}")

    try:
        parsed_args = await CommandParser.parse(update, context)
        (
            time_filter,
            subreddit_names,
            search_terms,
            media_count,
            media_type,
            include_comments,
            include_flair,
            include_title
        ) = parsed_args

        if not subreddit_names:
            await update.message.reply_text("Please specify at least one valid subreddit.")
            logger.warning("No valid subreddit names provided.")
            return

        logger.info(f"Parsed command arguments: {parsed_args}")
        await pipeline(
            update,
            subreddit_names,
            search_terms,
            sort="top" if time_filter else "hot",
            time_filter=time_filter,
            media_count=media_count,
            media_type=media_type,
            include_comments=include_comments,
            include_flair=include_flair,
            include_title=include_title
        )

    except ValueError as e:
        await update.message.reply_text(str(e))
        logger.error(f"Argument parsing failed: {e}")
    except Exception as e:
        await update.message.reply_text("An unexpected error occurred. Please try again.")
        logger.error(f"Unexpected error: {e}", exc_info=True)


async def clear_filter_command(update: Update, context: CallbackContext) -> None:
    telegram_user = update.message.from_user
    tg_username = telegram_user.username
    if not tg_username:
        await update.message.reply_text("You need a Telegram @username to use this feature.")
        return

    FollowedUserStore.clear_filters(tg_username)
    await update.message.reply_text("Your filters have been cleared.")


async def set_filter_command(update: Update, context: CallbackContext) -> None:
    telegram_user = update.message.from_user
    tg_username = telegram_user.username
    if not tg_username:
        await update.message.reply_text("You need a Telegram @username to use this feature.")
        return

    input_text = " ".join(context.args).strip()
    if not input_text:
        current_filters = FollowedUserStore.get_filters(tg_username)
        if not current_filters:
            await update.message.reply_text("You have no active filters.")
        else:
            await update.message.reply_text(f"Your active filters: {', '.join(current_filters)}")
        return

    terms = [term.strip() for term in input_text.split(",") if term.strip()]
    if not terms:
        await update.message.reply_text("No valid terms provided.")
        return

    FollowedUserStore.set_filters(tg_username, terms)
    await update.message.reply_text(f"Filter terms set: {', '.join(terms)}")


async def list_followed_users_command(update: Update, context: CallbackContext) -> None:
    telegram_user = update.message.from_user
    tg_username = telegram_user.username

    if not tg_username:
        await update.message.reply_text("You need a Telegram @username to use this feature.")
        return

    follower_map = FollowedUserStore.load_user_follower_map()
    followed_users = [reddit_user for reddit_user, tg_users in follower_map.items() if tg_username in tg_users]

    if not followed_users:
        await update.message.reply_text("You're not following any Reddit users.")
    else:
        await update.message.reply_text(
            "You're currently following:\n" + "\n".join(f"u/{user}" for user in sorted(followed_users))
        )


async def follow_user_command(update: Update, context: CallbackContext) -> None:
    telegram_user = update.message.from_user
    logger.info(f"Received /follow command from {telegram_user.username or telegram_user.id}")

    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /follow <reddit_username>")
        return

    reddit_username = context.args[0].lstrip("u/").strip().lower()
    if not reddit_username:
        await update.message.reply_text("Invalid Reddit username.")
        return

    tg_username = telegram_user.username
    if not tg_username:
        await update.message.reply_text("You need a Telegram @username to use this feature.")
        return

    try:
        reddit = await RedditClientManager.get_client()
        redditor = await reddit.redditor(reddit_username)
        await redditor.load()
    except (NotFound, Forbidden):
        await update.message.reply_text(f"Reddit user u/{reddit_username} was not found or is private.")
        return
    except Exception as e:
        logger.error(f"Failed to verify Reddit user u/{reddit_username}: {e}", exc_info=True)
        await update.message.reply_text("An error occurred while checking the Reddit user.")
        return

    current_map = FollowedUserStore.load_user_follower_map()
    already_following = tg_username in current_map.get(reddit_username, [])

    if already_following:
        await update.message.reply_text(f"You're already following u/{reddit_username}.")
    else:
        FollowedUserStore.add_follower(reddit_username, tg_username)
        await update.message.reply_text(f"You're now following u/{reddit_username}!")


async def unfollow_user_command(update: Update, context: CallbackContext) -> None:
    telegram_user = update.message.from_user
    logger.info(f"Received /unfollow command from {telegram_user.username or telegram_user.id}")

    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /unfollow <reddit_username>")
        return

    reddit_username = context.args[0].lstrip("u/").strip().lower()
    if not reddit_username:
        await update.message.reply_text("Invalid Reddit username.")
        return

    tg_username = telegram_user.username
    if not tg_username:
        await update.message.reply_text("You need a Telegram @username to use this feature.")
        return

    current_map = FollowedUserStore.load_user_follower_map()
    followers = set(current_map.get(reddit_username, []))

    if tg_username not in followers:
        await update.message.reply_text(f"You're not following u/{reddit_username}.")
    else:
        FollowedUserStore.remove_follower(reddit_username, tg_username)
        await update.message.reply_text(f"You've unfollowed u/{reddit_username}.")
