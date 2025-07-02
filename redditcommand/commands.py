# redditcommand/commands.py

import logging
from telegram import Update
from telegram.ext import CallbackContext
from asyncprawcore.exceptions import NotFound, Forbidden

from redditcommand.config import Messages, RedditClientManager
from redditcommand.utils.command_utils import CommandParser, CommandUtils
from redditcommand.utils.file_state_utils import FollowedUserStore

logger = logging.getLogger(__name__)


class RedditCommandHandler:
    @staticmethod
    async def reddit_media_command(update: Update, context: CallbackContext) -> None:
        from redditcommand.pipeline import RedditMediaPipeline
        logger.info(f"Received /r command from {update.message.from_user.username}")

        if not context.args:
            await update.message.reply_text(Messages.USAGE_MESSAGE)
            logger.warning("No arguments provided.")
            return

        for path in ["logs/skip_debug.log", "logs/accepted_debug.log"]:
            try:
                open(path, "w").close()
            except Exception as e:
                logger.warning(f"Could not clear log file {path}: {e}")

        try:
            parsed_args = await CommandParser.parse(update, context)
            (
                time_filter, subreddit_names, search_terms,
                media_count, media_type,
                include_comments, include_flair, include_title
            ) = parsed_args

            if not subreddit_names:
                await update.message.reply_text("Please specify at least one valid subreddit.")
                return

            pipeline = RedditMediaPipeline(
                update=update,
                subreddit_names=subreddit_names,
                search_terms=search_terms,
                sort="top" if time_filter else "hot",
                time_filter=time_filter,
                media_count=media_count,
                media_type=media_type,
                include_comments=include_comments,
                include_flair=include_flair,
                include_title=include_title
            )
            await pipeline.run()

        except ValueError as e:
            await update.message.reply_text(str(e))
            logger.error(f"Argument parsing failed: {e}")
        except Exception as e:
            await update.message.reply_text("An unexpected error occurred. Please try again.")
            logger.error(f"Unexpected error: {e}", exc_info=True)

    @staticmethod
    async def clear_filter_command(update: Update, context: CallbackContext) -> None:
        tg_user = await CommandUtils.require_username(update)
        if not tg_user:
            return

        FollowedUserStore.clear_filters(tg_user)
        await update.message.reply_text("Your filters have been cleared.")

    @staticmethod
    async def set_filter_command(update: Update, context: CallbackContext) -> None:
        tg_user = await CommandUtils.require_username(update)
        if not tg_user:
            return

        input_text = " ".join(context.args).strip()
        if not input_text:
            await CommandUtils.show_user_filters(update, tg_user)
            return

        terms = [term.strip() for term in input_text.split(",") if term.strip()]
        if not terms:
            await update.message.reply_text("No valid terms provided.")
            return

        FollowedUserStore.set_filters(tg_user, terms)
        await update.message.reply_text(f"Filter terms set: {', '.join(terms)}")

    @staticmethod
    async def list_followed_users_command(update: Update, context: CallbackContext) -> None:
        tg_user = await CommandUtils.require_username(update)
        if not tg_user:
            return

        users = CommandUtils.get_followed_users(tg_user)
        if not users:
            await update.message.reply_text("You're not following any Reddit users.")
        else:
            await update.message.reply_text(
                "You're currently following:\n" + "\n".join(f"u/{u}" for u in sorted(users))
            )

    @staticmethod
    async def follow_user_command(update: Update, context: CallbackContext) -> None:
        tg_user = await CommandUtils.require_username(update)
        if not tg_user:
            return

        if not context.args or len(context.args) != 1:
            await update.message.reply_text("Usage: /follow <reddit_username>")
            return

        reddit_username = CommandUtils.sanitize_reddit_username(context.args[0])
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
        if tg_user in current_map.get(reddit_username, []):
            await update.message.reply_text(f"You're already following u/{reddit_username}.")
        else:
            FollowedUserStore.add_follower(reddit_username, tg_user)
            await update.message.reply_text(f"You're now following u/{reddit_username}!")

    @staticmethod
    async def unfollow_user_command(update: Update, context: CallbackContext) -> None:
        tg_user = await CommandUtils.require_username(update)
        if not tg_user:
            return

        if not context.args or len(context.args) != 1:
            await update.message.reply_text("Usage: /unfollow <reddit_username>")
            return

        reddit_username = CommandUtils.sanitize_reddit_username(context.args[0])
        current_map = FollowedUserStore.load_user_follower_map()
        if tg_user not in current_map.get(reddit_username, []):
            await update.message.reply_text(f"You're not following u/{reddit_username}.")
        else:
            FollowedUserStore.remove_follower(reddit_username, tg_user)
            await update.message.reply_text(f"You've unfollowed u/{reddit_username}.")
