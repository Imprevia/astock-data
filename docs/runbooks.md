# Runbooks

## Setup

```powershell
python -m pip install -e ".[test]"
python scripts/install_hooks.py
git config --get core.hooksPath
```

最后一条应输出 `.githooks`。安装器可重复运行；非 Windows 平台会尝试为三个 hook 增加用户执行位。

## Validation

```powershell
python -m pytest -q
python -m pytest tests/test_docs_contract.py tests/test_docs_contract_review.py tests/test_hooks_contract.py -q
python scripts/check_docs_contract.py --mode fast
python scripts/check_docs_contract.py --mode full
```

行业五日资金变更的离线定向验证：

```powershell
python -m pytest tests/test_sector_f164_client.py tests/test_sector_f164_service.py tests/test_sector_f164_cache_warnings.py tests/test_sector_f164_contract.py -q
```

显式允许真实网络后，可对本地当天执行短窗口 smoke；`--no-cache` 避免污染日常缓存：

```powershell
$env:ASTOCK_LIVE_TESTS=1
$today = (Get-Date).ToString("yyyy-MM-dd")
python -m astock_data.cli sector-fund-flow-history BK1036 --curr-date $today --days 5 --format json --no-cache
```

输出中的 `history_by_code` 只表示逐日记录；`five_day_main_net_inflow_by_code` 可包含 push2his 求和或 f164-only 累计。外部网络或上游风控阻断时，记录 stderr、warning 和退出状态，不把 smoke 标为通过。

周末复盘最新交易日时，可用 Python API 的 `aggregate_only=True` 跳过逐板块历史请求。只有新浪上证指数最新K线日期与 `curr_date` 完全一致时才返回 f164 累计；日期不匹配或不可校验应保持空值和 warning。普通模式优先读取同日真实资金缓存，再降级到仅含行情字段的 THS 日K。

历史全局快讯 smoke：

```powershell
python -m astock_data.cli global-news --curr-date 2026-07-31 --look-back-days 1 --limit 15 --format json --no-cache
```

所有返回项的 `time` 必须落在 2026-07-31；若供应商档案未覆盖目标日，应返回空 `items` 和 warning，不能返回当前实时新闻。

腾讯五档盘口默认只取一张快照，不主动等待。需要动态可见深度证据时可显式请求有限采样：

```powershell
python -m astock_data.cli order-book 600809 --samples 3 --interval-seconds 1 --format json
```

`samples` 和 `interval-seconds` 均为 1-60，且 `(samples - 1) * interval-seconds` 不得超过 300 秒。档位对象使用 `position`、`price`、`volume_lots`；`exact_cancellation_available` 固定为 `false`。深度减少只标记为 `unattributed`，`left-view` 不得解释为精确撤单。全部样本无效会返回类型化数据源错误，部分成功则保留有效快照和 warning。

代表性行业 ETF 扩展的离线与真实行情验证：

```powershell
python -m pytest tests/test_public_api.py -q
python -m astock_data.cli etf-daily 515230 512720 512980 515880 562500 515260 518880 159869 516020 159825 --days 5 --format json
```

所有白名单代码应返回对应沪深市场前缀的行情；下游只能把近日涨跌幅作为行业活跃度代理，不得改称 ETF 份额净流入。

## Hook Lifecycle

- `pre-commit` 调用 `--mode fast`，只检查必需路径、active plan 非空字段和 docs 相对链接，不读取尚未产生的新提交消息。
- `commit-msg` 调用 `--mode staged --message-file "$1"`，以 Git 提供的真实消息文件对 staged 变更执行 Gate 1 和计划门禁；提交标记在此时生效。
- `pre-push` 读取 stdin 的每条 local/remote ref 与 OID。普通更新先确认 remote OID 存在，再逐提交检查 `remote_oid..local_oid`；新分支检查 local OID 中目标 remote 尚未拥有的提交；删除 ref 跳过；多 ref 逐条执行。
- `full` 用于本地验收：有 upstream 时逐提交检查 `upstream..HEAD`，无 upstream 时把相对 `HEAD` 的 working tree 与未跟踪文件作为一个未提交 gate。未跟踪文件分块计数，达到非小改阈值即停止；读取失败按非小改处理。
- 必需路径、active plan 非空字段和 docs 相对链接是范围级结构检查。Gate 1、计划变更和提交标记按 commit gate 独立计算；一个提交的 marker 不豁免同一 push/full 范围内的其他提交。

## Gate Recovery

- 缺少文档或 active plan 字段：按错误中给出的路径补齐事实源。
- 代码变更无文档：更新 `docs/`、`README.md` 或 `AGENTS.md` 中对应事实。
- 非小改无 active plan 变更：更新 `docs/exec-plans/active/*.md` 的状态、证据和下一步。
- `[push-missing-remote-object]`：按错误中的 remote/ref 执行 `git fetch <remote> <ref>`，再重试 push；不要改用当前分支或跳过该 ref。
- 紧急逃生口及提交标记定义以根 [AGENTS](../AGENTS.md) 为准。提交标记只在 `commit-msg` 及已提交的 push/full 范围可见，使用后必须留下原因。
- 外部数据源 smoke 失败时，先区分网络、上游协议变化与代码回归；默认离线套件不依赖网络。
