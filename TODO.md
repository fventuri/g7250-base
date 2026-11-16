# TODO

Roadmap mirrors `REVERSE_ENGINEERING_GUIDE.md`, tracked per unit.

## Done

- [x] Integrate the OEM **Operation Manual** as external ground-truth →
      `docs/hardware.md` (connectors per unit, accessories, specs, full
      menu/parameter catalog, manual↔firmware reconciliation). Corrections
      applied: shipped mic is the **H-22** (not HM-133); **PC USB
      (CAT+audio+FW-update, CH342) is on the Controller**; **LAN is on the
      Main Unit**; Main Unit has no external USB.
- [x] Scaffold repo; port tooling from X6100 BASE.
- [x] Replace F427 memory map with STM32H7 map (`MapSTM32H7Memory.java`).
- [x] Import both images into shared Ghidra project (base `0x08020000`).
- [x] Identify MCU family: STM32H7 / Cortex-M7 (HIGH CONFIDENCE). (README)
- [x] Export startup chain + vectors + function ranges for both units.
- [x] Seed `main_unit/docs/startup.md`, `control_unit/docs/startup.md`.
- [x] MCU family VERIFIED (H7 peripheral bases + AXI-SRAM errata).
- [x] Resolve `.data`/`.bss` ranges → `*/docs/memory_map.md` (both units).
- [x] Verify SystemInit for each unit (stock H7 CMSIS; FPU/FLASH/RCC/VTOR).
- [x] Control Unit: both pre-`.data` calls identified (PWR+VOSRDY, SystemInit).
- [x] Verify `__libc_init_array` for each unit.

- [x] Follow `main()` on both units → both are bare-metal superloops,
      NO RTOS. Documented in `*/docs/flow.md` and `docs/architecture.md`.
- [x] Establish system architecture: two M7s + SLIP/CRC16 serial link;
      Main = RF/DSP/network, Control = touchscreen front panel.
- [x] Dump strings for both units (`*/analysis/strings/strings.txt`).

## Phase 1 — Startup / memory (remaining)

- [ ] Confirm exact STM32H7 part number (no hardware on hand; infer from
      flash size / RCC PLL config / peripheral IRQ usage instead).
- [ ] Locate the running clock config (PLL / SystemClock_Config): neither
      SystemInit sets a running PLL. `FUN_08027774` (main) is tick setup,
      not PLL bring-up — find the PLL config and resulting SYSCLK.
- [ ] Resolve the 8-byte `.data`/`.bss` gap on the Control Unit.
- [ ] Rename the VERIFIED startup functions in Ghidra via
      `RenameVerifiedFromCsv.java` (SystemInit, __libc_init_array, PWR init,
      and the HIGH-CONFIDENCE helpers in `*/docs/flow.md`).

## Phase 2/3 — Peripherals & interrupts

- [x] Map active IRQs to H7 peripherals for both units (per-unit
      `docs/peripherals.md`). TIM services cross-check the H7 numbering.
- [x] Bus/peripheral inventory from base refs + access counts.
- [x] Inter-MCU SLIP link identified as **USART2** on both MCUs.
- [x] Control I2C1: GT911 touch @ 0x5D VERIFIED.
- [x] Main Unit SPI6 = **WCH CH394 Ethernet**, exclusive bus: master,
      mode 0, /8, PG12/13/14 AF5, BDMA ch0 RX (req 11) / ch1 TX (req 12),
      IRQ86; handle 0x24005420. See main_unit/docs/peripherals.md and
      analysis/peripherals/spi6_ch394.csv.
- [x] Main Unit SPI1/2/3: SPI1 = two RF shift-register chains (TX LPF bank +
      T/R; RX BPF + front-end switches), SPI2 idle, SPI3 = I2S3 48 kHz
      full-duplex sample stream (DMA1 Str5/Str0). See peripherals.md.
- [x] Main Unit I2C devices (all on I2C1): 24Cxx EEPROM @0x50 (NVPARAM/
      calib/ATU), AXP223 PMIC @0x34, VersaClock 6 clock gen @~0x6A.
      I2C2/I2C3 idle. Read/write helpers FUN_0802BB3C / FUN_0802B940.
      (No battery → AXP223 replaces X6100 MAX17205.) See i2c_devices.csv.
- [ ] Find the audio / I-Q codec control path (not on main I2C1 — SPI/I2S?
      or Control Unit). X6100 used CS4272 0x10 + TLV320AIC3204 0x18.
      Manual lead: the digital-mode line-in is the **Controller's USB
      "sound card"** (DIG-ON), audio relayed to Main over SLIP — look on
      the Control Unit USB-audio / I2S path (docs/hardware.md §6).
- [ ] CH394: find the chip-select, reset and interrupt GPIOs, and the
      absolute SPI6 SCK rate (needs PCLK4, see the clock-config item).
- [x] EEPROM layout: settings / calibration / NVPARAM marker / 2× ATU
      tables, CRC-8 0x31, 64-B pages (main_unit/docs/memory_map.md).
- [ ] Who writes the settings area (EEPROM 0x0000 / backup SRAM)? Nothing
      in the Main firmware does — factory tool or older firmware?
- [x] AXP223 rail map + VersaClock output plan (peripherals.md). Rail
      *use* is HYPOTHESIS.
- [ ] Confirm the VC6 crystal (26 MHz?), whether OUT1 is 245.76 or
      122.88 MHz, and where OUT1 goes (FPGA/ADC): needs a board photo or
      a probe.
- [ ] GPIO pin maps (I2C/SPI/UART AF pins) — compare X6100 assignments.
- [ ] Identify the ~26 (main) / ~28 (control) init functions from `main()`.
- [ ] Main Unit TRX-state struct at `0x24013C0C` — recover layout.
- [ ] Re-examine **Main Unit `USB_OTG_FS`** (base ref ×32): the Main Unit
      has no external USB connector (manual), so it is NOT the PC CAT/audio
      port — determine the real role (vestigial / internal / FW-update).
- [ ] Map the **Bluetooth** module (XG-BT-G7250) on the Control Unit —
      two-way audio + control channel (candidate: UART-attached BT). New
      peripheral from the manual; not yet located in firmware.

## Phase 5 — Inter-MCU SLIP protocol (docs/protocol.md)

- [x] SLIP framing (RFC1055, END 0xC0) VERIFIED; encode/decode primitives.
- [x] CRC-16/ARC (poly 0x8005, init 0) VERIFIED, identical on both units.
- [x] RX handlers + dispatch; payload sizes for types 0x01/02/03/06/08.
- [x] Identify message semantics: 0x01=remote settings/state (wfview),
      0x02=calibration data, 0x06=slave info. Structs located.
- [x] 0x01 settings block: partial field map (18 fields) in
      docs/protocol.md + cmd01_fields.csv; consumer FUN_08041EF4.
- [ ] Identify the 2 header bytes after `type` (seq/addr/len/sub-id?).
- [ ] Finish the 0x01 424-B layout (VFO/freq/mode, RF gain, VOX, EQ,
      DNR, wfview user/pass, flags 2 — offsets TBD).
- [ ] Decode 0x02 calibration (358B @0x24013AA4) and 0x06 slave-info
      (104B @0x24018F30) layouts; relate 0x02 to TRX struct 0x24013C0C.
- [ ] Complete the command-ID map (watch for more types beyond 01/02/03/06/08).
- [ ] Which USART instance / baud / pins (Phase 3 hardware init).
- [ ] Main Unit networking: CH394 Ethernet, CI-V over LAN, "WFV" audio/
      waterfall streaming — scope and document.

## Tooling

- [ ] Fix `ExportStartupEvidence.java` `.init_array` locator (X6100
      heuristic yields garbage `runtime_arrays.txt` on these images) —
      locate `__libc_init_array` arguments properly, or drop that output.
- [ ] Decide whether to add STM32H7 peripheral blocks to the memory map
      (currently RAM-only, matching the X6100 approach).

## Phase 2 — Interrupts

- [x] Map active IRQ numbers → H7 peripherals (main: 16, control: 13
      active) — done, see Phase 2/3 above and per-unit `docs/peripherals.md`.
- [ ] Identify Default_Handler and DMA callbacks per unit.

## Later phases (per RE guide)

- [ ] Phase 3 Hardware init (RCC/GPIO/DMA/SPI/I2C/USART/TIM/WDG).
- [x] Phase 4 Scheduler: bare-metal superloops, no RTOS, on both units
      (see Done; `*/docs/flow.md`).
- Phase 5 Inter-MCU protocol: tracked in its own section above.
- [ ] Phase 6 RX DSP pipeline.
- [ ] Phase 7 TX DSP pipeline.
- [ ] Compare with X6100 and G90 findings where behavior overlaps.
