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
| runtime array gap | `0x24001698` | `0x240016A0` | 8 B | — | VERIFIED extent |
| `.bss` | `0x240016A0` | `0x240614A4` | `0x5FE04` (392 708 B) | — (zeroed) | VERIFIED |
| heap + stack | `0x240614A4` | `0x24080000` | `0x1EB5C` (125 788 B) | — | HIGH CONFIDENCE |

- Initial MSP (stack top): `0x24080000` — VERIFIED; exactly the top of a
  512 KiB AXI SRAM.
- AXI SRAM used: the full `0x24000000`–`0x24080000` 512 KiB window.
- The 8-byte gap between `.data` and `.bss` mirrors the X6100
  runtime-array words at the same boundary (role unresolved).

## Unknowns

- Contents/role of the 8-byte `.data`/`.bss` gap.
- Heap/stack split.
- Use of DTCM / D2 / D3 SRAM (not touched by startup copy).
