# tests/test_handle_direct_link.py
import asyncio
import types
import pytest

pytestmark = pytest.mark.asyncio

class DummyPost:
    def __init__(self, id="pid"): self.id = id

# Autouse: never open a real aiohttp.ClientSession
@pytest.fixture(autouse=True)
def stub_global_session_and_aiohttp(monkeypatch):
    # Generic dummy response used by default
    class DummyResp:
        status = 200
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def json(self):
            return {"files": {"mp4": {"url": "//cdn.example/video.mp4"}}}

    class DummySession:
        # Important: get() is a normal method returning an async context manager
        def get(self, url): 
            return DummyResp()
        async def close(self): pass

    # Also guard against accidental real ClientSession creation anywhere
    import aiohttp
    class DummyClientSession:
        def __init__(self, *a, **k): pass
        def get(self, url): return DummyResp()
        async def close(self): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
    monkeypatch.setattr(aiohttp, "ClientSession", DummyClientSession)

    # Patch the utils module class in case anything calls it directly
    class GS:
        @staticmethod
        async def get(): return DummySession()
    monkeypatch.setattr("redditcommand.utils.session.GlobalSession", GS)

    # And patch the symbol actually used by handle_direct_link
    from redditcommand import handle_direct_link as hdl
    monkeypatch.setattr(hdl, "GlobalSession", GS)

# Helpers
def _mk_tmpman(monkeypatch, mod, tmpdir):
    # Common TempFileManager stub: create_temp_dir returns tmpdir, cleanup_file records calls
    calls = {"cleaned": []}
    def create_temp_dir(prefix): return str(tmpdir)
    def extract_post_id_from_url(url): return "xid"
    def cleanup_file(path): calls["cleaned"].append(path)
    monkeypatch.setattr(mod, "TempFileManager",
        types.SimpleNamespace(
            create_temp_dir=create_temp_dir,
            extract_post_id_from_url=extract_post_id_from_url,
            cleanup_file=cleanup_file
        )
    )
    return calls

# 1) Dispatcher: passthrough for direct extensions
async def test_resolve_passthrough(monkeypatch):
    from redditcommand import handle_direct_link as hdl
    r = hdl.MediaLinkResolver()
    out = await r.resolve("https://site/x/file.mp4")
    assert out == "https://site/x/file.mp4"

# 2) Unsupported -> None
async def test_resolve_unsupported_returns_none(monkeypatch):
    from redditcommand import handle_direct_link as hdl
    r = hdl.MediaLinkResolver()
    out = await r.resolve("https://unknown.vendor/resource")
    assert out is None

# 3) v.redd.it success chooses first valid DASH url and downloads
async def test_vreddit_success(monkeypatch, tmp_path):
    from redditcommand import handle_direct_link as hdl
    tmp_calls = _mk_tmpman(monkeypatch, hdl, tmp_path)

    # find_first_valid_url returns the second DASH variant
    async def find_first_valid_url(candidates): return candidates[1]
    async def download_file(url, out): 
        p = tmp_path / "dl.mp4"
        p.write_bytes(b"x")
        return str(p)
    monkeypatch.setattr("redditcommand.utils.media_utils.MediaDownloader.find_first_valid_url", staticmethod(find_first_valid_url))
    monkeypatch.setattr("redditcommand.utils.media_utils.MediaDownloader.download_file", staticmethod(download_file))

    r = hdl.MediaLinkResolver()
    out = await r._v_reddit("https://v.redd.it/abc", DummyPost("p1"))
    assert out.endswith(".mp4")
    assert len(tmp_calls["cleaned"]) == 0  # vreddit path does not cleanup temp dir here

# 4) v.redd.it fail when no valid DASH
async def test_vreddit_no_valid(monkeypatch):
    from redditcommand import handle_direct_link as hdl
    async def find_first_valid_url(candidates): return None
    monkeypatch.setattr("redditcommand.utils.media_utils.MediaDownloader.find_first_valid_url", staticmethod(find_first_valid_url))
    r = hdl.MediaLinkResolver()
    out = await r._v_reddit("https://v.redd.it/abc", None)
    assert out is None

# 5) imgur uses RedditVideoResolver fallback when available
async def test_imgur_fallback_success(monkeypatch):
    from redditcommand import handle_direct_link as hdl

    async def resolve_video(post): return "/tmp/ok.mp4"
    # Patch the symbol used inside handle_direct_link
    monkeypatch.setattr(hdl, "RedditVideoResolver",
                        types.SimpleNamespace(resolve_video=resolve_video))

    r = hdl.MediaLinkResolver()
    out = await r._imgur("https://imgur.com/xyz", DummyPost())
    assert out == "/tmp/ok.mp4"

# 6) imgur fallback missing -> warning path returns None
async def test_imgur_fallback_none(monkeypatch):
    from redditcommand import handle_direct_link as hdl
    async def resolve_video(post): return None
    monkeypatch.setattr("redditcommand.utils.reddit_video_resolver.RedditVideoResolver", types.SimpleNamespace(resolve_video=resolve_video))
    r = hdl.MediaLinkResolver()
    out = await r._imgur("https://imgur.com/xyz", DummyPost())
    assert out is None

# 7) streamable happy path (JSON has files.mp4.url)
async def test_streamable_success(monkeypatch, tmp_path):
    from redditcommand import handle_direct_link as hdl
    tmp_calls = _mk_tmpman(monkeypatch, hdl, tmp_path)

    # Dummy session is provided by autouse fixture. Override download_file.
    async def download_file(url, out):
        p = tmp_path / "s.mp4"
        p.write_bytes(b"z")
        return str(p)
    monkeypatch.setattr("redditcommand.utils.media_utils.MediaDownloader.download_file", staticmethod(download_file))

    r = hdl.MediaLinkResolver()
    await r.init()
    out = await r._streamable("https://streamable.com/abcd", DummyPost("p2"))
    assert out.endswith(".mp4")

# 8) streamable non-200 -> None
async def test_streamable_non200(monkeypatch):
    from redditcommand import handle_direct_link as hdl
    # non-200
    class DummySession:
        def get(self, url):
            class Resp:
                status = 404
                async def __aenter__(self): return self
                async def __aexit__(self, *a): pass
                async def json(self): return {}
            return Resp()
    r = hdl.MediaLinkResolver()
    r.session = DummySession()
    out = await r._streamable("https://streamable.com/abcd", DummyPost())
    assert out is None

# 9) streamable JSON missing path -> None
async def test_streamable_missing_path(monkeypatch):
    from redditcommand import handle_direct_link as hdl
    # missing path
    class DummySession:
        def get(self, url):
            class Resp:
                status = 200
                async def __aenter__(self): return self
                async def __aexit__(self, *a): pass
                async def json(self): return {"files": {}}
            return Resp()
    r = hdl.MediaLinkResolver()
    r.session = DummySession()
    out = await r._streamable("https://streamable.com/abcd", DummyPost())
    assert out is None

# 10) redgifs happy path picks first available URL and downloads
async def test_redgifs_success(monkeypatch, tmp_path):
    from redditcommand import handle_direct_link as hdl
    _mk_tmpman(monkeypatch, hdl, tmp_path)

    class URLs: 
        hd = "https://cdn/hd.mp4"; sd = None; file_url = None
    class GIF: 
        urls = URLs()
    class FakeAPI:
        async def login(self): pass
        async def get_gif(self, gid): return GIF()
        async def close(self): pass
    monkeypatch.setattr("redditcommand.handle_direct_link.RedGifsAPI", FakeAPI)

    async def download_file(url, out):
        p = tmp_path / "rg.mp4"; p.write_bytes(b"a"); return str(p)
    monkeypatch.setattr("redditcommand.utils.media_utils.MediaDownloader.download_file", staticmethod(download_file))

    r = hdl.MediaLinkResolver()
    out = await r._redgifs("https://redgifs.com/watch/mmm", DummyPost())
    assert out.endswith(".mp4")

# 11) redgifs missing all URLs -> None
async def test_redgifs_missing_urls(monkeypatch):
    from redditcommand import handle_direct_link as hdl
    class URLs: hd = None; sd = None; file_url = None
    class GIF: urls = URLs()
    class FakeAPI:
        async def login(self): pass
        async def get_gif(self, gid): return GIF()
        async def close(self): pass
    monkeypatch.setattr("redditcommand.handle_direct_link.RedGifsAPI", FakeAPI)
    r = hdl.MediaLinkResolver()
    out = await r._redgifs("https://redgifs.com/watch/mmm", DummyPost())
    assert out is None

# 12) yt-dlp success path writes output file and returns it
async def test_ytdlp_success(monkeypatch, tmp_path):
    from redditcommand import handle_direct_link as hdl
    tmp_calls = _mk_tmpman(monkeypatch, hdl, tmp_path)

    class FakeProc:
        def __init__(self, rc=0): self.returncode = rc
        async def communicate(self): return b"", b""
    async def create_proc(*args, **kwargs): return FakeProc(rc=0)

    # Simulate yt-dlp creating the output file
    out_file = tmp_path / "reddit_xid.mp4"
    out_file.write_bytes(b"ok")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_proc)

    r = hdl.MediaLinkResolver()
    got = await r._download_with_ytdlp("https://youtu.be/x", "xid")
    assert got == str(out_file)
    assert len(tmp_calls["cleaned"]) == 0

# 13) yt-dlp failure cleans up and returns None
async def test_ytdlp_failure(monkeypatch, tmp_path):
    from redditcommand import handle_direct_link as hdl
    tmp_calls = _mk_tmpman(monkeypatch, hdl, tmp_path)

    class FakeProc:
        def __init__(self, rc=1): self.returncode = rc
        async def communicate(self): return b"", b"boom"
    async def create_proc(*a, **k): return FakeProc(rc=1)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_proc)

    r = hdl.MediaLinkResolver()
    got = await r._download_with_ytdlp("https://youtu.be/x", "xid")
    assert got is None
    # Cleans up temp dir path
    assert tmp_calls["cleaned"]
