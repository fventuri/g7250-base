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
| **I2C1** | 217 direct accesses, IRQ-less (polled) | **GT911 capacitive touch** only (address 0x14, fallback 0x5D; see GT911 driver) | VERIFIED |
| I2C2 | base refs | auxiliary I2C | MED |
| **LTDC** | base refs + IRQ88 | TFT panel controller | HIGH |
| **FMC @ 0xC0000000** | ×41 refs + MPU region | external SDRAM framebuffer | HIGH |
| **DMA2D** | 65 accesses | Chrom-ART 2D graphics accelerator (UI) | HIGH |
| **SDMMC1** | base refs + IRQ49 | SD card, FatFS volume `0:` (voice memories); the configuration lives on the SPI flash `1:` (see storage.md) | HIGH |
| SPI2 = I²S2 | init `FUN_08021680`; PB12–PB15 AF5; DMA1 S0 RX / S1 TX circular | audio link to the Control AIC3204 (slave side) | VERIFIED |
| SPI1 | init `FUN_080225d4`; PB3–PB5 AF5; CS PG13 | **W25Qxx SPI NOR flash** (FatFS `1:` and the USB drive) | VERIFIED |
| SPI5 | no literal, handle or MSP (earlier refs were coincidental bytes) | unused | VERIFIED |
| **USART2** | IRQ38; PD5/PD6 AF7; 460 800 8N1; DMA1 S2 TX / S3 RX circular | inter-MCU SLIP link (↔ Main USART2) | VERIFIED |
| USART1 | init `FUN_08023234`; PA9/PA10 AF7; 115 200 8N1; RX DMA1 S4 circular | **Bluetooth module (AT commands)** | VERIFIED |
| **USB_OTG_FS** | base ref ×52; init `FUN_0803d90c`; IRQ101 | the MCU's own USB port, **mass-storage device** exposing the W25Qxx SPI flash (see USB section). The CAT/sound-card functions the manual names are not in this firmware; they must come from another USB chip (CH342 per the manual) | HIGH |
| TIM2/3/5/7/8/13/14 | active IRQs + strings | service timers (touch, encoders, audio, SLIP, input) | HIGH |
| GPIOA/B/C/E/H/I | heavy GPIO access | panel discretes, display/touch control | HIGH |
| EXTI2, RTC, IWDG1, CRC | accesses + IRQ8 | touch INT, RTC, watchdog, CRC | HIGH |

## I2C slaves

| Bus | Addr (7-bit) | Device | Evidence | Conf |
| --- | --- | --- | --- | --- |
| I2C1 | **0x14** (fallback **0x5D**) | GT911 capacitive touch controller | `gt911_init` (`FUN_08035034`) holds INT high during reset, which selects 0x14, probes 0x14 first and falls back to 0x5D; which one the fitted panel answers cannot be told from code | VERIFIED (probe order) |

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

**USB.** USB_OTG_FS is a USB mass-storage device, not a sound card (see
the USB mass storage section).

**Main↔Control audio (MEDIUM CONFIDENCE).** Audio does not travel over
SLIP: 460 800 baud is too slow for 48 kHz audio, and no message type
carries it. Mic and speaker audio presumably cross the CTRL cable as
analog signals (HYPOTHESIS).

## Timer map — VERIFIED (timer clock 240 MHz)

The table is in `analysis/peripherals/timers.csv`.

| Timer | Setting / rate | Role |
| --- | --- | --- |
| TIM2 | 32-bit encoder mode, one count per 4 edges | main-dial encoder |
| TIM3 | 100 Hz | GT911 poll (started only if the touch init succeeds) |
| TIM4 | 3.66 kHz PWM: CH1 PD12 held near 100 %, CH2 PD13 with an inverted duty set by `FUN_08036578` | backlight enable + dimming (MEDIUM CONFIDENCE) |
| TIM5 | 20 kHz | audio service |
| TIM7 | period reprogrammed to one tenth of a CW dot from the WPM setting (`FUN_080521d0`) | **CW text keyer** element clock; its ISR keys PE3/PE4 (mechanism HIGH CONFIDENCE; that these lines key the Main Unit is a HYPOTHESIS) |
| TIM8 | 30 MHz PWM-input capture on PI5 (period and high time) | H-22 mic-line decoder |
| TIM13 | 50 Hz (20 ms) | SLIP client (this makes the SLIP `0x01` period VERIFIED) |
| TIM14 | 1 kHz | input service |

## USB mass storage and firmware update — HIGH CONFIDENCE

**The disk.** The OTG_FS mass-storage class (`FUN_0803d90c`, VERIFIED)
exposes one writable LUN: the on-board **W25Qxx SPI NOR flash**, in
512-byte blocks.
- The storage callbacks read and write through the W25Qxx driver
  (`FUN_08036e6c` / `FUN_08036e94`).
- The size is detected from the JEDEC ID: 0xEF4014/15/17/18 give 1, 2,
  8 or 16 MiB.
- The same chip is a FatFS volume used by the application. There is no
  arbitration beyond a "flash ready" flag (MEDIUM CONFIDENCE).

**Descriptors (VERIFIED).**
- Device: USB 2.00, **VID 0x0483 / PID 0x572A** (the STM32Cube MSC
  default), one configuration, self-powered, 100 mA.
- One interface: mass storage, SCSI, bulk-only, with bulk endpoints
  0x81/0x01 of 64 bytes.
- **No CDC and no audio class.** The strings are the stock ST example
  names.
- The disk reports "not ready" while the firmware itself is using the
  flash. There is no other locking, so concurrent writes from the PC and
  the firmware could corrupt it (HIGH CONFIDENCE).

**The CH342 and the sound card (HYPOTHESIS, strong).** This port cannot
be the CH342 serial bridge or the sound card the manual describes, and
the Control MCU has no spare UART for a bridge. Both must be separate
chips on the Controller, presumably behind a USB hub that shares the
rear connector. Their serial lines most plausibly reach the Main Unit
UARTs over the CTRL cable.

**No update code in the application** (VERIFIED):
- no update file name;
- no flash programming key;
- no jump to the bootloader.

Its only software reset is the factory-reset path in the UI handler.
A firmware update is therefore done by the bootloader in sector 0
after a reset, presumably from a file the PC copied to this disk
(HYPOTHESIS: file names and checks are not in the application).

## RTC — VERIFIED

**Clock.** The RTC is clocked from LSE (32.768 kHz), giving 1 Hz.

**Backup marker.** Backup register 0 holds the marker 0xA5A5. When the
marker is missing, the clock is set to 00:00:00, 1 January 2000 and the
marker is written, so the time survives resets while the backup domain
stays powered.

**Use.** `FUN_08049bd4` reads the time and date into a seconds count,
and the UI date/time handler (`FUN_0804587c`) sets them. No other
backup register is used, so there is no bootloader flag word.

## H-22 microphone keypad (TIM8, PI5)

**Capture (HIGH CONFIDENCE).** TIM8 (`FUN_08022d40`) runs at 30 MHz
(prescaler 8). Its counter resets on every rising edge at PI5: CH1
captures the period and CH2 the high time. The IRQ46 handler passes
both to the symbol decoder `FUN_08035e2c`.

**Symbols (VERIFIED).** Symbols are ratio-coded, so absolute timing
does not matter. With r = low time / high time:
- r 0.65–1.35 → bit 0;
- r 1.65–2.35 → bit 1;
- r 3.65–4.35 → sync;
- anything else resets the frame.

**Frame (VERIFIED).**
1. At least 7 zero-symbols as preamble.
2. One sync symbol.
3. 39 data bits, LSB first: bits 0–19 form word A, bits 20–38 word B.

The frame is accepted only if bits 12–19 of A equal bits 12–19 of B.
Key code = ((A >> 15) & 0x0F) | ((A >> 6) & 0xF0).

**Key map** (`FUN_080478d0`). The codes are VERIFIED; the legends are
inferred from the actions (MEDIUM). Every new code first plays a
100 ms key beep. The full table is in
`analysis/peripherals/h22_keycodes.csv`.

| Code | Action |
| --- | --- |
| 0x04 / 0x84 | tune down / up by the frequency step |
| 0x11 / 0x12 | band or memory channel down / up |
| 0x48 / 0x44 / 0x13 | user functions F1 / F2 / F3 |
| 0x14 / 0x15 | volume + / − |
| 0x16 | VFO A/B swap |
| 0x24 | home channel |
| 0x81 | V/M toggle |
| 0x28 | enter or leave direct-frequency entry |
| 0xE8 | mode cycle (LSB → USB → CW → AM → SAM → NFM → WFM) |
| 0x17, 0xE1, 0xE2, 0x18–0x1E | digits 0–9 (band select outside direct entry) |

**User functions.** F1/F2/F3 each select one of: AGC, ATT, PRE, band
stack, antenna, filter group, NB, RIT, XIT, SPLIT, VOX, or one of two
per-VFO toggles.

Mic keys are ignored while the SWR scanner or a popup is active.

**Why this needed the firmware:** the H-22 serial format is not
published; only the decoder defines it.

## I2C devices and the PCA9557 expander — VERIFIED unless noted

**Buses.**
- **I2C1:** GT911 touch only (address in the GT911 section).
- **I2C2:** two devices, at about 100 kHz:
  - the AIC3204 codec (0x18), through HAL I2C transmit;
  - a PCA9557 I/O expander (0x19), through HAL I2C memory write.
- **I2C3** is not used. The "I2C3 kernel clock" seen earlier is the
  shared I2C1/2/3 clock mux.

**PCA9557 driver.**
- **Reset and init.** The expander is reset through PG3 (low 1 ms, then
  10 ms settle). It is then configured as all outputs with the value
  0x8B.
- **Writes are deferred.** `FUN_08052b68(mask, on)` changes a shadow
  copy, and the superloop flush `FUN_08052b5c` writes only the registers
  that changed.

| Bit | Boot | Behaviour | Role |
| --- | --- | --- | --- |
| 0, 1, 3 | 1 | never changed | static enables (HYPOTHESIS) |
| 2 | 0 | never changed | unused |
| 4 | 0 | BT-on sets, BT-off clears | Bluetooth module power |
| 5 | 0 | set when Main signals power-off (0x03 flags bit 2), cleared at the end of the Control shutdown | power-down pulse (role HYPOTHESIS) |
| 6 | 0 | 1 while transmitting | TX audio path |
| 7 | 1 | 1 while receiving | RX audio path |

Bits 6/7 follow bit 1 (TX) of the Main status word received in `0x03`
(`FUN_0804e4e8`). The switching is VERIFIED; its analog function is a
HYPOTHESIS. This corrects the earlier note that the audio path switch
followed a menu setting. Values are in
`analysis/peripherals/pca9557_bits.csv`.

## SPI1 — W25Qxx SPI NOR flash, VERIFIED

**Bus.** SPI1 (handle `0x24002080`) runs as master, full-duplex, 8-bit,
mode 0, software NSS, prescaler /2 from PLL1Q, giving **48 MHz SCK**. It
is polled, without DMA. Pins are PB3/PB4/PB5 (AF5), and the chip select
is **PG13**, a GPIO. The device object at `0x24000234` holds the handle,
the CS pin, the JEDEC ID, the size and a 4 KiB sector buffer.

**Commands.**

| Command | Use |
| --- | --- |
| 0x9F | JEDEC ID |
| 0x03 | read (3-byte address, 256-byte chunks) |
| 0x06 | write enable |
| 0x02 | page program (split at 256-byte pages) |
| 0x20 | 4 KiB sector erase |
| 0x05 | status poll on WIP (5 s timeout) |

**Writes.** A write first reads the 4 KiB sector and erases it only if
a bit must go from 0 to 1; otherwise it programs in place.

**Accepted IDs.** 0xEF4014/15/17/18 (1, 2, 8, 16 MiB). 0xEF4016 (W25Q32)
falls into the error path, which is a firmware quirk.

**FatFS glue.** 512-byte sectors and an 8-sector erase block. The drive
number follows the link order: the SD card becomes `0:`, this flash
`1:`.

**Why this needed the firmware:** the CS pin, clock, command set and
accepted parts are not visible from the board.

## GT911 driver — VERIFIED unless noted

All transfers are polled register accesses on I2C1, with 20 ms
cycle-counter timeouts per phase.

**Reset and address.** `gt911_init` (`FUN_08035034`) drives INT (PE2)
high, pulses RST (PG14) low for 20 ms, waits 120 ms and returns PE2 to
an input without pull. INT high at reset selects address **0x14**. The
driver probes 0x14 three times and falls back to 0x5D. The address
found is stored at `0x240001E4`.

**Module info and configuration.**
- It reads the product ID, firmware version and resolution (logged
  only).
- It reads the 186-byte configuration block and checks its checksum:
  the two's complement of the byte sum must match. A mismatch makes the
  init report failure.
- **No configuration is ever written.**

**INT mode.** The firmware reads a trigger-mode field from the
configuration and only logs a warning when it is not "high level". The
bits it tests may not be the documented ones (HYPOTHESIS; harmless,
since it only logs). EXTI2 is always rising edge.

**Calibration.** Commands 3 (baseline update) and 4 (calibrate) are
written, each followed by 100 ms. There is no user calibration.

**Reports** (EXTI2 handler `0x08022780`).
- Each interrupt reads the 42-byte status/point block.
- If the ready bit is set, the handler clears it, takes the touch count
  and stores the points; a change flag is set only when something
  differs.
- Zero points after a touch raise a release event.
- When I2C reads fail ten times in a row, the touch interrupt is
  switched off.

**Long press.** TIM3 (100 Hz) counts a hold timer and queues one
long-press event after about 0.5 s (MEDIUM). Coordinates are passed
unscaled (MEDIUM).

## Front-panel inputs — VERIFIED unless noted

**Button matrix.** 5 × 5 without diodes, plus one direct button,
scanned by `FUN_08035f80` from the TIM14 1 kHz tick.
- Group A = PA2, PI8, PA7, PC4, PC5; group B = PB2, PH6, PH7, PC13, PH9.
  All are open-drain with pull-up.
- Phase 1 drives B low and reads A (bits 0–4). Phase 2 drives A low and
  reads B (bits 16–20).
- A button at A[i] × B[j] gives the code (1 << (16 + j)) | (1 << i).
- PA0 is a direct button (bit 15).

**Timing (MEDIUM).**
- One scan takes about 5 ms, and a code change needs four equal scans
  (about 20–25 ms debounce).
- Hold fires once after 140 stable scans (about 0.84 s; a stable scan is
  6 ticks). Repeat first fires after about 60 scans (about 0.36 s), then
  every 21 scans (about 0.12 s). The consumer (`FUN_08042c20`) discards
  repeats (VERIFIED; corrects an earlier swap of hold and repeat).
- A release without a hold counts as a short press.

**Encoders.**
- **Eight GPIO quadrature encoders**, sampled at 1 kHz
  (`FUN_08034dc4`). One count per A rising edge, direction from B, two
  stable samples needed. After 20 quick steps a "fast" flag is set and
  held while steps keep coming within 1 s.
  - Pin pairs (A/B): PE5/PC1, PA4/PH8, PI11/PF6, PF7/PF8, PH12/PD4,
    PH15/PI0, PI1/PC2, PD3/PD7.
  - Probably four dual-concentric knobs (HYPOTHESIS).
- **Main dial:** the TIM2 hardware encoder (×4 decoding), read once per
  superloop pass.

**SD card detect.** PA15, active low. It is sampled every 10 ms, and
the card counts as present after 32 consecutive lows (320 ms). Every SD
wait loop aborts when PA15 goes high.

Pins are in `analysis/peripherals/inputs.csv`; function tables are in
`button_map.csv` / `encoder_map.csv` (see `gui.md`). The encoder fast
flag has no reader.

## Display subsystem — VERIFIED unless noted

The display is a parallel RGB565 TFT driven by LTDC; the FMC is plain
SDRAM for the framebuffers. There is no display controller behind the
FMC.

**LTDC** (`FUN_08021878`).
- **Format.** 1024×600, HSYNC 20 / HBP 140 / HFP 160, VSYNC 3 /
  VBP 20 / VFP 12, so 1344×635 in total.
- **Polarities.** HSYNC, VSYNC and DE are active low; the pixel clock is
  inverted.
- **Refresh.** With the 40 MHz pixel clock this gives about 46.9 Hz
  (derived).
- **Layer.** One RGB565 layer, alpha 255, on a black background.

**Double buffering.** The framebuffers are at `0xC0000000` and
`0xC012C000`. `FUN_080365a0` waits for VSYNC, switches the layer
address and swaps them. More SDRAM buffers hold the waterfall.

**Panel power sequence** (`FUN_080364ec`; pin roles MEDIUM).
1. PE6 high (panel power).
2. After 10 ms, PI3 and PF9 low.
3. After 10 ms, PF9 high (reset release).
4. After 10 ms, PI3 high (display enable).

**Backlight.** TIM4 at about 3.66 kHz.
- CH1 (PD12) is held at 100 % and set to 0 at shutdown, so it behaves
  as an enable.
- CH2 (PD13) is the inverted dimming PWM, duty 1 − brightness.

**FMC SDRAM** (`FUN_08020ecc`, commands in `FUN_080365e4`).
- **Geometry.** Bank 1, 9 column and 13 row bits, 16-bit, 4 banks, CAS
  2, so 32 MiB.
- **Clock.** SDCLK = 240/2 = 120 MHz.
- **Timings.** TMRD 2, TXSR 6, TRAS 4, TRC 6, TWR 2, TRP 2, TRCD 2.
- **Init sequence.** Clock enable, 100 ms, precharge-all, 8
  auto-refresh, mode register 0x220.
- **Refresh count** 918.

120 MHz is above the SDRAM clock limit given in the H743 datasheet
(MEDIUM; from memory).

**DMA2D.** It is polled and used for fills, copies, format-converting
copies (waterfall scrolling) and constant-alpha blends.

Register values are in `analysis/peripherals/display_config.csv`.

**Why this needed the firmware:** polarities, porches, the power
sequence, backlight polarity and SDRAM timing are register values with
no public schematic.
