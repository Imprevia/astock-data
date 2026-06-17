# tests/live

本目录保存 opt-in 真实网络冒烟测试。默认情况下，这些用例不会访问外部数据源；只有显式设置 `ASTOCK_LIVE_TESTS=1` 后才会执行。

## 覆盖场景

`test_smoke_live.py` 覆盖 7 个真实链路：

- 行情和 K 线数据获取。
- 技术指标生成。
- 基本面汇总。
- 个股新闻获取。
- 全球财经快讯获取。
- 龙虎榜、解禁或资金流等东方财富专属数据获取。
- CLI 或公开 API 的端到端可用性抽样。

## 约束

- 用例按串行思路维护，避免并发压测外部站点。
- 东方财富相关请求必须尊重项目限流入口和 `ASTOCK_EASTMONEY_MIN_INTERVAL` 配置。
- 网络超时、上游空响应或临时风控是可接受现象，记录现象并判断是否为接口变更。
- 不在本目录放置密钥、cookie、个人账号或本机专属配置。
- 新增真实网络用例时，优先选择少量代表性股票和短时间窗口。

## 验证

```powershell
$env:ASTOCK_LIVE_TESTS=1
python -m pytest tests/live/test_smoke_live.py -q
python -m pytest tests/test_agents_docs.py -q
```
