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
| 86 | `FUN_08023a78` | **SPI6** | **CH394 Ethernet** (see SPI6 section) | VERIFIED |

IRQ→peripheral mapping is HIGH CONFIDENCE (standard H7 NVIC table);
roles are inferred.

## Buses and peripherals in use

From base-address references and register-access counts:

| Peripheral | Evidence | Role (candidate) | Conf |
| --- | --- | --- | --- |
| **I2C1** | init `FUN_080218b4`; 13 driver funcs | EEPROM + AXP223 PMIC + VersaClock 6 (see I2C section) | VERIFIED |
| I2C2, I2C3 | init only | initialized but unused by any driver (idle/reserved) | HIGH |
| **SPI6** | init `FUN_08023120`, MSP in `FUN_0802317c`, IRQ86, BDMA ch0/ch1 | **WCH CH394 SPI-Ethernet**, exclusive bus (see SPI6 section) | VERIFIED |
| SPI1/2/3 | base refs; no active IRQ | audio I²S + SPI (open) | MED |
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

## SPI6 — WCH CH394 Ethernet, VERIFIED

SPI6 (D3 domain, `0x58001400`) drives the **CH394** SPI-Ethernet
controller behind the LAN connector, and nothing else.
Addresses and values: `analysis/peripherals/spi6_ch394.csv`.

**Evidence chain:**

1. **The init function is `FUN_08023120`** (called from `FUN_0802239c`).
   It fills the HAL handle at **`0x24005420`** with `Instance = SPI6`
   and calls `FUN_0802ebb0` (HAL_SPI_Init).
2. **The MSP init (`FUN_0802317c`, SPI6 branch) does the following:**
   - selects the SPI6 kernel clock (`PeriphClockSelection = 0x4000`,
     source 0 = PCLK4);
   - sets `RCC_APB4ENR.SPI6EN` (bit 5) and enables the GPIOG clock;
   - puts **PG12/PG13/PG14** in AF5, push-pull. On the H7 that is
     SPI6 MISO/SCK/MOSI;
   - links two BDMA channels: **BDMA_Channel0** (`0x58025408`) with
     request **11** = SPI6_RX (periph→mem) and **BDMA_Channel1**
     (`0x5802541C`) with request **12** = SPI6_TX (mem→periph). Both
     are byte-wide, with memory increment, normal mode;
   - sets the NVIC for **IRQ86** to priority 13 and enables it.
3. **The IRQ86 vector `0x08023a78` is a two-instruction stub:** it
   loads `0x24005420` and branches to `0x0802f570`, the HAL SPI IRQ
   dispatcher.
4. **Every function that refers to the handle `0x24005420`, other than
   the init and IRQ code, lies in one contiguous driver cluster**
   (`0x080450c8`–`0x08048d6f`, 26 functions). Every log message in that
   cluster carries the CH394 tag. Between them they report the chip
   version and MAC address, PHY and link state, opening and closing UDP
   sockets, reallocating socket buffers, a hardware reset, and errors on
   SPI write verification, stuck DMA transmits and stuck receives. Three
   of the functions that print these messages (`FUN_080487d4` chip
   version, `FUN_08047abc` write verification, `FUN_080455dc` TX DMA)
   use the handle directly.
5. **No other driver uses the handle,** so the bus serves only the
   CH394 (VERIFIED for references through literal pools).

**Why this needed the firmware:** the STM32H7 datasheet only lists the
pins SPI6 *can* use, and the CH394 datasheet only describes the chip.
Neither says that the G7250 wires the CH394 to SPI6, which pins and DMA
channels it uses, what the bus settings are, or that the bus carries
nothing else. No schematic of the G7250 has been published, and no
hardware was on hand for measurements.

**Link parameters (handle init), VERIFIED:**

| Field | Value |
| --- | --- |
| Role | master, full-duplex (2 lines) |
| Frame | 8-bit, MSB first, mode 0 (CPOL 0, CPHA 0), no CRC, no TI mode |
| NSS | software (`SSM`); NSS pulse mode set in the init struct; **no NSS pin in AF** → CS is a GPIO |
| Prescaler | `/8` from the SPI6 kernel clock (PCLK4); absolute SCK rate open until SYSCLK/PCLK4 is known |
| Transfer | DMA (BDMA ch0 RX, ch1 TX) + SPI IRQ86 |

**Still open:** which GPIO serves as CS, plus the CH394 reset and
interrupt pins. The log messages mention a hardware reset and edge
detection on the LAN link, so expect a RST GPIO and possibly an EXTI
line. The socket register map is not documented yet. A per-socket
command register and 8 sockets sharing a 16 KB TX/RX pool would fit a
WIZnet-style register model (HYPOTHESIS until traced).

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
  per the manual) + wfview remote (no X6100 equivalent). The CH394 sits
  on **SPI6** with BDMA (VERIFIED, see SPI6 section). The PC CAT/audio USB is on the
  **Controller** (CH342), not here — see `docs/hardware.md`.
- **Power:** no battery (mains/PSU) → AXP223 PMIC replaces the X6100
  MAX17205 fuel gauge. Only I2C1 is actively used (I2C2/I2C3 idle).
- Retains the X6100's VersaClock-family clock generator.
