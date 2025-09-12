import pytest

pytestmark = pytest.mark.asyncio


# ----- Helpers -----
class DummyUpdate:
    def __init__(self):
        self.messages = []
    async def reply_text(self, txt):
        self.messages.append(txt)


class DummyPost:
    def __init__(self, url, id_="pid"):
        self.url = url
        self.id = id_


# Quiet the logger used by the module under test
@pytest.fixture(autouse=True)
def quiet_logger(monkeypatch):
    class L:
        def info(self, *a, **k): pass
        def warning(self, *a, **k): pass
        def error(self, *a, **k): pass
    monkeypatch.setattr(
        "redditcommand.utils.log_manager.LogManager.setup_main_logger",
        lambda: L()
    )


# ----- Tests -----
async def test_pipeline_no_valid_subreddits_not_random(monkeypatch):
    # Arrange
    from redditcommand import pipeline as P
    u = DummyUpdate()
    calls = {"notify": []}

    async def init_client(getter):
        return object()
    async def validate(update, reddit, subs):
        return []
    async def notify_user(update, msg):
        calls["notify"].append(msg)
    async def notify_completion(*a, **k):
        pass

    monkeypatch.setattr(P, "PipelineHelper",
        type("PH", (), {
            "initialize_client": staticmethod(init_client),
            "validate_subreddits": staticmethod(validate),
            "notify_user": staticmethod(notify_user),
            "notify_completion": staticmethod(notify_completion),
        })
    )

    # MediaPostFetcher and MediaProcessor should not matter here
    monkeypatch.setattr(P, "MediaPostFetcher", lambda sem: None)
    monkeypatch.setattr(P, "MediaProcessor",
        type("MP", (), {
            "__init__": lambda self, r, u: None,
            "__aenter__": lambda self: self,
            "__aexit__": lambda self, *a: None,
            "process_batch": lambda self, *a, **k: [],
        })
    )

    # Act
    pl = P.RedditMediaPipeline(
        update=u,
        subreddit_names=["cats"],  # no "random"
        search_terms=[],
        media_count=1,
    )
    await pl.run()

    # Assert
    assert calls["notify"] == ["No valid or accessible subreddits provided."]


async def test_pipeline_happy_one_batch(monkeypatch):
    from redditcommand import pipeline as P

    u = DummyUpdate()
    record = {
        "validated_subs": None,
        "process_args": None,
        "notify_completion": None,
    }

    async def init_client(getter):  # getter is RedditClientManager.get_client
        return "reddit"
    async def validate(update, reddit, subs):
        record["validated_subs"] = subs
        return ["cats", "dogs"]
    async def notify_user(*a, **k):
        pass
    async def notify_completion(update, processed, requested, sent):
        record["notify_completion"] = (processed, requested, [p.url for p in sent])

    monkeypatch.setattr(P, "PipelineHelper",
        type("PH", (), {
            "initialize_client": staticmethod(init_client),
            "validate_subreddits": staticmethod(validate),
            "notify_user": staticmethod(notify_user),
            "notify_completion": staticmethod(notify_completion),
        })
    )

    class FakeFetcher:
        async def init_client(self): pass
        async def fetch_from_subreddits(
            self, subreddit_names, search_terms, sort, time_filter, media_type,
            media_count, update, processed_urls, include_comments
        ):
            # Return exactly media_count posts
            return [DummyPost(f"https://u/{i}") for i in range(media_count)]
    monkeypatch.setattr(P, "MediaPostFetcher", lambda sem: FakeFetcher())

    class FakeProcessor:
        def __init__(self, reddit, update): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def process_batch(self, posts, include_comments, include_flair, include_title):
            # Echo back all posts as "sent"
            record["process_args"] = (include_comments, include_flair, include_title, [p.url for p in posts])
            return posts
    monkeypatch.setattr(P, "MediaProcessor", FakeProcessor)

    pl = P.RedditMediaPipeline(
        update=u,
        subreddit_names=["cats", "dogs"],
        search_terms=["cute"],
        sort="hot",
        time_filter=None,
        media_count=2,
        media_type="video",
        include_comments=True,
        include_flair=False,
        include_title=True,
    )
    await pl.run()

    # Validated subs captured
    assert record["validated_subs"] == ["cats", "dogs"]
    # Processor received flags and posts
    pc, pf, pt, urls = record["process_args"]
    assert (pc, pf, pt) == (True, False, True)
    assert len(urls) == 2 and urls[0].startswith("https://u/")
    # Completion received with totals
    processed, requested, sent_urls = record["notify_completion"]
    assert processed == 2 and requested == 2 and len(sent_urls) == 2
    # processed_urls updated and not cleared for small count
    assert len(pl.processed_urls) == 2


async def test_pipeline_retries_then_success(monkeypatch):
    from redditcommand import pipeline as P

    u = DummyUpdate()
    seq = {"i": 0, "sleeps": 0, "fetch_calls": 0}

    async def init_client(getter): return "reddit"
    async def validate(update, reddit, subs): return ["sub"]

    async def fake_sleep(_):
        seq["sleeps"] += 1

    async def notify_user(*a, **k): pass
    async def notify_completion(*a, **k): pass

    monkeypatch.setattr(P, "PipelineHelper",
        type("PH", (), {
            "initialize_client": staticmethod(init_client),
            "validate_subreddits": staticmethod(validate),
            "notify_user": staticmethod(notify_user),
            "notify_completion": staticmethod(notify_completion),
        })
    )
    # Speed up test by reducing attempts
    monkeypatch.setattr(P.RetryConfig, "RETRY_ATTEMPTS", 3)
    monkeypatch.setattr(P, "asyncio",
        type("A", (), {"Semaphore": P.asyncio.Semaphore, "sleep": staticmethod(fake_sleep)})
    )

    class Fetcher:
        async def init_client(self): pass
        async def fetch_from_subreddits(self, *a, **k):
            seq["fetch_calls"] += 1
            # First call returns empty -> triggers retry and sleep
            if seq["i"] == 0:
                seq["i"] += 1
                return []
            # Second call returns one post -> success
            return [DummyPost("https://ok/1")]
    monkeypatch.setattr(P, "MediaPostFetcher", lambda sem: Fetcher())

    class Proc:
        def __init__(self, r, u): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def process_batch(self, posts, **k): return posts
    monkeypatch.setattr(P, "MediaProcessor", Proc)

    pl = P.RedditMediaPipeline(
        update=u,
        subreddit_names=["sub"],
        search_terms=[],
        media_count=1,
    )
    await pl.run()

    assert seq["fetch_calls"] >= 2
    assert seq["sleeps"] == 1
    assert pl.total_processed == 1


async def test_pipeline_processed_urls_cache_clears(monkeypatch):
    from redditcommand import pipeline as P

    u = DummyUpdate()
    async def init_client(getter): return "reddit"
    async def validate(update, reddit, subs): return ["s"]
    async def notify_user(*a, **k): pass
    async def notify_completion(*a, **k): pass

    monkeypatch.setattr(P, "PipelineHelper",
        type("PH", (), {
            "initialize_client": staticmethod(init_client),
            "validate_subreddits": staticmethod(validate),
            "notify_user": staticmethod(notify_user),
            "notify_completion": staticmethod(notify_completion),
        })
    )

    # Force small cache to trigger clearing
    monkeypatch.setattr(P.PipelineConfig, "MAX_PROCESSED_URLS", 3)

    class Fetcher:
        async def init_client(self): pass
        async def fetch_from_subreddits(self, *a, **k):
            # Return 4 unique posts so len(processed_urls) becomes 4 > 3
            return [DummyPost(f"https://p/{i}") for i in range(4)]
    monkeypatch.setattr(P, "MediaPostFetcher", lambda sem: Fetcher())

    class Proc:
        def __init__(self, r, u): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def process_batch(self, posts, **k): return posts  # mark all as sent
    monkeypatch.setattr(P, "MediaProcessor", Proc)

    pl = P.RedditMediaPipeline(
        update=u,
        subreddit_names=["s"],
        search_terms=[],
        media_count=4,
    )
    await pl.run()

    # Cache should have been cleared after exceeding 3
    assert len(pl.processed_urls) == 0
