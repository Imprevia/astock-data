# astock-data

`astock-data` 是一个严格的 A 股纯数据层包。它只提供结构化数据接口、CLI 和 MCP stdio 工具，不包含 LLM、Agent、Web UI、回测或投资决策逻辑。

> 免责声明：本项目仅供学习研究和数据工程验证，不构成任何投资建议。市场有风险，投资决策请咨询持牌专业机构。

## 项目简介

- 纯数据层：统一封装 A 股行情、财务、新闻、资金流、龙虎榜、解禁、行业和概念板块数据。
- 无 LLM/Agent 依赖：不会导入 `langchain`、`openai`、`anthropic`、`streamlit`、`fastapi` 等应用层或智能体依赖。
- 结构化返回：18 个公开 Python API 均返回 Pydantic 模型，不返回自由文本报告。
- 严格边界：只做数据获取、校验、缓存、格式化和协议适配，不做买卖建议、不做组合管理、不做收益承诺。

## 安装

需要 Python `>=3.10`。

```bash
cd G:\workspaces\stock-data-source
pip install -e .
```

如果当前解释器由 `uv` 管理并触发 PEP 668 外部管理环境限制，可在 PowerShell 中临时允许安装：

```powershell
$env:PIP_BREAK_SYSTEM_PACKAGES=1
python -m pip install -e .
```

测试依赖：

```bash
pip install -e ".[test]"
```

## Python API 用法

推荐从 `astock_data.api` 导入公开接口。完整公开函数共 18 个：

- `resolve_ticker`
- `get_stock_data`, `get_indicators`
- `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`
- `get_news`, `get_global_news`
- `get_insider_transactions`, `get_profit_forecast`, `get_hot_stocks`, `get_northbound_flow`
- `get_concept_blocks`, `get_fund_flow`, `get_dragon_tiger_board`, `get_lockup_expiry`, `get_industry_comparison`

代表性示例：

```python
from astock_data.api import get_fund_flow, get_stock_data, resolve_ticker

ticker = resolve_ticker("688017")
print(ticker.model_dump(mode="json"))

kline = get_stock_data("688017", "2026-05-01", "2026-05-12")
print(kline.model_dump(mode="json"))

flow = get_fund_flow("688017", "2026-05-12", include_history=True)
print(flow.model_dump(mode="json"))
```

离线示例见 `examples/python_usage.py`：

```bash
python examples/python_usage.py --mock
```

## CLI 用法

查看帮助：

```bash
astock-data --help
python -m astock_data.cli --help
```

K 线示例：

```bash
astock-data kline 688017 --start 2026-05-01 --end 2026-05-12 --format json
```

全局选项：

- `--format json|markdown|text`，默认 `json`
- `--no-cache`，本次调用绕过真实缓存，使用临时缓存目录

18 个子命令：

| 子命令 | 对应 Python API |
|---|---|
| `resolve` | `resolve_ticker` |
| `kline` | `get_stock_data` |
| `indicator` | `get_indicators` |
| `fundamentals` | `get_fundamentals` |
| `balance-sheet` | `get_balance_sheet` |
| `cashflow` | `get_cashflow` |
| `income-statement` | `get_income_statement` |
| `news` | `get_news` |
| `global-news` | `get_global_news` |
| `shareholders` | `get_insider_transactions` |
| `profit-forecast` | `get_profit_forecast` |
| `hot-stocks` | `get_hot_stocks` |
| `northbound` | `get_northbound_flow` |
| `concepts` | `get_concept_blocks` |
| `fund-flow` | `get_fund_flow` |
| `dragon-tiger` | `get_dragon_tiger_board` |
| `lockup` | `get_lockup_expiry` |
| `industry` | `get_industry_comparison` |

## MCP 设置

MCP 服务使用 FastMCP，默认传输方式是 `stdio`。启动命令：

```bash
python -m astock_data.mcp.server
```

opencode/Claude Code 风格 MCP 配置片段：

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

示例文件见 `examples/mcp_config.json`。不要配置 HTTP 或 SSE，本包当前决策是 stdio only。

18 个 MCP tools：

- `resolve_ticker`
- `get_stock_data`, `get_indicators`
- `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`
- `get_news`, `get_global_news`
- `get_insider_transactions`, `get_profit_forecast`, `get_hot_stocks`, `get_northbound_flow`
- `get_concept_blocks`, `get_fund_flow`, `get_dragon_tiger_board`, `get_lockup_expiry`, `get_industry_comparison`

## 数据源

| 来源 | 协议 | 主要数据 |
|---|---|---|
| mootdx | TCP 7709 | OHLCV K 线、财务快照、F10 文本、股票名称映射 |
| 腾讯财经 | HTTP `qt.gtimg.cn` | PE、PB、市值、换手率、实时行情快照 |
| 东方财富 | HTTP datacenter、push2、push2his、np-weblist、search-api | 龙虎榜、限售解禁、资金流、板块、个股信息、快讯 |
| 新浪财经 | HTTP | K 线历史、财报三表、个股新闻兜底 |
| 同花顺 10jqka | HTTP | EPS 一致预期、热门股票题材 |
| 财联社 cls.cn | HTTP | 全球财经快讯 |

东方财富请求统一经过线程安全限流入口，默认最小间隔 1 秒并带随机抖动，减少批量请求触发风控的概率。概念板块数据已从下线的百度 PAE 迁移至东方财富 `slist`。

## 缓存与限流配置

| 环境变量 | 说明 |
|---|---|
| `ASTOCK_CACHE_DIR` | 缓存目录，默认使用用户缓存目录下的 `astock-data` |
| `ASTOCK_EASTMONEY_MIN_INTERVAL` | 东方财富请求最小间隔，默认约 1 秒，批量任务可调大 |
| `ASTOCK_REQUEST_TIMEOUT` | HTTP 请求超时时间 |
| `ASTOCK_LIVE_TESTS` | 设为 `1` 时启用 live smoke 测试 |

缓存策略：K 线使用 CSV 缓存，结构化数据使用 SQLite JSON 缓存。`--no-cache` 会把本次 CLI 调用重定向到临时缓存目录，不污染真实缓存。

## 测试

离线测试：

```bash
python -m pytest
```

启用真实网络 smoke：

```powershell
$env:ASTOCK_LIVE_TESTS=1
python -m pytest
```

默认测试集以离线单元测试为主。live 测试依赖外部数据源可用性，失败时需区分网络波动、接口变更和代码问题。

## 边界与免责声明

- 本项目是 strict pure data layer，仅提供 A 股数据接口、CLI、MCP stdio 服务、缓存和格式化。
- 不包含 LLM、Agent、Web UI、投资建议、回测、交易执行、收益预测或组合管理。
- 所有资金流、龙虎榜、热股、解禁、行业对比字段都是事实数据或派生指标，不代表买入、卖出或持有建议。
- 数据来自公开网络接口，可能延迟、缺失或因上游变更而失效。
- 本项目仅供学习研究，不构成投资建议。使用者需自行承担投资风险。
