## Context

`add-market-breadth` 已完成 `get_market_breadth()`，但当前实现对东财 `push2.eastmoney.com` 存在单点依赖：指数快照使用 `stock/get`，全市场 quote rows 使用 `clist/get`。在当前网络下，这两个端点都持续以 `RemoteDisconnected` 拒连；与此同时，腾讯 `qt.gtimg.cn` 和新浪 `hq.sinajs.cn` 均可正常返回指数与个股样本行情。

市场广度入口服务于盘后复盘场景。它不应因为某一个 vendor 的风控或网络故障整体不可用；更合理的行为是按能力降级：指数可从腾讯/新浪取，涨跌停家数可从替代全市场 quote rows 取，连板梯队在缺少可靠涨停清单时返回空并附 warning。

## Goals / Non-Goals

**Goals:**

- 让 `get_market_breadth()` 在东财 `push2` 拒连时仍尽量返回部分结果。
- 为指数快照添加腾讯优先、必要时新浪兜底的 fallback。
- 为涨跌停家数添加全市场 quote rows fallback，优先验证腾讯全市场榜单，再考虑新浪分页。
- 在 `raw.sources` 中记录每个能力实际使用的数据源，而不是固定写死东财。
- 当 `board_ladders` 因无法取得涨停清单而不可计算时，返回 `{}` 并写入 warning，不抛出导致整个入口失败的异常。
- 保持现有 `get_market_breadth()` 签名和 `MarketBreadthResult` 模型不变。

**Non-Goals:**

- 不新增第三方依赖（不引入 AkShare，只把其 OSS 实现作为端点参考）。
- 不默认接入 Tushare、开盘啦/复盘啦 App 逆向接口。
- 不默认接入同花顺反爬较重的 `limit_up_pool` / `continuous_limit_pool` 作为生产 fallback。
- 不提供炸板家数。
- 不引入状态库或调度任务。

## Decisions

### 1. 按能力分别 fallback，而不是全函数单一 fallback

`get_market_breadth()` 的三个能力应独立降级：

```
indices       eastmoney -> tencent -> sina
limit_stats   eastmoney clist -> tencent market board -> sina market pagination
board_ladders derived from whichever rows identify limit-up stocks; otherwise {}
```

理由：指数、涨跌停家数、连板梯队的数据可得性不同。指数不应因为全市场 quote rows 失败而缺失；涨跌停家数不应因为连板不可算而失败。

### 2. 腾讯作为第一 index fallback

腾讯本次稳定接入一类能力：

- `qt.gtimg.cn/q=...` 批量快照：实测可用于指数快照和个股样本行情。
- 腾讯全市场榜单候选 `proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList`：实施 spike 中以候选参数请求返回 HTTP 400，暂不作为默认全市场 quote rows fallback。

理由：腾讯 `qt.gtimg.cn` 已在仓库中有 `TencentClient`，且当前网络可达；但全市场榜单候选端点未验证稳定，默认使用会引入额外不可控风险。

### 3. 新浪作为二级 fallback，而不是首选

新浪可提供指数与全市场分页数据，但 AkShare 源码注释提示重复运行可能被新浪暂时封 IP。它适合作为二级 fallback，而不是默认高频路径。

理由：`get_market_breadth()` 盘后低频调用可接受新浪兜底；默认使用则可能引入封 IP 风险。

### 4. 连板梯队在无涨停清单时降级为空

现有连板计算依赖「当日涨停股集合」。若东财和替代全市场 rows 都不可用，则不能构造涨停集合。此时应返回 `board_ladders={}`，并在 warnings 中说明「无法取得涨停清单，跳过连板推导」。

理由：这比抛错更适合复盘场景，也避免使用反爬/逆向接口作为默认来源。

### 5. 不默认接入同花顺/开盘啦逆向接口

同花顺 `dataapi/limit_up/*` 与开盘啦/复盘啦类接口可能提供涨停池、连板池或涨停天梯，但存在 Cookie/JS 反爬、App 逆向、接口稳定性和合规风险。它们可以作为未来实验性 change 单独评估，不进入本次默认 fallback。

### 6. 用 typed error 区分全源失败

如果所有指数源都失败，且所有全市场 quote 源也失败，`get_market_breadth()` 应抛现有 typed data-source error，而不是返回全空结果。若至少一个能力成功，则返回 partial result 并写 warnings。

## Risks / Trade-offs

- [风险] 腾讯全市场榜单字段/分页与东财不完全等价 → [缓解] 将 vendor row 先规范化为统一内部 quote row，再复用阈值分类逻辑。
- [风险] 新浪 fallback 被频繁调用可能封 IP → [缓解] 仅作为东财和腾讯都失败后的二级 fallback，并保留 warnings/source 标记。
- [风险] partial result 被误认为完整结果 → [缓解] warnings 必须明确说明哪些 capability fallback 或缺失，`raw.sources` 记录实际来源。
- [风险] 腾讯全市场榜单 endpoint 可能需要进一步 spike → [缓解] tasks 中先加入 offline client 测试和小规模 live smoke；若字段不稳定，实施时可只落指数 fallback，把全市场 fallback 留成后续。

## Migration Plan

1. 扩展 `TencentClient` 支持指数快照。
2. 扩展 `SinaClient` 支持指数快照和全市场分页兜底。
3. 重构 `market_breadth.py` 为 per-capability fallback orchestration。
4. 更新离线测试覆盖东财失败、腾讯成功、全源失败和 partial warnings。
5. 保持公开 API/CLI/MCP 不变，无迁移成本。

## Open Questions

- 腾讯 `getBoardRankList` 当前 spike 返回 HTTP 400，未来若要默认接入需另开 change 验证参数、字段与分页稳定性。
- 新浪分页 fallback 是否需要额外节流配置，还是复用现有 request timeout 即可？
- 是否要在未来单独提实验性 change 评估同花顺 `continuous_limit_pool` 作为连板官方来源？
