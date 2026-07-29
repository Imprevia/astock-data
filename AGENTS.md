## 目录职责
本目录是 `astock-data` 的仓库根目录，负责纯数据层、公共入口面、测试与发布元数据。

## 关键文件
- `docs/repository-guide.md`，任务路由、修改位置与安全边界。
- `docs/architecture.md`，系统边界、数据流和不可破坏的不变量。
- `docs/runbooks.md`，安装、验证、门禁和故障处理命令。
- `docs/status.md` 与 `docs/exec-plans/active/`，当前状态、执行计划和完成证据。
- `pyproject.toml`，定义依赖、pytest 配置、CLI 入口、MCP 相关安装信息。
- `astock_data/api.py`，25 个公开函数的统一门面。
- `astock_data/__init__.py`，顶层重导出与版本号。
- `astock_data/cli.py`，25 个 CLI 子命令入口。
- `astock_data/mcp/server.py`，25 个 FastMCP 工具入口。
- `tests/`，离线优先的回归测试与契约测试。

## 允许修改
- 纯数据层代码、测试、文档、打包元数据、CLI 和 MCP 的门面声明。
- 仅为公共 API、CLI、MCP、测试约束服务的说明文档。

## 禁止修改
- 不要把仓库改成 LLM、Agent、Web UI 或投研建议系统。
- 不要规避测试、缓存安全、resolver 安全边界或东财单一 chokepoint。
- 不要新增第三方对话框架、Web UI 或应用服务框架依赖或导入。

## 硬门禁
- 非平凡改动先更新 `docs/exec-plans/active/*.md`，并保持 `Stage`、`Status`、`Acceptance`、`Completion Evidence`、`Remaining Gaps`、`Next Step` 六个非空字段。
- 代码改动必须同步更新 `docs/`、`README.md` 或 `AGENTS.md` 中的对应事实；架构、运行路径和产品边界分别回写 architecture、runbooks 和 README。
- 完成前运行 `python scripts/check_docs_contract.py --mode full`；本地 hooks 仅调用同一检查器，不另存规则。
- `pre-commit` 只运行与提交消息无关的快速结构检查；`commit-msg` 用 Git 传入的消息文件检查 staged gates；`pre-push` 逐条检查 stdin 中的实际 ref OID 范围并跳过删除 ref。缺失 remote object 必须先 fetch 对应 remote/ref，不能降级为当前 HEAD。
- 逃生口只用于有理由的紧急操作：`SKIP_DOCS_CONTRACT=1` 跳过全部门禁，`SKIP_PLAN_GATE=1` 跳过计划门禁；`[skip-plan]`、`[docs-only]`、`[no-docs]` 在 `commit-msg` 只作用于当前 staged 提交，在 push/full 范围只作用于标记所在提交，不得跨提交共享，后两者必须附理由。

## 验证命令
- `python -m pytest -q`
- `python -m pytest tests/test_public_api.py -q`
- `python -m pytest tests/test_agents_docs.py -q`
- `python -m pytest tests/test_docs_contract.py tests/test_docs_contract_review.py tests/test_hooks_contract.py -q`
- `python scripts/check_docs_contract.py --mode full`

## 与公共接口的关系
根目录只负责把 25 个公开入口、25 个 CLI 子命令、25 个 MCP 工具组织成同一套纯数据层门面，不在这里放业务实现。
