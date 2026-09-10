# NVMe Driver for Legacy Mac OS X

このプロジェクトは、NVMeドライバ(NVMeGeneric)をMac OS X 10.6 Snow LeopardからOS X 10.9 Mavericksで利用可能にします。2種類のビルドを提供します。

| ビルド | 対応OS | OpenCoreのkernel範囲 |
| --- | --- | --- |
| NVMeGeneric-Snow | 10.6〜10.8 | 10.0.0–12.99.99 |
| NVMeGeneric-Mavericks | 10.9 | 13.0.0–13.99.99 |

Snow版は64-bit専用です。Snow Leopardはx86_64 kernelで起動する必要があります。
実機検証は各OSの最終アップデートである10.6.8、10.7.5、10.8.5、10.9.5だけで行っています。

このプロジェクトはfirmwareにNVMe対応を追加しません。NVMeから起動するには、Mac OS Xの起動前にfirmwareまたはboot loaderがNVMe controllerと対象volumeを認識できる必要があります。

[English](README.md)

## その他のOS version

このプロジェクトが対象とするのは10.6〜10.9です。それ以降は既存の手段を使用してください。

- OS X 10.10 Yosemite： [Internet Archiveに保存されたMacVidCardsのページ](https://web.archive.org/web/20160614135522/http://www.macvidcards.com/nvme-driver1.html)から、オリジナルのNVMeGeneric driverを使用します。
- OS X 10.11 El CapitanおよびmacOS 10.12 Sierra： [RehabManのpatch-nvme](https://github.com/RehabMan/patch-nvme)を使用し、正確なOS buildに対応するHackrNVMeFamilyを生成します。

## インストール

[Releases](https://github.com/b00t0x/nvme-legacy-osx/releases)からダウンロードしてください。

### HackintoshでOpenCoreからinject

zipはHackintosh向けです。`NVMeGeneric-Kexts-YYYYMMDD.zip`を展開し、対象のkextを`EFI/OC/Kexts`へコピーして、`config.plist`の`Kernel/Add`へ追加します。

推奨範囲は次のとおりです。

```text
NVMeGeneric-Snow.kext:       MinKernel 10.0.0, MaxKernel 12.99.99
NVMeGeneric-Mavericks.kext:  MinKernel 13.0.0, MaxKernel 13.99.99
```

### リアルMac向けpkg

10.6〜10.8では`NVMeGeneric-Snow-YYYYMMDD.pkg`、10.9では`NVMeGeneric-Mavericks-YYYYMMDD.pkg`を使用します。

## 確認済みの範囲

開発と検証はHackintoshで行いました。Intel Z97 systemとWD Blue SN500 PCIe 3.0 x2 NVMe SSDを使用し、全対応major versionでNVMe認識、HFS+ read/write、NVMe root boot、shutdown、restartを確認しています。

リアルMacでの動作は未確認です。EFI firmware updateによってNVMe bootに対応したMacでは、これらのOSをNVMeから起動できる可能性がありますが、検証はしていません。全てのNVMe controllerやMacとの互換性を保証するものではありません。

## データ保護

改変はLLMにより作成されたものであり、長期運用の安定性は未確認です。常用するsystemでは、別のSATA driveへ最新のTime Machine backupを保持することを推奨します。利用は自己責任であり、このsoftwareの利用によって生じたデータ消失その他の損害についてproject authorは責任を負いません。

## 技術資料とbuild

- [Mavericks版の変更](docs/CHANGES_MAVERICKS_ja.md)
- [Snow Leopard〜Mountain Lion版の変更](docs/CHANGES_SNOW_ja.md)
- [buildとreleaseの手順](docs/BUILD_ja.md)

[tools](./tools/)は[`manifests/inputs.sha256`](manifests/inputs.sha256)に記録した完全一致の
NVMeGeneric 1.1だけを入力として受理し、[`manifests/outputs.sha256`](manifests/outputs.sha256)に記録した正式版executableを再現します。

## ライセンスと帰属

[LICENSE](./LICENSE)の対象は、このプロジェクトが作成したスクリプトとドキュメントだけです。NVMeGenericは第三者のsoftwareであり、元のcopyrightとbinary内のnoticeを維持します。生成したbinaryを利用または配布する前に[`THIRD_PARTY_NOTICES_ja.md`](THIRD_PARTY_NOTICES_ja.md)を確認してください。
