# Harness Retrofit

## Stage

Complete

## Status

Oracle follow-up remediation and final local verification are complete. The plan remains active until the maintainer stages or commits the delivered files.

## Acceptance

- Repository facts are routed through concise docs without replacing the existing README or CHANGELOG.
- The stdlib-only docs contract selects staged, full, and explicit push change sets and enforces actionable documentation and plan gates.
- Cross-platform hook installation sets `core.hooksPath` to `.githooks`; thin pre-commit, commit-msg, and pre-push hooks invoke the correct lifecycle phase.
- Contract tests cover required docs, non-empty plan fields, streaming counts, ref ranges, gates, escape hatches, hooks, and installation.
- Missing remote objects produce a typed actionable failure, and push/full commit markers apply only to their owning commit while structural checks remain range-wide.
- Existing and new tests pass; every changed Python file has no more than 250 pure lines, and unavailable diagnostics are reported without overstatement.

## Completion Evidence

- Red phase: the first dedicated run failed 10 tests because required docs, scripts, and hooks did not exist.
- Contract suite: `python -m pytest tests/test_docs_contract.py tests/test_hooks_contract.py -q` passed 10 tests in 5.32 seconds.
- Full suite: `python -m pytest -q` passed 477 tests with 7 skips in 117.74 seconds.
- Full contract: `python scripts/check_docs_contract.py --mode full` passed; the configured upstream selected 0 committed paths while required paths, plan fields, and links were still validated.
- Hook installation: `python scripts/install_hooks.py` succeeded and `git config --get core.hooksPath` returned `.githooks`.
- Pure LOC: checker 192, installer 40, docs-contract tests 123, hook tests 37.
- Oracle remediation red phase: 9 of 19 focused tests failed for the four reviewed lifecycle and robustness defects.
- Oracle remediation focused green phase: 19 tests passed in 11.65 seconds after splitting Git selection and streaming count logic into `docs_contract_core.py`.
- Final focused suite: 19 tests passed in 10.04 seconds, including actual pre-commit, commit-msg, multi-ref pre-push, non-current ref, new-branch, and deletion-ref scenarios.
- Final regression suite: 486 tests passed with 7 skips in 115.38 seconds.
- Hook smoke: pre-commit fast, commit-msg staged, and a deletion-only pre-push invocation all exited successfully.
- Final full contract passed required paths, non-empty fields, relative links, and its configured-upstream selection; that range contained 0 committed paths.
- Installer completed and `git config --get core.hooksPath` returned `.githooks`.
- Final pure LOC: checker 190, core 116, installer 40, docs tests 146, review tests 78, hook tests 91.
- Oracle follow-up red phase reproduced unsupported remote-ref input, unknown remote object failure, and marker scope leakage; a dedicated full-selection assertion confirmed commit gates were not preserved.
- Oracle follow-up red evidence: the first focused run had 4 failures and 18 passes; the dedicated full-selection structure test also failed because `Selection` had no commit gates.
- Oracle follow-up focused suite: 22 tests passed in 15.46 seconds, including missing-object error shape and push/full marker isolation.
- Oracle follow-up regression suite: 489 tests passed with 7 skips in 118.71 seconds.
- Fast and full docs-contract modes passed with 0 selected paths in the current unstaged/configured-upstream contexts.
- Installer succeeded and `git config --get core.hooksPath` returned `.githooks`.
- Final pure LOC: checker 204, core 142, installer 40, docs tests 146, review tests 126, hook tests 91.
- Forbidden-pattern scan found no `Any`, `object` annotations, casts, type ignores, or broad exceptions in the six changed Python files; `rg` was unavailable, so the dedicated content scanner was used.

## Remaining Gaps

- The repository has no CI configuration; local hooks remain the enforcement boundary.
- `basedpyright` is not installed and prior installation permission was declined, so six requested LSP checks reported tool unavailability instead of clean diagnostics.
- The harness files are uncommitted. The pre-existing untracked `astock_data.zip` remains untouched and must stay excluded from any harness commit.

## Next Step

Stage the intended harness files without `astock_data.zip`; commit-msg will enforce the staged commit, and pre-push will enforce each pushed commit without sharing markers.
