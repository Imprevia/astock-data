# Tasks

## 1. Order-book data contract

- [x] 1.1 Add five-level order-book models with explicit lot units and truthful change semantics.
- [x] 1.2 Parse Tencent bid/ask levels and vendor timestamps without changing existing quote output.
- [x] 1.3 Add offline client and model regression tests.

## 2. Service and public adapters

- [x] 2.1 Add resolver-backed bounded order-book sampling and visible-price change calculation.
- [x] 2.2 Add the 26th Python API, CLI command, and MCP tool with matching arguments.
- [x] 2.3 Add service, API, CLI, MCP, and validation-boundary tests.

## 3. Buyer-exhaustion integration

- [x] 3.1 Collect order-book evidence only for the current target date.
- [x] 3.2 Add snapshot depth, spread, and unattributed visible-depth changes to JSON and Markdown output.
- [x] 3.3 Preserve historical-date isolation and dynamic limitations when sampling is static or unavailable.
- [x] 3.4 Add analysis-script regression tests.

## 4. Documentation and verification

- [x] 4.1 Update README, architecture, runbooks, status, and active-plan facts for the additive public capability.
- [x] 4.2 Complete independent code review with no blocking findings.
- [x] 4.3 Run focused data and analysis tests.
- [x] 4.4 Run the full data-package regression suite and docs contract.
- [x] 4.5 Run a live 600809 order-book smoke and record the outside-session limitation when applicable.
