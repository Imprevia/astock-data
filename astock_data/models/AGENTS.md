## 目录职责
`astock_data/models` 定义所有结构化结果契约，供服务、API、CLI、MCP 统一复用。

## 关键文件
- `base.py`，`ResultBase`、`Ticker`、通用元数据。
- `market.py`，行情与指标模型。
- `fundamentals.py`，财务与报表模型。
- `news.py`，新闻与全球资讯模型。
- `signals.py`，信号类结果模型。

## 允许修改
- 结果字段、序列化细节、枚举与校验规则。
- 仅在保持向后兼容的前提下扩展结构化契约。

## 禁止修改
- 不要把模型变成业务服务、网络客户端或格式化器。
- 不要放宽 `Ticker.code` 的校验规则。
- 不要移除 `ResultBase` 的 `source`、`retrieved_at`、`raw`、`warnings` 语义。

## 验证命令
- `python -m pytest tests/test_models.py -q`
- `python -m pytest tests/test_public_api.py -q`
- `python -m pytest -q`

## 与公共接口的关系
所有公开函数都应返回这里定义的结构化模型，CLI、MCP、格式化器都只消费这些契约。
