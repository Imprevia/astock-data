# Lessons Learned

- 入口面数量和映射由 README 契约表与测试共同约束；在多份文档复制清单会产生漂移。
- `daily-review` 的数据需求应先扩展 CLI 结构化契约，再由下游适配，不能跨过包边界复制 client 请求。
- 数据源封禁和临时限流属于可预期故障；降级链、缓存来源和 warning 必须可见，不能伪造完整结果。
- Windows 是默认支持平台；门禁逻辑放 Python 脚本，hooks 只做转发。
- 当前没有 CI，未安装本地 hooks 的工作区不会自动执行 docs-contract；安装状态必须进入验收证据。
