from pathlib import Path

import pytest
from pydantic import ValidationError

from astock_data.config import AStockSettings, get_settings
from astock_data.errors import (
    AStockDataError,
    AmbiguousTickerError,
    CacheError,
    DataSourceError,
    InvalidTickerError,
    MarketValidationError,
    NoDataError,
    RateLimitError,
    TickerResolutionError,
)


def test_defaults_load_without_env_vars(monkeypatch):
    monkeypatch.delenv("ASTOCK_EASTMONEY_MIN_INTERVAL", raising=False)
    monkeypatch.delenv("ASTOCK_CACHE_DIR", raising=False)
    monkeypatch.delenv("ASTOCK_LIVE_TESTS", raising=False)
    monkeypatch.delenv("ASTOCK_HTTP_PROXY", raising=False)
    monkeypatch.delenv("ASTOCK_USER_AGENT_POOL", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert isinstance(settings, AStockSettings)
    assert settings.eastmoney_min_interval == 1.0
    assert settings.request_timeout == 15.0
    assert settings.kline_cache_ttl_hours == 12.0
    assert settings.structured_cache_ttl_hours == 24.0
    assert settings.enable_live_tests is False
    assert settings.name_map_ttl_hours == 24.0
    assert settings.user_agent
    assert settings.http_proxy is None
    assert settings.user_agent_pool is None


def test_http_proxy_env_override(monkeypatch):
    monkeypatch.setenv("ASTOCK_HTTP_PROXY", "http://127.0.0.1:8080")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.http_proxy == "http://127.0.0.1:8080"


def test_user_agent_pool_env_override(monkeypatch):
    monkeypatch.setenv("ASTOCK_USER_AGENT_POOL", '["UA-X"]')
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.user_agent_pool == ["UA-X"]


def test_user_agent_pool_rejects_invalid_json(monkeypatch):
    monkeypatch.setenv("ASTOCK_USER_AGENT_POOL", "not-json")
    get_settings.cache_clear()

    with pytest.raises(ValidationError):
        get_settings()


def test_env_overrides_eastmoney_min_interval(monkeypatch):
    monkeypatch.setenv("ASTOCK_EASTMONEY_MIN_INTERVAL", "2.0")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.eastmoney_min_interval == 2.0


def test_live_tests_env_alias(monkeypatch):
    monkeypatch.setenv("ASTOCK_LIVE_TESTS", "true")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.enable_live_tests is True


def test_cache_dir_is_absolute_and_outside_source_repo(monkeypatch):
    monkeypatch.delenv("ASTOCK_CACHE_DIR", raising=False)
    get_settings.cache_clear()

    settings = get_settings()
    source_root = Path(__file__).resolve().parents[1]

    assert settings.cache_dir.is_absolute()
    assert not settings.cache_dir.is_relative_to(source_root)


def test_error_classes_are_importable_with_expected_bases():
    assert issubclass(TickerResolutionError, AStockDataError)
    assert issubclass(AmbiguousTickerError, TickerResolutionError)
    assert issubclass(InvalidTickerError, TickerResolutionError)
    assert issubclass(DataSourceError, AStockDataError)
    assert issubclass(RateLimitError, DataSourceError)
    assert issubclass(NoDataError, DataSourceError)
    assert issubclass(MarketValidationError, AStockDataError)
    assert issubclass(CacheError, AStockDataError)
