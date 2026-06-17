# Changelog

## 0.1.0

- 初始发布，建立严格 pure data layer 的 A 股数据包。
- 提供 18 个公开 Python 接口，覆盖行情、指标、财务、新闻、资金流、龙虎榜、解禁、行业和概念数据。
- 提供 18 个 CLI 子命令，支持 `json`、`markdown`、`text` 输出格式与 `--no-cache`。
- 提供 18 个 MCP tools，使用 FastMCP `stdio` 传输方式，便于 opencode 和 Claude Code 直接拉起。
- 实现混合缓存、线程安全的东方财富限流、统一 ticker 解析和严格输入校验。
- 明确无 LLM、无 Agent、无 Web UI、无投资建议边界。
- 补充 `AGENTS.md`、项目技能与离线示例，便于自动化与本地开发。
