import asyncio
import types
import pytest

pytestmark = pytest.mark.asyncio

# Minimal stand-ins
class DummySubmission:
    def __init__(self, id, url):
        self.id = id
        self.url = url

@pytest.fixture(autouse=True)
def patch_reddit_client(monkeypatch):
    # Avoid creating a real client
    class RCM:
        @staticmethod
        async def get_client():
            return object()
    monkeypatch.setattr("redditcommand.fetch.RedditClientManager", RCM)

@pytest.fixture(autouse=True)
def deterministic_shuffle(monkeypatch):
    # Keep subreddits order stable in tests
    monkeypatch.setattr("random.shuffle", lambda x: None)

# 1) Happy path across multiple subreddits, processed_urls and slicing enforced
async def test_fetch_from_subreddits_happy(monkeypatch):
    from redditcommand import fetch as F

    # Orchestrator returns posts for each subreddit
    calls = []
    async def get_posts(reddit, subreddit_name, search_terms, sort, time_filter, update):
        calls.append(subreddit_name)
        posts = [
            DummySubmission(f"{subreddit_name}-1", f"https://u/{subreddit_name}/1"),
            DummySubmission(f"{subreddit_name}-2", f"https://u/{subreddit_name}/2"),
        ]
        return posts, subreddit_name
    monkeypatch.setattr("redditcommand.utils.fetch_utils.FetchOrchestrator.get_posts", get_posts)

    # Filter passes through first N posts
    created_filters = []
    class FakeFilter:
        def __init__(self, subreddit_name, media_type, media_count, processed_urls):
            self.subreddit_name = subreddit_name
            self.media_type = media_type
            self.media_count = media_count
            self.processed_urls = processed_urls
            created_filters.append(self)
        async def filter(self, posts):
            return posts[: self.media_count]
    monkeypatch.setattr("redditcommand.fetch.MediaPostFilter", FakeFilter)

    # No dedup within a subreddit here
    async def filter_duplicates(posts, processed_post_ids):
        return posts
    monkeypatch.setattr("redditcommand.utils.fetch_utils.RedditPostFetcher.filter_duplicates", filter_duplicates)

    # One URL already processed across subs will be removed at the end
    processed_urls = { "https://u/a/1" }

    fp = F.MediaPostFetcher()
    out = await fp.fetch_from_subreddits(
        subreddit_names=["a", "b"],
        search_terms=["cat"],
        sort="hot",
        time_filter=None,
        media_type="video",
        media_count=3,
        processed_urls=processed_urls,
    )

    # We asked 3 total with 2 subs, target_count is max(1, 3 // 2) == 1 per sub
    # Items: a/1 and b/1; a/1 is in processed_urls so only b/1 remains
    assert len(out) == 1
    assert [p.url for p in out] == ["https://u/b/1"]

    # Filter instances captured correct target count
    assert [f.media_count for f in created_filters] == [1, 1]
    # Orchestrator called each subreddit
    assert calls == ["a", "b"]

# 2) Handles exception from one subreddit and still returns others
async def test_fetch_from_subreddits_handles_exception(monkeypatch):
    from redditcommand import fetch as F

    async def get_posts(reddit, subreddit_name, **kwargs):
        if subreddit_name == "badsub":
            raise RuntimeError("boom")
        return [DummySubmission("ok", f"https://u/{subreddit_name}/ok")], subreddit_name
    monkeypatch.setattr("redditcommand.utils.fetch_utils.FetchOrchestrator.get_posts", get_posts)

    class PF:
        def __init__(self, *a, **k): pass
        async def filter(self, posts): return posts
    monkeypatch.setattr("redditcommand.fetch.MediaPostFilter", PF)

    async def filter_duplicates(posts, processed_post_ids): return posts
    monkeypatch.setattr("redditcommand.utils.fetch_utils.RedditPostFetcher.filter_duplicates", filter_duplicates)

    fp = F.MediaPostFetcher()
    out = await fp.fetch_from_subreddits(["good", "badsub"], media_count=2)
    # One subreddit failed, we still get the other
    assert [p.url for p in out] == ["https://u/good/ok"]

# 3) fetch_from_single_subreddit returns [] if no posts
async def test_fetch_from_single_no_posts(monkeypatch):
    from redditcommand import fetch as F

    async def get_posts(**kwargs): return [], "rname"
    monkeypatch.setattr("redditcommand.utils.fetch_utils.FetchOrchestrator.get_posts", get_posts)

    fp = F.MediaPostFetcher()
    res = await fp.fetch_from_single_subreddit(
        subreddit_name="x",
        search_terms=None,
        sort="hot",
        time_filter=None,
        media_type=None,
        target_count=2,
        processed_post_ids=set(),
        update=None,
        processed_urls=set(),
    )
    assert res == []

# 4) fetch_from_single_subreddit passes through filter, then removes duplicates by id
async def test_fetch_from_single_filters_and_uniques(monkeypatch):
    from redditcommand import fetch as F

    posts = [DummySubmission("a", "u1"), DummySubmission("b", "u2"), DummySubmission("b", "u2")]

    async def get_posts(**kwargs): return posts, "x"
    monkeypatch.setattr("redditcommand.utils.fetch_utils.FetchOrchestrator.get_posts", get_posts)

    class PF:
        def __init__(self, subreddit_name, media_type, media_count, processed_urls):
            self.media_count = media_count
        async def filter(self, posts): return posts[: self.media_count]
    monkeypatch.setattr("redditcommand.fetch.MediaPostFilter", PF)

    async def filter_duplicates(posts, processed_post_ids):
        # Simulate removing duplicate by id
        seen = set()
        out = []
        for p in posts:
            if p.id in seen:
                continue
            seen.add(p.id)
            out.append(p)
        return out
    monkeypatch.setattr("redditcommand.utils.fetch_utils.RedditPostFetcher.filter_duplicates", filter_duplicates)

    fp = F.MediaPostFetcher()
    res = await fp.fetch_from_single_subreddit(
        subreddit_name="x",
        search_terms=None,
        sort="hot",
        time_filter=None,
        media_type=None,
        target_count=3,
        processed_post_ids=set(),
        update=None,
        processed_urls=set(),
    )
    # One duplicate removed
    assert [p.id for p in res] == ["a", "b"]

# 5) processed_urls at the end removes cross-subreddit dupes and slicing to media_count applies
async def test_fetch_from_subreddits_processed_urls_and_slice(monkeypatch):
    from redditcommand import fetch as F

    async def get_posts(reddit, subreddit_name, **kwargs):
        # Both subs yield the same URL to test de-dupe at the end
        return [DummySubmission(f"{subreddit_name}-id", "https://same/url")], subreddit_name
    monkeypatch.setattr("redditcommand.utils.fetch_utils.FetchOrchestrator.get_posts", get_posts)

    class PF:
        def __init__(self, *a, **k): pass
        async def filter(self, posts): return posts
    monkeypatch.setattr("redditcommand.fetch.MediaPostFilter", PF)

    async def filter_duplicates(posts, processed_post_ids): return posts
    monkeypatch.setattr("redditcommand.utils.fetch_utils.RedditPostFetcher.filter_duplicates", filter_duplicates)

    fp = F.MediaPostFetcher()
    out = await fp.fetch_from_subreddits(
        subreddit_names=["a", "b", "c"],
        media_count=2,
        processed_urls={"https://same/url"},  # already seen
    )
    # All items removed as duplicates, nothing to return
    assert out == []

# 6) invalid_subreddits are skipped and target_count derived from remaining
async def test_invalid_subreddits_and_target_count(monkeypatch):
    from redditcommand import fetch as F

    seen = []
    async def get_posts(reddit, subreddit_name, **kwargs):
        seen.append(subreddit_name)
        # Two posts per sub
        return [
            DummySubmission(f"{subreddit_name}-1", f"u/{subreddit_name}/1"),
            DummySubmission(f"{subreddit_name}-2", f"u/{subreddit_name}/2"),
        ], subreddit_name
    monkeypatch.setattr("redditcommand.utils.fetch_utils.FetchOrchestrator.get_posts", get_posts)

    class PF:
        def __init__(self, subreddit_name, media_type, media_count, processed_urls):
            self.media_count = media_count
        async def filter(self, posts): return posts[: self.media_count]
    monkeypatch.setattr("redditcommand.fetch.MediaPostFilter", PF)

    async def filter_duplicates(posts, processed_post_ids): return posts
    monkeypatch.setattr("redditcommand.utils.fetch_utils.RedditPostFetcher.filter_duplicates", filter_duplicates)

    fp = F.MediaPostFetcher()
    out = await fp.fetch_from_subreddits(
        subreddit_names=["ok1", "skipme", "ok2"],
        media_count=5,
        invalid_subreddits={"skipme"},
    )
    # Only ok1 and ok2 called
    assert seen == ["ok1", "ok2"]
    # target_count = max(1, 5 // 2) = 2 per sub, hence 4 total returned
    assert len(out) == 4
    assert {p.id for p in out} == {"ok1-1", "ok1-2", "ok2-1", "ok2-2"}

# 7) fetch_from_single_subreddit error path returns []
async def test_fetch_from_single_catches_exception(monkeypatch):
    from redditcommand import fetch as F

    async def get_posts(**kwargs):
        raise RuntimeError("network down")
    monkeypatch.setattr("redditcommand.utils.fetch_utils.FetchOrchestrator.get_posts", get_posts)

    fp = F.MediaPostFetcher()
    res = await fp.fetch_from_single_subreddit(
        subreddit_name="x",
        search_terms=None,
        sort="hot",
        time_filter=None,
        media_type=None,
        target_count=1,
        processed_post_ids=set(),
        update=None,
        processed_urls=set(),
    )
    assert res == []
