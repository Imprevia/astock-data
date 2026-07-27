from __future__ import annotations

import pytest

from astock_data.services import market_breadth

pytestmark = pytest.mark.unit


def test_default_eastmoney_client_is_configured_to_fail_fast(monkeypatch) -> None:
    created: list[tuple[float, int]] = []

    class FakeEastmoney:
        def __init__(self, *, timeout: float, max_retries: int) -> None:
            created.append((timeout, max_retries))

        def index_snapshot(self, secid: str) -> dict:
            return {"f58": secid, "f43": 1000.0, "f169": 1.0, "f170": 0.1}

        def clist_all(self, *, fields: str = "") -> list[dict]:
            return [{"f12": "000001", "f14": "平安银行", "f2": 10.0, "f3": 0.0}]

    class FakeTencent:
        def index_snapshots(self) -> dict[str, dict]:
            return {}

    class FakeSina:
        def index_snapshots(self) -> dict[str, dict]:
            return {}
        def market_all(self, **kwargs) -> list[dict]:
            return []

    monkeypatch.setattr(market_breadth, "EastmoneyClient", FakeEastmoney)
    monkeypatch.setattr(market_breadth, "TencentClient", FakeTencent)
    monkeypatch.setattr(market_breadth, "SinaClient", FakeSina)

    result = market_breadth.get_market_breadth("2026-06-17")

    # Eastmoney is now last in the fallback chain, but still uses fast-fail config.
    assert created == [(3.0, 0)]
