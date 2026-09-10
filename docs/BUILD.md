# Build and release process

[日本語版](BUILD_ja.md)

The repository does not download or contain NVMeGeneric. Supply a legally
obtained original NVMeGeneric 1.1 bundle whose files exactly match
[`manifests/inputs.sha256`](../manifests/inputs.sha256). The build stops before
writing output if any required input differs.

## Requirements

- A current macOS host
- Python 3
- Xcode command line package tools (`pkgbuild`, `productbuild`, and `xar`)
- The original `NVMeGeneric.kext`

No compiler or legacy SDK is required. The tools make bounded changes to the
existing x86_64 Mach-O and plist.

## Build the kexts

```sh
python3 tools/build_kexts.py /path/to/NVMeGeneric.kext build/kexts
```

The output executable and plist hashes must match
[`manifests/outputs.sha256`](../manifests/outputs.sha256). The tools refuse an
existing output directory so stale files cannot enter a new build.

## Build the packages

```sh
python3 tools/build_packages.py \
  --snow-kext build/kexts/NVMeGeneric-Snow.kext \
  --mavericks-kext build/kexts/NVMeGeneric-Mavericks.kext \
  --release 20260910 \
  --output build/packages
```

The package receipt version is the release date. This keeps it monotonic while
leaving NVMeGeneric's embedded kext version unchanged. The component archives
use legacy compression, and their already-compressed Payload and Scripts are
stored uncompressed in the outer product archive for Snow Leopard PackageKit.

The Distribution file performs the OS check before installation and enables
mounted offline system volumes. The postinstall script uses Installer's target
argument, verifies the executable, sets ownership and modes, then runs
`kextcache -u` against that target.

## Build all release assets

```sh
make release INPUT=/path/to/NVMeGeneric.kext RELEASE=20260910
```

This creates `dist/20260910/` with:

- `NVMeGeneric-Snow-20260910.pkg`
- `NVMeGeneric-Mavericks-20260910.pkg`
- `NVMeGeneric-Kexts-20260910.zip`

The zip contains both kexts and a per-file `SHA256SUMS` inventory.
`build_release.py` runs `verify_release.py` before reporting success.

GitHub displays a SHA-256 digest for each uploaded Release asset, so a separate
release-level checksum file is not generated.

Tag and release names use `YYYYMMDD`. Generated kext, package, and zip files are
ignored by Git and belong only in GitHub Releases.
