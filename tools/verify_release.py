#!/usr/bin/env python3
"""Verify the identity and basic structure of a generated release directory."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import tempfile
import zipfile
from pathlib import Path


EXECUTABLE_HASHES = {
    "NVMeGeneric-Mavericks.kext/Contents/MacOS/NVMeGeneric":
        "79353a360728266fecef8b7da8a0f087da541271b3d1c5b386631cfdba507358",
    "NVMeGeneric-Snow.kext/Contents/MacOS/NVMeGeneric":
        "dc2fcda7d17ed2f0429713fe13045277571ee006030c5c9a34b3f6ec0de7e0d3",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_package(
    path: Path,
    release: str,
    minimum: str,
    before: str,
    bundle_name: str,
    executable_hash: str,
) -> None:
    with tempfile.TemporaryDirectory(prefix="nvmegeneric-verify-pkg-") as temporary:
        expanded = Path(temporary)
        subprocess.run(["/usr/bin/xar", "-xf", str(path)], cwd=expanded, check=True)
        distribution = (expanded / "Distribution").read_text()
        for marker in (
            f'version="{release}"',
            f'<os-version min="{minimum}" before="{before}"/>',
            'rootVolumeOnly="false"',
            'enable_anywhere="true"',
            'onConclusion="RequireRestart"',
        ):
            if marker not in distribution:
                raise SystemExit(f"{path.name}: missing Distribution marker {marker}")
        components = [item for item in expanded.iterdir() if item.name.startswith("component-")]
        if len(components) != 1 or not (components[0] / "Payload").is_file():
            raise SystemExit(f"{path.name}: unexpected component layout")
        package_info = (components[0] / "PackageInfo").read_text()
        if f'version="{release}"' not in package_info or 'postinstall-action="restart"' not in package_info:
            raise SystemExit(f"{path.name}: unexpected PackageInfo metadata")

    with tempfile.TemporaryDirectory(prefix="nvmegeneric-verify-payload-") as temporary:
        expanded = Path(temporary) / "expanded"
        subprocess.run(["/usr/sbin/pkgutil", "--expand-full", str(path), str(expanded)], check=True)
        executables = list(expanded.glob(
            f"component-*/Payload/System/Library/Extensions/{bundle_name}/Contents/MacOS/NVMeGeneric"
        ))
        if len(executables) != 1 or sha256_bytes(executables[0].read_bytes()) != executable_hash:
            raise SystemExit(f"{path.name}: payload executable mismatch")
        scripts = list(expanded.glob("component-*/Scripts/postinstall"))
        if len(scripts) != 1 or 'target=${3:-/}' not in scripts[0].read_text():
            raise SystemExit(f"{path.name}: offline-target postinstall is missing")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--release", required=True)
    args = parser.parse_args()
    root = args.directory.resolve()
    names = {
        f"NVMeGeneric-Kexts-{args.release}.zip",
        f"NVMeGeneric-Snow-{args.release}.pkg",
        f"NVMeGeneric-Mavericks-{args.release}.pkg",
    }
    actual_names = {path.name for path in root.iterdir() if path.is_file()}
    if actual_names != names:
        raise SystemExit(f"unexpected release assets: {sorted(actual_names ^ names)}")

    archive = root / f"NVMeGeneric-Kexts-{args.release}.zip"
    prefix = f"NVMeGeneric-Kexts-{args.release}/"
    with zipfile.ZipFile(archive) as source:
        members = set(source.namelist())
        if any(name.startswith("__MACOSX/") or "/._" in name for name in members):
            raise SystemExit("zip contains unexpected AppleDouble metadata")
        for relative, expected in EXECUTABLE_HASHES.items():
            name = prefix + relative
            if name not in members or sha256_bytes(source.read(name)) != expected:
                raise SystemExit(f"zip executable mismatch: {relative}")
        if prefix + "SHA256SUMS" not in members:
            raise SystemExit("zip is missing SHA256SUMS")
        unexpected = {
            name for name in members
            if name != prefix + "SHA256SUMS"
            and not name.startswith(prefix + "NVMeGeneric-Snow.kext/")
            and not name.startswith(prefix + "NVMeGeneric-Mavericks.kext/")
            and name != prefix
        }
        if unexpected:
            raise SystemExit(f"zip contains unexpected files: {sorted(unexpected)}")

        inventory = source.read(prefix + "SHA256SUMS").decode().splitlines()
        seen = set()
        for line in inventory:
            expected, relative = line.split("  ", 1)
            name = prefix + relative
            if name not in members or sha256_bytes(source.read(name)) != expected:
                raise SystemExit(f"zip SHA-256 mismatch: {relative}")
            seen.add(name)
        archived_files = {name for name in members if not name.endswith("/")} - {
            prefix + "SHA256SUMS"
        }
        if seen != archived_files:
            raise SystemExit("zip SHA256SUMS does not cover exactly the archived kext files")

    verify_package(
        root / f"NVMeGeneric-Snow-{args.release}.pkg", args.release, "10.6", "10.9",
        "NVMeGeneric-Snow.kext", EXECUTABLE_HASHES["NVMeGeneric-Snow.kext/Contents/MacOS/NVMeGeneric"],
    )
    verify_package(
        root / f"NVMeGeneric-Mavericks-{args.release}.pkg", args.release, "10.9", "10.10",
        "NVMeGeneric-Mavericks.kext",
        EXECUTABLE_HASHES["NVMeGeneric-Mavericks.kext/Contents/MacOS/NVMeGeneric"],
    )
    print("release verification passed")


if __name__ == "__main__":
    main()
