from __future__ import annotations

import pytest
import requests_mock

from astock_data.clients.eastmoney import EastmoneyClient
from astock_data.clients.sina import SinaClient
from astock_data.clients.tencent import TencentClient

pytestmark = pytest.mark.unit


def _request_for_host(requests_mocker, host: str):
    return next(
        request
        for request in requests_mocker.request_history
        if request.hostname == host
    )


def test_eastmoney_datacenter_does_not_send_push2_referer(requests_mocker) -> None:
    requests_mocker.get(
        requests_mock.ANY,
        json={"result": {"data": []}},
    )

    EastmoneyClient(min_interval=0).datacenter("rpt_x")

    request = _request_for_host(requests_mocker, "datacenter-web.eastmoney.com")
    assert request.headers.get("Referer") != "https://quote.eastmoney.com/"


def test_eastmoney_push2_sends_quote_referer(requests_mocker) -> None:
    requests_mocker.get(requests_mock.ANY, json={"data": {}})

    EastmoneyClient(min_interval=0).index_snapshot("1.000001")

    request = _request_for_host(requests_mocker, "push2.eastmoney.com")
    assert request.headers["Referer"] == "https://quote.eastmoney.com/"


def test_sina_kline_sends_finance_referer(requests_mocker) -> None:
    requests_mocker.get(requests_mock.ANY, json=[])

    SinaClient().kline("000001")

    request = _request_for_host(requests_mocker, "money.finance.sina.com.cn")
    assert request.headers["Referer"] == "https://finance.sina.com.cn/"


def test_tencent_quote_sends_gu_referer(requests_mocker) -> None:
    requests_mocker.get(requests_mock.ANY, content=b"")

    TencentClient().quote(["000001"])

    request = _request_for_host(requests_mocker, "qt.gtimg.cn")
    assert request.headers["Referer"] == "https://gu.qq.com/"
