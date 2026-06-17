import csv
import datetime as dt
import json
import sqlite3
import threading

import pytest

from astock_data.errors import CacheError, InvalidTickerError
from astock_data.models.market import OHLCVBar

cache_module = pytest.importorskip("astock_data.cache", reason="Task 12 cache implementation pending")

CsvKlineCache = cache_module.CsvKlineCache
SQLiteStructuredCache = cache_module.SQLiteStructuredCache


def test_csv_kline_cache_roundtrips_ohlcv_rows(tmp_path):
    cache = CsvKlineCache(base_dir=tmp_path)
    bars = [
        OHLCVBar(
            date=dt.date(2026, 6, 15),
            open=10.1,
            high=10.9,
            low=9.8,
            close=10.5,
            volume=123456,
        ),
        OHLCVBar(
            date=dt.date(2026, 6, 16),
            open=10.5,
            high=11.2,
            low=10.2,
            close=10.8,
            volume=234567,
        ),
    ]

    cache.write("688017", bars)

    assert cache.read("688017") == bars


def test_csv_kline_cache_uses_safe_normalized_filename(tmp_path):
    cache = CsvKlineCache(base_dir=tmp_path)
    cache.write("688017", [])

    files = list(tmp_path.rglob("*.csv"))
    assert len(files) == 1
    assert files[0].name == "688017.csv"
    assert files[0].resolve().is_relative_to(tmp_path.resolve())


def test_csv_kline_cache_rejects_path_traversal_key(tmp_path):
    cache = CsvKlineCache(base_dir=tmp_path)

    with pytest.raises((InvalidTickerError, CacheError)):
        cache.write("../evil", [])


def test_csv_kline_cache_returns_none_for_stale_entry(tmp_path):
    cache = CsvKlineCache(base_dir=tmp_path, ttl=dt.timedelta(seconds=60))
    cache.write(
        "688017",
        [
            OHLCVBar(
                date=dt.date(2026, 6, 15),
                open=10.1,
                high=10.9,
                low=9.8,
                close=10.5,
                volume=123456,
            )
        ],
        created_at=dt.datetime(2026, 6, 15, 9, 30, tzinfo=dt.UTC),
    )

    assert cache.read("688017", now=dt.datetime(2026, 6, 15, 9, 32, tzinfo=dt.UTC)) is None


def test_csv_kline_cache_writes_utf8_files(tmp_path):
    cache = CsvKlineCache(base_dir=tmp_path)
    cache.write("688017", [])

    csv_file = next(tmp_path.rglob("*.csv"))

    with csv_file.open("r", encoding="utf-8", newline="") as file:
        assert next(csv.reader(file)) == ["date", "open", "high", "low", "close", "volume"]


def test_sqlite_structured_cache_roundtrips_payload(tmp_path):
    cache = SQLiteStructuredCache(base_dir=tmp_path)
    payload = {
        "pe": 23.5,
        "nested": {"currency": "CNY", "tags": ["科创板", "fundamentals"]},
    }

    cache.write("fundamentals", "688017", "2026-06-16", payload)

    assert cache.read("fundamentals", "688017", "2026-06-16") == payload


def test_sqlite_structured_cache_schema_columns_present(tmp_path):
    cache = SQLiteStructuredCache(base_dir=tmp_path)
    cache.write("fundamentals", "688017", "2026-06-16", {"pe": 23.5})

    db_file = next(tmp_path.rglob("*.sqlite*"))
    with sqlite3.connect(db_file) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(structured_cache)").fetchall()
        }

    assert {
        "key",
        "kind",
        "ticker",
        "trade_date",
        "created_at",
        "expires_at",
        "payload_json",
    }.issubset(columns)


def test_sqlite_structured_cache_returns_none_for_expired_payload(tmp_path):
    cache = SQLiteStructuredCache(base_dir=tmp_path, ttl=dt.timedelta(seconds=60))
    cache.write(
        "fundamentals",
        "688017",
        "2026-06-16",
        {"pe": 23.5},
        created_at=dt.datetime(2026, 6, 16, 9, 30, tzinfo=dt.UTC),
    )

    assert (
        cache.read(
            "fundamentals",
            "688017",
            "2026-06-16",
            now=dt.datetime(2026, 6, 16, 9, 32, tzinfo=dt.UTC),
        )
        is None
    )


def test_sqlite_structured_cache_concurrent_writes_do_not_corrupt(tmp_path):
    cache = SQLiteStructuredCache(base_dir=tmp_path)

    def write_payload(index):
        cache.write("fundamentals", f"68801{index}", "2026-06-16", {"index": index})

    threads = [threading.Thread(target=write_payload, args=(index,)) for index in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert [
        cache.read("fundamentals", f"68801{index}", "2026-06-16")
        for index in range(5)
    ] == [{"index": index} for index in range(5)]


def test_sqlite_structured_cache_rejects_path_traversal_key(tmp_path):
    cache = SQLiteStructuredCache(base_dir=tmp_path)

    with pytest.raises((InvalidTickerError, CacheError)):
        cache.write("fundamentals", "../evil", "2026-06-16", {"pe": 23.5})


def test_sqlite_structured_cache_stores_payload_as_json(tmp_path):
    cache = SQLiteStructuredCache(base_dir=tmp_path)
    payload = {"numbers": [1, 2, 3], "nested": {"flag": True, "value": None}}
    cache.write("fundamentals", "688017", "2026-06-16", payload)

    db_file = next(tmp_path.rglob("*.sqlite*"))
    with sqlite3.connect(db_file) as connection:
        payload_json = connection.execute(
            "SELECT payload_json FROM structured_cache WHERE kind = ? AND ticker = ?",
            ("fundamentals", "688017"),
        ).fetchone()[0]

    assert json.loads(payload_json) == payload
