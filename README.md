# Xiegu G7250 Firmware Reverse Engineering

## Project goal

Understand the architecture and behavior of the two STM32 MCUs in the
Xiegu G7250 (a new 100 W HF transceiver, related to the G90 and X6100)
well enough to document them completely and, eventually, implement
independent open-source firmware.

The original firmware is used only as a reference for observable
behavior and hardware interaction. This is a reverse-engineering
project, not a decompilation project — see [AGENTS.md](AGENTS.md).

Methodology and tooling are ported from the sibling X6100 BASE project
(`~/X6100/x6100-base`).

------------------------------------------------------------------------

## Hardware

Device: **Xiegu G7250**

Two MCUs, each with its own firmware image:

| Unit | Image | Size |
| --- | --- | ---: |
| Main Unit | `G7250_MainUnit_Fw_V1.0.1.bin` | 453 152 bytes |
| Control Unit | `G7250_ControlUnit_Fw_V1.0.1.bin` | 781 328 bytes |

### MCU family — STM32H7 (Cortex-M7), VERIFIED

The starting assumption was STM32F427 (as on the X6100). The evidence
says otherwise (reset vectors below; confirmed by H7-only peripheral
bases and the H7 AXI-SRAM errata in SystemInit — see
[docs/mcu_identification.md](docs/mcu_identification.md)):

| Unit | Initial MSP | Reset handler |
| --- | --- | --- |
| Main | `0x24050000` | `0x08024554` |
| Control | `0x24080000` | `0x080235AC` |

The initial stack pointers lie at `0x24000000`, which is the **AXI SRAM**
of the STM32H7 family (D1 domain) and does **not** exist on any STM32F4.
The Control Unit stack top `0x24080000` is exactly the top of the 512 KiB
AXI SRAM on H743/H750/H753-class parts. Both reset handlers are standard
ARM GCC startup (load SP, SystemInit, copy `.data`, clear `.bss`,
`__libc_init_array`, main).

Both import into Ghidra as `ARM:LE:32:Cortex`, Thumb-2, little-endian.
The exact part numbers are inferred from the firmware, not yet confirmed
from hardware: the Main Unit is most likely an **STM32H725xG/H735xG**
(MEDIUM) and the Control Unit an **STM32H743xI rev V** (HIGH); see
[docs/mcu_identification.md](docs/mcu_identification.md). The H7 RAM map
in `ghidra_scripts/MapSTM32H7Memory.java` is selected per unit (h72x for
Main, h743 for Control).

### Firmware images

The encrypted vendor images (`.bbf` / `.ctl`) are AES-256-ECB; the
decryption recipe is in `../FW/NOTES.txt`. SHA-256 of the decrypted
images analyzed here:

```
6e9e65198dd12bcdf1286f7ab3986cc53230530d9283c9a73976c84fb23b237e  G7250_MainUnit_Fw_V1.0.1.bin
e60c70bd4b6f912892587a31ba438d6a999af12458e428f1bdc9e1f93708dcf2  G7250_ControlUnit_Fw_V1.0.1.bin
```

Load base `0x08020000` for both (application region; the vectors below
it live in a bootloader not present in these images), HIGH CONFIDENCE.

------------------------------------------------------------------------

## Repository layout

```
ghidra_scripts/   headless export/rename scripts (shared by both units)
tools/            headless wrapper scripts + helpers (shared)
docs/             cross-unit documentation
main_unit/        docs/ + analysis/ for the Main Unit MCU
control_unit/     docs/ + analysis/ for the Control Unit MCU
```

Both images are imported into one shared read-only Ghidra project
(`g7250_import`), as two programs.

------------------------------------------------------------------------

## Reproducing the analysis

```sh
export GHIDRA_INSTALL=/opt/ghidra
export JAVA_HOME=/usr/lib/jvm/java-25

# 1. Import both images (base 0x08020000, ARM Cortex-M, H7 RAM map)
./tools/import.sh all

# 2. Select a unit, then run exporters
source tools/env-main.sh        # or: source tools/env-control.sh
OUTPUT_DIR="$OUTPUT_ROOT/startup"    ./tools/run_headless_startup.sh
OUTPUT_DIR="$OUTPUT_ROOT/interrupts" ./tools/run_headless_interrupts.sh
./tools/run_headless_function_ranges.sh "$OUTPUT_ROOT/memory/function_ranges.csv"
```

Ghidra: 12.1.4. Tooling verified with OpenJDK 25.

------------------------------------------------------------------------

## Status

- MCU family VERIFIED as STM32H7 / Cortex-M7.
- Startup, SystemInit, and memory map VERIFIED for both units.
- `main()` followed on both: **bare-metal superloops, no RTOS**; M7
  caches enabled; IWDG-kicked loops.
- System architecture established — see
  [docs/architecture.md](docs/architecture.md): two H7 MCUs over a
  **SLIP/CRC16 serial link**; Main Unit = RF/DSP baseband + CH394
  Ethernet (LAN)/CI-V/streaming, Control Unit = GT911 touchscreen front
  panel (FMC LCD, encoders, H-22 mic, SD/FatFS, PC USB / CH342).
- External hardware, accessories, specs, and the full user-facing menu/
  parameter set are documented from the OEM Operation Manual in
  [docs/hardware.md](docs/hardware.md).

See [TODO.md](TODO.md) and the per-unit `docs/`.

------------------------------------------------------------------------

## Scope of this public repository

This public repository contains the project's **documentation**, the
**reproducible Ghidra / analysis tooling**, and **derived metadata**
(function-range, IRQ, vector, and peripheral-access CSVs, plus extracted
string tables).

It intentionally **omits the raw decompiler and disassembler output**
(`*/analysis/**/*_decompile.*`, `*_disassembly.txt`, and the
snippet-bearing evidence `.txt` files). Those are verbatim derivatives of
the copyrighted OEM firmware; they are kept only in the private working
tree and used strictly as reference evidence under the clean-room rules
in [AGENTS.md](AGENTS.md). Some documents cite those evidence paths — the
referenced raw files are not part of this public tree by design.

The decrypted OEM firmware images are **not** included here.
