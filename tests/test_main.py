# tests/test_main.py
import types
import importlib.util
import pathlib
import pytest
import os

def _fake_logger():
    class L:
        def info(self, *a, **k): pass
        def warning(self, *a, **k): pass
        def error(self, *a, **k): pass
    return L()

@pytest.fixture
def clear_env(monkeypatch):
    # Windows env names are case-insensitive, be thorough
    keys = [
        "TELEGRAM_API_KEY", "Telegram_Api_Key", "telegram_api_key",
        "TELEGRAM_CHAT_ID", "Telegram_Chat_Id", "telegram_chat_id",
    ]
    for k in keys:
        monkeypatch.delenv(k, raising=False)

@pytest.fixture
def fake_log_manager(monkeypatch):
    import redditcommand.utils.log_manager as lm
    L = _fake_logger()
    fake_mod = types.SimpleNamespace(
        setup_error_logging=lambda *a, **k: None,
        setup_main_logger=lambda *a, **k: L,
    )
    monkeypatch.setattr(lm, "LogManager", fake_mod)
    return L

class FakeApp:
    def __init__(self): self.ran = False
    def run_polling(self): self.ran = True

class FakeBuilder:
    def __init__(self): self._token = None
    def token(self, t): self._token = t; return self
    def build(self): return FakeApp()

@pytest.fixture
def fake_application(monkeypatch):
    import telegram.ext as te
    monkeypatch.setattr(te, "Application", types.SimpleNamespace(builder=lambda: FakeBuilder()))
    return te.Application  # not used directly, but keeps symmetry

@pytest.fixture
def fake_registrar(monkeypatch):
    import telegram_utils.regist as regist
    calls = {"handlers": None, "jobs": None}
    class R:
        @staticmethod
        def register_command_handlers(app): calls["handlers"] = app
        @staticmethod
        def register_jobs(app, chat_id: int): calls["jobs"] = (app, chat_id)
    monkeypatch.setattr(regist, "TelegramRegistrar", R)
    return calls

def import_main_fresh(monkeypatch):
    # Never load .env during tests
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)

    # Load your project’s __main__.py by path under a unique module name
    main_path = pathlib.Path(__file__).resolve().parents[1] / "__main__.py"
    spec = importlib.util.spec_from_file_location("app_main_under_test", str(main_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def test_main_missing_env_vars(clear_env, fake_log_manager, fake_application, fake_registrar, monkeypatch):
    # Force empty values regardless of the shell
    monkeypatch.setenv("TELEGRAM_API_KEY", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")

    mod = import_main_fresh(monkeypatch)
    mod.main()

    # With no env, app should not register handlers or jobs
    assert fake_registrar["handlers"] is None
    assert fake_registrar["jobs"] is None

def test_main_happy_path(fake_log_manager, fake_application, fake_registrar, monkeypatch):
    monkeypatch.setenv("TELEGRAM_API_KEY", "abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "707296886")

    mod = import_main_fresh(monkeypatch)
    mod.main()

    assert fake_registrar["handlers"] is not None
    app, chat_id = fake_registrar["jobs"]
    assert isinstance(app, FakeApp)
    assert chat_id == 707296886
    assert app.ran is True
