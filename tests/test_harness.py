import requests
from pathlib import Path

from tests.conftest import LIVE_SKIP_REASON


def test_live_marker_skips_by_default(pytester, monkeypatch):
    monkeypatch.delenv("ASTOCK_LIVE_TESTS", raising=False)
    pytester.syspathinsert(Path(__file__).resolve().parents[1])
    pytester.makeconftest("pytest_plugins = ['tests.conftest']")
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.live
        def test_live_api_placeholder():
            assert False
        """
    )

    result = pytester.runpytest("-q")

    result.assert_outcomes(skipped=1)
    assert LIVE_SKIP_REASON == "set ASTOCK_LIVE_TESTS=1 to run"


def test_requests_mocker_intercepts_http(requests_mocker):
    requests_mocker.get("https://qt.gtimg.cn/q=sz000001", text="fake-response")

    response = requests.get("https://qt.gtimg.cn/q=sz000001", timeout=1)

    assert response.text == "fake-response"
    assert requests_mocker.called


def test_tmp_cache_dir_is_absolute_under_tmp(tmp_cache_dir, tmp_path):
    assert tmp_cache_dir.is_absolute()
    assert tmp_cache_dir.is_relative_to(tmp_path)
