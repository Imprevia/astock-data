# Tasks

## 1. Data contracts and clients

- [x] 1.1 Add optional `change_pct` and `turnover_pct` fields to `KlineBar`.
- [x] 1.2 Parse Eastmoney daily K-line change percentage and turnover fields.
- [x] 1.3 Preserve the full matching-date Tencent quote bar in `get_stock_amount` fallback.
- [x] 1.4 Add offline model, client, and service regression tests.

## 2. Resilient services

- [x] 2.1 Make minute and daily fund-flow retrieval fail independently with warnings.
- [x] 2.2 Add Sina sorted extreme-page retrieval with bounded stop conditions.
- [x] 2.3 Add backward-compatible market-breadth fast mode to API, CLI, and MCP.
- [x] 2.4 Add partial-result and latency-path regression tests.
- [x] 2.5 Replace the invalid stock-membership `slist` call with the individual-stock core-conception endpoint.
- [x] 2.6 Normalize industry, region, and concept membership and add offline client/service tests.
- [x] 2.7 Add explicit breadth availability, nullable per-direction counts, exact snapshot-date verification, and malformed/truncated source tests.

## 3. Buyer-exhaustion integration

- [x] 3.1 Collect stock amount, fund flow, and fast market breadth through `astock_data.cli`.
- [x] 3.2 Merge exact metrics using documented precedence and date isolation.
- [x] 3.3 Extend JSON and Markdown evidence output with dynamic limitations.
- [x] 3.4 Add standalone analysis-script regression tests.
- [x] 3.5 Distinguish published, not-listed, and unavailable dragon-tiger states.
- [x] 3.6 Distinguish pending, observed, and unavailable forward-confirmation states.
- [x] 3.7 Collect restored concept membership and update `wildman-daily-review` evidence routing.

## 4. Review and verification

- [ ] 4.1 Complete independent code review with no blocking findings.
- [ ] 4.2 Run focused data and analysis tests.
- [x] 4.3 Run the full data-package regression suite.
- [x] 4.4 Run the full docs contract.
- [x] 4.5 Run a live 600809 analysis smoke and record remaining external-source warnings.
