from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Final

HOOK_NAMES: Final = ("pre-commit", "commit-msg", "pre-push")


def main() -> int:
    repo = Path.cwd()
    missing = [name for name in HOOK_NAMES if not (repo / ".githooks" / name).is_file()]
    if not (repo / ".git").is_dir():
        print("hook installer: current directory is not a Git repository", file=sys.stderr)
        return 1
    if missing:
        print(f"hook installer: missing hooks: {', '.join(missing)}", file=sys.stderr)
        return 1

    configured = subprocess.run(
        ("git", "config", "core.hooksPath", ".githooks"),
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if configured.returncode != 0:
        print(configured.stderr.strip(), file=sys.stderr)
        return configured.returncode

    if os.name != "nt":
        for name in HOOK_NAMES:
            hook = repo / ".githooks" / name
            try:
                hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
            except OSError as error:
                print(f"hook installer: chmod failed for {hook}: {error}", file=sys.stderr)
                return 1
    print("hook installer: core.hooksPath=.githooks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
