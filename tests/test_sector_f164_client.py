from __future__ import annotations

import pytest

from astock_data.clients import eastmoney as eastmoney_module
from astock_data.clients.eastmoney import EastmoneyClient

pytestmark = pytest.mark.unit


@pytest.fixture
def client() -> EastmoneyClient:
    return EastmoneyClient(min_interval=0.0, timeout=5.0)


def test_five_day_sector_flow_parses_yuan_and_preserves_zero(
    requests_mocker,
    client: EastmoneyClient,
) -> None:
    # Given
    requests_mocker.get(
        eastmoney_module.GETBKZJ_URL,
        json={
            "data": {
                "diff": [
                    {"f12": "BK1036", "f14": "半导体", "f164": 123456789.0},
                    {"f12": "BK1037", "f14": "软件开发", "f164": 0},
                ]
            }
        },
    )

    # When
    rows = eastmoney_module.fetch_sector_five_day_main_net_inflow(client=client)

    # Then
    assert rows == [
        {
            "code": "BK1036",
            "name": "半导体",
            "five_day_main_net_inflow": 123456789.0,
        },
        {
            "code": "BK1037",
            "name": "软件开发",
            "five_day_main_net_inflow": 0.0,
        },
    ]
    assert requests_mocker.request_history[-1].qs == {
        "key": ["f164"],
        "code": ["m:90+s:4"],
    }


def test_five_day_sector_flow_skips_missing_or_invalid_fields(
    requests_mocker,
    client: EastmoneyClient,
) -> None:
    # Given
    requests_mocker.get(
        eastmoney_module.GETBKZJ_URL,
        json={
            "data": {
                "diff": [
                    {"f14": "缺少代码", "f164": 1},
                    {"f12": "BK1001", "f164": 2},
                    {"f12": "BK1002", "f14": "缺少数值"},
                    {"f12": "BK1003", "f14": "空值", "f164": None},
                    {"f12": "BK1004", "f14": "占位符", "f164": "-"},
                ]
            }
        },
    )

    # When
    rows = eastmoney_module.fetch_sector_five_day_main_net_inflow(client=client)

    # Then
    assert rows == []


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"data": None},
        {"data": {}},
        {"data": {"diff": []}},
    ],
)
def test_five_day_sector_flow_returns_empty_for_empty_payload(
    requests_mocker,
    client: EastmoneyClient,
    payload: dict,
) -> None:
    # Given
    requests_mocker.get(eastmoney_module.GETBKZJ_URL, json=payload)

    # When
    rows = eastmoney_module.fetch_sector_five_day_main_net_inflow(client=client)

    # Then
    assert rows == []
