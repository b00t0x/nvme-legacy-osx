#!/usr/bin/env python3
"""Build legacy-compressed /S/L/E installers for the promoted NVMeGeneric kexts."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import os
import pathlib
import plistlib
import shutil
import subprocess
import tempfile


SNOW_EXEC_SHA256 = "dc2fcda7d17ed2f0429713fe13045277571ee006030c5c9a34b3f6ec0de7e0d3"
MAVERICKS_EXEC_SHA256 = "79353a360728266fecef8b7da8a0f087da541271b3d1c5b386631cfdba507358"


def digest(path: pathlib.Path, algorithm: str) -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def write_executable(path: pathlib.Path, text: str) -> None:
    path.write_text(text)
    path.chmod(0o755)


def postinstall(bundle_name: str, expected_md5: str) -> str:
    return f"""#!/bin/sh
set -eu

target=${{3:-/}}
case "$target" in
    /) extensions='/System/Library/Extensions' ;;
    *) target=${{target%/}}; extensions="$target/System/Library/Extensions" ;;
esac
bundle="$extensions/{bundle_name}"
executable="$bundle/Contents/MacOS/NVMeGeneric"

if [ ! -f "$executable" ]; then
    echo "Installed NVMeGeneric executable is missing." >&2
    exit 1
fi
if [ "$(/sbin/md5 -q "$executable")" != "{expected_md5}" ]; then
    echo "Installed NVMeGeneric executable failed its identity check." >&2
    exit 1
fi

/usr/sbin/chown -R 0:0 "$bundle"
/usr/bin/find "$bundle" -type d -exec /bin/chmod 755 {{}} \\;
/usr/bin/find "$bundle" -type f -exec /bin/chmod 644 {{}} \\;
/bin/chmod 755 "$executable"
/usr/bin/touch "$extensions"

if ! /usr/sbin/kextcache -u "$target"; then
    echo "kextcache -u $target failed; do not boot that volume until the cache is repaired." >&2
    exit 1
fi

exit 0
"""




def component_plist(relative_bundle: str) -> list[dict[str, object]]:
    return [
        {
            "RootRelativeBundlePath": relative_bundle,
            "BundleIsRelocatable": False,
            "BundleIsVersionChecked": False,
            "BundleHasStrictIdentifier": True,
            "BundleOverwriteAction": "upgrade",
        }
    ]


def distribution(
    title: str,
    identifier: str,
    component_name: str,
    minimum_version: str,
    before_version: str,
    package_version: str,
) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
    <title>{title}</title>
    <options customize="never" rootVolumeOnly="false"/>
    <domains enable_anywhere="true" enable_currentUserHome="false" enable_localSystem="true"/>
    <volume-check script="true">
        <allowed-os-versions>
            <os-version min="{minimum_version}" before="{before_version}"/>
        </allowed-os-versions>
    </volume-check>
    <choices-outline>
        <line choice="default"/>
    </choices-outline>
    <choice id="default" visible="false" title="{title}" description="{title}">
        <pkg-ref id="{identifier}"/>
    </choice>
    <pkg-ref id="{identifier}" version="{package_version}" onConclusion="RequireRestart">{component_name}</pkg-ref>
</installer-gui-script>
"""


def require_restart(package: pathlib.Path) -> None:
    with tempfile.TemporaryDirectory(prefix="nvmegeneric-pkg-restart-") as temporary:
        expanded = pathlib.Path(temporary)
        subprocess.run(["/usr/bin/xar", "-xf", str(package)], cwd=expanded, check=True)
        package_info = expanded / "PackageInfo"
        text = package_info.read_text()
        marker = 'postinstall-action="none"'
        if text.count(marker) != 1:
            raise SystemExit(f"unexpected PackageInfo restart action in {package}")
        package_info.write_text(text.replace(marker, 'postinstall-action="restart"'))
        rebuilt = expanded / "rebuilt.pkg"
        subprocess.run(
            [
                "/usr/bin/xar", "-cf", str(rebuilt),
                "Bom", "Payload", "Scripts", "PackageInfo",
            ],
            cwd=expanded,
            check=True,
        )
        os.replace(rebuilt, package)


def make_legacy_product_archive(package: pathlib.Path) -> None:
    """Store the already-compressed payload archives raw for legacy PackageKit."""
    with tempfile.TemporaryDirectory(prefix="nvmegeneric-product-legacy-") as temporary:
        expanded = pathlib.Path(temporary)
        subprocess.run(["/usr/bin/xar", "-xf", str(package)], cwd=expanded, check=True)
        members = sorted(path.name for path in expanded.iterdir())
        rebuilt = expanded / "rebuilt.pkg"
        subprocess.run(
            [
                "/usr/bin/xar", "-cf", str(rebuilt),
                "--distribution",
                "--no-compress=Payload",
                "--no-compress=Scripts",
                *members,
            ],
            cwd=expanded,
            check=True,
        )
        os.replace(rebuilt, package)


def validate_kext(
    path: pathlib.Path,
    bundle_name: str,
    expected_sha256: str,
    expected_cf_bundle_name: str,
) -> None:
    info_path = path / "Contents/Info.plist"
    executable = path / "Contents/MacOS/NVMeGeneric"
    if not info_path.is_file() or not executable.is_file():
        raise SystemExit(f"invalid kext tree: {path}")
    with info_path.open("rb") as source:
        info = plistlib.load(source)
    expected = {
        "CFBundleName": expected_cf_bundle_name,
        "CFBundleExecutable": "NVMeGeneric",
        "CFBundleIdentifier": "com.MinnowStor.NVMeGeneric",
        "OSBundleRequired": "Root",
    }
    for key, value in expected.items():
        if info.get(key) != value:
            raise SystemExit(f"{path}: {key} is {info.get(key)!r}, expected {value!r}")
    actual = digest(executable, "sha256")
    if actual != expected_sha256:
        raise SystemExit(f"{path}: executable SHA-256 {actual}, expected {expected_sha256}")


def build_one(
    work: pathlib.Path,
    output: pathlib.Path,
    source_kext: pathlib.Path,
    bundle_name: str,
    package_name: str,
    identifier: str,
    minimum_version: str,
    before_version: str,
    expected_md5: str,
    package_version: str,
) -> None:
    root = work / f"{package_name}-root"
    scripts = work / f"{package_name}-scripts"
    destination = root / "System/Library/Extensions" / bundle_name
    destination.parent.mkdir(parents=True)
    shutil.copytree(source_kext, destination, symlinks=True)
    subprocess.run(["/usr/bin/xattr", "-cr", str(destination)], check=True)
    for directory, _, files in os.walk(destination):
        pathlib.Path(directory).chmod(0o755)
        for filename in files:
            (pathlib.Path(directory) / filename).chmod(0o644)
    (destination / "Contents/MacOS/NVMeGeneric").chmod(0o755)

    scripts.mkdir()
    write_executable(scripts / "postinstall", postinstall(bundle_name, expected_md5))

    components = work / f"{package_name}-components.plist"
    with components.open("wb") as target:
        plistlib.dump(
            component_plist(f"System/Library/Extensions/{bundle_name}"),
            target,
            fmt=plistlib.FMT_XML,
            sort_keys=False,
        )

    component_name = f"component-{package_name}"
    component = work / component_name
    subprocess.run(
        [
            "/usr/bin/pkgbuild",
            "--root", str(root),
            "--component-plist", str(components),
            "--scripts", str(scripts),
            "--identifier", identifier,
            "--version", package_version,
            "--install-location", "/",
            "--ownership", "recommended",
            "--compression", "legacy",
            str(component),
        ],
        check=True,
    )
    require_restart(component)

    distribution_path = work / f"{package_name}.dist"
    distribution_path.write_text(
        distribution(
            package_name.removesuffix(".pkg"), identifier, component_name,
            minimum_version, before_version, package_version,
        )
    )
    subprocess.run(
        [
            "/usr/bin/productbuild",
            "--distribution", str(distribution_path),
            "--package-path", str(work),
            str(output / package_name),
        ],
        check=True,
    )
    make_legacy_product_archive(output / package_name)






def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snow-kext", type=pathlib.Path, required=True)
    parser.add_argument("--mavericks-kext", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--release", required=True, help="release date in YYYYMMDD form")
    args = parser.parse_args()

    try:
        datetime.datetime.strptime(args.release, "%Y%m%d")
    except ValueError:
        raise SystemExit("--release must be a valid date in YYYYMMDD form")
    if len(args.release) != 8 or not args.release.isdigit():
        raise SystemExit("--release must be a valid date in YYYYMMDD form")

    snow = args.snow_kext.resolve()
    mavericks = args.mavericks_kext.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing existing output: {output}")

    validate_kext(snow, "NVMeGeneric-Snow.kext", SNOW_EXEC_SHA256, "NVMeGeneric-Snow")
    validate_kext(mavericks, "NVMeGeneric-Mavericks.kext", MAVERICKS_EXEC_SHA256, "NVMeGeneric")
    output.mkdir(parents=True)

    with tempfile.TemporaryDirectory(prefix="nvmegeneric-pkg-") as temporary:
        work = pathlib.Path(temporary)
        build_one(
            work, output, snow, "NVMeGeneric-Snow.kext", f"NVMeGeneric-Snow-{args.release}.pkg",
            "local.nvmegeneric.legacy.snow", "10.6", "10.9",
            "69128895db3048fdc46f6fc6c26f7b08", args.release,
        )
        build_one(
            work, output, mavericks, "NVMeGeneric-Mavericks.kext", f"NVMeGeneric-Mavericks-{args.release}.pkg",
            "local.nvmegeneric.legacy.mavericks", "10.9", "10.10",
            "5fd39cc6a3fe3532c04fcf21eb17a0da", args.release,
        )



if __name__ == "__main__":
    main()
