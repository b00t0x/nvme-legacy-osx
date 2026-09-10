#!/usr/bin/env python3
"""Build dated packages and the combined kext zip for a GitHub release."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def validate_release(value: str) -> None:
    if len(value) != 8 or not value.isdigit():
        raise SystemExit("--release must be a valid date in YYYYMMDD form")
    try:
        datetime.datetime.strptime(value, "%Y%m%d")
    except ValueError as error:
        raise SystemExit("--release must be a valid date in YYYYMMDD form") from error


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_tree_inventory(root: Path) -> None:
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            entries.append(f"{sha256(path)}  {path.relative_to(root)}")
    (root / "SHA256SUMS").write_text("\n".join(entries) + "\n")


def write_zip(root: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in [root, *sorted(root.rglob("*"))]:
            name = str(path.relative_to(root.parent))
            if path.is_dir():
                name += "/"
            archive.write(path, name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True, help="original NVMeGeneric.kext")
    parser.add_argument("--release", required=True, help="release date in YYYYMMDD form")
    parser.add_argument("--output", type=Path, required=True, help="new output directory")
    args = parser.parse_args()
    validate_release(args.release)

    root = Path(__file__).resolve().parent.parent
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing existing output: {output}")
    output.mkdir(parents=True)

    with tempfile.TemporaryDirectory(prefix="nvmegeneric-release-") as temporary:
        work = Path(temporary)
        kexts = work / "kexts"
        packages = work / "packages"
        subprocess.run(
            [sys.executable, str(root / "tools/build_kexts.py"), str(args.input), str(kexts)],
            check=True,
        )
        subprocess.run(
            [
                sys.executable,
                str(root / "tools/build_packages.py"),
                "--snow-kext", str(kexts / "NVMeGeneric-Snow.kext"),
                "--mavericks-kext", str(kexts / "NVMeGeneric-Mavericks.kext"),
                "--release", args.release,
                "--output", str(packages),
            ],
            check=True,
        )
        for package in packages.iterdir():
            shutil.copy2(package, output / package.name)

        archive_root = work / f"NVMeGeneric-Kexts-{args.release}"
        archive_root.mkdir()
        shutil.copytree(kexts / "NVMeGeneric-Snow.kext", archive_root / "NVMeGeneric-Snow.kext")
        shutil.copytree(
            kexts / "NVMeGeneric-Mavericks.kext",
            archive_root / "NVMeGeneric-Mavericks.kext",
        )
        write_tree_inventory(archive_root)
        write_zip(archive_root, output / f"NVMeGeneric-Kexts-{args.release}.zip")

    subprocess.run(
        [sys.executable, str(root / "tools/verify_release.py"), str(output), "--release", args.release],
        check=True,
    )
    print(f"release={output}")


if __name__ == "__main__":
    main()
