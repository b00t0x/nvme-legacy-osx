# Snow Leopard through Mountain Lion changes

[日本語版](CHANGES_SNOW_ja.md)

`NVMeGeneric-Snow.kext` is one shared build for Mac OS X 10.6.8, OS X 10.7.5,
and OS X 10.8.5. It includes the Mavericks compatibility changes plus the
following older-kernel adaptations.

## IOKit imports

The `IOService` reporting methods absent from these systems are redirected to
unused reserved `IOService` slots. Calls to `IOLockLock` and `IOLockUnlock` are
retargeted to `lck_mtx_lock` and `lck_mtx_unlock`.

## Lion DMA behavior

Mountain Lion accepts zero `numAddressBits` as an unrestricted
`IODMACommand::initWithSpecification` request, while Lion rejects it. The 2
requests in `nvme_qpair_construct` are changed to an explicit 64-bit limit,
which preserves the intended `OutputHost64` mapping on all 3 systems.

## Shutdown and restart

This build contains the same abort-safe synchronize and unmap changes described
for the Mavericks build. The fix was developed after a Lion shutdown panic and
an intermittent shutdown stall, then verified with repeated restart testing.

## Snow Leopard filesystem loading

OpenCore could inject the initial shared binary on Snow Leopard, but Snow's
filesystem/cache kext linker rejected its trailing zero `LC_SOURCE_VERSION`
command as a malformed `MH_KEXT_BUNDLE`. The final build removes that one load
command. Sections, code, symbols, and relocations remain unchanged.

`CFBundleName` is `NVMeGeneric-Snow` and `OSBundleRequired` is `Root`. The
executable name, bundle identifier, and embedded version remain unchanged.

The promoted executable SHA-256 is
`dc2fcda7d17ed2f0429713fe13045277571ee006030c5c9a34b3f6ec0de7e0d3`.
