# Tasks

## 1. Data contracts and clients

- [ ] 1.1 Add optional `change_pct` and `turnover_pct` fields to `KlineBar`.
- [ ] 1.2 Parse Eastmoney daily K-line change percentage and turnover fields.
- [ ] 1.3 Preserve the full matching-date Tencent quote bar in `get_stock_amount` fallback.
- [ ] 1.4 Add offline model, client, and service regression tests.

## 2. Resilient services

- [ ] 2.1 Make minute and daily fund-flow retrieval fail independently with warnings.
- [ ] 2.2 Add Sina sorted extreme-page retrieval with bounded stop conditions.
- [ ] 2.3 Add backward-compatible market-breadth fast mode to API, CLI, and MCP.
- [ ] 2.4 Add partial-result and latency-path regression tests.

## 3. Buyer-exhaustion integration

- [ ] 3.1 Collect stock amount, fund flow, and fast market breadth through `astock_data.cli`.
- [ ] 3.2 Merge exact metrics using documented precedence and date isolation.
- [ ] 3.3 Extend JSON and Markdown evidence output with dynamic limitations.
- [ ] 3.4 Add standalone analysis-script regression tests.

## 4. Review and verification

- [ ] 4.1 Complete independent code review with no blocking findings.
- [ ] 4.2 Run focused data and analysis tests.
- [ ] 4.3 Run the full data-package regression suite.
- [ ] 4.4 Run the full docs contract.
- [ ] 4.5 Run a live 600809 analysis smoke and record remaining external-source warnings.
