# Main Unit — Startup

Image: `G7250_MainUnit_Fw_V1.0.1.bin` · load base `0x08020000`
Evidence: `main_unit/analysis/startup/`

## Vector table (core entries)

| Entry | Value | Meaning | Confidence |
| --- | --- | --- | --- |
| `vector[0]` | `0x24050000` | Initial MSP (AXI SRAM) | VERIFIED |
| `vector[1]` | `0x08024555` | Reset_Handler (Thumb → `0x08024554`) | VERIFIED |

The initial MSP in AXI SRAM (`0x24000000` region) is the primary
evidence for the STM32H7 family (see README). VERIFIED.

## Reset handler — `FUN_08024554`

Standard ARM GCC startup, VERIFIED from disassembly
(`reset_disassembly.txt`):

```
ldr sp, =0x24050000      ; initial stack pointer (AXI SRAM)   VERIFIED
bl  0x08023bd0           ; SystemInit                          VERIFIED (see below)
                          ; copy .data  0x24000000..0x24004C58 <- 0x0808486C
                          ; clear .bss  0x24004C58..0x24035C20
bl  0x0805407c           ; __libc_init_array                   VERIFIED
bl  0x0802239c           ; main (candidate)                    HIGH CONFIDENCE
bx  lr
```

Chain:

    Reset_Handler
        -> SystemInit            FUN_08023bd0   VERIFIED
        -> copy .data / clear .bss              VERIFIED (see memory_map.md)
        -> __libc_init_array     FUN_0805407c   VERIFIED
        -> main                  FUN_0802239c   HIGH CONFIDENCE (candidate)

## SystemInit — `FUN_08023bd0` (VERIFIED STM32H7 CMSIS)

Evidence: `startup_call_1_08023bd0_decompile.c`, literals in
`data_init_words.csv` / `0x08023c60`+. Resolved register bases (all
STM32H7, VERIFIED):

| Literal | Value | Register |
| --- | --- | --- |
| `0x08023C60` | `0xE000ED00` | SCB (CPACR @+0x88, VTOR @+0x08) |
| `0x08023C64` | `0x52002000` | FLASH ACR |
| `0x08023C68` | `0x58024400` | RCC |
| `0x08023C6C` | `0xEAF6ED7F` | RCC->CR reset mask |
| `0x08023C7C` | `0x52004000` | FLASH bank2 region |
| `0x08023C80` | `0x08020000` | value written to `SCB->VTOR` |

Behavior: enable FPU (`SCB->CPACR |= 0xF<<20`), set FLASH latency to 7
wait states, `RCC->CR |= HSION`, reset `RCC->CFGR`, mask `RCC->CR`, clear
the D1/D2/D3 bus dividers and PLL config registers, disable RCC
interrupts, set `SCB->VTOR = 0x08020000`. This is the stock STM32H7
CMSIS `SystemInit()`. The FPU/VTOR/RCC base addresses are definitive H7.

`__libc_init_array` (`FUN_0805407c`) VERIFIED: iterates the
`.preinit_array` and `.init_array` pointer tables, calling `_init`
(`FUN_0805aec0`) between them.

`.preinit_array` is empty. `.init_array` = `0x08084860`–`0x08084868`
and has 2 entries: frame_dummy (`0x080202f4`), and a constructor at
`0x0803b414` that enables the DWT cycle counter (the noise-reduction
code reads it for its cycle statistics). VERIFIED: located by the
corrected `ExportStartupEvidence.java`.

Unlike the Control Unit, the Main Unit reset does **not** make a
separate PWR/VOSRDY call before SystemInit.

## Unknowns

- SystemInit does not program the PLL to a running state here; the
  actual clock-up (PLL/SystemClock_Config) must happen later (in `main`
  or a HAL init). Not yet located.
- Whether an RTOS is started inside `main`.

## Exception handlers — VERIFIED

**Default handler.** `0x080245A4` (107 vectors) is a bare infinite loop.

**Load-meter hook.** Every other handler starts by calling a
cycle-counter hook (`FUN_0803adc0`). It feeds a CPU-load meter, which
`FUN_0803ae04` reports about once per second.

**Per-handler behaviour:**
- NMI, MemManage, BusFault and UsageFault then loop forever.
- SVC, DebugMon and PendSV return.
- SysTick runs the HAL tick.
- **HardFault** writes CFSR, HFSR, MMFAR and BFAR, then two words
  labelled PC and LR, to USART1 by direct register polling, and halts.

**Dump bug (HIGH CONFIDENCE).** The HardFault handler reads MSP after
pushing 16 bytes, so the words it labels PC and LR are really the
stacked R2 and R1.

No handler resets the MCU. The HAL timer callbacks are empty: all
periodic work sits in the vector stubs (interrupt paths in `flow.md`,
priorities in `docs/dma.md`).
