## 目录职责
`astock_data/services` 放 5 个服务模块，把客户端和模型组合成 17 个 `get_*` 公共函数。

## 关键文件
- `market_data.py`，`get_stock_data` 与 `get_indicators`。
- `fundamentals.py`，`get_fundamentals`、三表接口。
- `news.py`，`get_news` 与 `get_global_news`。
- `signals_a.py`，游资、盈利预期、热股、北向资金。
- `signals_b.py`，概念、资金流、龙虎榜、解禁、行业比较。

## 允许修改
- 服务编排、缓存读写、模型组装、warnings、返回结构、日期筛选。
- 所有 ticker 输入都要先走 `resolver.resolve_ticker`。

## 禁止修改
- 不要返回裸字符串或未结构化对象。
- 不要在服务层直接拼东财 URL。
- 不要跳过缓存安全、市场校验或 resolver。

## 验证命令
- `python -m pytest tests/test_public_api.py -q`
- `python -m pytest tests/test_market_data_service.py -q`
- `python -m pytest tests/test_fundamentals_service.py -q`
- `python -m pytest tests/test_news_service.py -q`
- `python -m pytest tests/test_signals_group_a.py -q`
- `python -m pytest tests/test_signals_group_b.py -q`

## 与公共接口的关系
这里是 17 个 `get_*` 入口的实现层，`api.py` 和 `mcp/server.py` 只做转发，不重复业务逻辑。
