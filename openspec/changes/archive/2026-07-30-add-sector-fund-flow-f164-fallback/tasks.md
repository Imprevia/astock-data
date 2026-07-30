## 1. 执行计划与失败测试

- [x] 1.1 在 `docs/exec-plans/active/` 创建本变更执行计划，填写 Stage、Status、Acceptance、Completion Evidence、Remaining Gaps 和 Next Step，并加入活动计划索引
- [x] 1.2 为东方财富 `getbkzj` 正常载荷、缺失字段和空载荷增加客户端失败测试，锁定 `f164` 元单位解析及 `m:90+s:4` 请求参数
- [x] 1.3 为服务编排增加失败测试，覆盖当前日期五日窗口触发一次批量降级、完整 push2his 不触发、非五日窗口不触发和过去日期不触发
- [x] 1.4 为结果模型和公共 JSON 增加失败测试，锁定逐日序列与 `five_day_main_net_inflow_by_code` 的分离、默认空映射和向后兼容

## 2. 客户端与结果模型

- [x] 2.1 在 `astock_data/clients/eastmoney.py` 增加 `getbkzj` URL 常量和行业五日累计批量解析函数，确保所有东方财富请求仍经过统一客户端、限流与重试入口
- [x] 2.2 在行业资金历史结果模型中增加 `five_day_main_net_inflow_by_code` 默认空映射，并保持 `history_by_code` 现有字段及记录结构不变
- [x] 2.3 运行客户端和模型定向测试，确认有效零值被保留、无效或缺失值不被伪造为零

## 3. 服务编排与缓存

- [x] 3.1 在 `get_sector_fund_flow_history` 中保留 push2his 逐日序列，并在 `days == 5`、目标日期为当前日期且存在缺失板块时惰性加载一次共享 `f164` 批量结果
- [x] 3.2 对有效 push2his 五日序列写入真实求和累计，对仅 `f164` 命中的板块只写累计映射并保持逐日序列为空
- [x] 3.3 收紧同花顺降级语义，禁止由 `amount`、`close`、`pct_change` 或缺失字段生成主力净流入、五日累计或零值记录
- [x] 3.4 增加按目标日期隔离且不跨日期回退的 `f164` 结构化缓存，并验证一次服务调用最多请求一次批量接口
- [x] 3.5 为仅累计、同花顺行情、缓存命中和所有资金来源缺失生成明确且不重复刷屏的 warnings

## 4. 公共门面与事实文档

- [x] 4.1 更新 Python API、CLI 与 MCP 的契约测试和序列化路径，确保三个门面输出同一模型中的逐日序列、五日累计映射和 warnings
- [x] 4.2 更新 README、架构/运行文档、CHANGELOG 和 `docs/status.md`，准确描述 push2his 逐日能力、`f164` 当前五日累计限制、同花顺行情边界及缓存策略
- [x] 4.3 回写活动执行计划的完成证据、剩余缺口和下一步，确保文档事实与实现一致

## 5. 验证

- [x] 5.1 运行行业资金客户端、服务、公共 API、CLI 和 MCP 定向测试并修复本变更引入的问题
- [x] 5.2 运行 `python -m pytest -q` 完整测试套件
- [x] 5.3 运行 `python scripts/check_docs_contract.py --mode full` 并确认文档门禁通过
- [x] 5.4 在显式开启 live 测试的环境中执行当前日期五日行业资金 smoke，确认 `f164` 仅作为部分累计降级且不污染历史日期
