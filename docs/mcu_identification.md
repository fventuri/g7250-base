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

## Part number (inferred from firmware; no hardware marking seen)

The two MCUs belong to **different STM32H7 sub-families**.

| Unit | Most likely part | Confidence | Key evidence |
| --- | --- | --- | --- |
| Main | **STM32H725xG** (or H735xG) | MEDIUM | HAL built for a device with TIM23/TIM24 and UART9/USART10, which only H72x/H73x have; SMPS-capable supply code using the SMPS 2.5 V setting; 550 MHz at Scale 0 with VOS = 00 and no overdrive (H72x/H73x encoding); stack top `0x24050000` = 320 KiB AXI SRAM (H72x default); image up to `0x0808EA20` needs the 1 MiB variant |
| Control | **STM32H743xI, revision V** | HIGH | LDO-only supply; Scale 0 via SYSCFG overdrive (H743 rev V method); 480 MHz requires rev V; image runs contiguously to `0x080DEC10`, which needs 2 MiB (bank 1 ≥ 1 MiB); USB OTG_FS at `0x40080000`; LTDC, DMA2D and FMC in use; the GUI library checks for DEV_ID 0x450 |

**Ruled out:**
- H750 and H730: 128 KiB of flash cannot hold the images.
- H7A3/B3: 280 MHz maximum.
- H743 for the Main Unit: 550 MHz and TIM23/24 are impossible on it.
- H723/H733 for the Main Unit: no SMPS (LOW-confidence exclusion).

**Not distinguishable from the firmware:** H725 vs H735, and H743 vs
H753, because crypto is unused. Neither image reads the flash-size
register.

The Main Unit H72x evidence is literal-pool constants for TIM23/24 and
UART9/USART10, which appear only in the Main image. VERIFIED.

**Why this needed the firmware:** no PCB photo or chip marking was
available. Only the binary shows the device header it was built for,
the supply-mode variant, the VOS encoding and the flash/RAM extents.

## Open

- Verify both part numbers against the chip markings.
- `ghidra_scripts/MapSTM32H7Memory.java` assumes an H743-class RAM
  layout. For the Main Unit an H72x layout (AXI 320 KiB, D2 32 KiB)
  would be more accurate.

## Impact vs. the X6100 project

- Ghidra language is the same (`ARM:LE:32:Cortex`, Thumb-2, LE), so the
  import flow and most export scripts port directly.
- Peripheral register addresses differ between STM32F4 and STM32H7.
  X6100 (F427) peripheral addresses must **not** be reused without
  re-verification against the H7 memory map.
- Cortex-M7 adds I/D caches and TCM; expect cache/MPU/TCM setup in early
  startup that the M4-based X6100 does not have.
