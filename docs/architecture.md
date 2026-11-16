# G7250 system architecture (overview)

Two STM32H7 (Cortex-M7) MCUs, each bare-metal (no RTOS), connected by a
serial link. VERIFIED from the decompiled `main()` of each unit and from
shared diagnostic strings.

```
        +-----------------------+        SLIP over serial        +------------------------+
        |     Main Unit MCU     |<------ (CRC16 framed) -------->|    Control Unit MCU    |
        |   RF / DSP baseband   |   TIM13 "SLIP Client" on the   |  Touchscreen front     |
        |   (SLIP server side)  |   control side                 |  panel (SLIP client)   |
        +-----------+-----------+                                 +-----------+-----------+
                    |                                                          |
        PA bias/ALC, TRX params, audio                          GT911 touch, FMC LCD (ext
        processor, TIM5, CH394 Ethernet                         SDRAM @0xC0000000), rotary
        (LAN) + CI-V + A/V streaming                            encoders, H-22 mic, SD/FatFS,
                                                                PC USB (CH342: CAT+audio)
```

## Shared traits (both units) — VERIFIED

- STM32H7 / Cortex-M7, application at flash `0x08020000`, RAM in AXI SRAM
  (`0x24000000`). See `mcu_identification.md` and each unit's
  `memory_map.md`.
- Startup: stock H7 CMSIS SystemInit, then `main()`. See each unit's
  `startup.md`.
- `main()` enables the Cortex-M7 **I-cache and D-cache** (SCB->CCR) early.
  Implication: any DMA buffers need cache maintenance / non-cacheable MPU
  regions — relevant to the RX/TX pipelines.
- **Bare-metal superloop**, no RTOS, no scheduler. Periodic work is driven
  by hardware timers and by `HAL_GetTick`-based time checks in the loop.
- **Independent watchdog (IWDG1, `0x58004800`).**
  - **Not configured (VERIFIED).** Neither application starts or
    configures it: there is no start or unlock key, and the prescaler
    and reload are never written. The timeout therefore comes from the
    option bytes or the bootloader.
  - **Main** kicks it once per superloop iteration, in the CH394 reset
    wait (every 200 ms) and at shutdown. Main's boot runs more than 2 s
    without a kick, so on Main the IWDG is either off or set to a timeout
    of several seconds (MEDIUM CONFIDENCE).
  - **Control** kicks it once per superloop iteration and from SysTick
    every 256 ms. It therefore only catches a stall with interrupts
    blocked, not a hung main loop.

## Inter-MCU link — HYPOTHESIS/HIGH CONFIDENCE

- Transport is **SLIP** (RFC 1055 byte framing) over a USART, with a
  **CRC16** per packet. Shared strings on both units:
  `SLIP Rx Buffer Full`, `Wrong CRC, mine = %04X, thires = %04X`,
  `Invalid SLIP Packet, raw_len = %ld, dec_len = %ld`, `USART Overrun`.
- The Control Unit hosts the "SLIP Client" (TIM13); the Main Unit is the
  counterpart. Command set decoded in `protocol.md`.
- **The link is USART2 on both MCUs** (IRQ38 active on each, DMA-driven) —
  i.e. Main `USART2` ↔ Control `USART2`. HIGH CONFIDENCE.

Per-unit peripheral inventories (IRQ map, buses, I2C slaves) are in
`main_unit/docs/peripherals.md` and `control_unit/docs/peripherals.md`.

## Roles

| | Main Unit | Control Unit |
| --- | --- | --- |
| Program | `G7250_MainUnit_Fw_V1.0.1.bin` | `G7250_ControlUnit_Fw_V1.0.1.bin` |
| `main()` | `0x0802239C` | `0x08021E74` |
| Functions recovered | 683 | 1696 |
| Role | RF/DSP baseband, PA, audio, networking | Human interface / front panel |
| Notable HW | PA bias DACs, TIM5, **CH394 Ethernet (LAN)**, CI-V, A/V streaming | GT911 touch, FMC LCD + ext SDRAM, encoders, H-22 mic, SD/FatFS, PC USB (CH342) |
| Watchdog | IWDG1 kicked in loop, CH394 wait, shutdown; never configured | IWDG1 kicked in loop and SysTick; never configured |

External connectors, accessories, specs, and the user-facing menu/
parameter set are documented from the OEM manual in
[hardware.md](hardware.md). Note from that source: the **PC USB**
(CAT + sound-card audio + firmware update, CH342 driver) is on the
**Control Unit**, and the **LAN/Ethernet** is on the **Main Unit** — the
Main Unit has no external USB connector.

The Main Unit's Ethernet stack (WCH **CH394** SPI-Ethernet) carries CI-V
(Icom CAT) and audio/waterfall ("WFV") streaming, with LAN link
monitoring and self-heal — i.e. the radio supports networked/remote
operation. This has no X6100 analogue. The CH394 is attached to
**SPI6** (master, mode 0, BDMA ch0/ch1, IRQ86), which it uses
exclusively — VERIFIED, see `main_unit/docs/peripherals.md`. The
socket/streaming layer above it is not yet traced.
