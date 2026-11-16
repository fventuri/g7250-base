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
| **SPI1** | init `FUN_08023060`, TX-only | two shift-register chains: TX low-pass filter bank + RX front-end/BPF control (see SPI1 section) | HIGH |
| SPI2 | init `FUN_080230c0`, TX-only | initialised, PB13/PB15 configured, **no users** (idle/reserved) | HIGH |
| **SPI3 = I²S3** | init `FUN_08021c78`, DMA1 Str5/Str0 (IRQ16/11) | full-duplex 48 kHz audio/IQ sample stream (see I²S3 section) | VERIFIED |
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
| Prescaler | `/8` from PCLK4 (137.5 MHz), so **SCK ≈ 17.19 MHz** (HIGH CONFIDENCE; assumes the 25 MHz HSE the firmware is built for) |
| Transfer | DMA (BDMA ch0 RX, ch1 TX) + SPI IRQ86 |

**Still open:** which GPIO serves as CS, plus the CH394 reset and
interrupt pins. The log messages mention a hardware reset and edge
detection on the LAN link, so expect a RST GPIO and possibly an EXTI
line. The socket register map is not documented yet. A per-socket
command register and 8 sockets sharing a 16 KB TX/RX pool would fit a
WIZnet-style register model (HYPOTHESIS until traced).

## SPI1 — RF filter/switch shift registers, HIGH CONFIDENCE

SPI1 has no IRQ and no DMA. The init (`FUN_08023060`) sets it up as a
**transmit-only master**: 8-bit, mode 0, software NSS, prescaler /2.
The MSP init (`FUN_0802317c`, SPI1 branch) selects the SPI1/2/3 kernel
clock and puts **PG11** (SCK) and **PD7** (MOSI) in AF5. There is no
MISO pin.

A small device layer drives it (`FUN_08044010` binds a device,
`FUN_08043fe0` writes a frame). Each device has its own SPI handle and
two GPIO callbacks:

- a **latch line**, pulled low before each frame and high after it;
- an **output-enable line**, held inactive during init and made active
  after the first frame is written.

This latch-plus-output-enable pattern, with write-only frames and a
RAM shadow copy, is that of serial-in/parallel-out shift registers of
the 74HC595 kind (chip type: HYPOTHESIS). SPI1 carries two such chains:

| Chain | Shadow | Frame | Latch | Output enable | Driver functions |
| --- | --- | --- | --- | --- | --- |
| A (8 bit) | `0x24017884` | 1 byte | **PA11** | **PA10** | init `FUN_080495a0`; band `FUN_080495d8`; bit 7 `FUN_0804960c` |
| B (24 bit) | `0x24019148` | 3 bytes, MSB first | **PH12** | **PH10** | init `FUN_0804a2f0`; BPF `FUN_0804a430`; others below |

Both chains are written from the band and frequency update path
(`FUN_0803ec3c`, `FUN_0803ebb0`) and from the RX/TX switch-over paths
(`FUN_0803d03c` to RX, `FUN_0803e338` to TX).

**Chain A: TX low-pass filter bank plus T/R line**
- **Bits 0–6** select one filter at a time from the operating
  frequency. Edges: 2, 4, 8, 15, 23, 33 and 60 MHz, giving 7 bands.
  Above 60 MHz no bit is set. (HIGH CONFIDENCE.) These are the usual
  edges of an HF+6 m PA low-pass bank (role: HIGH CONFIDENCE).
- **Bit 7** is set by the switch-to-TX path and cleared by the
  switch-to-RX path, so it is a T/R relay or PA-enable line. (HIGH
  CONFIDENCE.)

**Chain B: RX band-pass bank and front-end switches**
- **Bits 0–15 and 23** select an RX band-pass/preselector segment from
  the frequency (`FUN_0804a430`). Edges are at about 1.6, 2, 3, 4.5,
  6.5, 8, 10, 15, 22, 30, 50, 54 and 70 MHz. A few segments have an
  alternate selection that depends on two caller flags (TX state and
  one other). The firmware only rewrites the chain when the value
  changes. (Mechanism HIGH CONFIDENCE; exact segment edges MEDIUM
  CONFIDENCE.)
- **Bits 16 and 17** are set by operating mode: bit 16 for mode codes
  4, 8 and 9, bit 17 for mode codes 6 and 7, and neither for the
  others. This is probably an IF/filter path per mode. (Mechanism HIGH
  CONFIDENCE; meaning HYPOTHESIS.)
- **Bits 18–20** form a 1-of-3 selector from one TRX-state setting
  (`FUN_0804a370`). **Bits 21–22** form a 2-way selector from another
  setting (`FUN_0804a608`). The switch-to-TX path sets both to the "off"
  value. They are probably the RX attenuator and preamp (HYPOTHESIS).
- **Init value:** bits 17, 20 and 22 set, all others cleared.

## SPI2 — idle, HIGH CONFIDENCE

`FUN_080230c0` initialises SPI2 with the same transmit-only settings
as SPI1, and the MSP init puts PB13 (SCK) and PB15 (MOSI) in AF5. No
code outside init refers to its handle (`0x240054a8`). It is unused
in V1.0.1, possibly reserved for a hardware variant.

## SPI3 = I²S3 — sample stream, VERIFIED (peer device: see audio item)

SPI3 runs in **I²S mode**: init `FUN_08021c78` (HAL I²S init
`FUN_0802bde8`), MSP init `FUN_08021ccc`.

| Parameter | Value |
| --- | --- |
| Mode | **master, full-duplex** |
| Standard | Philips I²S, clock polarity low, MSB first |
| Data format | 32-bit data field |
| Audio frequency | **48 kHz** |
| MCLK output | disabled |
| Kernel clock | SPI1/2/3 mux set to the external clock pin I2S_CKIN (HIGH CONFIDENCE; value 3 of the mux). SPI1 and SPI2 share this mux |
| Pins (AF6, very high speed, pull-up) | **PA15** WS, **PC10** CK, **PC11** SDI, **PC12** SDO |
| TX DMA | **DMA1 Stream5**, request 62 (SPI3_TX), mem→periph, half-word, **circular**, very high priority, IRQ16 |
| RX DMA | **DMA1 Stream0**, request 61 (SPI3_RX), periph→mem, word, **circular**, very high priority, IRQ11 |

The stream starts in `FUN_08035fac` (called from `FUN_0803e2f4`). It
clears two 3 KiB buffers and starts a full-duplex DMA transfer over
both. Half-transfer and transfer-complete callbacks
(`FUN_08035ed4`, `FUN_08035f40`) set ping-pong flags for the audio/DSP
code. This explains the active IRQs 11 and 16 and accounts for
DMA1 Streams 0 and 5.

**Why this needed the firmware:** no G7250 schematic is public. The
STM32 datasheet only lists possible pin functions. The filter edges,
the shift-register bit assignment, the latch/enable pins and the I²S
format exist only in the firmware's behaviour.

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
| `0x68`/`0x6A`* | `0xD0`/`0xD4`* | **VersaClock 6** clock generator | driver `FUN_0804abbc` logs a successful init-table write; it tries both addresses, then writes a 112-B (`0x70`) register init table | VERIFIED |

\* The VersaClock driver tries 0x68 first, then 0x6A (see the
VersaClock 6 output plan below).

### AXP223 rail plan — VERIFIED (use: HYPOTHESIS)

`FUN_0804a8e8` is called from `main` and only ever addresses the 7-bit
address 0x34. It first forces a safe state with only DCDC1 on, then
programs the voltages, waits 10 ms and enables everything in one
write. Each code matches the voltage the driver logs just before it
writes. There is no sequencing between rails. `FUN_0804a854` restores
the safe state; it is called from the shutdown routine `FUN_08021edc`
and before the jump to the bootloader in `FUN_0802200c`.

| Rail | Register / code | Voltage | Enabled | Likely use |
| --- | --- | ---: | :---: | --- |
| DCDC1 | 0x21 / 0x11 | 3.3 V | yes (also in safe state) | MCU 3.3 V (MEDIUM) |
| DCDC2 | 0x22 / 0x1E | 1.2 V | yes | FPGA core (HYPOTHESIS) |
| DCDC3 | 0x23 / 0x3C | 1.8 V | yes | FPGA/converter 1.8 V (HYPOTHESIS) |
| DCDC5 | 0x25 / 0x1E | 2.5 V | yes | FPGA aux / LVDS bank (HYPOTHESIS) |
| ALDO1 | 0x28 / 0x1A | 3.3 V | yes | analog/clock 3.3 V (HYPOTHESIS) |
| DLDO1 | 0x15 / 0x0B | 1.8 V | yes | analog 1.8 V (HYPOTHESIS) |
| DCDC4, DC5LDO, ALDO2/3, ELDO1–3, DLDO2–4, DC1SW | — | — | off | unused |

The enables are reg 0x10 = 0x6E and reg 0x12 = 0x08, decoded with the
public AXP22x bit layout (HIGH CONFIDENCE). Reg 0x13 bit 0 is set; its
meaning is a HYPOTHESIS. Per-rail values are in
`analysis/peripherals/axp223_rails.csv`.

### VersaClock 6 output plan — HIGH (frequency MEDIUM)

`FUN_0804abbc` (called from `FUN_0804ae68`) writes registers 0x00–0x6F
in one burst from a 112-byte table in flash at `0x0807F840`. It tries
the 7-bit address **0x68 first**, then 0x6A, so the earlier "0x6A" is
only the fallback. No code reprograms the chip later.

- **Reference:** crystal input; CLKIN and the doubler are off; the
  divide-by-2 pre-divider is selected. The PLL feedback is integer 222
  with no fraction, so VCO = 111 × Fref. (HIGH CONFIDENCE.)
- **Dividers:** FOD1 is a fractional divider of 11.7431640625, without
  spread spectrum. FOD2–4 are disabled. (HIGH CONFIDENCE.)
- **Outputs:** OUT1 is LVDS at 3.3 V and enabled. OUT2–4 are set up as
  3.3 V CMOS, but their buffers are off. (OUT1 HIGH CONFIDENCE,
  OUT2–4 MEDIUM CONFIDENCE.)
- **Frequency:** a 26 MHz crystal gives VCO = 2886 MHz and
  **OUT1 = 245.76 MHz**, exactly 5120 × 48 kHz. Other common crystals
  give no round value. (MEDIUM CONFIDENCE.) If the output stage halves
  the divider output, OUT1 is 122.88 MHz instead (HYPOTHESIS).
- **Role:** the chip has a single output, and it is **not** the MCU's
  HSE: it is far above the HSE limit, and the chip is programmed after
  the MCU clocks are up. It is the sample clock for the FPGA or the
  data converters (MEDIUM CONFIDENCE). The I²S3 kernel clock on
  I2S_CKIN is then most likely derived from it by the FPGA
  (HYPOTHESIS). Decoded values are in
  `analysis/peripherals/vc6_clock_plan.csv`.

**Why this needed the firmware:** both chips are programmed over I2C
or from OTP. Their datasheets give register maps only. The voltages,
enables, divider plan and output types exist only in the init code and
table.

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
