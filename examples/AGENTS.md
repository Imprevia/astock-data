## 目录职责
`examples` 放 `astock-data` 的最小可运行示例，用于展示 Python API 和 MCP stdio 配置，不承载生产逻辑。

## 关键文件
- `python_usage.py`，Python API 示例；`--mock` 模式离线输出结构化样例数据。
- `mcp_config.json`，opencode/Claude Code 风格的 MCP stdio 配置片段。

## 如何运行
- 离线示例：`python examples/python_usage.py --mock`
- 真实数据示例：`python examples/python_usage.py`
- MCP 服务命令：`python -m astock_data.mcp.server`

## 允许修改
- 更新示例以匹配 19 个公开 API、19 个 CLI 子命令和 19 个 MCP tools。
- 保持示例小而清晰，优先展示结构化 JSON 输出。

## 禁止修改
- 不要在示例里加入 LLM、Agent、Web UI、交易执行或投资建议。
- 不要写入私有 API key、个人绝对路径或依赖本机环境的配置。

## 验证命令
- `python examples/python_usage.py --mock`
- `python -m pytest tests/test_agents_docs.py -q`
