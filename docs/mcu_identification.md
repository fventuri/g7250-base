# MCU identification

**Conclusion: both G7250 MCUs are STM32H7 family (Cortex-M7), not
STM32F427. VERIFIED.**

Upgraded from HIGH CONFIDENCE to VERIFIED once both SystemInit routines
were decompiled: they drive STM32H7-only peripheral base addresses and
contain the H7-specific AXI-SRAM errata workaround (see below).

## Peripheral bases (VERIFIED, from SystemInit literals)

Resolved from the reset/SystemInit literal pools (main `0x08023C60`+,
control `0x08022A54`+). Every one is an STM32H7 base; none matches F4:

| Peripheral | Address (both units) | STM32F4 equivalent |
| --- | --- | --- |
| Cortex-M SCB | `0xE000ED00` | same (CPACR @+0x88, VTOR @+0x08) |
| RCC | `0x58024400` | `0x40023800` — differs |
| PWR | `0x58024800` | `0x40007000` — differs |
| FLASH | `0x52002000` | `0x40023C00` — differs |
| DBGMCU IDCODE | `0x5C001000` | `0xE0042000` — differs |
| AXI interconnect (GPV) | `0x51008000` | n/a on F4 |

The control-unit SystemInit applies the STM32H7 rev-Y workaround
`*(uint32_t*)0x51008108 = 1` guarded by a `DBGMCU->IDCODE` revision
check — an H7-specific CMSIS code path with no F4 analogue.

## Original reset-vector evidence

Reset vectors (first two words of each image), VERIFIED:

| Unit | Initial MSP | Reset handler |
| --- | --- | --- |
| Main | `0x24050000` | `0x08024554` |
| Control | `0x24080000` | `0x080235AC` |

1. **AXI SRAM at `0x24000000`.** Both initial stack pointers lie in the
   `0x24000000` region. On STM32F4 (including F427) SRAM is at
   `0x20000000` and CCMRAM at `0x10000000`; there is no memory at
   `0x24000000`. On STM32H7, `0x24000000` is the D1-domain AXI SRAM.
2. **512 KiB boundary.** The Control Unit MSP `0x24080000` is exactly
   `0x24000000 + 0x80000` — the top of the 512 KiB AXI SRAM on
   H742/H743/H750/H753-class parts.
3. **Standard ARM GCC startup** in both reset handlers (load SP,
   SystemInit, copy `.data`, clear `.bss`, `__libc_init_array`, main),
   consistent with STM32 HAL/CMSIS firmware.

## Open

- Exact part number (H743 vs H750 vs H753 vs H7A3/H7B3) not yet confirmed
  from hardware. This affects flash size, RAM sizes beyond AXI SRAM, and
  peripheral availability. Confirm from PCB markings.
- The Ghidra RAM map (`ghidra_scripts/MapSTM32H7Memory.java`) currently
  assumes an H743/H750/H753-class layout.

## Impact vs. the X6100 project

- Ghidra language is the same (`ARM:LE:32:Cortex`, Thumb-2, LE), so the
  import flow and most export scripts port directly.
- Peripheral register addresses differ between STM32F4 and STM32H7.
  X6100 (F427) peripheral addresses must **not** be reused without
  re-verification against the H7 memory map.
- Cortex-M7 adds I/D caches and TCM; expect cache/MPU/TCM setup in early
  startup that the M4-based X6100 does not have.
