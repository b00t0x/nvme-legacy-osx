# Mavericks版の変更

[English](CHANGES_MAVERICKS.md)

`NVMeGeneric-Mavericks.kext`はYosemite向けNVMeGeneric 1.1を元にしています。元のbinaryは10.11 SDKでbuildされていますが、NVMe実装そのものが10.11 runtimeを必須とするわけではありません。Mavericksで問題になったのはimportされたC++ symbolと、shutdown時のsemaphore処理でした。

## import symbol

patcherはMavericksに存在しないimportを、ABI互換で利用可能なentryへ変更します。

| 元のimport | Mavericks向けimport |
| --- | --- |
| `IOBlockStorageDevice::doSetPriority(...)` | `IOBlockStorageDevice`のreserved slot 1 |
| `IOService::init(OSDictionary*)` | `IORegistryEntry::init(OSDictionary*)` |
| `IOService::init(IORegistryEntry*, IORegistryPlane const*)` | 対応する`IORegistryEntry::init(...)` |

symbol tableの変更によって元のcode signatureは無効になるため、patcherは`LC_CODE_SIGNATURE`とbundle内の`_CodeSignature` directoryを削除します。

## shutdownとrestart

元の同期flush/unmap処理は、stack localなsemaphore handleのアドレスをcompletion callbackへ渡していました。shutdownがwaitを中断すると、callbackが後から無効なsemaphoreをsignalする場合があります。Mavericksではrestart時に断続的なkernel panicとして再現しました。

正式版はsemaphoreの値自体をcallbackへ渡します。synchronize waitが中断された場合はsemaphoreをdestroyせずにreturnし、advisory unmapが中断された場合は残りのrangeを破棄します。これにより遅れて発生するsignalのpanicと、無期限retryによるshutdown停止の両方を回避します。まれな中断経路ではrebootまでsemaphoreを1個保持する可能性があります。

また、削除した`current_task()`呼び出しに対応するexternal relocationも除去し、kernel linkerが置換後のinstructionを上書きしないようにしています。

## bundle metadata

NVMe root volumeへのアクセスに必要なcacheへdriverを含めるため、`OSBundleRequired`を`Root`に設定しました。executable名、bundle identifier、binary内のversionは変更していません。

正式版executableのSHA-256は
`79353a360728266fecef8b7da8a0f087da541271b3d1c5b386631cfdba507358`です。
