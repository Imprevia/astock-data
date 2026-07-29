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
