#!/usr/bin/env python3
"""Build the two promoted kext bundles from an original NVMeGeneric 1.1 bundle."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path


INPUT_HASHES = {
    "Contents/MacOS/NVMeGeneric": "c6b79e62a09e6d0775d6ea36ce588a093be9d7b2feb53acde82ab4ac0410fd03",
    "Contents/Info.plist": "c4ea9e5c494a87a5819a235a661c03089d83374bd924842328c252717bb50d40",
    "Contents/Resources/en.lproj/InfoPlist.strings": "39cf2ee07b7b333e7c179d0bf4d798a5b72af6a4e584f51e642703bbfa4fc828",
}
OUTPUT_HASHES = {
    "mavericks-executable": "79353a360728266fecef8b7da8a0f087da541271b3d1c5b386631cfdba507358",
    "mavericks-plist": "b993a55a7af6cbdc42d0b1769f28f1d3495144fc507ebea28a858c6a9f585e68",
    "snow-executable": "dc2fcda7d17ed2f0429713fe13045277571ee006030c5c9a34b3f6ec0de7e0d3",
    "snow-plist": "8f452d3ccb20fce37882239b2c0653f3b6d5667e1467c75158b0ab9c0707f64c",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_hash(path: Path, expected: str) -> None:
    if not path.is_file():
        raise SystemExit(f"missing required input: {path}")
    actual = sha256(path)
    if actual != expected:
        raise SystemExit(f"unexpected SHA-256 for {path}: {actual}")


def replace_once(data: bytes, old: bytes, new: bytes, label: str) -> bytes:
    if data.count(old) != 1:
        raise SystemExit(f"expected one {label} marker, found {data.count(old)}")
    return data.replace(old, new)


def build_bundle(source: Path, output: Path, target: str) -> None:
    contents = output / "Contents"
    executable = contents / "MacOS/NVMeGeneric"
    executable.parent.mkdir(parents=True)

    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("patch_binary.py")),
            "--target",
            target,
            str(source / "Contents/MacOS/NVMeGeneric"),
            str(executable),
        ],
        check=True,
    )

    plist = (source / "Contents/Info.plist").read_bytes()
    if target == "mavericks":
        marker = b"\t<key>OSBundleLibraries</key>\n"
        plist = replace_once(
            plist,
            marker,
            b"\t<key>OSBundleRequired</key>\n\t<string>Root</string>\n" + marker,
            "OSBundleLibraries",
        )
        resources = source / "Contents/Resources"
        shutil.copytree(resources, contents / "Resources")
        expected_plist = OUTPUT_HASHES["mavericks-plist"]
        expected_executable = OUTPUT_HASHES["mavericks-executable"]
    else:
        plist = replace_once(
            plist,
            b"\t<key>CFBundleName</key>\n\t<string>NVMeGeneric</string>\n",
            b"\t<key>CFBundleName</key>\n\t<string>NVMeGeneric-Snow</string>\n",
            "CFBundleName",
        )
        marker = b"\t</dict>\n</dict>\n</plist>\n"
        plist = replace_once(
            plist,
            marker,
            b"\t</dict>\n\t<key>OSBundleRequired</key>\n\t<string>Root</string>\n</dict>\n</plist>\n",
            "final OSBundleLibraries closing tag",
        )
        expected_plist = OUTPUT_HASHES["snow-plist"]
        expected_executable = OUTPUT_HASHES["snow-executable"]

    info = contents / "Info.plist"
    info.write_bytes(plist)
    executable.chmod(0o755)
    info.chmod(0o644)
    for resource in (contents / "Resources").rglob("*") if (contents / "Resources").exists() else ():
        resource.chmod(0o755 if resource.is_dir() else 0o644)

    require_hash(executable, expected_executable)
    require_hash(info, expected_plist)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="original NVMeGeneric.kext")
    parser.add_argument("output", type=Path, help="new, empty output directory")
    args = parser.parse_args()

    source = args.input.resolve()
    output = args.output.resolve()
    for relative, expected in INPUT_HASHES.items():
        require_hash(source / relative, expected)
    if output.exists():
        raise SystemExit(f"refusing existing output: {output}")
    output.mkdir(parents=True)

    build_bundle(source, output / "NVMeGeneric-Mavericks.kext", "mavericks")
    build_bundle(source, output / "NVMeGeneric-Snow.kext", "snow")
    print(f"built={output}")


if __name__ == "__main__":
    main()
