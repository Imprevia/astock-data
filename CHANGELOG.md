# Changelog

## [Unreleased]

### Added
- 北交所 920xxx/43xxxx 代码段支持：resolver 正则、Ticker 模型、CSV/SQLite 缓存、TDX/腾讯/新浪客户端市场前缀映射
- CLI 注册 daily-review 6 个命令：`index-kline`、`stock-amount`、`sector-fund-flow`、`sector-strength`、`sector-fund-flow-history`、`etf-daily`
- 行业5日资金流 `dataapi/bkzj` 优先源：东财 push2his 被封时通过 `data.eastmoney.com/dataapi/bkzj/getbkzj` 批量获取真实主力资金流（496个行业全覆盖）
- 指数K线新浪降级：`SinaClient.index_kline()` 方法，东财 push2his 失败后从新浪获取完整10条日K线
- 个股成交额腾讯降级：`TencentClient.quote()` 新增 `amount_wan` 字段，东财失败后从腾讯获取实时成交额
- ETF K线新浪降级：东财 push2his 失败后从新浪获取ETF日K线
- `EastmoneyClient` 新增可选 `max_retries` 参数

### Changed
- `get_sector_fund_flow_history` 降级链从 push2his优先 改为 dataapi优先（避免被封时30个行业串行等待超时）
- `get_market_breadth` 东财重试从3次降为1次+3秒超时，加速腾讯/新浪降级
- `_market_for_code` 北交所映射修正：920/43/8 → bj（之前9开头误映射为sh）

## 0.1.0

- 初始发布，建立严格 pure data layer 的 A 股数据包。
- 提供 18 个公开 Python 接口，覆盖行情、指标、财务、新闻、资金流、龙虎榜、解禁、行业和概念数据。
- 提供 18 个 CLI 子命令，支持 `json`、`markdown`、`text` 输出格式与 `--no-cache`。
- 提供 18 个 MCP tools，使用 FastMCP `stdio` 传输方式，便于 opencode 和 Claude Code 直接拉起。
- 实现混合缓存、线程安全的东方财富限流、统一 ticker 解析和严格输入校验。
- 明确无 LLM、无 Agent、无 Web UI、无投资建议边界。
- 补充 `AGENTS.md`、项目技能与离线示例，便于自动化与本地开发。
