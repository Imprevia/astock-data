# astock-data

`astock-data` 是一个严格的 A 股纯数据层包。它只提供结构化数据接口、CLI 和 MCP stdio 工具，不包含 LLM、Agent、Web UI、回测或投资决策逻辑。

> 免责声明：本项目仅供学习研究和数据工程验证，不构成任何投资建议。市场有风险，投资决策请咨询持牌专业机构。

## 项目简介

- 纯数据层：统一封装 A 股行情、市场广度、财务、新闻、资金流、龙虎榜、解禁、行业和概念板块数据。
- 无 LLM/Agent 依赖：不会导入 `langchain`、`openai`、`anthropic`、`streamlit`、`fastapi` 等应用层或智能体依赖。
- 结构化返回：26 个公开 Python API 均返回 Pydantic 模型，不返回自由文本报告。
- 严格边界：只做数据获取、校验、缓存、格式化和协议适配，不做买卖建议、不做组合管理、不做收益承诺。

## 安装

需要 Python `>=3.10`。

```bash
cd G:\workspaces\gupiao\stock-data-source
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

## 项目文档

修改入口与安全边界见 [`docs/repository-guide.md`](docs/repository-guide.md)，架构不变量见 [`docs/architecture.md`](docs/architecture.md)，本地运行与门禁命令见 [`docs/runbooks.md`](docs/runbooks.md)，当前实现状态见 [`docs/status.md`](docs/status.md)。发布变化继续记录在 [`CHANGELOG.md`](CHANGELOG.md)。

## Python API 用法

推荐从 `astock_data.api` 导入公开接口。完整公开函数共 26 个：

- `resolve_ticker`
- `get_stock_data`, `get_indicators`, `get_market_breadth`, `get_order_book`
- `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`
- `get_news`, `get_global_news`
- `get_insider_transactions`, `get_profit_forecast`, `get_hot_stocks`, `get_northbound_flow`
- `get_concept_blocks`, `get_fund_flow`, `get_dragon_tiger_board`, `get_lockup_expiry`, `get_industry_comparison`
- `get_index_kline`, `get_stock_amount`, `get_etf_daily`
- `get_sector_fund_flow`, `get_sector_fund_flow_history`, `get_sector_strength`

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

26 个子命令：

| 子命令 | 对应 Python API |
|---|---|
| `resolve` | `resolve_ticker` |
| `kline` | `get_stock_data` |
| `indicator` | `get_indicators` |
| `market-breadth` | `get_market_breadth` |
| `order-book` | `get_order_book` |
| `index-kline` | `get_index_kline` |
| `stock-amount` | `get_stock_amount` |
| `etf-daily` | `get_etf_daily` |
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
| `sector-fund-flow` | `get_sector_fund_flow` |
| `sector-fund-flow-history` | `get_sector_fund_flow_history` |
| `sector-strength` | `get_sector_strength` |

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

26 个 MCP tools：

- `resolve_ticker`
- `get_stock_data`, `get_indicators`, `get_market_breadth`, `get_order_book`
- `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`
- `get_news`, `get_global_news`
- `get_insider_transactions`, `get_profit_forecast`, `get_hot_stocks`, `get_northbound_flow`
- `get_concept_blocks`, `get_fund_flow`, `get_dragon_tiger_board`, `get_lockup_expiry`, `get_industry_comparison`
- `get_index_kline`
- `get_stock_amount`
- `get_etf_daily`
- `get_sector_fund_flow`
- `get_sector_fund_flow_history`
- `get_sector_strength`

## 数据源

| 来源 | 协议 | 主要数据 |
|---|---|---|
| mootdx | TCP 7709 | OHLCV K 线、财务快照、F10 文本、股票名称映射 |
| 腾讯财经 | HTTP `qt.gtimg.cn` | PE、PB、市值、换手率、实时行情快照、五档盘口、市场广度指数兜底、个股成交额降级 |
| 东方财富 | HTTP datacenter、dataapi、push2、push2his、np-weblist、search-api | 指数快照、全市场行情、龙虎榜、限售解禁、资金流、板块、个股信息、快讯 |
| 新浪财经 | HTTP | K 线历史、财报三表、个股新闻兜底、市场广度二级兜底、指数K线降级、ETF K线降级 |
| 同花顺 10jqka | HTTP | EPS 一致预期、热门股票题材、行业K线降级 |
| 财联社 cls.cn | HTTP | 全球财经快讯 |

东方财富请求统一经过线程安全限流入口，默认最小间隔 1 秒并带随机抖动，同时启用 UA 随机化及 429/503 自动重试（读取 `Retry-After`），减少批量请求触发风控的概率。腾讯财经请求带 `Referer` 并启用 UA 随机化；新浪财经 K 线和财报请求带 `Referer`，并启用 UA 随机化及 429/503 重试。概念板块数据已从下线的百度 PAE 迁移至东方财富 HSF10 `core-conception` 的有序 `ssbk`；只有显式 `ssbk=[]` 表示成功空集合，响应缺键、类型错误或非法 `BOARD_RANK` 会作为数据源错误返回。

`get_global_news(curr_date, look_back_days, limit)` 会使用东方财富 7×24 接口返回的 `sortEnd` 游标向历史翻页，并严格过滤到请求的日期窗口。旧版缓存中缺少窗口元数据或日期越界的实时新闻不会作为历史事实返回；公开快讯档案未覆盖目标日期时返回空列表和明确 warning。

`get_market_breadth()` 按能力降级：指数快照依次尝试腾讯、新浪、东方财富；涨跌停家数依次尝试新浪分页、东方财富全市场行情。历史目标日只有在新浪指数 K 线能够把当前快照日期精确验证为目标日时才返回事实，否则整体状态为 `unavailable`。快速模式的涨跌停统计带 `available`、`partial`、`unavailable` 状态；单侧失败时失败侧计数为 `null`，双侧失败时两侧均为 `null`，不会用 `0/0` 伪装缺失。返回结果的 `raw.sources` 会记录 `indices`、`limit_stats`、`board_ladders` 的实际来源；如果只能返回部分结果，`warnings` 会说明失败来源、fallback 来源或连板推导跳过原因。新浪分页属于低频路径，重复调用可能触发上游临时限流。

### 数据获取降级链

当东方财富 push2/push2his 被反爬封禁时，各接口按以下降级链获取数据：

| 接口 | 主源 | 降级1 | 降级2 | 降级3 |
|---|---|---|---|---|
| market-breadth 指数 | 腾讯 | 新浪 | 东财push2 | — |
| market-breadth 涨跌停 | 新浪分页 | 东财push2 clist | — | — |
| order-book | 腾讯五档实时快照 | — | — | — |
| index-kline | 东财push2his | 新浪K线 | mootdx | — |
| stock-amount | 东财push2his | 腾讯quote | — | — |
| etf-daily | 新浪K线 | 东财push2his | — | — |
| sector-fund-flow-history | 东财push2his逐日资金 | 日期校验后的东财f164最新交易日五日累计 | SQLite资金缓存 | 同花顺行业日K |
| sector-strength | 东财push2 clist | SQLite缓存 | — | — |

`etf-daily` 的行业 ETF 白名单覆盖 broad-market 既有代码，并新增软件 `515230`、计算机 `512720`、传媒 `512980`、通信 `515880`、机器人 `562500`、电子 `515260`、黄金 `518880`、游戏 `159869`、化工 `516020`、农业 `159825`。这些代码供下游做代表性行业行情代理，不表达精确 ETF 份额流入。

`order-book` 返回腾讯可见的买卖五档，数量单位为手（1 手 = 100 股）。默认只请求一个快照；可通过 `--samples` 和 `--interval-seconds` 进行有界多次采样，单次调用的计划等待时间不超过 300 秒。同侧同价深度减少只标记为 `depth-decrease` / `unattributed`，价格进出五档只标记为 `entered-view` / `left-view`；这些变化不能证明精确撤单、订单身份或隐藏流动性。

`sector-fund-flow-history` 的 `history_by_code` 始终保留真实逐日记录。有效 push2his 资金序列必须在日期过滤后至少包含一个非布尔 `int`/`float` 类型的 `main_net_inflow`；仅有空值、字符串或布尔值的 dated rows 不会阻止降级，也不会作为资金历史对外返回。仅当 `days == 5` 且新浪上证指数最新K线日期与目标日期完全一致时，服务才会通过一次 `getbkzj` 批量请求读取官方行业范围 `m:90+s:4` 的 `f164`，并把元单位累计值写入独立的 `five_day_main_net_inflow_by_code`。日期不匹配或不可校验时禁用 f164，避免把无日期参数的当前值错配给历史日期。`aggregate_only=True` 可跳过逐板块 push2his，只获取这份已校验的批量累计；它不会据此伪造五条日记录或正流入天数。

同花顺降级只提供行业日 K 的 `date`、`close`、`amount`、`pct_change` 字段，不代表逐日主力净流入，也不会生成五日资金累计。回退顺序优先使用同日真实资金缓存，再考虑 THS 行情。成功的 f164 批量映射按目标日期精确缓存供同日复用，不读取其他日期作为回退；warnings 会区分 push2his、f164-only、THS 行情、缓存和完全缺失。

## 缓存与限流配置

| 环境变量 | 说明 |
|---|---|
| `ASTOCK_CACHE_DIR` | 缓存目录，默认使用用户缓存目录下的 `astock-data` |
| `ASTOCK_EASTMONEY_MIN_INTERVAL` | 东方财富请求最小间隔，默认约 1 秒，批量任务可调大 |
| `ASTOCK_REQUEST_TIMEOUT` | HTTP 请求超时时间 |
| `ASTOCK_HTTP_PROXY` | 可选 HTTP 代理，应用于所有 HTTP 数据源请求，默认关闭 |
| `ASTOCK_USER_AGENT_POOL` | 可选自定义 UA 池，JSON 数组，默认使用内置桌面 UA |
| `ASTOCK_LIVE_TESTS` | 设为 `1` 时启用 live smoke 测试 |

缓存策略：K 线使用 CSV 缓存，结构化数据使用 SQLite JSON 缓存。行业 f164 五日累计使用目标日期参与键构造并只做精确日期读取，不允许跨日期回退。`--no-cache` 会把本次 CLI 调用重定向到临时缓存目录，不污染真实缓存。

### Ticker 代码支持

支持全部 A 股代码段：上交所（6开头）、深交所（0/3开头）、北交所（43/8/920开头）。920xxx 是北交所新代码段，已纳入 resolver 正则校验和所有客户端的市场前缀映射。

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
- 所有市场广度、资金流、龙虎榜、热股、解禁、行业对比字段都是事实数据或派生指标，不代表买入、卖出或持有建议。
- 数据来自公开网络接口，可能延迟、缺失或因上游变更而失效。
- 本项目仅供学习研究，不构成投资建议。使用者需自行承担投资风险。
