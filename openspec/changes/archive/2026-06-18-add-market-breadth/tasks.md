## 1. Client Layer

- [x] 1.1 Extend `astock_data/clients/eastmoney.py` with index snapshot support using fixed secids and `PUSH2_STOCK_GET_PATH`.
- [x] 1.2 Extend `astock_data/clients/eastmoney.py` with a paginated `clist` helper that returns all A-share quote rows via `PUSH2_CLIST_PATH`.
- [x] 1.3 Add Eastmoney client unit tests for index snapshot parsing, empty/malformed payload handling, and `clist` pagination.

## 2. Models

- [x] 2.1 Add `IndexSnapshot`, `LimitStats`, `BoardItem`, and `MarketBreadthResult` models to `astock_data/models/market.py`.
- [x] 2.2 Re-export the new market breadth models from `astock_data/models/__init__.py`.
- [x] 2.3 Add model tests covering serialization, `ResultBase` metadata, `source` string behavior, and `board_ladders` keyed by board count.

## 3. Service Implementation

- [x] 3.1 Create `astock_data/services/market_breadth.py` with fixed index secid constants and `get_market_breadth(date: str = "")`.
- [x] 3.2 Implement ISO date validation and empty-date defaulting in the market breadth service.
- [x] 3.3 Implement limit-up/limit-down threshold classification for ST, 创业板/科创板, 北交所, and ordinary A-share rows.
- [x] 3.4 Implement stateless board ladder derivation from current limit-up rows and cached daily K-line data with default 20-day lookback.
- [x] 3.5 Populate `MarketBreadthResult` with `source="eastmoney+derived"`, `retrieved_at`, `raw` source details, and derived-board warnings.
- [x] 3.6 Add service tests with mocked Eastmoney rows and mocked K-line bars for limit counts, 3-board ladder derivation, chain-breaking, and no persistent state writes.

## 4. Public Facades

- [x] 4.1 Re-export `get_market_breadth` from `astock_data/services/__init__.py` and update service package docstrings/counts from 17 to 18 `get_*` functions.
- [x] 4.2 Re-export `get_market_breadth` from `astock_data/api.py` and update public API docstrings/counts from 18 to 19 functions.
- [x] 4.3 Re-export `get_market_breadth` from `astock_data/__init__.py` and keep package-level `__all__` aligned.
- [x] 4.4 Update `tests/test_public_api.py` to assert 19 public API functions and include `get_market_breadth`.

## 5. CLI and MCP

- [x] 5.1 Add `market-breadth` CLI subcommand to `astock_data/cli.py` with optional `--date` and existing `--format` handling.
- [x] 5.2 Add CLI tests or update existing CLI coverage to verify `market-breadth` JSON output delegates to `get_market_breadth`.
- [x] 5.3 Add `get_market_breadth` MCP tool to `astock_data/mcp/server.py` with optional `date` parameter.
- [x] 5.4 Add or update MCP contract tests to include the 19th tool.

## 6. Documentation and Agent Instructions

- [x] 6.1 Update `README.md` Python API, CLI, MCP, and data source sections from 18 to 19 public entries.
- [x] 6.2 Update root `AGENTS.md` counts and key-file descriptions from 18 public entries / 18 CLI / 18 MCP to 19 where applicable.
- [x] 6.3 Update nested `astock_data/AGENTS.md` and `astock_data/services/AGENTS.md` counts from 17 `get_*` service entries to 18 where applicable.
- [x] 6.4 Update `astock_data/models/AGENTS.md` only if the market model responsibility text needs to mention market breadth contracts.

## 7. Verification

- [x] 7.1 Run `python -m pytest tests/test_eastmoney_client.py -q`.
- [x] 7.2 Run `python -m pytest tests/test_market_breadth_service.py -q`.
- [x] 7.3 Run `python -m pytest tests/test_public_api.py -q`.
- [x] 7.4 Run `python -m pytest tests/test_agents_docs.py -q`.
- [x] 7.5 Run `python -m pytest -q` and document any unrelated pre-existing failures.
