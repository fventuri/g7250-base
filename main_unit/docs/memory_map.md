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
| Tail fill | `0x080894C4` | `0x0808EA20` | VERIFIED (content) |

**Tail fill.** The 21 852 bytes after the `.data` load image are three
0xFF words, 21 836 zero bytes and a final 0xFF word. Nothing in the
image refers to this area, and it holds no code, table, bootloader or
FPGA image. The 0xFF words may be unstamped placeholders, as in erased
flash (HYPOTHESIS).

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
- AXI SRAM used: `0x24000000`–`0x24050000` = the full 320 KiB AXI
  SRAM of an H72x/H73x (default TCM/AXI split; see docs/mcu_identification.md). On an H72x with the default TCM split, `0x24050000` is the top of
  AXI SRAM; nothing above it exists or is referenced.

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

## MPU, caches and RAM use — VERIFIED unless noted

**MPU** (`FUN_0804a7c0`, enabled with PRIVDEFENA before the caches are
switched on):

| Region | Base | Size | Attributes | Purpose |
| --- | --- | --- | --- | --- |
| R0 | `0x60000000` | 1 MiB | strongly ordered, shareable | guard against speculative reads of FMC bank 1, which has nothing behind it (HIGH CONFIDENCE) |
| R1 | `0x30000000` | 32 KiB | normal, non-cacheable | all of the H72x D2 SRAM |
| R2 | `0x38800000` | 4 KiB | strongly ordered, shareable | backup SRAM |
| R3 | `0x38000000` | 16 KiB | normal, non-cacheable | all of the H72x SRAM4 |

AXI SRAM has no region, so it keeps the default write-back
write-allocate attributes. The region sizes match the RM0468 D2 and
SRAM4 sizes, which is further evidence for the H72x part.

**Cache maintenance.** The MDMA copy helper `FUN_0803b01c` cleans the
source and destination lines, runs MDMA channel 0 polled, then cleans
and invalidates the destination. The fill helper `FUN_0803aee8` does
the same on channel 4.

**Heap and stack.** `_sbrk` is `FUN_08023b88`. The heap starts at the
end of `.bss` (`0x24035C20`) and may grow to `0x24050000` − 0x400, so
the stack always has at least 1 KiB and the heap at most 106 464 B.
The firmware places nothing in ITCM or DTCM.

**Buffer placement:**

| Address | Region | Content | Why there |
| --- | --- | --- | --- |
| `0x30000000`–`0x30002F40` | D2 | wfview audio work buffers, TX-audio ring, packet / retransmit rings | non-cacheable shared buffers |
| `0x30003740` | D2 | ADC1 DMA (7 half-words) | DMA1, non-cacheable |
| `0x30003760` / `0x30004360` | D2 | I²S3 RX / TX DMA (3 KiB each) | DMA1, circular |
| `0x30004960` | D2 | DSP buffer | |
| `0x30004F60` | D2 | console USART1 RX ring | DMA1 |
| `0x30005360` / `0x30005B60` | D2 | SLIP TX encoded / SLIP RX ring | DMA1 |
| `0x38000000` / `0x38000800` | SRAM4 | CH394 TX / RX staging | the BDMA reaches only D3 memory |
| `0x38001000` / `0x38001300` / `0x38001600` | SRAM4 | HDSDR IQ ping-pong and packet | sent through SPI6 / BDMA |
| `0x38800000` | backup SRAM | settings mirror (read only) | strongly ordered |

**Why this needed the firmware:** the MPU attributes, buffer placement,
heap/stack reserve and cache strategy are linker and software choices.

## RAM objects — HIGH CONFIDENCE unless noted

The key globals (87 objects) are listed in `analysis/memory/ram_objects.csv`
with address, size, region, role, owner and users. Sizes marked ≤ are
upper bounds, taken from the gap to the next referenced address.

Beyond the structures documented elsewhere, the map includes:
- the RX I/Q ping-pong buffers (4 × 768 B at `0x2400F5F0`);
- the scope/FFT ping-pong (2 × 1 KiB at `0x24035420`);
- the FIR state buffers (1568 B = 201 + 192 − 1 floats, MEDIUM);
- the NR frame and resampler buffers (MEDIUM);
- the wfview session buffers, the largest `.bss` objects (MEDIUM).
