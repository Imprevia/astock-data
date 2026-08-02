# Fix Historical Review Data Retrieval

## Stage

Complete

## Status

All three historical review retrieval defects are repaired and verified. The change is complete and awaiting normal repository archival/commit handling.

## Acceptance

- `get_global_news(curr_date, look_back_days, limit)` paginates Eastmoney fast news with the vendor-provided `sortEnd` cursor, returns only items inside the requested inclusive date window, and never reuses out-of-window cached rows as historical facts.
- Existing current-news behavior remains available when `curr_date` is empty, while dated requests emit explicit warnings when the live archive cannot reach the requested window.
- `daily-review` historical money-flow scans read daily K lines ending on the requested review date and calculate volume ratios only from that historical window.
- `daily-review` sector scans fall back to the structured sector-strength snapshot when the legacy sector rank endpoint fails, and expose both inflow and outflow rankings without inventing unavailable history.
- Focused offline tests, relevant regression tests, docs contracts, and an opt-in 2026-07-31 live smoke pass or retain explicit upstream warnings.

## Completion Evidence

- Root cause confirmed by a live probe: Eastmoney ignored a literal date in `sortEnd`, but returned a working opaque `sortEnd` cursor in response metadata; replaying that cursor returned the next older page.
- The existing `get_global_news` implementation explicitly skipped date filtering and cached live rows under the caller-supplied historical date.
- The existing `money_flow.py` called `get_stock_amount(code, 5)` without forwarding its `--date` cutoff.
- The existing `sector_scan.py` returned an empty table immediately when the single Eastmoney rank source failed, even though `get_sector_strength` succeeded for the same review date.
- Red phase: focused news/client tests failed 3 cases for the missing cursor method, missing historical pagination, and leaked out-of-window rows.
- Focused green: `python -m pytest tests/test_eastmoney_client.py tests/test_news_service.py -q` passed 67 tests.
- Full regression: `python -m pytest -q --basetemp <writable-dir>` passed 518 tests with 7 skips in 67.71 seconds.
- Docs gate: `python scripts/check_docs_contract.py --mode full` passed.
- Live news smoke returned 15 items dated exactly 2026-07-31 instead of current 2026-08-02 rows.
- Live sector smoke recovered Top10 inflow and Top10 outflow rankings from the cached sector-strength snapshot after the legacy rank endpoint disconnected.
- Live money-flow smoke returned five dated bars per candidate and calculated ratios for all 30 hot-stock candidates; 太极实业's 2026-07-31 estimated amount was 63.05亿元 versus 63.38亿元 from the single-day source.
- `daily-review` Python compilation passed for `astock_source.py`, `money_flow.py`, and `sector_scan.py`.

## Remaining Gaps

- Public live archives retain only a finite number of fast-news rows; older dates return an empty result with a warning.
- A missing user stock-pool YAML is configuration absence, not a data-source defect, and remains outside this repair.
- Historical amount fallback is an explicit `volume × OHLC mean` estimate when exact Eastmoney amounts are unavailable.
- External upstream availability and anti-bot behavior remain outside repository control.

## Next Step

Archive this completed plan after the changes are committed or otherwise accepted by the user.
