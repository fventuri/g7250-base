# Control Unit — peripherals

MCU: STM32H7 (Cortex-M7). This is the touchscreen front panel. Evidence:
active interrupt vectors, peripheral register accesses, base-address
references, and boot-log strings (see `docs/flow.md`). IRQ numbers use
the **STM32H7** NVIC table.

## Active interrupts (→ H7 peripheral)

| IRQ | Handler | H7 peripheral | Inferred role | Conf |
| ---: | --- | --- | --- | --- |
| 8 | `FUN_08022780` | EXTI2 | external line (touch INT?) | HIGH |
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
| SPI1/2, SPI5 | base refs; SPI2/I2S2 ×6 | SPI2/I2S2 likely audio I²S; others TBD | MED |
| **USART2** | IRQ38 + DMA | inter-MCU SLIP link (↔ Main USART2) | HIGH |
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
