## 目录职责
本目录是 `astock-data` 的仓库根目录，负责纯数据层、公共入口面、测试与发布元数据。

## 关键文件
- `pyproject.toml`，定义依赖、pytest 配置、CLI 入口、MCP 相关安装信息。
- `astock_data/api.py`，19 个公开函数的统一门面。
- `astock_data/__init__.py`，顶层重导出与版本号。
- `astock_data/cli.py`，19 个 CLI 子命令入口。
- `astock_data/mcp/server.py`，19 个 FastMCP 工具入口。
- `tests/`，离线优先的回归测试与契约测试。

## 允许修改
- 纯数据层代码、测试、文档、打包元数据、CLI 和 MCP 的门面声明。
- 仅为公共 API、CLI、MCP、测试约束服务的说明文档。

## 禁止修改
- 不要把仓库改成 LLM、Agent、Web UI 或投研建议系统。
- 不要规避测试、缓存安全、resolver 安全边界或东财单一 chokepoint。
- 不要新增第三方对话框架、Web UI 或 HTTP 服务框架依赖或导入。

## 验证命令
- `python -m pytest -q`
- `python -m pytest tests/test_public_api.py -q`
- `python -m pytest tests/test_agents_docs.py -q`

## 与公共接口的关系
根目录只负责把 19 个公开入口、19 个 CLI 子命令、19 个 MCP 工具组织成同一套纯数据层门面，不在这里放业务实现。
