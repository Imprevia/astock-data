## Why

现有 18 个公开入口全部是「个股导向」——每个 `get_*` 都要 `symbol` 并经过 `resolve_ticker` 收敛。但盘后复盘（如 `daily-review` skill 的「看大局」环节）需要的**指数、涨跌停家数、连板梯队**是「市场层面」数据，不带个股 symbol，当前没有任何入口能一次拿全。复盘者不得不手动从多个行情软件拼凑这三个数字，效率低且易错。

本变更新增一个「市场广度」能力域，落地成单一聚合入口 `get_market_breadth()`，一次返回指数快照、涨跌停家数与连板梯队，专供盘后复盘等低频场景消费。

## What Changes

- 新增第 19 个公开 Python 函数 `get_market_breadth(date: str = "")`，返回结构化 `MarketBreadthResult`（Pydantic 模型，遵循现有契约）。
- 新增对应 CLI 子命令 `market-breadth` 与 MCP tool `get_market_breadth`，使 Python / CLI / MCP 三层门面同步对齐（18 → 19）。
- 新增 `EastmoneyClient` 的指数快照与全市场行情拉取能力（`clist` 翻页 + 涨跌幅本地分类）。
- 新增市场广度模型：`MarketBreadthResult` / `IndexSnapshot` / `LimitStats` / `BoardItem`。
- 指数以**预定义枚举**形式提供（secid 写死），用户不传代码，**完全绕开 `resolve_ticker` 个股安全边界**。
- 连板梯队采用**无状态现算**：从 K 线回溯计算连板数，依赖现有 `CsvKlineCache` 热路径，**不引入任何持久化状态**。
- 更新 `astock_data/api.py`、`services/__init__.py`、`cli.py`、`mcp/server.py`、`__all__` 导出列表、README 公开函数计数（18 → 19）。
- 更新 `tests/test_public_api.py` 的「18 个公开入口」契约断言为 19。

**不改 / 不破坏：**
- 不修改现有 18 个入口的签名、返回类型或行为。
- 不引入 `resolve_ticker` 的任何变动（指数枚举根本不经过它）。
- 不引入新依赖（连板自算复用已有 `pandas` + 现有 `get_stock_data` 的 K 线管道）。
- 不破坏 `ResultBase` 的 `source` / `retrieved_at` / `raw` / `warnings` 语义（`source` 字段的微调见 design.md 的结构化取舍）。

## Capabilities

### New Capabilities
- `market-breadth`: 市场广度数据能力域。聚合「大盘指数快照 + 涨跌停家数统计 + 连板梯队清单」三类市场层面数据，通过单一公开入口 `get_market_breadth()` 提供，服务于盘后复盘等低频、一次拿全的场景。

### Modified Capabilities
<!-- 无现有 capability 的 spec 级行为变更。现有 18 个入口的签名与返回契约保持不变。 -->

## Impact

- **公开 API**：`astock_data/api.py` 新增 `get_market_breadth`，`__all__` 从 18 扩到 19。
- **服务层**：新增 `astock_data/services/market_breadth.py`（或并入 `market_data.py`，见 design.md），承载指数快照、clist 分类、连板现算三段编排。
- **客户端层**：`astock_data/clients/eastmoney.py` 新增指数快照方法与 `clist` 翻页辅助方法；所有 `eastmoney.com` 新 URL 仍只允许出现在该文件（chokepoint 不变）。
- **模型层**：`astock_data/models/market.py`（或新建 `breadth.py`）新增 4 个模型。
- **CLI**：`astock_data/cli.py` 新增 `market-breadth` 子命令。
- **MCP**：`astock_data/mcp/server.py` 新增 `get_market_breadth` tool。
- **文档**：README 公开函数计数、CLI/MCP 工具表、数据源表同步更新。
- **测试**：新增 `tests/test_market_breadth_service.py`（离线 mock）；更新 `tests/test_public_api.py` 的入口计数与 `__all__` 断言。
- **AGENTS.md**：根目录与 `astock_data/`、`services/`、`clients/`、`models/` 各层 AGENTS.md 中「18 个公开入口 / 17 个 get_* / 18 个 CLI / 18 个 MCP」的计数表述需同步评估更新（见 tasks.md）。
- **依赖**：无新增第三方依赖。
- **安全边界**：不触碰 `resolve_ticker`；指数 secid 枚举免校验，无新增 ticker 流入面。
