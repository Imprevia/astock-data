# Architecture

## System Boundary

`astock-data` 是 pure data layer。它对外提供同一组 26 个 Python API、26 个 CLI 子命令和 26 个 MCP stdio tools；完整名称与映射只在 [README](../README.md) 维护。`daily-review` 是下游消费者，只能经 `python -m astock_data.cli` 接收 JSON，依赖方向不可反转。

## Data Flow

```text
caller -> API / CLI / MCP adapter -> service -> resolver -> data-source client
                                         |              |
                                         +-> cache <----+
```

- API、CLI、MCP 仅做协议适配并共享服务契约，不加入报告或决策逻辑。
- resolver 是 ticker 输入规范化和市场归属的唯一公共入口；服务不得复制解析规则。
- clients 拥有外部数据源协议、超时、限流与降级；东方财富请求保持统一 chokepoint。
- 全局快讯历史查询必须沿供应商返回的 `sortEnd` 游标向前分页，并在 service 层按请求窗口严格过滤；实时行不得缓存为其他历史日期。
- cache 只持久化结构化事实并遵守路径安全；`--no-cache` 使用临时目录，不污染真实缓存。
- services 编排数据源与降级，models 定义结构化返回；缺失数据必须保留来源、warning 或类型化错误。
- `KlineBar` 的 `change_pct` 与 `turnover_pct` 是可空增量字段。个股成交额的腾讯回退只保留供应商时间戳对应日期的 OHLCV、成交额、涨跌幅和换手率；下游必须按目标日期精确匹配，不能把当前报价回填历史日期。
- 个股分钟资金流与日线资金流是两个独立能力；任一请求失败只清空对应集合并记录 warning，不得中止另一个成功结果或整个 CLI。历史分析不得使用只有时分、无法验证交易日期的当前分钟序列或其 signal，只能使用与目标日精确匹配的日线记录。
- 市场广度默认路径保留全市场分页与日期校验成交额；`fast=True` 先尝试单次东财 clist，失败后只请求新浪按涨跌幅排序的有界极值页，并显式把 `raw.market_amount` 保持为不可用。所有请求日期（包括本地当天）的快照都必须经新浪指数 K 线精确验证目标交易日，无法验证或日期不匹配时整体 `unavailable`。东财 clist 只有在有效总数与返回行数完全一致时才能证明快照完整；新浪市场行缺少代码或有效涨跌幅时必须降级，不能规范化为零。涨跌停统计按两侧完整性返回 `available`、`partial` 或 `unavailable`，缺失侧使用 `null`，Markdown/Text 也必须显式显示两级状态和不可用方向。腾讯指数与新浪行情的首选组合是正常复合来源，不标记为 fallback。
- 龙虎榜事件查询成功但目标日没有事件时，不请求席位端点；目标日存在已公布事件时，买入和卖出席位端点独立降级并记录 warning，不能让席位故障覆盖已确认的 `published` 或 `not-listed` 事实。
- 个股概念成员只从东财 HSF10 core-conception 的有序 `ssbk` 读取：rank 1-3 为行业，rank 4 为地域，其余为概念或风格；只有显式 `ssbk=[]` 是成功空集合，缺键、非列表或非法 `BOARD_RANK` 必须抛出 `DataSourceError`。
- 腾讯五档盘口只表达当前可见买卖深度，档位字段统一为 `position`，结果固定声明 `exact_cancellation_available=false`。多次采样按同侧同价比较；同价减少标记 `depth-decrease` 且归因为 `unattributed`，价格离开五档只标记 `left-view`。采样总计划等待最多 300 秒，默认单快照不等待；全部样本无效时抛出带腾讯来源上下文的类型化错误，部分成功保留快照和 warning。截断 quote 行不进入盘口模型。
- 行业资金逐日序列只由 push2his 或其日序列缓存提供；无日期参数的 `getbkzj` f164 只在新浪指数证明目标日为最新交易日时表达五日累计，独立于逐日记录。
- 行业 ETF 白名单只控制可获取的代表性 ETF K 线；下游细分行业别名映射属于复盘层，ETF 价格变化不得表述为精确份额流入。

## Invariants

- 26 API / CLI / MCP 三个入口面保持一一对应，契约表内容不得在架构文档复制或分叉。
- 数据包不包含复盘、交易执行、组合管理、收益承诺或应用界面。
- 当前仓库没有 CI；执行约束由本地 docs-contract、Git hooks 和 pytest 提供。
- f164 仅在五日窗口且新浪上证指数最新K线日期精确匹配目标日时批量获取，按板块代码精确匹配；`aggregate_only` 路径跳过逐板块请求，适合复盘先恢复全量累计。普通路径保持八工作线程并发，回退顺序为 push2his、同日真实资金缓存、THS 行情。THS 行情字段不得升级为资金事实，f164 也不得生成逐日记录或正流入天数。
- ETF 代码必须进入明确白名单后才能请求新浪或东财；新增代表性代码需有真实 K 线 smoke 和离线前缀测试，未知代码继续拒绝。
