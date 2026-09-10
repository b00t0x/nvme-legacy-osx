#!/usr/bin/env python3
"""Run repository checks that do not require the third-party input binary."""

from __future__ import annotations

import py_compile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    for path in sorted((ROOT / "tools").glob("*.py")):
        py_compile.compile(str(path), doraise=True)

    pairs = [
        ("README.md", "README_ja.md"),
        ("THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES_ja.md"),
        ("docs/BUILD.md", "docs/BUILD_ja.md"),
        ("docs/CHANGES_MAVERICKS.md", "docs/CHANGES_MAVERICKS_ja.md"),
        ("docs/CHANGES_SNOW.md", "docs/CHANGES_SNOW_ja.md"),
    ]
    for english, japanese in pairs:
        if not (ROOT / english).is_file() or not (ROOT / japanese).is_file():
            raise SystemExit(f"missing documentation pair: {english}, {japanese}")

    forbidden = {".kext", ".pkg", ".zip"}
    tracked = subprocess_output(["git", "ls-files"])
    offenders = [name for name in tracked if any(part.endswith(tuple(forbidden)) for part in Path(name).parts)]
    if offenders:
        raise SystemExit(f"generated or third-party artifacts are tracked: {offenders}")
    print("repository checks passed")


def subprocess_output(command: list[str]) -> list[str]:
    import subprocess
    return subprocess.run(command, cwd=ROOT, check=True, text=True, capture_output=True).stdout.splitlines()


if __name__ == "__main__":
    main()
