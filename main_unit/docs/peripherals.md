# Main Unit — peripherals

MCU: STM32H7 (Cortex-M7). Evidence: active interrupt vectors
(`analysis/interrupts/active_irqs.csv`), peripheral register accesses
(`analysis/peripherals/peripheral_accesses.csv`), and literal references
to peripheral base addresses. IRQ numbers use the **STM32H7** NVIC table
(differs from the STM32F4 used by the X6100).

## Active interrupts (→ H7 peripheral)

| IRQ | Handler | H7 peripheral | Inferred role | Conf |
| ---: | --- | --- | --- | --- |
| 3 | `FUN_080222dc` | RTC_WKUP | wakeup timer | HIGH |
| 9 | `FUN_08023584` | EXTI3 | external signal line | HIGH |
| 10 | `FUN_0802358c` | EXTI4 | external signal line | HIGH |
| 11 | `FUN_08023b20` | DMA1_Stream0 | DMA (audio/ADC/UART) | HIGH |
| 15 | `FUN_08023594` | DMA1_Stream4 | DMA | HIGH |
| 16 | `FUN_08023b34` | DMA1_Stream5 | DMA | HIGH |
| 18 | `FUN_080235a0` | ADC1/ADC2 | analog metering | HIGH |
| 23 | `FUN_080235b4` | EXTI9_5 | external signal lines 5–9 | HIGH |
| 38 | `FUN_080235bc` | **USART2** | **inter-MCU SLIP link** | HIGH |
| 40 | `FUN_080235c8` | EXTI15_10 | external signal lines 10–15 | HIGH |
| 47 | `FUN_080235e8` | DMA1_Stream7 | DMA | HIGH |
| 50 | `FUN_080239c8` | TIM5 | periodic service | HIGH |
| 54 | `FUN_080239e0` | TIM6_DAC | time base / DAC trigger | HIGH |
| 55 | `FUN_08023a48` | TIM7 | time base | HIGH |
| 68 | `FUN_08023a64` | DMA2_Stream5 | DMA | HIGH |
| 86 | `FUN_08023a78` | **SPI6** | D3-domain SPI (see below) | HIGH |

IRQ→peripheral mapping is HIGH CONFIDENCE (standard H7 NVIC table);
roles are inferred.

## Buses and peripherals in use

From base-address references and register-access counts:

| Peripheral | Evidence | Role (candidate) | Conf |
| --- | --- | --- | --- |
| **I2C1** | init `FUN_080218b4`; 13 driver funcs | EEPROM + AXP223 PMIC + VersaClock 6 (see I2C section) | VERIFIED |
| I2C2, I2C3 | init only | initialized but unused by any driver (idle/reserved) | HIGH |
| SPI1/2/3, **SPI6** | base refs; SPI6 has active IRQ86 | audio I²S + SPI; SPI6 (D3) likely CH394 Ethernet or a codec/ADC | MED |
| **USART2** | IRQ38 + DMA | inter-MCU SLIP link (↔ Control USART2) | HIGH |
| USART1 | base refs (×6) | debug console / CAT | MED |
| **ADC1/2 + ADC3** | IRQ18 + 27/41 accesses | RF metering: fwd/ref power, SWR, Vext, temp, S-meter | HIGH |
| TIM5/6/7 | active IRQs | time bases / DAC & audio triggers | HIGH |
| **USB_OTG_FS** | base ref ×32 | USB device — role unclear: the **Main Unit has no external USB connector** (manual), so this is **not** the PC CAT/audio port (that is on the Controller, CH342). Vestigial / internal / FW-update? | LOW |
| **FMC @ 0xC0000000** | ×65 refs | external SDRAM (DSP / streaming buffers) | HIGH |
| DMA1 (str0/4/5/7), DMA2 (str5) | active IRQs | peripheral DMA | HIGH |
| GPIOA/B/E/G/H | heavy GPIOE/G access | RF band switching, PA control, discretes | HIGH |
| RTC, IWDG1, EXTI | accesses + IRQs | wakeup, watchdog, external lines | HIGH |

Note: SPI/I2C/SAI/UART are driven through HAL handle structs, so their
register-access counts understate real usage; base-address references
and IRQs are the reliable signal.

## I2C devices — VERIFIED

All application I2C traffic is on **I2C1** (handle `0x24004F38`). I2C2 and
I2C3 are initialized (`FUN_08021920` / `FUN_0802198c`) but **no driver
uses them** — idle/reserved (vestigial X6100 topology, or strapped-only).

I2C transfer helpers: read `FUN_0802BB3C(handle, devAddr, memAddr,
addrSize, buf, len, timeout)`, write `FUN_0802B940(...)`. `devAddr` is the
8-bit (`<<1`) address written to `I2C_CR2.SADD`.

| 7-bit | 8-bit | Device | Evidence | Conf |
| ---: | ---: | --- | --- | --- |
| `0x50` | `0xA0` | 24Cxx **EEPROM** | NVPARAM (settings 424 B + header/checksum), calibration, ATU data; backup-SRAM (`0x38800000`) cached; strings `EEPROM NVPARAM Saved`, `Read EEPROM error` | VERIFIED |
| `0x34` | `0x68` | **AXP223 PMIC** | strings `axp223 (0x68) write reg`, `Set ALDO1/DCDC1/2/3/5/DLDO1 Vout`, `Init PSU`; driver `FUN_0804a8e8` | VERIFIED |
| `0x6A`* | `0xD4`* | **VersaClock 6** clock generator | strings `vc6clkgen(%02X): write init table ok`; driver `FUN_0804abbc` bus-scans then writes a 112-B (`0x70`) register init table | VERIFIED (addr auto-scanned; 0x6A default) |

\* VersaClock address is auto-detected by a bus scan; `0x6A` is the
5P49V6xxx default.

### vs. X6100

- **No battery** (G7250 is mains/PSU powered): the X6100's **MAX17205
  fuel gauge (0x36) is absent**; instead an **AXP223 PMIC (0x34)**
  generates the rails. This is the main I2C topology difference.
- The **VersaClock 6** clock generator carries over from the X6100
  (which used a 5P49V60 at 0x6A) — LO / sample-clock synthesis.
- The X6100 audio/I-Q codecs (CS4272 0x10, TLV320AIC3204 0x18) are **not
  on main I2C1**. The audio/I-Q path control is elsewhere (SPI/I2S, or the
  Control Unit) — open.
- NV storage via 24Cxx EEPROM + backup-SRAM cache (the X6100 kept
  calibration in flash).

## Differences vs. X6100

- MCU is STM32H7/M7 (vs. F427/M4): different NVIC table and peripheral
  map; adds caches, FMC external SDRAM, LTDC-class peripherals.
- **Networking:** CH394 Ethernet (**LAN connector is on the Main Unit**,
  per the manual) + wfview remote (no X6100 equivalent). SPI6 is a strong
  candidate for the CH394 link. The PC CAT/audio USB is on the
  **Controller** (CH342), not here — see `docs/hardware.md`.
- **Power:** no battery (mains/PSU) → AXP223 PMIC replaces the X6100
  MAX17205 fuel gauge. Only I2C1 is actively used (I2C2/I2C3 idle).
- Retains the X6100's VersaClock-family clock generator.
