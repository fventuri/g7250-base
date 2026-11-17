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
- AXI SRAM used: the full `0x24000000`–`0x24080000` 512 KiB window (VERIFIED).
- The 8-byte gap between `.data` and `.bss` is **linker alignment
  padding** (HIGH CONFIDENCE). Evidence:
  - The `.data` copy loop in the reset handler stops exactly at
    `0x24001698` (VERIFIED).
  - Nothing in the image refers into the gap.
  - `.bss` starts at the 32-byte boundary `0x240016A0` with the standard
    GCC runtime objects: the destructor-helper "completed" flag at
    `0x240016A0` (used by `0x080202a0`) and the frame-info object at
    `0x240016A4` (used by `FUN_080202c4`) (HIGH CONFIDENCE).

  So the `.bss` output section is aligned to at least 16 bytes, most
  likely 32. That is typical of cache-line-aligned DMA buffers on the
  Cortex-M7; which object forces it is not identified. The Main Unit,
  whose `.bss` needs only 8-byte alignment, has no such gap. The
  earlier comparison with the X6100 runtime-array words does not apply.
  The 16 bytes after the `.data` load image in flash are zero padding as
  well.

## MPU, caches and RAM use — VERIFIED unless noted

**MPU** (set up in `main` `FUN_08021e74`). All regions have full access
and execute permission, no subregions, and PRIVDEFENA:

| Region | Base | Size | Attributes |
| --- | --- | --- | --- |
| R0 | DTCM `0x20000000` | 128 KiB | write-back write-allocate (no effect on a TCM) |
| R1 | AXI `0x24000000` | 512 KiB | write-back write-allocate |
| R2 | D2 `0x30000000` | 512 KiB | write-back write-allocate (larger than the 288 KiB D2; D2 is unused) |
| R3 | SRAM4 `0x38000000` | 64 KiB | normal, non-cacheable |
| R4 | SDRAM `0xC0000000` | 32 MiB | normal, write-through, no write-allocate |

**Cache maintenance.** No cache maintenance instructions were found
(HIGH CONFIDENCE). That is safe here: every peripheral-DMA buffer sits
in non-cacheable SRAM4, and the framebuffer is write-through.

**Heap and stack.** `_sbrk` is `FUN_08022944`. The heap starts at
`0x240614A8` and may grow to `0x24080000` − 0x4000, so the stack always
has at least 16 KiB and the heap at most 109 400 B. Nothing is placed in
ITCM, DTCM or D2 SRAM.

**Buffer placement:**

| Address | Region | Content |
| --- | --- | --- |
| `0x38000000` / `0x38001000` | SRAM4 | SLIP RX ring (4 KiB) / TX encoded |
| `0x38003000` | SRAM4 | Bluetooth USART1 RX ring (1 KiB) |
| `0x38003400` / `0x38004400` | SRAM4 | I²S2 RX / TX (4 KiB each) |
| `0xC0000000` | SDRAM | framebuffer (write-through for LTDC/DMA2D) |

Open: whether the SDMMC internal DMA writes into cacheable AXI buffers
without cache maintenance, which would be a coherency risk.

## RAM objects — HIGH CONFIDENCE unless noted

**UI state (VERIFIED).** The UI state struct is 0xBD0 bytes. Three
instances are filled with the same compiled defaults at boot: live
`0x2400AEB8` (the config.ini and SLIP `0x01` source, accessor
`FUN_0803e754`), defaults `0x24009718` (source for restore-default) and
the GUI's last-drawn copy `0x2400A2E8` (redraw-on-change).

The key globals (42 objects) are listed in `analysis/memory/ram_objects.csv`.
Sizes marked ≤ are upper bounds.

**emWin.** The GUI context is at `0x24000038`. Its private `.bss`
(`0x240016BC`–`0x24001ABC`) sits at the start of `.bss`, which is the
likely source of the 32-byte `.bss` alignment (HYPOTHESIS). The emWin
memory pool is in SDRAM at `0xC0800000` (MEDIUM).

**Other objects:**
- newlib `_impure_ptr` (`0x24001648`);
- the FatFS volume objects (`0x240075CC`, `0x24007808`);
- the USB device handle (`0x24007CDC`);
- the 1024×600 RGB565 framebuffer at `0xC0000000` (1 228 800 B).
