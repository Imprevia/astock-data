# Repository Guide

本仓库是 Python `>=3.10` 的 A 股纯数据层。产品能力、安装和完整 25 项接口表以 [README](../README.md) 为准，未发布变化以 [CHANGELOG](../CHANGELOG.md) 为准。

## 修改路由

| 任务 | 位置 | 同步事实源 |
|---|---|---|
| 公共 Python / CLI / MCP 契约 | `astock_data/api.py`、`astock_data/cli.py`、`astock_data/mcp/` | README、architecture、契约测试 |
| resolver、缓存、数据源适配 | `astock_data/resolver.py`、`astock_data/cache/`、`astock_data/clients/` | architecture、runbooks、对应测试 |
| 服务编排与结构化模型 | `astock_data/services/`、`astock_data/models/` | architecture、对应测试 |
| 当前工作与证据 | `docs/exec-plans/active/`、`docs/status.md` | active plan 与 status |
| 本地门禁 | `scripts/`、`.githooks/` | runbooks、契约测试 |

## 安全边界

- 包只获取、校验、缓存、格式化并适配结构化市场数据，不拥有复盘、交易或投资建议逻辑。
- 下游 `daily-review` 仅通过 `python -m astock_data.cli` 的 JSON 接口消费本包，不复制数据源请求实现。
- 不直接修改缓存、压缩包、工具状态目录或生成目录；默认测试保持离线。
- 先更新 active plan，再修改代码；验证命令见 [runbooks](runbooks.md)。
