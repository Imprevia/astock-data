## 目录职责
`astock_data/mcp` 提供 FastMCP stdio 服务，把 19 个公开函数暴露给 MCP 客户端。

## 关键文件
- `server.py`，19 个工具注册与 `FastMCP("astock-data")`。
- `__init__.py`，包初始化。

## 允许修改
- 工具声明、参数说明、错误包装、JSON 兼容性、导出列表。
- 只在保持 19 工具一致性的前提下改动。

## 禁止修改
- 不要把 MCP 改成 HTTP Web 服务。
- 不要返回不可 JSON 序列化的对象。
- 不要让 MCP 直接绕过服务层或 resolver。

## 验证命令
- `python -m pytest tests/test_mcp_server.py -q`
- `python -m pytest tests/test_public_api.py -q`
- `python -m pytest -q`

## 与公共接口的关系
MCP 只做 stdio 暴露，19 个工具必须与 `astock_data.api` 一一对应。
