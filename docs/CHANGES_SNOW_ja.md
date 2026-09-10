# Snow Leopard〜Mountain Lion版の変更

[English](CHANGES_SNOW.md)

`NVMeGeneric-Snow.kext`はMac OS X 10.6.8、OS X 10.7.5、OS X 10.8.5で共用するbuildです。Mavericks向けの互換性変更に加えて、古いkernel向けに以下を変更しています。

## IOKit import

これらのOSに存在しない`IOService`のreporting methodを、未使用のreserved `IOService` slotへ変更します。`IOLockLock`と`IOLockUnlock`の呼び出しは`lck_mtx_lock`と`lck_mtx_unlock`へ変更します。

## LionのDMA動作

Mountain Lionでは`IODMACommand::initWithSpecification`の`numAddressBits = 0`を無制限として受理しますが、Lionでは拒否されます。`nvme_qpair_construct`内の2回のrequestを明示的な64-bit limitへ変更し、3世代で意図した`OutputHost64` mappingを維持します。

## shutdownとrestart

Mavericks版と同じ、synchronize/unmapの中断に対する安全化を含みます。Lionのshutdown panicと断続的なshutdown停止を受けて修正し、restartの反復試験で確認しました。

## Snow Leopardでのfilesystem load

初期の共用binaryはOpenCoreからSnow Leopardへinjectできましたが、filesystem/cacheからloadすると、Snowのkext linkerが末尾の値0の`LC_SOURCE_VERSION` commandを不正な`MH_KEXT_BUNDLE`として拒否しました。正式版はこのload commandだけを削除しています。section、code、symbol、relocationは変更しません。

`CFBundleName`は`NVMeGeneric-Snow`、`OSBundleRequired`は`Root`です。executable名、bundle identifier、binary内のversionは変更していません。

正式版executableのSHA-256は
`dc2fcda7d17ed2f0429713fe13045277571ee006030c5c9a34b3f6ec0de7e0d3`です。
