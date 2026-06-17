# tests/fixtures

本目录保存离线测试使用的最小匿名响应样本，用于让客户端、服务层和格式化测试在无网络条件下稳定运行。

## 关键文件

- `tencent_quote.txt`: 腾讯行情快照的精简 GBK 稳定样本，覆盖字段位置解析。
- `eastmoney_datacenter.json`: 东方财富 datacenter 响应样本，覆盖表格型 JSON 结构。
- `sina_kline.json`: 新浪 K 线响应样本，覆盖日期、OHLCV 字段解析。
- `sina_financial_*.json`: 新浪财报三表响应样本，分别覆盖资产负债、利润和现金流结构。
- `sina_news.html`: 新浪个股新闻 HTML 响应样本，覆盖中文页面解析。

## 约束

- 样本必须保持最小化，只保留测试断言需要的字段和行。
- 样本必须匿名化，不包含个人信息、账号、cookie、token 或内部标识。
- 不提交真实大负载、整页抓包、长历史行情或无法解释来源的内容。
- 新增样本时，同步说明它服务的测试场景和字段含义。

## 验证

```powershell
python -m pytest tests/test_tencent_client.py tests/test_sina_client.py tests/test_eastmoney_client.py -q
python -m pytest tests/test_agents_docs.py -q
```
