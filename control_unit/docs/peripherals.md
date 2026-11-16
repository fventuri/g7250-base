# Control Unit — peripherals

MCU: STM32H7 (Cortex-M7). This is the touchscreen front panel. Evidence:
active interrupt vectors, peripheral register accesses, base-address
references, and boot-log strings (see `docs/flow.md`). IRQ numbers use
the **STM32H7** NVIC table.

## Active interrupts (→ H7 peripheral)

| IRQ | Handler | H7 peripheral | Inferred role | Conf |
| ---: | --- | --- | --- | --- |
| 8 | `FUN_08022780` | EXTI2 | **GT911 touch INT on PE2** | VERIFIED |
| 11 | `FUN_0802275c` | DMA1_Stream0 | DMA (I2C/SPI/audio) | HIGH |
| 12 | `FUN_08022768` | DMA1_Stream1 | DMA | HIGH |
| 13 | `FUN_08022774` | DMA1_Stream2 | DMA | HIGH |
| 29 | `FUN_08022790` | **TIM3** | GT911 touch poll service | HIGH |
| 38 | `FUN_080227a4` | **USART2** | **inter-MCU SLIP link** | HIGH |
| 44 | `FUN_080227b0` | TIM8_UP / **TIM13** | SLIP client service | HIGH |
| 45 | `FUN_080227cc` | TIM8_TRG_COM / **TIM14** | InputDev service | HIGH |
| 46 | `FUN_08022840` | TIM8_CC | mic service (TIM8) — reads the **H-22** mic keypad over the MIC MDATA/MSVSW serial lines; "hm133" is the legacy internal name | HIGH |
| 49 | `FUN_08022880` | **SDMMC1** | SD card (FatFS) | HIGH |
| 50 | `FUN_0802288c` | **TIM5** | Audio service | HIGH |
| 55 | `FUN_080228a0` | TIM7 | time base | HIGH |
| 88 | `FUN_080228b4` | **LTDC** | TFT display controller | HIGH |
| 101 | `FUN_080228c0` | OTG_FS | USB device (mass storage) | HIGH |

The TIM assignments corroborate the boot-log services exactly (TIM13
SLIP, TIM14 InputDev, TIM3 GT911, TIM5 audio) — strong cross-check on
the H7 IRQ numbering.

## Buses and peripherals in use

| Peripheral | Evidence | Role | Conf |
| --- | --- | --- | --- |
| **I2C1** | 217 direct accesses, IRQ-less (polled) | **GT911 capacitive touch @ 0x5D** (VERIFIED) + possibly others | HIGH |
| I2C2 | base refs | auxiliary I2C | MED |
| **LTDC** | base refs + IRQ88 | TFT panel controller | HIGH |
| **FMC @ 0xC0000000** | ×41 refs + MPU region | external SDRAM framebuffer | HIGH |
| **DMA2D** | 65 accesses | Chrom-ART 2D graphics accelerator (UI) | HIGH |
| **SDMMC1** | base refs + IRQ49 | SD card (config.ini on `1:/`) | HIGH |
| SPI2 = I²S2 | init `FUN_08021680`; PB12–PB15 AF5; DMA1 S0 RX / S1 TX circular | audio link to the Control AIC3204 (slave side) | VERIFIED |
| SPI1, SPI5 | SPI1 on PB3–PB5; SPI5 base refs | SPI1 = SPI flash for FatFS (HYPOTHESIS); SPI5 TBD | MED |
| **USART2** | IRQ38; PD5/PD6 AF7; 460 800 8N1; DMA1 S2 TX / S3 RX circular | inter-MCU SLIP link (↔ Main USART2) | VERIFIED |
| USART1 | init `FUN_08023234`; PA9/PA10 AF7; 115 200 8N1; RX DMA1 S4 circular | **Bluetooth module (AT commands)** | VERIFIED |
| **USB_OTG_FS** | base ref ×52 | **PC USB** (manual): CAT/control + **audio sound card** (digital-mode line-in) + firmware update; PC driver **CH342**. N1MM CW keying | HIGH |
| TIM2/3/5/7/8/13/14 | active IRQs + strings | service timers (touch, encoders, audio, SLIP, input) | HIGH |
| GPIOA/B/C/E/H/I | heavy GPIO access | panel discretes, display/touch control | HIGH |
| EXTI2, RTC, IWDG1, CRC | accesses + IRQ8 | touch INT, RTC, watchdog, CRC | HIGH |

## I2C slaves

| Bus | Addr (7-bit) | Device | Evidence | Conf |
| --- | --- | --- | --- | --- |
| I2C1 | **0x5D** | GT911 capacitive touch controller | `I2C_CR2` SADD in `FUN_08035034` (gt911_init): `CR2=0x020020BA` → `0xBA>>1=0x5D`; GT911 default | VERIFIED |

GT911 driver: init `FUN_08035034`, transfer `FUN_08034ec4`, GPIO/clock
`FUN_08021414`. Other I2C1/I2C2 devices (if any) not yet enumerated.

## Differences vs. X6100

The X6100 has no separate touchscreen-panel MCU. The Control Unit is a
new subsystem: GT911 touch, LTDC + FMC SDRAM + DMA2D graphics, SDMMC SD
card, rotary encoders, H-22 mic, and the PC-facing USB (CH342) — a full
GUI front end driving the Main Unit over SLIP. External connectors and
the full menu/parameter set are in `docs/hardware.md`.

## GPIO pin map — register values VERIFIED, roles as noted

**Method.** HAL_GPIO_Init on this unit is `FUN_08026d80` (it also
programs SYSCFG EXTICR and the EXTI trigger/mask registers). The
write and read helpers are `FUN_080271a4` / `FUN_08027198`. The full
table is `analysis/peripherals/gpio_map.csv`.

**Highlights:**
- **FMC SDRAM (`FUN_08020f38`, AF12).** 16-bit data, A0–A12, BA0/1 and
  NBL0/1 on SDRAM bank 1. Data pins: PD0/1, PD8–10, PD14/15, PE0/1 and
  PE7–15. Address pins: PF0–5, PF11–15, PG0–2, PG4/5 and PG15. Strobes:
  PG8 SDCLK, PC0 SDNWE, PC3 SDCKE0, PH3 SDNE0.
- **LTDC (`FUN_08021928`).** 16-bit RGB565 with HSYNC on PI10, VSYNC on
  PI9, DE on PF10 and the pixel clock on PG7.
- **SDMMC1.** 4-bit, on PC8–PC12 and PD2.
- **GT911 touch (VERIFIED).** INT on PE2 (EXTI2, rising edge), RST on
  PG14, held low for 20 ms.
- **Encoder.** TIM2 in encoder mode on PA5/PA1, probably the main dial
  (HIGH CONFIDENCE).
- **PWM.** TIM4 CH1/CH2 on PD12/PD13, started during display bring-up
  (backlight? HYPOTHESIS).
- **Key matrix (MEDIUM CONFIDENCE).** `FUN_08035f80` scans open-drain
  lines with pull-ups and reads them back: PA2, PA7, PB2, PC4, PC5,
  PC13, PH6, PH7, PH9 and PI8.
- **SPI and I²S.**
  - SPI1 on PB3–PB5 (with MISO). A log line about a FatFS init on SPI
    suggests an SPI flash (HYPOTHESIS).
  - SPI2 runs as I²S2 on PB12–PB15: full-duplex, with circular 32-bit
    DMA on DMA1 Stream0 (RX) and Stream1 (TX).
- **Audio codec reset on PH2 (HIGH CONFIDENCE).** It is held low for
  100 ms, then the codec is initialised for 48 kHz/32-bit, with the
  same sequence the Main Unit uses. **The Control Unit therefore has
  its own audio codec.**
- **USB.** USB_OTG_FS is on PA11/PA12 (AF10), clocked from HSI48, with
  IRQ101. The MCU drives its own USB port, so the note that the PC USB
  goes through a CH342 needs re-checking.
- **UARTs.** USART1 on PA9/PA10, USART2 (SLIP) on PD5/PD6.

**Why this needed the firmware:** no schematic is public. The
datasheet lists only possible pin functions.

## USART1 — Bluetooth module (XG-BT-G7250), VERIFIED unless noted

**Link.** USART1 (PA9 TX / PA10 RX, AF7) runs at 115 200 8N1.
Reception uses circular DMA1 Stream4 (request 41) into a 1 KiB ring at
`0x38003000` (SRAM4), started by `FUN_080332dc` and drained by polling
from the superloop task `FUN_080332c8`. There is no USART1 IRQ, and
transmission is blocking.

**Protocol: line-based AT commands.** Each command is "AT" + command +
arguments + CR LF, and the driver expects an "OK" line. Each command
has a 3 s timeout, 5 retries and a completion callback. Lines with an
unsolicited-message prefix go to a handler that is empty in V1.0.1.

**Commands.**
- `+BD<name>` sets the device name (under 32 characters; defaults to
  the module name).
- `+CZ`, `+B4` with argument `00`, and `+CW` take no other arguments.
  Their meaning is a HYPOTHESIS: they look like a vendor BT-audio
  module command set.

No command reads the address or the link status back, so the
Bluetooth settings page shows placeholders (MEDIUM CONFIDENCE).

**Power (HIGH CONFIDENCE).** Module power is bit 4 of a PCA9557 I2C GPIO
expander (I2C2, 7-bit 0x19, reset PG3). BT-on (`FUN_08033248`) sets
the bit and queues the name command. BT-off (`FUN_08033230`) clears it
and flushes the queue. At boot `FUN_080447d8` applies the stored enable
setting.

**Audio (MEDIUM CONFIDENCE).** There is no digital audio link to the
module: no SAI, I²S2 belongs to the codec, and USART1 carries only AT
text. BT audio presumably runs analog through the Control Unit audio
codec (HYPOTHESIS). Bluetooth is handled entirely on the Control Unit;
there is no SLIP message for it (HIGH CONFIDENCE).

**Why this needed the firmware:** the manual names only the module. The
UART, pins, DMA, AT dialect, timeouts and the power switch on the
expander exist only in the code.

## Audio codec and I²S2 — VERIFIED unless noted

**Second codec.** A second **TLV320AIC3204** sits on **I2C2** at 7-bit
0x18 (`0x40005800`, handle `0x24001B98`), with reset on **PH2**
(`FUN_08052964`). Here the **codec is the I²S master**: its PLL runs
from a 12.288 MHz MCLK, BCLK and WCLK are outputs, and a CLKOUT
divider is enabled (HIGH CONFIDENCE).

**I²S2 on the MCU side** (`FUN_08021680`, MSP in the SPI2 branch) is
an **I²S slave, full-duplex, 32-bit, 48 kHz**, on PB12–PB15 (AF5).
DMA1 Stream0 handles RX (request 39) and Stream1 TX (request 40), both
circular and word-wide; this accounts for IRQs 11 and 12. The 4 KiB
buffers are in SRAM4 (`0x38003400` / `0x38004400`), and the DMA is
started by `FUN_08052830`.

**TIM5 audio service.** `FUN_08050cb0` processes 256-frame blocks: it
passes ADC to DAC with a gain table on the left channel, and offers one
capture hook and two playback hooks (probably the voice
recorder/player; hook use HYPOTHESIS). `FUN_0804e4e8` applies the codec
settings: right-channel input select and gain, headphone gain, and
PCA9557 bits 6/7 as an audio path switch (HYPOTHESIS).

**USB.** USB_OTG_FS is a **USB mass-storage device**, not a sound card.
The descriptor is VID 0x0483 / PID 0x572A with a bulk-only SCSI
interface. The PC sound card must therefore be a separate USB audio
chip that the firmware does not see (HYPOTHESIS).

**Main↔Control audio (MEDIUM CONFIDENCE).** Audio does not travel over
SLIP: 460 800 baud is too slow for 48 kHz audio, and no message type
carries it. Mic and speaker audio presumably cross the CTRL cable as
analog signals (HYPOTHESIS).

