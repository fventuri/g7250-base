# Main Unit — Memory map

Image: `G7250_MainUnit_Fw_V1.0.1.bin` (453 152 B) · load base `0x08020000`
Evidence: `main_unit/analysis/startup/data_init_words.csv` (reset literal
pool), reset disassembly. All ranges VERIFIED from the reset handler.

## Flash image

| Region | Start | End (excl.) | Confidence |
| --- | ---: | ---: | --- |
| Application image | `0x08020000` | `0x0808EA20` | VERIFIED (base + file size) |
| Vector table | `0x08020000` | — | VERIFIED (`SCB->VTOR = 0x08020000`) |
| `.data` load image | `0x0808486C` | `0x080894C4` | VERIFIED |

Bytes for `0x08000000`–`0x0801FFFF` are absent (bootloader region, not
in this image), same convention as the X6100.

## RAM (all in AXI SRAM, `0x24000000` / D1 domain)

| Section | Start | End (excl.) | Size | Load from | Confidence |
| --- | ---: | ---: | ---: | ---: | --- |
| `.data` | `0x24000000` | `0x24004C58` | `0x4C58` (19 544 B) | flash `0x0808486C` | VERIFIED |
| `.bss` | `0x24004C58` | `0x24035C20` | `0x30FC8` (200 648 B) | — (zeroed) | VERIFIED |
| heap + stack | `0x24035C20` | `0x24050000` | `0x1A3E0` (107 488 B) | — | HIGH CONFIDENCE |

- Initial MSP (stack top): `0x24050000` — VERIFIED (vector[0] and reset
  `ldr sp`).
- AXI SRAM used: `0x24000000`–`0x24050000` = 320 KiB of the ≥512 KiB AXI
  SRAM. Region above `0x24050000` (incl. the 192 KiB up to the 512 KiB
  boundary) is not statically allocated; likely DMA/runtime use.

## Unknowns

- Heap/stack split (no `_sbrk` analyzed yet).
- Use of DTCM (`0x20000000`), D2/D3 SRAM, and the AXI SRAM above the
  stack — none referenced by the startup copy; check DMA setup later.
