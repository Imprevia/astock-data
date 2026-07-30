## Purpose

`sector-fund-flow-history` provides recent daily main fund-flow history for industry sectors and a constrained current-date five-day aggregate fallback. It keeps push2his daily series as the authoritative source, exposes a separate five-day aggregate mapping, and prevents dateless current-window data from polluting historical reports.

## Requirements

### Requirement: 行业五日累计资金批量获取
系统 SHALL 通过东方财富板块资金接口，以 `key=f164` 和官方行业范围 `m:90+s:4` 批量获取行业代码、名称及五日主力净流入累计值，并保持金额单位为元。

#### Scenario: 正常解析行业五日累计值
- **WHEN** 上游返回包含 `f12`、`f14` 和数值型 `f164` 的行业记录
- **THEN** 系统返回对应的行业代码、名称和五日主力净流入累计值

#### Scenario: 上游记录缺失必要字段
- **WHEN** 上游记录缺少行业代码、名称或有效 `f164`
- **THEN** 系统跳过或将该值保留为空，且不得抛出未处理的字段访问异常

### Requirement: 五日累计降级适用范围
系统 MUST 仅在请求窗口为五日、目标日期等于本地当前日期且至少一个板块缺少有效逐日资金序列时使用 `f164`，每次服务调用最多发起一次批量请求。

#### Scenario: 当前日期五日历史缺失
- **WHEN** `days` 为 5、目标日期为本地当前日期且 push2his 未返回某板块的有效逐日资金记录
- **THEN** 系统至多请求一次 `f164` 批量数据，并按板块代码补充该板块的五日累计值

#### Scenario: push2his 已返回完整记录
- **WHEN** 所有请求板块均有有效 push2his 逐日资金记录
- **THEN** 系统不请求 `f164` 接口

#### Scenario: 请求窗口不是五日
- **WHEN** `days` 不等于 5
- **THEN** 系统不得请求或使用 `f164` 数据

### Requirement: 历史日期隔离
系统 MUST NOT 将无日期参数的当前 `f164` 滚动值用于非当前目标日期。

#### Scenario: 显式请求过去日期
- **WHEN** 目标日期早于本地当前日期
- **THEN** 系统不调用 `f164`，并继续使用支持目标日期的逐日数据源或日期隔离缓存

#### Scenario: 周末回看最近交易日
- **WHEN** 本地当前日期与请求的最近交易日不同
- **THEN** 系统不调用 `f164`，即使接口当前窗口可能对应该交易日

### Requirement: 完整序列与部分累计结果分离
系统 SHALL 在 `history_by_code` 中保留真实上游逐日记录，并通过独立的 `five_day_main_net_inflow_by_code` 映射表达五日累计主力净流入；系统 MUST NOT 为累计值伪造逐日记录。

#### Scenario: push2his 逐日序列成功
- **WHEN** 某板块返回五日有效逐日 `main_net_inflow` 记录
- **THEN** `history_by_code` 保留这些记录，且五日累计映射包含其真实求和值

#### Scenario: 仅 f164 累计值可用
- **WHEN** 某板块没有有效逐日记录但 `f164` 返回累计值
- **THEN** 该板块的逐日序列保持空，五日累计映射包含 `f164` 值，并产生“无逐日序列”的来源警告

#### Scenario: 同花顺仅返回行情字段
- **WHEN** 同花顺降级记录只包含日期、收盘价、成交额或涨跌幅
- **THEN** 系统不得由这些字段生成 `main_net_inflow`、五日资金累计值或零值逐日记录

### Requirement: 公共门面契约一致
Python API、CLI 和 MCP SHALL 通过同一个结果模型暴露逐日序列、五日累计映射和降级警告，新增字段默认可为空且不得破坏现有 `history_by_code` 消费者。

#### Scenario: CLI 序列化部分结果
- **WHEN** 当前五日窗口仅获得某板块的 `f164` 累计值
- **THEN** CLI JSON 同时输出空的该板块逐日序列、真实的五日累计值和明确警告

#### Scenario: 旧消费者只读取逐日字段
- **WHEN** 消费者忽略新增五日累计映射
- **THEN** 原有 `history_by_code` 字段名称和逐日记录结构保持不变

### Requirement: 五日累计缓存隔离
系统 SHALL 缓存成功的 `f164` 批量载荷以减少同日重复请求，并 MUST 按目标日期隔离该缓存，不得跨日期回退后冒充当前滚动窗口。

#### Scenario: 同日重复请求
- **WHEN** 同一当前日期和五日窗口重复请求行业累计资金
- **THEN** 系统可以复用该日期的有效批量缓存

#### Scenario: 当前日期缓存不存在
- **WHEN** 仅存在其他日期的 `f164` 缓存
- **THEN** 系统不得把其他日期缓存作为当前五日累计结果返回
