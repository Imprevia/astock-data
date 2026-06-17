import os
from pathlib import Path

import pytest


pytest_plugins = ["pytester"]

LIVE_SKIP_REASON = "set ASTOCK_LIVE_TESTS=1 to run"


def pytest_configure(config):
    config.addinivalue_line("markers", "unit: fast offline unit tests")
    config.addinivalue_line("markers", "integration: offline integration tests")
    config.addinivalue_line("markers", "live: tests that may call real third-party APIs")


def pytest_collection_modifyitems(config, items):
    if os.environ.get("ASTOCK_LIVE_TESTS") == "1":
        return

    skip_live = pytest.mark.skip(reason=LIVE_SKIP_REASON)
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture
def tmp_cache_dir(tmp_path):
    return Path(tmp_path / "astock-cache").resolve()


@pytest.fixture
def settings_override(monkeypatch, tmp_cache_dir):
    monkeypatch.setenv("ASTOCK_CACHE_DIR", str(tmp_cache_dir))
    from astock_data.config import get_settings

    get_settings.cache_clear()
    yield tmp_cache_dir
    get_settings.cache_clear()


@pytest.fixture
def requests_mocker():
    import requests_mock

    with requests_mock.Mocker(real_http=False) as mocker:
        yield mocker
