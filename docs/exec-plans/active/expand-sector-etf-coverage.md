# Expand Sector ETF Coverage

## Stage

Complete

## Status

The representative ETF expansion is implemented. The data layer accepts the verified ETF set, and daily-review maps explicit fine-grained aliases while retaining the price-proxy disclaimer and unmatched degradation.

## Acceptance

- The data-layer ETF allowlist includes verified software, computer, media, communication, robot, electronics, gold, gaming, chemical, and agriculture ETFs.
- Each new ETF code retains the existing Sina-primary and Eastmoney-fallback behavior.
- `daily-review` maps fine-grained industry aliases to representative ETFs without claiming exact ETF-share flow.
- The 2026-07-31 Top30 ETF coverage materially improves and unmatched sectors remain explicitly degraded.
- Focused tests, full regression, docs contract, and live smoke pass.

## Completion Evidence

- Direct Sina K-line smoke returned five bars for the new representative ETF set, including chemical `516020` and agriculture `159825`.
- Existing daily-review output shows ETF degradation for most software, media, communication, equipment, and electronics sub-industries because matching uses only literal broad keywords.
- The final 2026-07-31 smoke covered 82 of 89 industry rows; only seven sectors without a defensible representative ETF remain unmatched.
- Focused API/CLI/MCP/docs tests passed 91 cases; the full suite passed 525 tests with 7 skips; the full docs contract passed.

## Remaining Gaps

- Representative ETFs are proxies for fine-grained sectors and do not provide exact ETF share-flow attribution.
- Fine-grained sectors without a defensible representative ETF must remain unmatched.

## Next Step

Archive the completed plan when repository history handling is requested.
