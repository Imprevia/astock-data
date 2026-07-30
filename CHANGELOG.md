# Changelog

## [Unreleased]

### Added
- 北交所 920xxx/43xxxx 代码段支持：resolver 正则、Ticker 模型、CSV/SQLite 缓存、TDX/腾讯/新浪客户端市场前缀映射
- CLI 注册 daily-review 6 个命令：`index-kline`、`stock-amount`、`sector-fund-flow`、`sector-strength`、`sector-fund-flow-history`、`etf-daily`
- 行业五日资金结果新增 `five_day_main_net_inflow_by_code`，可表达 push2his 逐日求和或当前日期的 f164-only 累计，同时保持 `history_by_code` 兼容
- 东方财富 `getbkzj` f164 官方行业范围批量客户端，固定参数为 `key=f164`、`code=m:90+s:4`，保留元单位和有效零值
- 指数K线新浪降级：`SinaClient.index_kline()` 方法，东财 push2his 失败后从新浪获取完整10条日K线
- 个股成交额腾讯降级：`TencentClient.quote()` 新增 `amount_wan` 字段，东财失败后从腾讯获取实时成交额
- ETF K线新浪降级：东财 push2his 失败后从新浪获取ETF日K线
- `EastmoneyClient` 新增可选 `max_retries` 参数

### Changed
- `get_sector_fund_flow_history` 保持 push2his 为逐日权威源；仅在今日五日窗口存在缺失序列时整次调用加载一次 f164，并按精确目标日期缓存
- 同花顺行业 K 线继续兼容返回行情字段，但不再可能被解释为逐日主力净流入或五日资金累计
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
