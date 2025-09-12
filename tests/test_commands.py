# tests/test_commands.py
import types
import pytest

pytestmark = pytest.mark.asyncio

# ----- Tiny Telegram stand-ins -----
class DummyFromUser:
    def __init__(self, username="tester"):
        self.username = username

class DummyMessage:
    def __init__(self):
        self.from_user = DummyFromUser()
        self.replies = []
    async def reply_text(self, text):
        self.replies.append(text)

class DummyUpdate:
    def __init__(self):
        self.message = DummyMessage()

class DummyContext:
    def __init__(self, args=None):
        self.args = args or []

# ----- Common fixtures -----
@pytest.fixture(autouse=True)
def patch_logger(monkeypatch):
    class L:
        def info(self, *a, **k): pass
        def warning(self, *a, **k): pass
        def error(self, *a, **k): pass
    monkeypatch.setattr("redditcommand.utils.log_manager.LogManager.setup_main_logger", lambda: L())

@pytest.fixture(autouse=True)
def default_require_username(monkeypatch):
    async def req(update):
        return "tg_user"
    monkeypatch.setattr("redditcommand.utils.command_utils.CommandUtils.require_username", req)

@pytest.fixture(autouse=True)
def patch_sanitizer(monkeypatch):
    monkeypatch.setattr(
        "redditcommand.utils.command_utils.CommandUtils.sanitize_reddit_username",
        staticmethod(lambda x: x)
    )

# ----- Tests for reddit_media_command -----
async def test_reddit_media_command_no_args(monkeypatch, tmp_path):
    from redditcommand import commands as C
    u = DummyUpdate()
    ctx = DummyContext(args=[])

    await C.RedditCommandHandler.reddit_media_command(u, ctx)
    from redditcommand.config import Messages
    assert u.message.replies == [Messages.USAGE_MESSAGE]

async def test_reddit_media_command_no_subreddits_after_parse(monkeypatch, tmp_path):
    from redditcommand import commands as C
    u = DummyUpdate()
    ctx = DummyContext(args=["something"])

    async def fake_parse(update, context):
        # time_filter, subreddit_names, search_terms, media_count, media_type, include_comments, include_flair, include_title
        return ("week", [], ["cats"], 2, "video", False, False, False)
    monkeypatch.setattr("redditcommand.utils.command_utils.CommandParser.parse", fake_parse)

    await C.RedditCommandHandler.reddit_media_command(u, ctx)
    from redditcommand.config import Messages
    assert u.message.replies == [Messages.NO_SUBREDDITS_PROVIDED]

async def test_reddit_media_command_happy(monkeypatch, tmp_path):
    from redditcommand import commands as C
    u = DummyUpdate()
    ctx = DummyContext(args=["week", "cats"])

    # Use temp files for logs
    monkeypatch.setattr("redditcommand.config.LogConfig", types.SimpleNamespace(
        SKIP_LOG_PATH=str(tmp_path / "skip.log"),
        ACCEPTED_LOG_PATH=str(tmp_path / "acc.log")
    ))

    async def fake_parse(update, context):
        return ("week", ["cats", "dogs"], ["cute"], 3, "video", True, True, False)
    monkeypatch.setattr("redditcommand.utils.command_utils.CommandParser.parse", fake_parse)

    called = {"kwargs": None, "ran": False}
    class FakePipeline:
        def __init__(self, **kwargs):
            called["kwargs"] = kwargs
        async def run(self):
            called["ran"] = True
    monkeypatch.setattr("redditcommand.pipeline.RedditMediaPipeline", FakePipeline)

    await C.RedditCommandHandler.reddit_media_command(u, ctx)

    assert called["ran"] is True
    k = called["kwargs"]
    from redditcommand.config import RedditDefaults
    assert k["subreddit_names"] == ["cats", "dogs"]
    assert k["search_terms"] == ["cute"]
    assert k["media_count"] == 3
    assert k["media_type"] == "video"
    assert k["include_comments"] is True and k["include_flair"] is True and k["include_title"] is False
    assert k["sort"] == RedditDefaults.DEFAULT_SORT_WITH_TIME_FILTER
    assert k["time_filter"] == "week"

async def test_reddit_media_command_sort_without_timefilter(monkeypatch, tmp_path):
    from redditcommand import commands as C
    u = DummyUpdate()
    ctx = DummyContext(args=["cats"])

    # Use temp files for logs
    monkeypatch.setattr("redditcommand.config.LogConfig", types.SimpleNamespace(
        SKIP_LOG_PATH=str(tmp_path / "skip2.log"),
        ACCEPTED_LOG_PATH=str(tmp_path / "acc2.log")
    ))

    async def fake_parse(update, context):
        return (None, ["cats"], ["meme"], 1, None, False, False, False)
    monkeypatch.setattr("redditcommand.utils.command_utils.CommandParser.parse", fake_parse)

    captured = {"kwargs": None}
    class FakePipeline:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs
        async def run(self): pass
    monkeypatch.setattr("redditcommand.pipeline.RedditMediaPipeline", FakePipeline)

    await C.RedditCommandHandler.reddit_media_command(u, ctx)
    from redditcommand.config import RedditDefaults
    assert captured["kwargs"]["sort"] == RedditDefaults.DEFAULT_SORT_NO_TIME_FILTER

async def test_reddit_media_command_valueerror(monkeypatch):
    from redditcommand import commands as C
    u = DummyUpdate()
    ctx = DummyContext(args=["x"])

    async def bad_parse(update, context):
        raise ValueError("bad args")
    monkeypatch.setattr("redditcommand.utils.command_utils.CommandParser.parse", bad_parse)

    await C.RedditCommandHandler.reddit_media_command(u, ctx)
    assert u.message.replies == ["bad args"]

async def test_reddit_media_command_unexpected(monkeypatch):
    from redditcommand import commands as C
    u = DummyUpdate()
    ctx = DummyContext(args=["x"])

    async def bad_parse(update, context):
        raise RuntimeError("whoops")
    monkeypatch.setattr("redditcommand.utils.command_utils.CommandParser.parse", bad_parse)

    await C.RedditCommandHandler.reddit_media_command(u, ctx)
    from redditcommand.config import Messages
    assert u.message.replies == [Messages.UNEXPECTED_ERROR]

# ----- clear_filter_command -----
async def test_clear_filter_command_requires_username(monkeypatch):
    from redditcommand import commands as C

    async def no_user(update):
        return None
    monkeypatch.setattr("redditcommand.utils.command_utils.CommandUtils.require_username", no_user)

    u = DummyUpdate()
    ctx = DummyContext()
    cleared = {"called": False}
    monkeypatch.setattr("redditcommand.utils.file_state_utils.FollowedUserStore.clear_filters",
                        lambda tg_user: cleared.__setitem__("called", True))

    await C.RedditCommandHandler.clear_filter_command(u, ctx)
    assert cleared["called"] is False
    assert u.message.replies == []

async def test_clear_filter_command_happy(monkeypatch):
    from redditcommand import commands as C
    u = DummyUpdate()
    ctx = DummyContext()
    called = {"user": None}
    monkeypatch.setattr("redditcommand.utils.file_state_utils.FollowedUserStore.clear_filters",
                        lambda tg_user: called.__setitem__("user", tg_user))
    await C.RedditCommandHandler.clear_filter_command(u, ctx)
    from redditcommand.config import Messages
    assert called["user"] == "tg_user"
    assert u.message.replies == [Messages.FILTERS_CLEARED]

# ----- set_filter_command -----
async def test_set_filter_command_show_when_empty(monkeypatch):
    from redditcommand import commands as C
    u = DummyUpdate()
    ctx = DummyContext(args=[])
    shown = {"called": False}
    async def show_user_filters(update, user):
        shown["called"] = True
    monkeypatch.setattr("redditcommand.utils.command_utils.CommandUtils.show_user_filters", show_user_filters)
    await C.RedditCommandHandler.set_filter_command(u, ctx)
    assert shown["called"] is True

async def test_set_filter_command_invalid_terms(monkeypatch):
    from redditcommand import commands as C
    u = DummyUpdate()
    ctx = DummyContext(args=[",", " ,  , "])
    await C.RedditCommandHandler.set_filter_command(u, ctx)
    from redditcommand.config import Messages
    assert u.message.replies == [Messages.NO_VALID_TERMS]

async def test_set_filter_command_happy(monkeypatch):
    from redditcommand import commands as C
    u = DummyUpdate()
    ctx = DummyContext(args=["cats,", " dogs  , ,fox  "])
    stored = {"user": None, "terms": None}
    monkeypatch.setattr("redditcommand.utils.file_state_utils.FollowedUserStore.set_filters",
                        lambda user, terms: (stored.__setitem__("user", user),
                                             stored.__setitem__("terms", terms)))
    await C.RedditCommandHandler.set_filter_command(u, ctx)
    from redditcommand.config import Messages
    assert stored["user"] == "tg_user"
    assert stored["terms"] == ["cats", "dogs", "fox"]
    assert u.message.replies == [Messages.FILTERS_SET.format(terms="cats, dogs, fox")]

# ----- list_followed_users_command -----
async def test_list_followed_users_empty(monkeypatch):
    from redditcommand import commands as C
    u = DummyUpdate()
    ctx = DummyContext()
    monkeypatch.setattr("redditcommand.utils.command_utils.CommandUtils.get_followed_users", lambda user: [])
    await C.RedditCommandHandler.list_followed_users_command(u, ctx)
    from redditcommand.config import Messages
    assert u.message.replies == [Messages.NOT_FOLLOWING_ANYONE]

async def test_list_followed_users_some(monkeypatch):
    from redditcommand import commands as C
    u = DummyUpdate()
    ctx = DummyContext()
    monkeypatch.setattr("redditcommand.utils.command_utils.CommandUtils.get_followed_users", lambda user: {"z", "a"})
    await C.RedditCommandHandler.list_followed_users_command(u, ctx)
    from redditcommand.config import Messages
    assert u.message.replies == [Messages.FOLLOWING_LIST_HEADER.format(users="u/a\nu/z")]

# ----- follow_user_command -----
async def test_follow_user_usage_when_no_arg(monkeypatch):
    from redditcommand import commands as C
    u = DummyUpdate()
    ctx = DummyContext(args=[])
    await C.RedditCommandHandler.follow_user_command(u, ctx)
    from redditcommand.config import Messages
    assert u.message.replies == [Messages.FOLLOW_USER_USAGE]

async def test_follow_user_user_not_found(monkeypatch):
    from redditcommand import commands as C
    # Replace exception classes in the module so except blocks match
    class NF(Exception): pass
    class FB(Exception): pass
    monkeypatch.setattr(C, "NotFound", NF)
    monkeypatch.setattr(C, "Forbidden", FB)

    class FakeRedditor:
        async def load(self): raise NF("nope")

    class Client:
        async def redditor(self, name): return FakeRedditor()

    async def get_client():
        return Client()
    # Patch the manager in the commands module, not config
    monkeypatch.setattr("redditcommand.commands.RedditClientManager",
                        types.SimpleNamespace(get_client=get_client))

    u = DummyUpdate()
    ctx = DummyContext(args=["u/abc"])
    await C.RedditCommandHandler.follow_user_command(u, ctx)
    from redditcommand.config import Messages
    assert u.message.replies == [Messages.USER_NOT_FOUND.format(username="u/abc")]

async def test_follow_user_generic_error(monkeypatch):
    from redditcommand import commands as C
    class FakeRedditor:
        async def load(self): raise RuntimeError("boom")
    class Client:
        async def redditor(self, name): return FakeRedditor()

    async def get_client():
        return Client()
    monkeypatch.setattr("redditcommand.commands.RedditClientManager",
                        types.SimpleNamespace(get_client=get_client))

    u = DummyUpdate()
    ctx = DummyContext(args=["name"])
    await C.RedditCommandHandler.follow_user_command(u, ctx)
    from redditcommand.config import Messages
    assert u.message.replies == [Messages.CHECK_USER_ERROR]

async def test_follow_user_already_following(monkeypatch):
    from redditcommand import commands as C
    class FakeRedditor:
        async def load(self): return None
    class Client:
        async def redditor(self, name): return FakeRedditor()

    async def get_client():
        return Client()
    monkeypatch.setattr("redditcommand.commands.RedditClientManager",
                        types.SimpleNamespace(get_client=get_client))

    monkeypatch.setattr("redditcommand.utils.file_state_utils.FollowedUserStore.load_user_follower_map",
                        lambda: {"name": ["tg_user"]})

    u = DummyUpdate()
    ctx = DummyContext(args=["name"])
    await C.RedditCommandHandler.follow_user_command(u, ctx)
    from redditcommand.config import Messages
    assert u.message.replies == [Messages.ALREADY_FOLLOWING.format(username="name")]

async def test_follow_user_new_follow(monkeypatch):
    from redditcommand import commands as C
    class FakeRedditor:
        async def load(self): return None
    class Client:
        async def redditor(self, name): return FakeRedditor()

    async def get_client():
        return Client()
    monkeypatch.setattr("redditcommand.commands.RedditClientManager",
                        types.SimpleNamespace(get_client=get_client))

    added = {"args": None}
    def add_follower(username, tg_user): added["args"] = (username, tg_user)
    monkeypatch.setattr("redditcommand.utils.file_state_utils.FollowedUserStore.add_follower", add_follower)
    monkeypatch.setattr("redditcommand.utils.file_state_utils.FollowedUserStore.load_user_follower_map", lambda: {})

    u = DummyUpdate()
    ctx = DummyContext(args=["name"])
    await C.RedditCommandHandler.follow_user_command(u, ctx)
    from redditcommand.config import Messages
    assert added["args"] == ("name", "tg_user")
    assert u.message.replies == [Messages.NOW_FOLLOWING.format(username="name")]

# ----- unfollow_user_command -----
async def test_unfollow_usage_when_no_arg(monkeypatch):
    from redditcommand import commands as C
    u = DummyUpdate()
    ctx = DummyContext(args=[])
    await C.RedditCommandHandler.unfollow_user_command(u, ctx)
    from redditcommand.config import Messages
    assert u.message.replies == [Messages.UNFOLLOW_USER_USAGE]

async def test_unfollow_not_following(monkeypatch):
    from redditcommand import commands as C
    monkeypatch.setattr("redditcommand.utils.file_state_utils.FollowedUserStore.load_user_follower_map", lambda: {})
    u = DummyUpdate()
    ctx = DummyContext(args=["name"])
    await C.RedditCommandHandler.unfollow_user_command(u, ctx)
    from redditcommand.config import Messages
    assert u.message.replies == [Messages.NOT_FOLLOWING_ANYONE]

async def test_unfollow_happy(monkeypatch):
    from redditcommand import commands as C
    removed = {"args": None}
    def remove_follower(username, tg_user): removed["args"] = (username, tg_user)
    monkeypatch.setattr("redditcommand.utils.file_state_utils.FollowedUserStore.remove_follower", remove_follower)
    monkeypatch.setattr("redditcommand.utils.file_state_utils.FollowedUserStore.load_user_follower_map",
                        lambda: {"name": ["tg_user"]})
    u = DummyUpdate()
    ctx = DummyContext(args=["name"])
    await C.RedditCommandHandler.unfollow_user_command(u, ctx)
    from redditcommand.config import Messages
    assert removed["args"] == ("name", "tg_user")
    assert u.message.replies == [Messages.UNFOLLOWED.format(username="name")]

# ----- set_subreddit_command -----
async def test_set_subreddit_no_args(monkeypatch):
    from redditcommand import commands as C
    u = DummyUpdate()
    ctx = DummyContext(args=[])
    await C.RedditCommandHandler.set_subreddit_command(u, ctx)
    from redditcommand.config import Messages
    assert u.message.replies == [Messages.PROVIDE_DEFAULT_SUBREDDIT]

async def test_set_subreddit_invalid(monkeypatch):
    from redditcommand import commands as C
    u = DummyUpdate()
    ctx = DummyContext(args=["cats!"])
    await C.RedditCommandHandler.set_subreddit_command(u, ctx)
    from redditcommand.config import Messages
    assert u.message.replies == [Messages.NO_SUBREDDITS_PROVIDED]

async def test_set_subreddit_happy(monkeypatch):
    from redditcommand import commands as C
    u = DummyUpdate()
    ctx = DummyContext(args=["Cats"])
    stored = {"sub": None}
    monkeypatch.setattr("redditcommand.utils.file_state_utils.FollowedUserStore.set_global_top_subreddit",
                        lambda s: stored.__setitem__("sub", s))
    await C.RedditCommandHandler.set_subreddit_command(u, ctx)
    from redditcommand.config import Messages
    assert stored["sub"] == "cats"
    assert u.message.replies == [Messages.DEFAULT_SUBREDDIT_SET.format(subreddit="cats")]
