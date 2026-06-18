## 目录职责
`astock_data` 是纯数据层包，负责配置、错误、市场校验、resolver、客户端、服务、模型、缓存、格式化、MCP 门面。

## 关键文件
- `api.py`，19 个公开函数的唯一 Python 门面。
- `resolver.py`，ticker 安全边界，所有用户输入先过这里。
- `config.py`，运行时配置与缓存目录。
- `errors.py`，统一异常层次。
- `market.py`，交易日与日期校验。

## 允许修改
- 纯数据层内部实现、类型、导出列表、错误信息、测试用契约说明。
- 与 19 个公开函数对齐的轻量门面和再导出。

## 禁止修改
- 不要在包内引入 Web、LLM、Agent、投研建议或外部状态机。
- 不要绕过 `resolver`，不要让服务层直接接受未校验的 ticker。
- 不要在包内新增非纯数据副作用。

## 验证命令
- `python -m pytest tests/test_public_api.py -q`
- `python -m pytest tests/test_resolver_contract.py -q`
- `python -m pytest -q`

## 与公共接口的关系
这里承载 19 个公开入口的实现基础，`api.py` 面向 CLI 和 MCP，`resolver.py` 是所有 ticker 流入点的唯一安全边界。
