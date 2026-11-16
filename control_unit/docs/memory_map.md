# Control Unit — Memory map

Image: `G7250_ControlUnit_Fw_V1.0.1.bin` (781 328 B) · load base `0x08020000`
Evidence: `control_unit/analysis/startup/data_init_words.csv` (reset
literal pool), reset disassembly. All ranges VERIFIED from the reset
handler.

## Flash image

| Region | Start | End (excl.) | Confidence |
| --- | ---: | ---: | --- |
| Application image | `0x08020000` | `0x080DEC10` | VERIFIED (base + file size) |
| Vector table | `0x08020000` | — | VERIFIED (`SCB->VTOR = 0x08020000`) |
| `.data` load image | `0x080DD568` | `0x080DEC00` | VERIFIED (tail of image) |

The `.data` load image ends only 16 bytes before the physical end of
the file — the application occupies essentially the whole image.

## RAM (all in AXI SRAM, `0x24000000` / D1 domain)

| Section | Start | End (excl.) | Size | Load from | Confidence |
| --- | ---: | ---: | ---: | ---: | --- |
| `.data` | `0x24000000` | `0x24001698` | `0x1698` (5 784 B) | flash `0x080DD568` | VERIFIED |
| alignment padding | `0x24001698` | `0x240016A0` | 8 B | — | VERIFIED (unused) |
| `.bss` | `0x240016A0` | `0x240614A4` | `0x5FE04` (392 708 B) | — (zeroed) | VERIFIED |
| heap + stack | `0x240614A4` | `0x24080000` | `0x1EB5C` (125 788 B) | — | HIGH CONFIDENCE |

- Initial MSP (stack top): `0x24080000` — VERIFIED; exactly the top of a
  512 KiB AXI SRAM.
- AXI SRAM used: the full `0x24000000`–`0x24080000` 512 KiB window.
- The 8-byte gap between `.data` and `.bss` is **linker alignment
  padding** (HIGH CONFIDENCE). Evidence:
  - The `.data` copy loop in the reset handler stops exactly at
    `0x24001698`.
  - Nothing in the image refers into the gap.
  - `.bss` starts at the 32-byte boundary `0x240016A0` with the standard
    GCC runtime objects: the destructor-helper "completed" flag at
    `0x240016A0` (used by `0x080202a0`) and the frame-info object at
    `0x240016A4` (used by `FUN_080202c4`).

  So the `.bss` output section is aligned to at least 16 bytes, most
  likely 32. That is typical of cache-line-aligned DMA buffers on the
  Cortex-M7; which object forces it is not identified. The Main Unit,
  whose `.bss` needs only 8-byte alignment, has no such gap. The
  earlier comparison with the X6100 runtime-array words does not apply.
  The 16 bytes after the `.data` load image in flash are zero padding as
  well.

## Unknowns

- Heap/stack split.
- Use of DTCM / D2 / D3 SRAM (not touched by startup copy).
