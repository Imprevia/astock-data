from __future__ import annotations

import datetime as dt

import pytest

from astock_data.clients.sina import SinaClient
from astock_data.errors import DataSourceError
from astock_data.services import market_breadth

pytestmark = pytest.mark.unit
_REAL_VERIFY_SNAPSHOT_DATE = market_breadth._verify_snapshot_date


@pytest.fixture(autouse=True)
def _freeze_current_session(monkeypatch) -> None:
    monkeypatch.setattr(
        market_breadth,
        "_local_today",
        lambda: dt.date(2026, 6, 17),
    )
    monkeypatch.setattr(
        market_breadth,
        "_verify_snapshot_date",
        lambda _sina, target, _warnings: (target.isoformat(), "verified"),
    )


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


def _index_rows() -> dict[str, dict]:
    return {
        key: {
            "name": key,
            "price": 1000.0,
            "change": 1.0,
            "change_pct": 0.1,
        }
        for key in ["sh", "sz", "cyb", "kc50", "hs300", "zz500"]
    }


def test_fast_mode_uses_one_eastmoney_clist_call_and_skips_market_amount(monkeypatch) -> None:
    monkeypatch.setattr(
        "astock_data.services.signals_a.get_hot_stocks",
        lambda *args, **kwargs: (_ for _ in ()).throw(DataSourceError("skip")),
    )

    class FakeEastmoney:
        def __init__(self) -> None:
            self.calls = 0

        def clist(self, **kwargs):
            self.calls += 1
            assert kwargs["page"] == 1
            return ([{"f12": "000001", "f14": "平安银行", "f3": 0.0}], 1)

    class FakeTencent:
        def index_snapshots(self) -> dict[str, dict]:
            return _index_rows()

    class FakeSina:
        def index_snapshots(self) -> dict[str, dict]:
            raise AssertionError("Tencent indices should be preferred")

        def market_page(self, **kwargs) -> list[dict]:
            raise AssertionError("Sina extremes should not run when clist succeeds")

    eastmoney = FakeEastmoney()
    result = market_breadth.get_market_breadth(
        "2026-06-17",
        fast=True,
        eastmoney=eastmoney,
        tencent=FakeTencent(),
        sina=FakeSina(),
    )

    assert eastmoney.calls == 1
    assert result.raw["fast"] is True
    assert result.raw["market_amount"] is None
    assert result.raw["sources"]["limit_stats"] == "eastmoney.clist"
    assert any("full-market amount" in warning for warning in result.warnings)


def test_fast_mode_falls_back_to_two_bounded_sina_extreme_pages(monkeypatch) -> None:
    monkeypatch.setattr(
        "astock_data.services.signals_a.get_hot_stocks",
        lambda *args, **kwargs: (_ for _ in ()).throw(DataSourceError("skip")),
    )
    calls: list[tuple[int, bool, str]] = []

    class FailingEastmoney:
        def clist(self, **kwargs):
            raise DataSourceError("clist blocked")

    class FakeTencent:
        def index_snapshots(self) -> dict[str, dict]:
            return _index_rows()

    class FakeSina:
        def index_snapshots(self) -> dict[str, dict]:
            raise AssertionError("Tencent indices should be preferred")

        def market_page(
            self,
            *,
            page: int,
            page_size: int,
            sort_field: str,
            ascending: bool,
        ) -> list[dict]:
            calls.append((page, ascending, sort_field))
            if ascending:
                return [
                    {"code": "600001", "name": "样本B", "change_pct": -10.0},
                    {"code": "600002", "name": "样本C", "change_pct": -3.0},
                ]
            return [
                {"code": "000001", "name": "样本A", "change_pct": 10.0},
                {"code": "000002", "name": "样本D", "change_pct": 3.0},
            ]

    result = market_breadth.get_market_breadth(
        "2026-06-17",
        fast=True,
        eastmoney=FailingEastmoney(),
        tencent=FakeTencent(),
        sina=FakeSina(),
        stock_data_func=lambda *args: (_ for _ in ()).throw(DataSourceError("skip")),
    )

    assert calls == [
        (1, False, "changepercent"),
        (1, True, "changepercent"),
    ]
    assert result.limit_stats.limit_up_count == 1
    assert result.limit_stats.limit_down_count == 1
    assert result.raw["sources"]["limit_stats"] == "sina.extremes"


def test_preferred_tencent_and_sina_composite_is_not_labeled_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        "astock_data.services.signals_a.get_hot_stocks",
        lambda *args, **kwargs: (_ for _ in ()).throw(DataSourceError("skip")),
    )

    class FakeTencent:
        def index_snapshots(self) -> dict[str, dict]:
            return _index_rows()

    class FakeSina:
        def index_snapshots(self) -> dict[str, dict]:
            raise AssertionError("Tencent indices should be preferred")

        def market_all(self) -> list[dict]:
            return [{"code": "000001", "name": "平安银行", "change_pct": 0.0}]

    result = market_breadth.get_market_breadth(
        "2026-06-17",
        eastmoney=object(),
        tencent=FakeTencent(),
        sina=FakeSina(),
    )

    assert result.source == "tencent+sina"
    assert "fallback" not in result.source


def test_fast_mode_all_limit_sources_failed_is_unavailable_not_zero(monkeypatch) -> None:
    monkeypatch.setattr(
        "astock_data.services.signals_a.get_hot_stocks",
        lambda *args, **kwargs: (_ for _ in ()).throw(DataSourceError("skip")),
    )

    class FailingEastmoney:
        def clist(self, **kwargs):
            raise DataSourceError("clist blocked")

    class FakeTencent:
        def index_snapshots(self) -> dict[str, dict]:
            return _index_rows()

    class FailingSina:
        def index_snapshots(self) -> dict[str, dict]:
            raise AssertionError("Tencent indices should be preferred")

        def market_page(self, **kwargs) -> list[dict]:
            raise DataSourceError("extreme page blocked")

    result = market_breadth.get_market_breadth(
        "2026-06-17",
        fast=True,
        eastmoney=FailingEastmoney(),
        tencent=FakeTencent(),
        sina=FailingSina(),
    )

    assert result.status == "partial"
    assert result.limit_stats.status == "unavailable"
    assert result.limit_stats.limit_up_count is None
    assert result.limit_stats.limit_down_count is None


def test_fast_mode_empty_first_extreme_pages_are_unavailable_not_zero(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "astock_data.services.signals_a.get_hot_stocks",
        lambda *args, **kwargs: (_ for _ in ()).throw(DataSourceError("skip")),
    )

    class FailingEastmoney:
        def clist(self, **kwargs):
            raise DataSourceError("clist blocked")

    class FakeTencent:
        def index_snapshots(self) -> dict[str, dict]:
            return _index_rows()

    class EmptySina:
        def index_snapshots(self) -> dict[str, dict]:
            raise AssertionError("Tencent indices should be preferred")

        def market_page(self, **kwargs) -> list[dict]:
            return []

    result = market_breadth.get_market_breadth(
        "2026-06-17",
        fast=True,
        eastmoney=FailingEastmoney(),
        tencent=FakeTencent(),
        sina=EmptySina(),
    )

    assert result.limit_stats.status == "unavailable"
    assert result.limit_stats.limit_up_count is None
    assert result.limit_stats.limit_down_count is None


def test_fast_mode_one_limit_side_failed_is_partial(monkeypatch) -> None:
    monkeypatch.setattr(
        "astock_data.services.signals_a.get_hot_stocks",
        lambda *args, **kwargs: (_ for _ in ()).throw(DataSourceError("skip")),
    )

    class FailingEastmoney:
        def clist(self, **kwargs):
            raise DataSourceError("clist blocked")

    class FakeTencent:
        def index_snapshots(self) -> dict[str, dict]:
            return _index_rows()

    class OneSidedSina:
        def index_snapshots(self) -> dict[str, dict]:
            raise AssertionError("Tencent indices should be preferred")

        def market_page(self, *, ascending: bool, **kwargs) -> list[dict]:
            if ascending:
                raise DataSourceError("losers blocked")
            return [
                {"code": "000001", "name": "样本A", "change_pct": 10.0},
                {"code": "000002", "name": "样本B", "change_pct": 3.0},
            ]

    result = market_breadth.get_market_breadth(
        "2026-06-17",
        fast=True,
        eastmoney=FailingEastmoney(),
        tencent=FakeTencent(),
        sina=OneSidedSina(),
        stock_data_func=lambda *args: (_ for _ in ()).throw(DataSourceError("skip")),
    )

    assert result.status == "partial"
    assert result.limit_stats.status == "partial"
    assert result.limit_stats.limit_up_count == 1
    assert result.limit_stats.limit_down_count is None


def test_historical_snapshot_without_date_verification_is_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        market_breadth,
        "_local_today",
        lambda: dt.date(2026, 6, 18),
    )
    monkeypatch.setattr(
        market_breadth,
        "_verify_snapshot_date",
        _REAL_VERIFY_SNAPSHOT_DATE,
    )

    class NoVerificationSina:
        pass

    result = market_breadth.get_market_breadth(
        "2026-06-17",
        fast=True,
        eastmoney=object(),
        tencent=object(),
        sina=NoVerificationSina(),
    )

    assert result.status == "unavailable"
    assert result.indices == []
    assert result.limit_stats.status == "unavailable"
    assert result.raw["snapshot_date_status"] == "unavailable"


def test_historical_snapshot_with_exact_date_verification_is_available(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        market_breadth,
        "_local_today",
        lambda: dt.date(2026, 6, 18),
    )
    monkeypatch.setattr(
        market_breadth,
        "_verify_snapshot_date",
        _REAL_VERIFY_SNAPSHOT_DATE,
    )
    monkeypatch.setattr(
        "astock_data.services.signals_a.get_hot_stocks",
        lambda *args, **kwargs: (_ for _ in ()).throw(DataSourceError("skip")),
    )

    class FakeEastmoney:
        def clist(self, **kwargs):
            return ([{"f12": "000001", "f14": "平安银行", "f3": 0.0}], 1)

    class FakeTencent:
        def index_snapshots(self) -> dict[str, dict]:
            return _index_rows()

    class VerifyingSina:
        def index_kline(self, symbol: str, datalen: int = 1) -> list[dict]:
            return [{"date": "2026-06-17"}]

        def index_snapshots(self) -> dict[str, dict]:
            raise AssertionError("Tencent indices should be preferred")

    result = market_breadth.get_market_breadth(
        "2026-06-17",
        fast=True,
        eastmoney=FakeEastmoney(),
        tencent=FakeTencent(),
        sina=VerifyingSina(),
    )

    assert result.status == "available"
    assert result.raw["snapshot_date"] == "2026-06-17"
    assert result.raw["snapshot_date_status"] == "verified"


def test_current_non_trading_date_rejects_stale_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(
        market_breadth,
        "_local_today",
        lambda: dt.date(2026, 6, 20),
    )
    monkeypatch.setattr(
        market_breadth,
        "_verify_snapshot_date",
        _REAL_VERIFY_SNAPSHOT_DATE,
    )

    class StaleSina:
        def index_kline(self, symbol: str, datalen: int = 1) -> list[dict]:
            return [{"date": "2026-06-19"}]

    result = market_breadth.get_market_breadth(
        "2026-06-20",
        fast=True,
        eastmoney=object(),
        tencent=object(),
        sina=StaleSina(),
    )

    assert result.status == "unavailable"
    assert result.raw["snapshot_date"] == "2026-06-19"
    assert result.raw["snapshot_date_status"] == "mismatch"


def test_fast_mode_malformed_clist_falls_back_instead_of_counting_zero(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "astock_data.services.signals_a.get_hot_stocks",
        lambda *args, **kwargs: (_ for _ in ()).throw(DataSourceError("skip")),
    )

    class MalformedEastmoney:
        def clist(self, **kwargs):
            return ([{"f12": "000001", "f14": "样本A", "f3": "-"}], 1)

    class FakeTencent:
        def index_snapshots(self) -> dict[str, dict]:
            return _index_rows()

    class EmptySina:
        def index_snapshots(self) -> dict[str, dict]:
            raise AssertionError("Tencent indices should be preferred")

        def market_page(self, **kwargs) -> list[dict]:
            return []

    result = market_breadth.get_market_breadth(
        "2026-06-17",
        fast=True,
        eastmoney=MalformedEastmoney(),
        tencent=FakeTencent(),
        sina=EmptySina(),
    )

    assert result.limit_stats.status == "unavailable"
    assert result.limit_stats.limit_up_count is None
    assert result.limit_stats.limit_down_count is None
    assert any("invalid change percentage" in item for item in result.warnings)


def test_fast_mode_malformed_sina_page_marks_direction_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "astock_data.services.signals_a.get_hot_stocks",
        lambda *args, **kwargs: (_ for _ in ()).throw(DataSourceError("skip")),
    )

    class FailingEastmoney:
        def clist(self, **kwargs):
            raise DataSourceError("blocked")

    class FakeTencent:
        def index_snapshots(self) -> dict[str, dict]:
            return _index_rows()

    class MalformedSina:
        def index_snapshots(self) -> dict[str, dict]:
            raise AssertionError("Tencent indices should be preferred")

        def market_page(self, *, ascending: bool, **kwargs) -> list[dict]:
            if ascending:
                return [
                    {"code": "600001", "name": "样本B", "change_pct": -10.0},
                    {"code": "600002", "name": "样本C", "change_pct": -3.0},
                ]
            return [{"code": "000001", "name": "样本A", "change_pct": "-"}]

    result = market_breadth.get_market_breadth(
        "2026-06-17",
        fast=True,
        eastmoney=FailingEastmoney(),
        tencent=FakeTencent(),
        sina=MalformedSina(),
    )

    assert result.limit_stats.status == "partial"
    assert result.limit_stats.limit_up_count is None
    assert result.limit_stats.limit_down_count == 1


def test_fast_mode_rejects_malformed_rows_through_real_sina_parser(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "astock_data.services.signals_a.get_hot_stocks",
        lambda *args, **kwargs: (_ for _ in ()).throw(DataSourceError("skip")),
    )

    class FailingEastmoney:
        def clist(self, **kwargs):
            raise DataSourceError("blocked")

    class FakeTencent:
        def index_snapshots(self) -> dict[str, dict]:
            return _index_rows()

    class RealParsingSina(SinaClient):
        def _get_json(self, url, params=None):
            return [{"symbol": "sh600000", "changepercent": "-"}]

        def index_snapshots(self) -> dict[str, dict]:
            raise AssertionError("Tencent indices should be preferred")

    result = market_breadth.get_market_breadth(
        "2026-06-17",
        fast=True,
        eastmoney=FailingEastmoney(),
        tencent=FakeTencent(),
        sina=RealParsingSina(),
    )

    assert result.limit_stats.status == "unavailable"
    assert result.limit_stats.limit_up_count is None
    assert result.limit_stats.limit_down_count is None
    assert any("invalid change percentage" in item for item in result.warnings)


def test_no_ladders_do_not_claim_derived_source(monkeypatch) -> None:
    monkeypatch.setattr(
        "astock_data.services.signals_a.get_hot_stocks",
        lambda *args, **kwargs: (_ for _ in ()).throw(DataSourceError("skip")),
    )

    class FakeEastmoney:
        def clist(self, **kwargs):
            return ([{"f12": "000001", "f14": "样本A", "f3": 0.0}], 1)

    class FakeTencent:
        def index_snapshots(self) -> dict[str, dict]:
            return _index_rows()

    class FakeSina:
        def index_snapshots(self) -> dict[str, dict]:
            raise AssertionError("Tencent indices should be preferred")

    result = market_breadth.get_market_breadth(
        "2026-06-17",
        fast=True,
        eastmoney=FakeEastmoney(),
        tencent=FakeTencent(),
        sina=FakeSina(),
    )

    assert result.board_ladders == {}
    assert result.raw["sources"]["board_ladders"] is None
    assert "derived" not in result.source
    assert not any("board_ladders are derived" in item for item in result.warnings)
