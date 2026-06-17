from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone

from astock_data.api import get_stock_data, resolve_ticker
from astock_data.models.base import Ticker
from astock_data.models.market import OHLCVBar, StockDataResult


def build_mock_stock_data() -> StockDataResult:
    return StockDataResult(
        source="mock",
        retrieved_at=datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc),
        ticker=Ticker(code="688017", market="sh", name="示例股票"),
        bars=[
            OHLCVBar(date=date(2026, 5, 11), open=10.1, high=10.8, low=10.0, close=10.6, volume=123456),
            OHLCVBar(date=date(2026, 5, 12), open=10.6, high=11.0, low=10.4, close=10.9, volume=156789),
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="astock-data Python API example")
    parser.add_argument("--mock", action="store_true", help="Run offline with structured mock data")
    args = parser.parse_args()

    if args.mock:
        ticker = Ticker(code="688017", market="sh", name="示例股票")
        stock_data = build_mock_stock_data()
    else:
        ticker = resolve_ticker("688017")
        stock_data = get_stock_data("688017", "2026-05-01", "2026-05-12")

    payload = {
        "mode": "mock" if args.mock else "live",
        "ticker": ticker.model_dump(mode="json"),
        "stock_data": stock_data.model_dump(mode="json"),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
