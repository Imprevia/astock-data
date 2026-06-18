## 1. Tencent Fallback Client Support

- [x] 1.1 Extend `astock_data/clients/tencent.py` with fixed-index batch quote support for `sh000001`, `sz399001`, `sz399006`, `sh000688`, `sh000300`, and `sh000905`.
- [x] 1.2 Add a Tencent full-market board helper around `proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList` if spike confirms stable pagination and fields.
- [x] 1.3 Add offline `tests/test_tencent_client.py` coverage for index quote parsing, GBK decoding, transport errors, and full-market row normalization when implemented.

## 2. Optional Sina Secondary Fallback

- [x] 2.1 Extend `astock_data/clients/sina.py` with index snapshot support using `hq.sinajs.cn` short index quote format.
- [x] 2.2 If Tencent full-market pagination is insufficient, add a Sina market pagination helper with conservative page limits and warnings about封 IP risk.
- [x] 2.3 Add offline `tests/test_sina_client.py` coverage for index quote parsing and optional market pagination parsing.

## 3. Market Breadth Orchestration

- [x] 3.1 Refactor `astock_data/services/market_breadth.py` to fetch indices via source order `eastmoney -> tencent -> sina`.
- [x] 3.2 Refactor limit-stat quote rows via source order `eastmoney clist -> tencent market board -> sina market pagination`.
- [x] 3.3 Normalize vendor quote rows into one internal shape before applying existing threshold classification.
- [x] 3.4 Populate `raw.sources.indices`, `raw.sources.limit_stats`, and `raw.sources.board_ladders` with actual sources used.
- [x] 3.5 Record warnings for failed higher-priority sources and successful fallback source names.
- [x] 3.6 Return `board_ladders={}` with warning when no current limit-up set is available but indices or limit stats are available.
- [x] 3.7 Raise a typed data-source error only when all index sources and all full-market quote sources fail.

## 4. Tests and Documentation

- [x] 4.1 Update `tests/test_market_breadth_service.py` for Eastmoney failure -> Tencent success, Tencent failure -> Sina success, partial board-ladder skip, and all-source failure.
- [x] 4.2 Add or update formatter/model tests only if `raw.sources` or warning text changes serialization assumptions.
- [x] 4.3 Update README data-source notes to describe market breadth fallback behavior and partial-result warnings.
- [x] 4.4 Update `openspec/changes/add-market-breadth-fallbacks/design.md` if implementation spike shows Tencent full-market endpoint is not stable enough for default use.

## 5. Verification

- [x] 5.1 Run `python -m pytest tests/test_tencent_client.py -q`.
- [x] 5.2 Run `python -m pytest tests/test_sina_client.py -q` if Sina fallback is implemented.
- [x] 5.3 Run `python -m pytest tests/test_market_breadth_service.py -q`.
- [x] 5.4 Run `python -m pytest tests/test_public_api.py tests/test_cli.py tests/test_mcp_server.py -q`.
- [x] 5.5 Run `python -m pytest -q` and document unrelated pre-existing failures.
