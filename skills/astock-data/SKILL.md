# astock-data Skill

## Triggers and keywords

Use this skill for A-share data, A股, 行情, K线, OHLCV, 技术指标, 龙虎榜, 资金流, 主力资金, 概念板块, 行业对比, 解禁, 北向, 沪深港通, 财报, 资产负债表, 现金流量表, 利润表, 新闻, 快讯, stock data, fund flow, dragon tiger, lockup, fundamentals, K-line, concept blocks, northbound flow.

## When to use

Use `astock-data` when an opencode or Claude Code workflow needs structured A-share data for daily market checks, research evidence, data validation, model input, or analysis pipelines. It is a strict data-query helper. It returns facts and structured records only, never portfolio actions, trading decisions, or investment recommendations.

## Prerequisites

Install from the `stock-data-source` project root:

```bash
pip install -e .
```

If the interpreter is uv-managed and blocks editable install, set the PowerShell override before installing:

```powershell
$env:PIP_BREAK_SYSTEM_PACKAGES=1
python -m pip install -e .
```

Primary MCP stdio server:

```bash
python -m astock_data.mcp.server
```

CLI fallback:

```bash
astock-data --help
python -m astock_data.cli --help
```

Use `python -m astock_data.cli` when the console script directory is not on `PATH`.

## Primary path, MCP stdio

Register the server as an MCP stdio server. Do not configure HTTP or SSE transport.

```json
{
  "mcpServers": {
    "astock-data": {
      "command": "python",
      "args": ["-m", "astock_data.mcp.server"],
      "transport": "stdio"
    }
  }
}
```

Available MCP tools, one per public API function:

- `resolve_ticker`
- `get_stock_data`
- `get_indicators`
- `get_fundamentals`
- `get_balance_sheet`
- `get_cashflow`
- `get_income_statement`
- `get_news`
- `get_global_news`
- `get_insider_transactions`
- `get_profit_forecast`
- `get_hot_stocks`
- `get_northbound_flow`
- `get_concept_blocks`
- `get_fund_flow`
- `get_dragon_tiger_board`
- `get_lockup_expiry`
- `get_industry_comparison`

Tool results are JSON-serializable objects from Pydantic `model_dump(mode="json")`. Typed failures return this shape instead of a traceback:

```json
{"error":{"type":"InvalidTickerError","message":"..."}}
```

## Fallback path, CLI

Use the CLI when MCP is unavailable, when capturing evidence from a shell, or when a workflow needs explicit command transcripts. Prefer JSON for machine consumption and Markdown for human or LLM reading.

```bash
python -m astock_data.cli <subcommand> ... --format json
python -m astock_data.cli <subcommand> ... --format markdown
```

Global options:

- `--format json|markdown|text`, default `json`
- `--no-cache`, bypasses the persistent cache for the invocation

CLI subcommands:

- `resolve`, `kline`, `indicator`, `fundamentals`, `balance-sheet`, `cashflow`, `income-statement`
- `news`, `global-news`, `shareholders`, `profit-forecast`, `hot-stocks`, `northbound`
- `concepts`, `fund-flow`, `dragon-tiger`, `lockup`, `industry`

## Recipes

### Resolve ticker

```bash
python -m astock_data.cli resolve 688017 --format json
```

Expected shape:

```json
{"code":"688017","market":"sh","name":null}
```

### Get K-line JSON

```bash
python -m astock_data.cli kline 688017 --start 2026-05-01 --end 2026-05-12 --format json
```

Expected shape:

```json
{"source":"...","retrieved_at":"...","ticker":{"code":"688017","market":"sh"},"bars":[{"date":"2026-05-12","open":0,"high":0,"low":0,"close":0,"volume":0}],"warnings":[]}
```

### Get fund flow

```bash
python -m astock_data.cli fund-flow 688017 --curr-date 2026-05-12 --include-history --format json
```

Expected shape:

```json
{"source":"...","retrieved_at":"...","ticker":"688017","items":[{"time":"...","main_net_inflow":0}],"history":[{"date":"...","main_net_inflow":0}],"warnings":[]}
```

### Get concept blocks

```bash
python -m astock_data.cli concepts 688017 --format json
```

Expected shape:

```json
{"source":"...","retrieved_at":"...","ticker":"688017","concepts":[{"name":"...","code":"..."}],"warnings":[]}
```

### Get dragon-tiger board

```bash
python -m astock_data.cli dragon-tiger 688017 --trade-date 2026-05-12 --look-back-days 30 --format json
```

Expected shape:

```json
{"source":"...","retrieved_at":"...","ticker":"688017","events":[{"trade_date":"...","reason":"..."}],"seats":[{"seat_name":"...","buy_amount":0,"sell_amount":0}],"warnings":[]}
```

### Get stock news

```bash
python -m astock_data.cli news 688017 --start 2026-05-01 --end 2026-05-12 --format json
```

Expected shape:

```json
{"source":"...","retrieved_at":"...","ticker":"688017","items":[{"title":"...","content":null,"time":"...","source":"...","url":"..."}],"warnings":[]}
```

### Get financial statement

```bash
python -m astock_data.cli balance-sheet 688017 --freq quarterly --curr-date 2026-05-12 --format json
```

Expected shape:

```json
{"source":"...","retrieved_at":"...","ticker":"688017","reports":[{"report_date":"...","fields":{}}],"warnings":[]}
```

## Error handling

MCP tools and CLI commands surface typed errors as structured JSON:

```json
{"error":{"type":"ErrorClassName","message":"human readable message"}}
```

Invalid ticker strings are rejected by the shared resolver. Chinese names are resolved to 6-digit codes when unambiguous. Ambiguous Chinese names return a typed ambiguity error. Unknown names return a typed resolution error. Non-trading days, bad date windows, unsupported indicators, rate limits, data-source failures, and cache failures also use the typed error envelope.

For CLI use, read JSON from stdout on success. On failure, read the error JSON from stderr and treat the nonzero exit code as a failed data query.

## Evidence and output guidance

Save raw structured JSON to evidence paths before summarizing it:

```bash
python -m astock_data.cli kline 688017 --start 2026-05-01 --end 2026-05-12 --format json > evidence/688017-kline.json
python -m astock_data.cli fund-flow 688017 --curr-date 2026-05-12 --format json > evidence/688017-fund-flow.json
```

Use `--format json` for automated workflows, tests, audit trails, and downstream parsers. Use `--format markdown` for quick human review or LLM context. Keep source fields, retrieval timestamps, warnings, and error objects in evidence files so later steps can verify data lineage.

## Scope guardrail

This skill is data-query only. Do not use it to produce buy, sell, or hold advice. Do not generate investment recommendations, portfolio allocations, price targets, return promises, or trade instructions. If a workflow needs an opinion, first collect factual data with this skill, then pass that evidence to a separate analysis process with its own compliance rules.
