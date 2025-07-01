# telegram_utils.py

from datetime import time, timezone, timedelta
from telegram.ext import Application, CommandHandler

from redditcommand.commands import (
    reddit_media_command,
    follow_user_command,
    unfollow_user_command,
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


def register_command_handlers(application: Application) -> None:
    commands = {
        'r': reddit_media_command,
        'rtopweek': send_weekly_top_post_command,
        'rtopday': send_daily_top_post_command,
        'rtopmonth': send_monthly_top_post_command,
        'rtopyear': send_yearly_top_post_command,
        'rtopall': send_all_time_top_post_command,
        'follow': follow_user_command,
        'followed': list_followed_users_command,
        'unfollow': unfollow_user_command,
        'filter': set_filter_command,
        'clearfilters': clear_filter_command
    }

    for cmd, handler in commands.items():
        application.add_handler(CommandHandler(cmd, handler))


def register_jobs(application: Application, chat_id: int) -> None:
    job_queue = application.job_queue

    job_queue.run_daily(send_daily_top_post_job, time=time(20, tzinfo=helsinki_time), name="daily_top_post")
    job_queue.run_daily(send_weekly_top_post_job, time=time(21, tzinfo=helsinki_time), days=(0,), name="weekly_top_post")
    job_queue.run_daily(send_monthly_top_post_job, time=time(0, 0, tzinfo=helsinki_time), name="monthly_top_post")
    job_queue.run_daily(send_yearly_top_post_job, time=time(0, 0, tzinfo=helsinki_time), name="yearly_top_post")

    job_queue.run_repeating(
        callback=lambda ctx: check_and_send_new_user_posts(ctx.job.chat_id),
        interval=300,
        first=10,
        name="followed_user_post_check",
        chat_id=chat_id
    )
