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

## I2C EEPROM (24Cxx @ 0x50) layout — VERIFIED

**Part and access.** The part is at least a 24C128: the highest
address used is 0x24A7. Addressing is 2-byte. Writes go in 64-B page
chunks, each starting on a 64-B boundary, with a fixed 10 ms gap and
no ACK polling.

**Checksum.** CRC-8: polynomial 0x31, MSB-first, init 0, no final XOR.
The table is built at boot by `FUN_0804ad24` into `0x24019158`, and
`FUN_0804ae14` computes the checksum.

| Range | Size | Record | RAM image | Load / save | Integrity |
| --- | ---: | --- | --- | --- | --- |
| 0x0000–0x01A7 | 424 B | Settings (= SLIP `0x01` struct) | `0x24013C0C` | `FUN_0803c08c` / none | byte 0x64 at offsets 0x000, 0x1A3, 0x1A4; no CRC |
| 0x0800–0x0965 | 358 B | Calibration (= SLIP `0x02` block) | `0x24013AA4` | `FUN_0803c5e4` / `FUN_0803c534` | board id 0x0A at 0x000, CRC-8 of 0x000–0x163 at 0x164, end marker 0x64 at 0x165 |
| 0x1000–0x1002 | 3 B | NVPARAM marker | `0x24013AA0` | `FUN_0803c448` | header 0x3E, flag byte, CRC-8 of bytes 0–1 |
| 0x1800–0x1E53 | 1620 B | ATU table, antenna index 0 | `0x24016A34` | `FUN_080411d8` / `FUN_08041228` | empty slot = 0xFF |
| 0x1E54–0x24A7 | 1620 B | ATU table, antenna index 1 | `0x24017088` | same | empty slot = 0xFF |

**Settings.** The loader reads backup SRAM (`0x38800000`) first and
falls back to the EEPROM, checking the 0x64 markers both times. Main
calls it with an argument that forces defaults, so in practice the
Main Unit boots on defaults and waits for the Control Unit's `0x01`
push. (HIGH CONFIDENCE.) No code in this firmware writes the settings
area of the EEPROM, and no writer of the backup SRAM was found either
(HIGH CONFIDENCE).

**Calibration.** A bad block is replaced by defaults and written back
at once. After loading, a few runtime fields are overridden without
being saved. The block is saved at shutdown (`FUN_08021edc`) when its
dirty flag (`0x24013A9C`) is set.

**NVPARAM marker.** On a bad header or CRC the firmware logs an error.
When the record is valid, it rewrites it with the flag set and logs
that it was saved. Its purpose is probably a boot marker (HYPOTHESIS).

**ATU table.** There are two antenna blocks of 540 three-byte slots.
- **Slot number** = frequency in Hz / 100000 − 1, clamped to 0–539.
  That gives 100 kHz bins up to 54 MHz.
- **Slot bytes:** L, C, S, where S is the network type. S = 0xFF means
  the slot is empty.
- **Antenna block:** selected by settings byte 0x09F, bit 0.
- **Use:** tune/save is `FUN_08041358` and recall is `FUN_080412bc`.
  The tuner seeds a search from the slots ±1 and ±2 next to the
  current one.
- **Saving:** at shutdown, when the flag at `0x240176E8` is set.

Ranges and functions are in `analysis/memory/eeprom_map.csv`.

**Why this needed the firmware:** the record addresses, markers, CRC
parameters and ATU slot scheme are software conventions. No datasheet
or measurement can reveal them.

## Unknowns

- Heap/stack split (no `_sbrk` analyzed yet).
- Use of DTCM (`0x20000000`), D2/D3 SRAM, and the AXI SRAM above the
  stack — none referenced by the startup copy; check DMA setup later.
