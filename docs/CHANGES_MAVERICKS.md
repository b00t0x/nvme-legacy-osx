# Mavericks changes

[日本語版](CHANGES_MAVERICKS_ja.md)

`NVMeGeneric-Mavericks.kext` is derived from NVMeGeneric 1.1 for Yosemite. The
original binary was built with the 10.11 SDK, but its NVMe implementation does
not inherently require the 10.11 runtime. The incompatibilities encountered on
Mavericks were imported C++ symbols and shutdown-time semaphore handling.

## Imported symbols

The patcher retargets these unavailable imports to ABI-compatible entries that
exist on Mavericks:

| Original import | Mavericks import |
| --- | --- |
| `IOBlockStorageDevice::doSetPriority(...)` | reserved `IOBlockStorageDevice` slot 1 |
| `IOService::init(OSDictionary*)` | `IORegistryEntry::init(OSDictionary*)` |
| `IOService::init(IORegistryEntry*, IORegistryPlane const*)` | corresponding `IORegistryEntry::init(...)` |

The original code signature becomes invalid when the symbol table changes, so
the patcher removes `LC_CODE_SIGNATURE` and the bundle's `_CodeSignature`
directory.

## Shutdown and restart

The original synchronous flush and unmap paths passed the address of a
stack-local semaphore handle to their completion callback. If shutdown
interrupted the wait, the callback could later signal an invalid semaphore. On
Mavericks this produced an intermittent kernel panic during restart.

The promoted build passes the semaphore value itself to the callback. An
interrupted synchronize wait returns without destroying that semaphore, and an
interrupted advisory unmap abandons the remaining ranges. This avoids both the
late signal panic and the unbounded retry that could stall shutdown. The rare
interrupted path may retain one semaphore until reboot.

The patch also removes the external relocation for the eliminated
`current_task()` call so the kernel linker cannot overwrite the replacement
instructions.

## Bundle metadata

`OSBundleRequired` is set to `Root`, which allows the driver to be included in
the cache needed to access an NVMe root volume. The executable name, bundle
identifier, and embedded version remain unchanged.

The promoted executable SHA-256 is
`79353a360728266fecef8b7da8a0f087da541271b3d1c5b386631cfdba507358`.
