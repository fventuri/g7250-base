# DMA and interrupt allocation (both units)

Both MCUs use the STM32 HAL with CubeMX-style init. The tables below
come from the handle-init and MSP-init functions, which write the DMA
handle fields (instance, request, direction, increments, widths, mode,
priority, FIFO) and call the NVIC priority/enable helpers. Constant
values are decoded with the STM32H7 HAL encodings (HIGH CONFIDENCE);
the register values themselves are VERIFIED. Tables in CSV form:
`main_unit/analysis/peripherals/dma_map.csv`,
`control_unit/analysis/peripherals/dma_map.csv` and the two
`analysis/interrupts/nvic_priorities.csv` files.

**Priority scheme (both units, VERIFIED).** HAL_Init selects priority
grouping 4: all four priority bits are pre-emption priority, there are
no sub-priorities, and a lower number wins. The Main Unit gives SysTick
priority 15 (lowest). The Control Unit initialises the tick with
priority 0, so SysTick is among its highest-priority interrupts.

## Main Unit (STM32H725/H735 class)

### DMA1 / DMA2 streams (DMAMUX1)

| Stream | Request | Owner | Direction | Width (P/M) | Mode | Priority | FIFO | IRQ (prio) | Buffer |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- |
| DMA1 S0 | 61 SPI3_RX | I²S3 RX (codec ADC) | P→M | 32/32 | circular | very high | off | 11 (1) | `0x30003760` (D2) (VERIFIED) |
| DMA1 S1 | — | unused | | | | | | | |
| DMA1 S2 | 43 USART2_RX | SLIP link RX | P→M | 8/8 | circular | low | off | none (14 not enabled) | `0x30005B60` (D2) (VERIFIED) |
| DMA1 S3 | 41 USART1_RX | console RX ring | P→M | 8/8 | circular | low | off | none (14 not enabled) | `0x30004F60` (D2) (VERIFIED) |
| DMA1 S4 | 44 USART2_TX | SLIP link TX | M→P | 8/8 | normal | high | off | 15 (10) | `0x30005360` (D2) (VERIFIED) |
| DMA1 S5 | 62 SPI3_TX | I²S3 TX (codec DAC) | M→P | 16/16 | circular | very high | off | 16 (1) | `0x30004360` (D2) (VERIFIED) |
| DMA1 S6 | — | unused | | | | | | | |
| DMA1 S7 | 9 ADC1 | ADC1 scan, 7 conversions | P→M | 16/16 | circular | medium | off | 47 (0) | `0x30003740` (D2) (VERIFIED) |
| DMA2 S5 | 0 (memory) | memory-to-memory, configured only | M→M | 16/16 | normal | medium | on, full threshold, 8-beat bursts | 68 (7) | none: no code starts it |
| DMA2 other | — | unused | | | | | | | |

Notes:
- DMA2 Stream 5 is set up with the source address incrementing and the
  destination fixed, and its IRQ is enabled, but nothing outside the
  init and the IRQ stub uses its handle (`0x24004E10`). It is unused in
  V1.0.1 (HIGH CONFIDENCE).
- The DMA1 Stream 7 vector is not a plain HAL stub: it first filters the
  seven ADC samples in D2 SRAM for the meters, then calls the HAL DMA
  handler.
- The I²S3 TX stream is half-word wide while the RX stream is
  word-wide. The I²S frame is 32-bit (`peripherals.md`).

### BDMA (D3 domain, DMAMUX2)

| Channel | Request | Owner | Direction | Width | Mode | Priority | IRQ (prio) | Buffer |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- |
| BDMA ch0 | 11 SPI6_RX | CH394 RX | P→M | 8/8 | normal | medium | 129 (13) | `0x38000800` (SRAM4) (VERIFIED) |
| BDMA ch1 | 12 SPI6_TX | CH394 TX | M→P | 8/8 | normal | medium | 130 (13) | `0x38000000` (SRAM4) (VERIFIED) |
| BDMA ch2–7 | — | unused | | | | | | |

The BDMA can only reach D3 memory, which is why the CH394 staging
buffers sit in SRAM4.

### MDMA (software-triggered, polled)

`FUN_08022dc8` configures five channels. All of them use the software
request, full-transfer trigger, packing and a 32-byte buffer length.
None has an interrupt: the MDMA vector is the default handler and is
never enabled, so the helpers start a transfer and poll for it (VERIFIED).

| Channel | Handle | Config | Used by |
| --- | --- | --- | --- |
| ch0 | `0x240052A0` | word→word, both sides increment, medium priority | MDMA copy helper `FUN_0803b01c`, called from the RX DSP `FUN_08033610`, the wfview TX-audio ring reader `FUN_080376c0` and `FUN_0803a5ac` / `FUN_0803a9f4` (VERIFIED) |
| ch1 | `0x24005230` | same as ch0 | RX DSP `FUN_08033610` and TX DSP `FUN_08034b88` (VERIFIED) |
| ch2 | `0x240051C0` | same as ch0 | RX/TX DSP, as ch1 (VERIFIED) |
| ch3 | `0x24005150` | byte→byte, both increment, low priority | configured only (VERIFIED) |
| ch4 | `0x240050E0` | source fixed, destination word-increment, medium priority (a fill) | MDMA fill helper `FUN_0803aee8` (buffer clears); de-initialised before the bootloader jump (VERIFIED) |

The copy helper falls back to a CPU copy when the MDMA is busy, and
does its own D-cache maintenance (see `memory_map.md`).

### NVIC

| IRQ | Vector | Prio | Set up in | Notes |
| ---: | --- | ---: | --- | --- |
| — | SysTick | 15 | HAL_InitTick | 1 kHz HAL tick |
| 3 | RTC_WKUP | — | never enabled by the application | bootloader-jump vector; can only fire if the bootloader left it enabled |
| 9 | EXTI3 (PH3) | 6 | GPIO init; enabled at the end of boot | CW key/paddle |
| 10 | EXTI4 (PH4) | 6 | as IRQ 9 | CW key/paddle |
| 11 | DMA1_Stream0 | 1 | I²S MSP | I²S3 RX |
| 15 | DMA1_Stream4 | 10 | DMA init | USART2 TX |
| 16 | DMA1_Stream5 | 1 | I²S MSP | I²S3 TX |
| 18 | ADC1_2 | 9 | ADC MSP | |
| 23 | EXTI9_5 (PH6) | 6 | as IRQ 9 | PTT |
| 38 | USART2 | 10 | UART MSP | SLIP link |
| 40 | EXTI15_10 (PE10, PC13) | 2 | GPIO init | FPGA sample strobe, CH394 INT# |
| 47 | DMA1_Stream7 | 0 | DMA init | ADC1 metering |
| 50 | TIM5 | 5 | TIM MSP | DSP scheduler, 20 kHz |
| 54 | TIM6_DAC | 8 | DAC MSP and TIM MSP | 100 Hz housekeeping + DAC |
| 55 | TIM7 | 9 | TIM MSP | 1 kHz service + SLIP status frames |
| 68 | DMA2_Stream5 | 7 | DMA init | unused stream |
| 72, 73 | I2C3_EV / I2C3_ER | 13 | I2C MSP | **enabled, but the vectors are the default handler**; harmless because no I2C3 interrupt-mode call exists |
| 86 | SPI6 | 13 | SPI MSP | CH394 |
| 118 | TIM17 | 4 | TIM MSP | 20 kHz sample-side service |
| 129, 130 | BDMA_Channel0/1 | 13 | BDMA init | SPI6 RX/TX |

Everything else, including DMA1 Streams 2 and 3, the MDMA and the
USART1/UART4 vectors, points at the default handler.

## Control Unit (STM32H743)

### DMA1 streams (DMAMUX1)

| Stream | Request | Owner | Direction | Width (P/M) | Mode | Priority | FIFO | IRQ (prio) | Buffer |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- |
| DMA1 S0 | 39 SPI2_RX | I²S2 RX (codec ADC) | P→M | 32/32 | circular | very high | off | 11 (3) | `0x38003400` (SRAM4) (VERIFIED) |
| DMA1 S1 | 40 SPI2_TX | I²S2 TX (codec DAC) | M→P | 32/32 | circular | very high | off | 12 (3) | `0x38004400` (SRAM4) (VERIFIED) |
| DMA1 S2 | 44 USART2_TX | SLIP link TX | M→P | 8/8 | normal | high | off | 13 (1) | `0x38001000` (SRAM4) (VERIFIED) |
| DMA1 S3 | 43 USART2_RX | SLIP link RX | P→M | 8/8 | circular | high | off | none (14 not enabled) | `0x38000000` (SRAM4) (VERIFIED) |
| DMA1 S4 | 41 USART1_RX | Bluetooth AT ring | P→M | 8/8 | circular | low | off | none (15 not enabled) | `0x38003000` (SRAM4) (VERIFIED) |
| DMA1 S5–S7, DMA2, BDMA, MDMA | — | unused | | | | | | | |

The other bus masters are DMA2D (graphics, no interrupt enabled), LTDC
(its own master, IRQ 88) and the SDMMC1 internal DMA (IRQ 49).

### NVIC

| IRQ | Vector | Prio | Set up in | Notes |
| ---: | --- | ---: | --- | --- |
| — | SysTick | 0 | HAL_InitTick | 1 kHz tick; also refreshes the IWDG every 256 ticks |
| 8 | EXTI2 (PE2) | 4 | GT911 init (direct NVIC register writes) | touch INT |
| 11 | DMA1_Stream0 | 3 | DMA init | I²S2 RX |
| 12 | DMA1_Stream1 | 3 | DMA init | I²S2 TX |
| 13 | DMA1_Stream2 | 1 | DMA init | USART2 TX |
| 29 | TIM3 | 10 | TIM MSP | GT911 poll, 100 Hz |
| 38 | USART2 | 1 | UART MSP | SLIP link |
| 44 | TIM8_UP_TIM13 | 1 | TIM MSP (both timers) | SLIP client, 50 Hz |
| 45 | TIM8_TRG_COM_TIM14 | 11 | TIM MSP (both timers) | input service, 1 kHz |
| 46 | TIM8_CC | 10 | TIM MSP | mic line capture |
| 49 | SDMMC1 | 8 | SD MSP | |
| 50 | TIM5 | 4 | TIM MSP | audio service, 20 kHz |
| 55 | TIM7 | 0 | TIM MSP | CW text keyer element clock |
| 88 | LTDC | 13 | LTDC MSP | |
| 101 | OTG_FS | 12 | USB MSP | mass-storage device |

**Why this needed the firmware:** the reference manual lists which
DMAMUX requests and streams *can* be used. Which stream serves which
peripheral, with which mode, width and priority, and how the interrupt
priorities are ranked, are software choices visible only in the init
code.
