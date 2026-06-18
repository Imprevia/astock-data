## Why

`get_market_breadth()` 当前把指数快照与全市场行情都绑定在东财 `push2.eastmoney.com`。在当前网络下，东财 `stock/get` 与 `clist/get` 都持续返回 `RemoteDisconnected`，导致市场广度入口整体不可用；但同一环境下腾讯 `qt.gtimg.cn` 和新浪 `hq.sinajs.cn` 可正常返回指数与样本行情。因此需要把市场广度从「东财单点依赖」升级为「多源降级」能力。

## What Changes

- 为 `get_market_breadth()` 增加分层数据源降级：东财失败时，指数快照降级到腾讯，必要时再降级到新浪。
- 为涨跌停家数增加全市场行情 fallback：优先探索并接入腾讯全市场榜单；若腾讯全市场不可用，再考虑新浪分页作为二级备选。
- 将 `MarketBreadthResult.raw.sources` 从静态说明改为实际来源记录，例如 `indices=tencent`、`limit_stats=sina`、`board_ladders=derived.kline.threshold`。
- 当无法取得当日涨停清单时，`limit_stats` 尽量从可用全市场行情返回；`board_ladders` 降级为空字典并写入 warning，而不是让整个入口失败。
- 增加离线测试覆盖：东财失败后腾讯/新浪 fallback、partial result warnings、来源标记、全源失败时的 typed error。

**不改 / 不破坏：**
- 不新增第三方依赖，不引入 Tushare、AkShare、开盘啦/复盘啦 App 逆向接口作为默认路径。
- 不改变 `get_market_breadth()` 的公开签名或返回模型。
- 不改变现有 resolver 边界，指数仍由内部枚举映射。
- 不承诺炸板家数，不引入状态库。

## Capabilities

### New Capabilities
<!-- 无新增 capability。 -->

### Modified Capabilities
- `market-breadth`: 增加指数快照、涨跌停家数与连板梯队的多源降级行为；明确 partial result 与 warnings 语义。

## Impact

- **客户端层**：`TencentClient` 需要支持指数批量快照；可能新增腾讯全市场榜单 helper。若新浪作为二级 fallback，需要在 `SinaClient` 增加指数/全市场分页辅助。
- **服务层**：`astock_data/services/market_breadth.py` 需要从单源顺序调用改为 per-capability fallback orchestration。
- **模型层**：模型结构保持不变；`raw.sources` 内容从静态映射升级为实际来源记录。
- **测试**：新增/更新 `tests/test_market_breadth_service.py`、`tests/test_tencent_client.py`、必要时 `tests/test_sina_client.py`。
- **文档**：README 数据源说明补充市场广度 fallback；OpenSpec design 记录为什么不默认接入同花顺/开盘啦逆向接口。
