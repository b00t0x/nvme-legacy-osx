#!/usr/bin/env python3
"""Produce a promoted Mavericks or Snow NVMeGeneric executable."""

from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


MH_MAGIC_64 = 0xFEEDFACF
LC_SYMTAB = 0x2
LC_DYSYMTAB = 0xB
LC_SEGMENT_64 = 0x19
LC_CODE_SIGNATURE = 0x1D
NLIST_64_SIZE = 16
RELOCATION_INFO_SIZE = 8
X86_64_RELOC_BRANCH = 2

EXPECTED_SHA256 = "c6b79e62a09e6d0775d6ea36ce588a093be9d7b2feb53acde82ab4ac0410fd03"
EXPECTED_PRE_STRIP_SHA256 = {
    "mavericks": "79353a360728266fecef8b7da8a0f087da541271b3d1c5b386631cfdba507358",
    "snow": "75cf1d483aea0ae0cca0de7649bcef669b60b781d4f51507bf0d79f11aa598a1",
}
EXPECTED_OUTPUT_SHA256 = {
    "mavericks": "79353a360728266fecef8b7da8a0f087da541271b3d1c5b386631cfdba507358",
    "snow": "dc2fcda7d17ed2f0429713fe13045277571ee006030c5c9a34b3f6ec0de7e0d3",
}

MAVERICKS_REPLACEMENTS = {
    "__ZN20IOBlockStorageDevice13doSetPriorityEP26IOBlockStorageDeviceExtentjh":
        "__ZN20IOBlockStorageDevice30_RESERVEDIOBlockStorageDevice1Ev",
    "__ZN9IOService4initEP12OSDictionary":
        "__ZN15IORegistryEntry4initEP12OSDictionary",
    "__ZN9IOService4initEP15IORegistryEntryPK15IORegistryPlane":
        "__ZN15IORegistryEntry4initEPS_PK15IORegistryPlane",
}

MOUNTAIN_LION_REPLACEMENTS = {
    **MAVERICKS_REPLACEMENTS,
    "__ZN9IOService15configureReportEP19IOReportChannelListjPvS2_":
        "__ZN9IOService19_RESERVEDIOService0Ev",
    "__ZN9IOService12updateReportEP19IOReportChannelListjPvS2_":
        "__ZN9IOService19_RESERVEDIOService1Ev",
    "_IOLockLock": "_lck_mtx_lock",
    "_IOLockUnlock": "_lck_mtx_unlock",
}

# Lion's IODMACommand::initWithSpecification rejects numAddressBits == 0,
# while Mountain Lion accepts it as unrestricted.  NVMeGeneric makes exactly
# two such calls in nvme_qpair_construct.  An explicit 64 preserves the
# intended full-width OutputHost64 mapping on both implementations.
LION_TEXT_PATCHES = {
    0x6279: (bytes.fromhex("be00000000"), bytes.fromhex("be40000000")),
    0x62A8: (bytes.fromhex("be00000000"), bytes.fromhex("be40000000")),
}

# semaphore_wait() is abort-safe on the legacy kernels.  Both synchronous bio
# paths pass the address of a stack-local semaphore handle to the completion
# callback, so returning after an interrupted wait leaves the callback with a
# dead stack context.  Retry non-zero waits until the completion signal is
# consumed, then destroy the semaphore and return.
SYNC_WAIT_RETRY_TEXT_PATCHES = {
    # doUnmap: replace the ignored wait result and index/count loop with
    # test/retry plus an equivalent pointer/decrement loop in the same 17 bytes.
    0x45AC: (
        bytes.fromhex("41ffc64883c310443b75cc0f8239ffffff"),
        bytes.fromhex("85c075f34883c310ff4dcc0f8539ffffff"),
    ),
    # doSynchronize: preserve current_task() in r12 across the request, retry
    # an interrupted wait, and use the saved task for semaphore_destroy().  The
    # inactive path keeps kIOReturnNotReady in eax and jumps past the active
    # path's final success normalization.
    0x4658: (
        bytes.fromhex("41bcd90200e0"),
        bytes.fromhex("b8d90200e090"),
    ),
    0x4660: (
        bytes.fromhex("0f859b000000"),
        bytes.fromhex("0f859e000000"),
    ),
    0x466F: (bytes.fromhex("4531e4"), bytes.fromhex("4989c4")),
    0x46F0: (bytes.fromhex("e800000000"), bytes.fromhex("85c075f390")),
    0x46F9: (bytes.fromhex("4889c7"), bytes.fromhex("4c89e7")),
    0x4701: (bytes.fromhex("4489e0"), bytes.fromhex("31c090")),
}

# Passing the semaphore value itself to sync_op_done removes the callback's
# dependency on the caller's stack frame.  If doSynchronize's wait is aborted,
# return without destroying that semaphore: a late completion can then signal
# a valid object, while shutdown is not trapped in an unbounded retry.  The
# exceptional path leaks one semaphore until reboot; the normal path still
# waits, destroys it, and returns exactly as in the retry candidate.
SYNC_WAIT_ABORT_SAFE_TEXT_PATCHES = {
    # doUnmap and doSynchronize callback contexts: value, not &stack_handle.
    0x4592: (bytes.fromhex("488d45d0"), bytes.fromhex("488b45d0")),
    0x46D7: (bytes.fromhex("488d45d0"), bytes.fromhex("488b45d0")),
    # sync_op_done: pass the stored value directly to semaphore_signal().
    0x460A: (bytes.fromhex("488b3b"), bytes.fromhex("4889df")),
    # doSynchronize: an interrupted wait skips destruction and returns the
    # non-zero Mach result; a successful wait follows the existing path.
    0x46F0: (bytes.fromhex("85c075f390"), bytes.fromhex("85c0751090")),
}

# doUnmap shares sync_op_done and the same semaphore context. On interruption,
# skip the remaining advisory unmap extents and leave the semaphore valid for a
# late completion instead of retrying forever during shutdown.
UNMAP_ABORT_SAFE_TEXT_PATCHES = {
    0x45AF: (bytes.fromhex("f3"), bytes.fromhex("1e")),
}
# The doSynchronize patch removes the second current_task() call.  Its external
# branch relocation must be removed too, or the kext linker would overwrite the
# new test/jump bytes at load time.
SYNC_WAIT_REMOVED_RELOCATION = (0x46F1, "_current_task")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a promoted NVMeGeneric executable")
    parser.add_argument("--target", choices=("mavericks", "snow"), required=True)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    return parser.parse_args()


def c_string(data: bytes, offset: int, limit: int) -> str:
    end = data.find(b"\0", offset, limit)
    if end < 0:
        raise ValueError(f"unterminated symbol string at 0x{offset:x}")
    return data[offset:end].decode("utf-8")


def remove_source_version(source: bytes) -> bytes:
    """Remove the trailing zero LC_SOURCE_VERSION rejected by Snow kxld."""
    ncmds, sizeofcmds = struct.unpack_from("<II", source, 16)
    command_offset = 32
    commands = []
    for _ in range(ncmds):
        command, command_size = struct.unpack_from("<II", source, command_offset)
        commands.append((command_offset, command, command_size))
        command_offset += command_size
    if command_offset != 32 + sizeofcmds:
        raise SystemExit("ncmds and sizeofcmds disagree")
    offset, command, size = commands[-1]
    if command != 0x2A or size != 16 or struct.unpack_from("<Q", source, offset + 8)[0] != 0:
        raise SystemExit("expected a trailing zero LC_SOURCE_VERSION")
    output = bytearray(source)
    struct.pack_into("<II", output, 16, ncmds - 1, sizeofcmds - size)
    output[offset:offset + size] = bytes(size)
    return bytes(output)


def main() -> None:
    args = parse_args()
    binary_target = "lion" if args.target == "snow" else "mavericks"
    replacements = (MAVERICKS_REPLACEMENTS if binary_target == "mavericks"
                    else MOUNTAIN_LION_REPLACEMENTS)
    source = args.input.read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    if digest != EXPECTED_SHA256:
        raise SystemExit(f"unexpected input SHA-256: {digest}")

    if len(source) < 32 or struct.unpack_from("<I", source)[0] != MH_MAGIC_64:
        raise SystemExit("input is not a little-endian 64-bit Mach-O")

    ncmds = struct.unpack_from("<I", source, 16)[0]
    command_offset = 32
    symtab = None
    symtab_command_offset = None
    dysymtab = None
    dysymtab_command_offset = None
    linkedit = None
    code_signature = None
    command_offsets = []
    for _ in range(ncmds):
        command, command_size = struct.unpack_from("<II", source, command_offset)
        if command_size < 8 or command_offset + command_size > len(source):
            raise SystemExit("invalid Mach-O load command")
        if command == LC_SYMTAB:
            symtab = struct.unpack_from("<IIII", source, command_offset + 8)
            symtab_command_offset = command_offset
        elif command == LC_DYSYMTAB:
            dysymtab = struct.unpack_from("<18I", source, command_offset + 8)
            dysymtab_command_offset = command_offset
        elif command == LC_SEGMENT_64:
            segment_name = source[command_offset + 8:command_offset + 24].rstrip(b"\0")
            if segment_name == b"__LINKEDIT":
                linkedit = command_offset
        elif command == LC_CODE_SIGNATURE:
            code_signature = (command_offset, command_size, *struct.unpack_from("<II", source, command_offset + 8))
        command_offsets.append(command_offset)
        command_offset += command_size

    if (symtab is None or symtab_command_offset is None or
            dysymtab is None or dysymtab_command_offset is None or linkedit is None):
        raise SystemExit("required Mach-O metadata was not found")
    if code_signature is None or code_signature[0] != command_offsets[-1]:
        raise SystemExit("LC_CODE_SIGNATURE must be the final load command")
    symbol_offset, symbol_count, string_offset, string_size = symtab
    string_limit = string_offset + string_size
    if symbol_offset + symbol_count * NLIST_64_SIZE > len(source) or string_limit > len(source):
        raise SystemExit("symbol or string table is outside the file")

    output = bytearray(source[:string_limit])
    seen_replacements: dict[str, int] = {name: 0 for name in replacements}
    for index in range(symbol_count):
        entry_offset = symbol_offset + index * NLIST_64_SIZE
        string_index = struct.unpack_from("<I", source, entry_offset)[0]
        if string_index >= string_size:
            raise SystemExit(f"symbol {index} has an invalid string index")
        name = c_string(source, string_offset + string_index, string_limit)
        if name in replacements:
            seen_replacements[name] += 1
            replacement = replacements[name].encode("utf-8") + b"\0"
            new_string_index = len(output) - string_offset
            output.extend(replacement)
            struct.pack_into("<I", output, entry_offset, new_string_index)

    unexpected = {name: count for name, count in seen_replacements.items() if count != 1}
    if unexpected:
        raise SystemExit(f"replacement symbols must occur exactly once: {unexpected}")

    # The original signature is invalid after symbol retargeting.  Remove its
    # final load command and use the former signature area for appended names.
    signature_command_offset, signature_command_size, signature_offset, _ = code_signature
    if signature_offset < string_limit:
        raise SystemExit("code signature overlaps the original string table")
    struct.pack_into("<II", output, 16, ncmds - 1,
                     struct.unpack_from("<I", source, 20)[0] - signature_command_size)
    output[signature_command_offset:signature_command_offset + signature_command_size] = bytes(signature_command_size)
    new_string_size = len(output) - string_offset
    struct.pack_into("<I", output, symtab_command_offset + 20, new_string_size)
    linkedit_file_offset = struct.unpack_from("<Q", source, linkedit + 40)[0]
    struct.pack_into("<Q", output, linkedit + 48, len(output) - linkedit_file_offset)
    if binary_target == "lion":
        for offset, (expected, replacement) in LION_TEXT_PATCHES.items():
            actual = bytes(output[offset:offset + len(expected)])
            if actual != expected:
                raise SystemExit(
                    f"unexpected Lion patch bytes at 0x{offset:x}: {actual.hex()}"
                )
            output[offset:offset + len(replacement)] = replacement
    for offset, (expected, replacement) in SYNC_WAIT_RETRY_TEXT_PATCHES.items():
        actual = bytes(output[offset:offset + len(expected)])
        if actual != expected:
            raise SystemExit(
                f"unexpected sync-wait patch bytes at 0x{offset:x}: {actual.hex()}"
            )
        output[offset:offset + len(replacement)] = replacement

    external_relocation_offset = dysymtab[14]
    external_relocation_count = dysymtab[15]
    wanted_address, wanted_symbol = SYNC_WAIT_REMOVED_RELOCATION
    matches = []
    for index in range(external_relocation_count):
        entry_offset = external_relocation_offset + index * RELOCATION_INFO_SIZE
        address, info = struct.unpack_from("<iI", source, entry_offset)
        symbol_index = info & 0xFFFFFF
        pcrel = (info >> 24) & 1
        length = (info >> 25) & 3
        external = (info >> 27) & 1
        relocation_type = (info >> 28) & 0xF
        if symbol_index >= symbol_count:
            raise SystemExit(f"relocation {index} has invalid symbol index")
        string_index = struct.unpack_from(
            "<I", source, symbol_offset + symbol_index * NLIST_64_SIZE
        )[0]
        symbol_name = c_string(source, string_offset + string_index, string_limit)
        if address == wanted_address and symbol_name == wanted_symbol:
            matches.append((index, entry_offset, pcrel, length, external, relocation_type))
    if len(matches) != 1:
        raise SystemExit(
            f"expected one relocation at 0x{wanted_address:x} for {wanted_symbol}: {matches}"
        )
    index, entry_offset, pcrel, length, external, relocation_type = matches[0]
    if (pcrel, length, external, relocation_type) != (1, 2, 1, X86_64_RELOC_BRANCH):
        raise SystemExit(f"unexpected relocation encoding: {matches[0]}")
    relocation_end = (external_relocation_offset +
                      external_relocation_count * RELOCATION_INFO_SIZE)
    if relocation_end > string_offset:
        raise SystemExit("external relocation table overlaps the string table")
    output[entry_offset:relocation_end - RELOCATION_INFO_SIZE] = output[
        entry_offset + RELOCATION_INFO_SIZE:relocation_end
    ]
    output[relocation_end - RELOCATION_INFO_SIZE:relocation_end] = bytes(
        RELOCATION_INFO_SIZE
    )
    struct.pack_into(
        "<I", output, dysymtab_command_offset + 68, external_relocation_count - 1
    )
    source_relocations = [
        source[offset:offset + RELOCATION_INFO_SIZE]
        for offset in range(
            external_relocation_offset,
            relocation_end,
            RELOCATION_INFO_SIZE,
        )
    ]
    output_relocations = [
        bytes(output[offset:offset + RELOCATION_INFO_SIZE])
        for offset in range(
            external_relocation_offset,
            relocation_end - RELOCATION_INFO_SIZE,
            RELOCATION_INFO_SIZE,
        )
    ]
    expected_relocations = (
        source_relocations[:index] + source_relocations[index + 1:]
    )
    if output_relocations != expected_relocations:
        raise SystemExit("external relocation compaction changed another entry")
    for offset, (expected, replacement) in SYNC_WAIT_ABORT_SAFE_TEXT_PATCHES.items():
        actual = bytes(output[offset:offset + len(expected)])
        if actual != expected:
            raise SystemExit(
                f"unexpected sync-wait abort-safe bytes at 0x{offset:x}: {actual.hex()}"
            )
        output[offset:offset + len(replacement)] = replacement
    for offset, (expected, replacement) in UNMAP_ABORT_SAFE_TEXT_PATCHES.items():
        actual = bytes(output[offset:offset + len(expected)])
        if actual != expected:
            raise SystemExit(
                f"unexpected unmap abort-safe bytes at 0x{offset:x}: {actual.hex()}"
            )
        output[offset:offset + len(replacement)] = replacement

    struct.pack_into("<Q", output, linkedit + 48, len(output) - linkedit_file_offset)
    pre_strip_digest = hashlib.sha256(output).hexdigest()
    if pre_strip_digest != EXPECTED_PRE_STRIP_SHA256[args.target]:
        raise SystemExit(f"unexpected pre-strip output SHA-256: {pre_strip_digest}")
    final_output = remove_source_version(bytes(output)) if args.target == "snow" else bytes(output)
    output_digest = hashlib.sha256(final_output).hexdigest()
    if output_digest != EXPECTED_OUTPUT_SHA256[args.target]:
        raise SystemExit(f"unexpected output SHA-256: {output_digest}")
    if args.output.exists():
        raise SystemExit(f"refusing existing output: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(final_output)
    args.output.chmod(args.input.stat().st_mode & 0o777)
    print(f"input_sha256={digest}")
    print(f"output_sha256={output_digest}")
    print(f"target={args.target}")


if __name__ == "__main__":
    main()
