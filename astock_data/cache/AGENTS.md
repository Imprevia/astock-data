## 目录职责
`astock_data/cache` 放混合缓存实现，服务层只通过这里做读写。

## 关键文件
- `kline_csv.py`，`CsvKlineCache`。
- `structured_sqlite.py`，`SQLiteStructuredCache`。
- `__init__.py`，缓存导出。

## 允许修改
- TTL、键构造、序列化、并发保护、读取回退和路径安全。
- 仅保留对离线测试有用的缓存能力。

## 禁止修改
- 不要把缓存键做得不安全，不要允许路径穿越。
- 不要绕过 TTL。
- 不要把缓存变成网络或业务层。

## 验证命令
- `python -m pytest tests/test_cache_contract.py -q`
- `python -m pytest tests/test_market_data_service.py -q`
- `python -m pytest -q`

## 与公共接口的关系
缓存只服务 17 个 `get_*` 入口的性能和离线可重复性，不能改变对外返回契约。
