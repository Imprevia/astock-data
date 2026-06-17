from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from platformdirs import user_cache_dir


def _default_cache_dir() -> Path:
    try:
        cache_path = Path(user_cache_dir("astock-data"))
    except Exception:
        cache_path = Path.home() / ".astock-data"
    return cache_path.expanduser().resolve()


class AStockSettings(BaseSettings):
    """Runtime settings for the pure A-share data layer."""

    model_config = SettingsConfigDict(env_prefix="ASTOCK_", extra="ignore")

    eastmoney_min_interval: float = 1.0
    request_timeout: float = 15.0
    cache_dir: Path = Field(default_factory=_default_cache_dir)
    kline_cache_ttl_hours: float = 12.0
    structured_cache_ttl_hours: float = 24.0
    enable_live_tests: bool = Field(default=False, validation_alias="ASTOCK_LIVE_TESTS")
    name_map_ttl_hours: float = 24.0
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36 astock-data/0.1.0"
    )

    @field_validator("cache_dir", mode="after")
    @classmethod
    def resolve_cache_dir(cls, value: Path) -> Path:
        """Normalize the cache directory to an absolute path."""

        return value.expanduser().resolve()


@lru_cache
def get_settings() -> AStockSettings:
    """Return cached package settings loaded from environment variables."""

    return AStockSettings()
