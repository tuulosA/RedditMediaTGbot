# main.py

import os

from dotenv import load_dotenv

from datetime import time, timezone, timedelta
from telegram.ext import Application, CommandHandler

from redditcommand.utils.logger import setup_logging

from redditcommand.commands import (
    reddit_media_command,
    follow_user_command,
    unfollow_user_command,
    set_filter_command,
    set_filter_command,
    clear_filter_command,
    list_followed_users_command
)

from redditcommand.automatic_posts.top_post import (
    send_daily_top_post_job,
    send_daily_top_post_command,
    send_weekly_top_post_job,
    send_weekly_top_post_command,
    send_monthly_top_post_job,
    send_monthly_top_post_command,
    send_yearly_top_post_job,
    send_yearly_top_post_command,
    send_all_time_top_post_command
)

from redditcommand.follow_user import check_and_send_new_user_posts

helsinki_time = timezone(timedelta(hours=3))


def main():
    load_dotenv()

    logger = setup_logging()
    logger.info("Bot is starting...")

    telegram_api_key = os.getenv("TELEGRAM_API_KEY")
    if not telegram_api_key:
        logger.error("TELEGRAM_API_KEY is not set in the environment. Exiting...")
        return
    
    application = Application.builder().token(telegram_api_key).build()

    command_handlers = [
        CommandHandler('r', reddit_media_command),
        CommandHandler('rtopweek', send_weekly_top_post_command),
        CommandHandler('rtopday', send_daily_top_post_command),
        CommandHandler('rtopmonth', send_monthly_top_post_command),
        CommandHandler('rtopyear', send_yearly_top_post_command),
        CommandHandler('rtopall', send_all_time_top_post_command),
        CommandHandler("follow", follow_user_command),
        CommandHandler("followed", list_followed_users_command),
        CommandHandler("unfollow", unfollow_user_command),
        CommandHandler("filter", set_filter_command),
        CommandHandler("clearfilters", clear_filter_command)
    ]
    
    for handler in command_handlers:
        application.add_handler(handler)

    job_queue = application.job_queue

    job_queue.run_daily(
        send_daily_top_post_job,
        time=time(hour=20, tzinfo=helsinki_time),
        days=(0, 1, 2, 3, 4, 5, 6),
        name="daily_top_post"
    )

    job_queue.run_daily(
        send_weekly_top_post_job,
        time=time(hour=21, tzinfo=helsinki_time),
        days=(0,),
        name="weekly_top_post"
    )

    job_queue.run_daily(
        send_monthly_top_post_job,
        time=time(hour=0, minute=0, tzinfo=helsinki_time),
        name="monthly_top_post"
    )

    job_queue.run_daily(
        send_yearly_top_post_job,
        time=time(hour=0, minute=0, tzinfo=helsinki_time),
        name="yearly_top_post"
    )

    job_queue.run_repeating(
        callback=lambda ctx: check_and_send_new_user_posts(ctx.job.chat_id),
        interval=300,  # every 10 minutes
        first=10,  # first run after 10 seconds
        name="followed_user_post_check",
        chat_id=int(os.getenv("TELEGRAM_CHAT_ID"))
    )

    logger.info("Bot is now polling...")
    application.run_polling()

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"Error starting the bot: {e}")
