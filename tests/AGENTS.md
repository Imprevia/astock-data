## 目录职责
`tests` 放 pytest 契约、回归、离线 fixture 和覆盖扫描。

## 关键文件
- `conftest.py`，marker、live 跳过、fixture 约定。
- `test_public_api.py`，18 个公开入口契约。
- `test_agents_docs.py`，`AGENTS.md` 覆盖扫描。
- `fixtures/`，离线样例数据。

## 允许修改
- 新增离线测试、契约测试、fixture、marker 相关配置。
- 仅在不破坏离线默认策略的前提下扩展测试。

## 禁止修改
- 不要在测试里跳过关键契约，不要绕过缓存安全或 resolver。
- 不要引入 live 依赖作为默认路径。

## 验证命令
- `python -m pytest -q`
- `python -m pytest tests/test_agents_docs.py -q`
- `python -m pytest tests/test_public_api.py -q`

## 与公共接口的关系
测试目录守住 18 个公开入口、17 个服务入口、18 个 MCP 工具和所有安全边界的行为契约。
