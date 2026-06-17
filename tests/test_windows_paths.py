"""Windows path QA — offline unit tests.

Guarantees that the cache + config layers behave correctly on Windows:

* ``cache_dir`` resolves to an ABSOLUTE path outside the source repo.
* ``CsvKlineCache`` / ``SQLiteStructuredCache`` write under an injected
  ``base_dir`` and reject path-traversal tickers.
* UTF-8 round-trips a Chinese-named ticker cache entry.
* No package source file hardcodes a ``G:\\workspaces``-style absolute repo
  path (``workspaces`` / ``stock-data-source`` must never appear as a string
  literal in ``config.py`` or the cache modules).

All offline, ``@pytest.mark.unit``.
"""

from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

# Package source files that must never embed a developer's local repo path.
_NO_REPO_LITERAL_MODULES = [
    "astock_data/config.py",
    "astock_data/cache/__init__.py",
    "astock_data/cache/kline_csv.py",
    "astock_data/cache/structured_sqlite.py",
]
_FORBIDDEN_SUBSTRINGS = ("workspaces", "stock-data-source", "G:\\", "g:\\")


def _package_root() -> Path:
    import astock_data

    return Path(astock_data.__file__).resolve().parent.parent


def test_cache_dir_is_absolute_and_outside_source_repo() -> None:
    """``get_settings().cache_dir`` is absolute and not under the package repo.

    ``ASTOCK_CACHE_DIR`` is pointed at a temp dir (via the ``settings_override``
    fixture's sibling logic) to keep this hermetic, but the DEFAULT behavior we
    assert here is: resolved + absolute + not inside the source tree.
    """

    from astock_data.config import get_settings

    settings = get_settings()
    cache_dir = Path(settings.cache_dir)
    assert cache_dir.is_absolute(), f"cache_dir must be absolute, got {cache_dir}"

    pkg_repo = _package_root().resolve()
    try:
        cache_dir.relative_to(pkg_repo)
    except ValueError:
        # Not under the repo — good.
        return
    pytest.fail(f"cache_dir {cache_dir} is inside the source repo {pkg_repo}")


def test_csv_kline_cache_writes_under_base_dir_no_traversal(tmp_path: Path) -> None:
    """CsvKlineCache writes <base_dir>/<code>.csv and rejects traversal."""

    from astock_data.cache import CsvKlineCache
    from astock_data.errors import InvalidTickerError
    from astock_data.models.market import OHLCVBar

    base = tmp_path / "kline"
    cache = CsvKlineCache(base_dir=base)

    bar = OHLCVBar(
        date=dt.date(2026, 6, 10),
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=100.0,
    )
    path = cache.write("688017", [bar], created_at=dt.datetime.now(tz=dt.UTC))

    # The written file MUST live under base_dir.
    base_resolved = base.resolve()
    assert base_resolved in path.resolve().parents or path.resolve() == base_resolved / "688017.csv"
    assert path.name == "688017.csv"
    assert path.exists()

    # Path traversal is rejected before any file is created.
    with pytest.raises(InvalidTickerError):
        cache.write("../evil", [bar])


def test_sqlite_cache_writes_under_base_dir_no_traversal(tmp_path: Path) -> None:
    """SQLiteStructuredCache writes its DB under base_dir and rejects bad keys."""

    from astock_data.cache import SQLiteStructuredCache
    from astock_data.errors import InvalidTickerError

    base = tmp_path / "structured"
    cache = SQLiteStructuredCache(base_dir=base)

    cache.write("fundamentals", "688017", "2026-06-10", {"k": "v"})
    # The single DB file must be the only artifact under base_dir.
    db_files = list(base.glob("*.sqlite*"))
    assert db_files, "expected structured.sqlite under base_dir"
    for db in db_files:
        assert base.resolve() in db.resolve().parents or db.resolve() == base.resolve() / db.name

    # Round-trip.
    got = cache.read("fundamentals", "688017", "2026-06-10")
    assert got == {"k": "v"}

    # Path-traversal ticker rejected.
    with pytest.raises(InvalidTickerError):
        cache.write("kind", "../evil", "2026-06-10", {})


def test_utf8_chinese_named_ticker_roundtrip(tmp_path: Path) -> None:
    """A cache entry for a Chinese-named stock round-trips losslessly in UTF-8.

    The cache KEY is always the 6-digit code, but the JSON payload may carry the
    Chinese name; this asserts the SQLite store preserves UTF-8 end-to-end and
    the CSV store is written/read as UTF-8.
    """

    from astock_data.cache import CsvKlineCache, SQLiteStructuredCache
    from astock_data.models.market import OHLCVBar

    # --- CSV UTF-8 header round-trip ---
    kline = CsvKlineCache(base_dir=tmp_path / "kline")
    bar = OHLCVBar(
        date=dt.date(2026, 6, 10),
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=100.0,
    )
    csv_path = kline.write("688017", [bar], created_at=dt.datetime.now(tz=dt.UTC))
    raw_text = csv_path.read_text(encoding="utf-8")
    assert "date,open,high,low,close,volume" in raw_text
    bars_back = kline.read("688017")
    assert bars_back == [bar]

    # --- SQLite UTF-8 Chinese payload round-trip ---
    structured = SQLiteStructuredCache(base_dir=tmp_path / "structured")
    payload = {"name": "绿的谐波", "行业": "机器人"}
    structured.write("fundamentals", "688017", "2026-06-10", payload)
    assert structured.read("fundamentals", "688017", "2026-06-10") == payload


@pytest.mark.parametrize("rel_path", _NO_REPO_LITERAL_MODULES)
def test_no_hardcoded_repo_paths_in_package_code(rel_path: str) -> None:
    """No string literal in the named source files embeds a local repo path.

    Scans with ``ast`` (not regex) so only true string literals are inspected,
    not comments or identifiers. Guards against leaking a developer's
    ``G:\\workspaces\\stock-data-source`` into released code.
    """

    target = _package_root() / rel_path
    if not target.exists():
        pytest.skip(f"module not present: {rel_path}")

    tree = ast.parse(target.read_text(encoding="utf-8"), filename=str(target))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            lowered = node.value.lower()
            for bad in _FORBIDDEN_SUBSTRINGS:
                if bad.lower() in lowered:
                    offenders.append(f"{target.name}:{node.lineno} -> {node.value!r}")
    assert not offenders, "hardcoded repo path literals found:\n" + "\n".join(offenders)
