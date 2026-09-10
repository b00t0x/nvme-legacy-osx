# buildとreleaseの手順

[English](BUILD.md)

このrepositoryはNVMeGenericをdownloadせず、binaryも含みません。合法的に入手し、[`manifests/inputs.sha256`](../manifests/inputs.sha256)の全fileと完全一致するNVMeGeneric 1.1 bundleを用意してください。必須inputが1つでも異なる場合、outputを書き込む前にbuildを停止します。

## 必要な環境

- 現行のmacOS host
- Python 3
- Xcode command line package tools（`pkgbuild`、`productbuild`、`xar`）
- 元の`NVMeGeneric.kext`

compilerやlegacy SDKは不要です。既存のx86_64 Mach-Oとplistに限定的な変更を加えます。

## kextのbuild

```sh
python3 tools/build_kexts.py /path/to/NVMeGeneric.kext build/kexts
```

生成したexecutableとplistのhashは[`manifests/outputs.sha256`](../manifests/outputs.sha256)と一致する必要があります。古いfileの混入を防ぐため、output directoryが既に存在する場合は処理を拒否します。

## pkgのbuild

```sh
python3 tools/build_packages.py \
  --snow-kext build/kexts/NVMeGeneric-Snow.kext \
  --mavericks-kext build/kexts/NVMeGeneric-Mavericks.kext \
  --release 20260910 \
  --output build/packages
```

pkgのreceipt versionにはrelease日を使います。これによりversionを単調増加させつつ、NVMeGeneric binary内のkext versionは変更しません。component archiveにはlegacy compressionを使い、Snow LeopardのPackageKitに合わせて、圧縮済みのPayloadとScriptsを外側のproduct archiveへ無圧縮で格納します。

Distribution fileはインストール開始前にOS versionを確認し、mount済みのoffline system volumeも選択可能にします。postinstall scriptはInstallerから渡されたtargetを使い、executableを照合し、ownerとmodeを設定してから、対象volumeに対して`kextcache -u`を実行します。

## release asset一式のbuild

```sh
make release INPUT=/path/to/NVMeGeneric.kext RELEASE=20260910
```

`dist/20260910/`に以下を生成します。

- `NVMeGeneric-Snow-20260910.pkg`
- `NVMeGeneric-Mavericks-20260910.pkg`
- `NVMeGeneric-Kexts-20260910.zip`

zipには両方のkextと、全fileのSHA-256一覧である`SHA256SUMS`だけを含めます。`build_release.py`は成功を表示する前に`verify_release.py`を実行します。

GitHubがuploadされた各Release assetのSHA-256 digestを表示するため、release直下のchecksum fileは生成しません。

tagとrelease名は`YYYYMMDD`形式です。生成したkext、pkg、zipはGitの対象外で、GitHub Releasesだけに配置します。
