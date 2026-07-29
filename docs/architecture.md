# Architecture

## System Boundary

`astock-data` 是 pure data layer。它对外提供同一组 25 个 Python API、25 个 CLI 子命令和 25 个 MCP stdio tools；完整名称与映射只在 [README](../README.md) 维护。`daily-review` 是下游消费者，只能经 `python -m astock_data.cli` 接收 JSON，依赖方向不可反转。

## Data Flow

```text
caller -> API / CLI / MCP adapter -> service -> resolver -> data-source client
                                         |              |
                                         +-> cache <----+
```

- API、CLI、MCP 仅做协议适配并共享服务契约，不加入报告或决策逻辑。
- resolver 是 ticker 输入规范化和市场归属的唯一公共入口；服务不得复制解析规则。
- clients 拥有外部数据源协议、超时、限流与降级；东方财富请求保持统一 chokepoint。
- cache 只持久化结构化事实并遵守路径安全；`--no-cache` 使用临时目录，不污染真实缓存。
- services 编排数据源与降级，models 定义结构化返回；缺失数据必须保留来源、warning 或类型化错误。

## Invariants

- 25 API / CLI / MCP 三个入口面保持一一对应，契约表内容不得在架构文档复制或分叉。
- 数据包不包含复盘、交易执行、组合管理、收益承诺或应用界面。
- 当前仓库没有 CI；执行约束由本地 docs-contract、Git hooks 和 pytest 提供。
