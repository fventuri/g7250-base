# G7250 hardware verification plan

Status: PLAN. No test has been run yet. Expected results come from this
repo's documents and keep their confidence level. A result becomes
VERIFIED only once it is measured on a real unit.

**Goal.** Close the open items in `TODO.md` and the questions Q1–Q9 in
`docs/hpsdr_gap_analysis.md` that firmware analysis cannot settle. Run
the tiers in order and stop at the one you are comfortable with.

| Tier | What | Risk | Who |
| --- | --- | --- | --- |
| 0 | Photos, network captures, USB/CAT tests; case closed | none to the radio | owner |
| 1 | Case opened for photos only | low (ESD, warranty) | owner, carefully |
| 2 | Passive probing of a running board | medium (a slipped probe shorts pins) | **experienced help needed** |
| 3 | SWD read of option bytes | **high** (one wrong click erases or locks the MCU) | **expert only, read-only** |

## General rules

- **Transmit** only into a 50 Ω dummy load rated ≥ 100 W, at minimum
  power (≤ 5 W), on a ham band. The firmware has no SWR, temperature or
  voltage TX inhibit (VERIFIED, `main_unit/docs/flow.md`), so a bad load
  is not caught. Never connect a signal generator to an antenna port
  during TX.
- **Out of scope.** No test changes TX band limits, protections,
  calibration or settings it does not need, and this plan describes no
  way to change them.
- **Main console.** If a serial port shows the Main log, never press
  Enter: it opens the service menu, which changes the drive DAC and the
  SWR terms (`main_unit/docs/peripherals.md` USART1). If a menu
  appears, close the terminal without typing.
- **USB disk.** The Controller's SPI flash appears as a USB drive with
  no write locking. Copy files from it; never write, format or delete.
- **Repo.** Commit measured values, own photos and derived tables only.
  No firmware bytes, no flash dumps, no raw captures with the wfview
  password (use a throwaway one).
- **Log** the date, the firmware versions from the version screen, the
  settings used and the file names of photos and captures.

## Equipment

| Item | Tier |
| --- | --- |
| Camera or phone with macro, good light, a ruler | 0, 1 |
| PC with Ethernet, Wireshark/`tshark`, Python 3 + numpy | 0 |
| HDSDR with the vendor plug-in (or a small discover/heartbeat script per `network.md`), wfview | 0 |
| Serial terminal with hex mode (CoolTerm, minicom, Hamlib `rigctl`) | 0 |
| 50 Ω dummy load ≥ 100 W; a CW paddle | 0 |
| Known signal: a strong broadcast station, or a generator with ≥ 40 dB attenuation | 0 |
| ESD wrist strap and mat, matching screwdrivers | 1 |
| Logic analyser ≥ 100 MS/s, ≥ 12 channels, fine probes; oscilloscope ≥ 100 MHz; multimeter | 2 |
| ST-LINK V2/V3, STM32CubeProgrammer | 3 |

## Tier 0 — no opening, no modification

### T0.1 Front panel, screens, labels

- **Goal.** Panel legends, knob/push pairing, the open GUI screens.
- **Steps.** Photograph the Controller face-on and at an angle, the H-22
  (both sides, plug) and every label (model, serial, MAC, regulatory).
  Count the knobs and note which are dual-concentric. For each button,
  a short press and a 1 s hold; for each knob and ring, a turn and a
  push; note what the screen does. Photograph every menu page,
  including SYSTEM → NETWORK and the version screen (Main, Control,
  FPGA).
- **Expected.** 22 matrix buttons plus one direct button; 8 encoders
  plus the main dial, i.e. four dual-concentric knobs (HYPOTHESIS).
  Functions should match `button_map.csv` / `encoder_map.csv`
  (`control_unit/docs/gui.md`).
- **Closes.** "Panel legends for the 22 matrix buttons and the knob/push
  pairing"; helps "GUI: identify appUi 1, system sub-pages 2/3/4/7 and
  windows 1/3".

### T0.2 Rear connectors and the CTRL cable

- **Steps.** Photograph every connector. Note the CTRL connector type,
  pin count and cable type.
- **Expected.** The list in `docs/hardware.md` §1.
- **Closes.** Nothing by itself. If the CTRL cable is a standard type, a
  breakout adapter lets T2.6 run without opening the case.

### T0.3 HDSDR mode: packet rate per span (Q1)

- **Setup.** SYSTEM → NETWORK: static IP, HDSDR service, PC on the same
  subnet. Wireshark capture filter `udp port 50002`. Start the client.
- **Steps.**
  1. Confirm discover `0x0101` and report `0x0201`; record the 4-byte
     device id and the MAC.
  2. For each FFT SPAN (48k/96k/192k/384k), capture 10 s and count the
     `0x0202` packets (`tshark -r f.pcapng -q -z io,stat,1`).
  3. Stop the client; time how long the stream continues.
- **Expected per hypothesis** (774 B, 192 complex samples per packet):

  | Hypothesis | Packets/s at 48k / 96k / 192k / 384k |
  | --- | --- |
  | Tap after decimation, always 48 kHz (`network.md`, VERIFIED in code) | 250 / 250 / 250 / 250 |
  | Tap at the FPGA rate, 48 × 1/2/4/8 kHz (HYPOTHESIS) | 250 / 500 / 1000 / 2000 |

  The stream should stop about 10 s after the last heartbeat.
- **Closes.** Confirms the HDSDR rate and timeout in `network.md`; the
  device-id unknown of route (b). Answers Q1 only if the rate scales;
  otherwise Q1 needs T2.1.

### T0.4 HDSDR mode: I/Q orientation, LO meaning, scale (Q8)

- **Steps.**
  1. Pick a known carrier: a strong AM broadcast or time-signal station,
     or a generator at about −60 dBm.
  2. Set the client LO 10 kHz below it. Does the front-panel frequency
     follow the `0x0103` command?
  3. Capture 5 s; rebuild I + jQ from the int16 payload (I first) and
     run an FFT in Python. Repeat with the LO 10 kHz above.
  4. Generator only: step the level by 10 dB; record the peak int16
     value and the S-meter.
- **Expected per hypothesis.**
  - Normal orientation: peak at +10 kHz, then −10 kHz. Mirrored: I/Q
    swapped or Q inverted.
  - LO = VFO: the front panel follows. Independent LO: it stays put.
  - About 3.16× amplitude per 10 dB until clipping, which gives full
    scale.
- **Closes.** Q8; the LO and I/Q-scaling unknowns of routes (b)/(c).

### T0.5 RX during TX (Q7)

- **Steps.** Dummy load, minimum power, CW TRAINER off. While capturing
  as in T0.3, key a 5 s carrier with the paddle.
- **Expected.** Packets with live data → RX continues in TX. A gap, or
  zero or frozen payloads → RX stops. RX entry clears the TX rings
  (VERIFIED), but no RX-during-TX behaviour is documented, so both are
  open.
- **Closes.** Q7; the P1 duplex row of the gap analysis.

### T0.6 wfview mode: audio and scope packets

- **Steps.** Service = wfview, throwaway user and password. Capture
  `udp portrange 50001-50003` (base port P to P+2). Connect wfview as
  an IC-7300 on LAN; try LPCM 16-bit 48 kHz, 16 kHz and 8-bit. Run the
  wfview scope for 30 s. Optional, into the dummy load: PTT for 3 s.
- **Expected.** Handshake as in `network.md`; audio every 20 ms in
  chunks ≤ 1364 B; pings every 100 ms (control, CI-V) and 500 ms
  (audio). Either scope waveform frames (CI-V `27 00`) appear, or only
  stored scope settings are echoed (no sender found; HIGH).
- **Closes.** "wfview audio and scope packet layouts"; the scope unknown
  of route (c).

### T0.7 USB census of the Controller

- **Steps.** Connect the rear USB. List VID:PID and the hub tree (macOS
  System Information → USB or `ioreg -p IOUSB`; Linux `lsusb -t -v`;
  Windows Device Manager → Hardware Ids). Note the sound card's name and
  sample rates, and the USB drive's size and file names (copy only).
- **Expected.** A hub; a WCH CH342 (VID 0x1A86) with two serial ports;
  an audio-class device from a separate chip (its VID names it); the
  MCU mass-storage device 0x0483:0x572A (VERIFIED in code). A 1, 2, 8 or
  16 MiB drive narrows the W25Qxx part.
- **Closes.** Partly: "USB hub, CH342 and USB sound-card chips", "the PC
  USB sound-card chip", "Which W25Qxx part is fitted".

### T0.8 Serial port census

- **Steps.** Open both CH342 ports at 115 200 8N1, receive only. Power-
  cycle the radio. Switch Bluetooth off and on in the menu.
- **Expected per hypothesis.**
  - Boot log on a port → Main USART1 console (PB6/PB7, 115 200,
    VERIFIED in code). Never press Enter.
  - An `AT+BD…` line at Bluetooth-on → the port shares the Control
    USART1 line with the module.
  - Neither → another path (for example a Main UART over CTRL).
- **Closes.** "… where their UART lines go"; part of "Control USART1
  CI-V: physical endpoint".

### T0.9 CI-V fingerprint over USB

- **Steps.** Try 115 200, 19 200, 9600 baud. Send read commands only:
  `FE FE A0 E0 03 FD` (frequency), `FE FE 55 E0 03 FD` (wrong address),
  `FE FE 55 E0 19 00 FD` (id), `FE FE A0 E0 30 FD` (unknown command).
  Turn the dial and watch for unsolicited frames. Repeat the first
  frame with Bluetooth off.
- **Expected per hypothesis** (`docs/civ.md`).
  - Control parser: answers 0x55; `19` returns 0x55; FA for the unknown
    command; `00` transceive frames on dial changes.
  - Main-style (wfview) parser: ignores 0x55 and the unknown command; no
    transceive frames.
  - Answers with Bluetooth off → USB CAT does not pass the BT module.
- **Closes.** "Control USART1 CI-V: physical endpoint (BT SPP vs PC
  serial bridge)"; the CI-V endpoint unknown of route (b).

### T0.10 Bluetooth identity

- **Steps.** Pair a phone or Linux PC; note name, MAC and profiles
  (`bluetoothctl info`, `sdptool browse <MAC>`).
- **Expected.** An audio profile per the manual. SPP would mean a second
  CI-V path. The MAC OUI may name the chip vendor.
- **Closes.** Partly "Bluetooth: identify the module chip".

### T0.11 CW key path (function only)

- **Steps.** CW TRAINER on (sidetone, no RF). Key dits and dahs; toggle
  the paddle-reverse setting.
- **Expected.** Correct elements, swapped after the toggle, matching the
  Main PH3/PH4 swap (VERIFIED in code). Does not prove the wiring.
- **Closes.** Prepares T2.6.

## Tier 1 — case opened, photos only

**Before you start.**
- Opening may void the warranty. Ask the dealer first, or wait until
  the unit has run normally for some weeks.
- Disconnect DC, antenna, LAN and USB; wait one minute.
- Wrist strap on, work on the mat, touch the chassis first.
- Photograph before each screw; keep screws in labelled cups.
- Unplug no cable or ribbon, lift no soldered shield, touch no
  component. Photograph a clip-on shield's position before lifting it.
- Per board: whole-board shots, then each chip close up with the
  marking readable (top line part, second line variant/package, date and
  lot code).

### T1.1 Main Unit

| Chip / area | What to read | Closes |
| --- | --- | --- |
| STM32 MCU | part number, revision letter | "Verify both part numbers" (expected H725xG/H735xG, MEDIUM) |
| FPGA and its configuration flash | vendor, family, part | Q5 |
| ADC at the RF input | part number | Q5 context |
| VersaClock 6 and its crystal | marking; crystal value (expected 26.000); where OUT1 runs (FPGA or ADC) | "Confirm the VC6 crystal …" |
| CH394, AXP223, AIC3204, 24Cxx | markings; EEPROM size digits | confirms `peripherals.md` |
| 8-channel 10-bit DAC on SPI2 | marking | "Identify the SPI2 DAC chip" |
| SPI1 shift registers | marking (74HC595 type, HYPOTHESIS) | SPI1 chip type |
| Detector, ALC and bias area | op-amps or comparators between detector and bias/drive | "analog SWR/ALC fold-back" (see T2.8) |
| Headers, pads, empty footprints | SWD (SWDIO/SWCLK), UART labels | prepares T2, T3 |

### T1.2 Controller

| Chip / area | What to read | Closes |
| --- | --- | --- |
| STM32 MCU | part number, revision (expected H743xI rev V, HIGH) | "Verify both part numbers" |
| SDRAM | part (expected 32 MiB, 16-bit) | "Display: … SDRAM part" |
| W25Qxx | marking | "Which W25Qxx part is fitted" |
| Display FPC | label, if visible without unplugging | "Display: panel model" |
| USB hub, CH342, USB audio chip | markings; traces from the CH342 towards CTRL | "Board trace: USB hub, CH342 …" |
| Bluetooth module | module and chip marking | "Bluetooth: identify the module chip" |
| PCA9557, AIC3204, GT911 | markings; visible traces from the PCA9557 outputs | "PCA9557 bits 0/1/3/5 and 6/7" (start) |
| SWD and test pads | labels | prepares T3 |

The photos are also the starting point for tracing the unknown GPIOs
(Main PH9/PH13/PH15, PE14/PE15, PA8/PC8, PA12; Control PH13/PG9/PG10/
PI4). Inner layers need T2 continuity checks.

## Tier 2 — passive measurements (needs experienced help)

**Rules.** Probe test pads, vias or resistor ends only, never adjacent
fine-pitch pins with a hook. Fit probes with the power off. Ground the
analyser to board ground. RX unless a test says otherwise. Continuity
checks with the power off.

### T2.1 PE10 rate and samples per interrupt (Q1)

- **Steps.** Analyser on PE0–PE10, ≥ 100 MS/s. Per FFT SPAN, capture
  100 ms. Measure the PE10 frequency f and the bytes read after each
  `0x04` command (6 bytes per complex sample → N samples).
- **Expected.** Rate = f × N; HYPOTHESIS 48/96/192/384 kS/s. The docs
  disagree on the order of N over indices 0..3 (`peripherals.md`
  8/4/2/1, the gap analysis 1/2/4/8); the capture settles it.
- **Closes.** Q1; "FPGA: … PE10 interrupt rate"; "DSP open: FPGA strobe
  rate".

### T2.2 TX I/Q rate (Q2)

- **Steps.** As T2.1, keyed into the dummy load at minimum power. Count
  the `0x03` samples per PE10 edge; check whether `0x04` reads go on.
- **Expected.** 48 kHz is plausible (HYPOTHESIS); zeros for the first
  200 interrupts (VERIFIED in code).
- **Closes.** Q2; confirms Q7.

### T2.3 Configuration frame and status (Q3, Q9)

- **Steps.** Capture the 24-byte `0x01` frame at VFO 7.000, 7.100 and
  14.100 MHz, and while changing span, PRE and ATT. Capture `0x02`
  reads in RX, in TX and at ADC overload. Note when `0x05/06` and
  `0x09/0A` are sent.
- **Expected.** If the three 32-bit words are NCO words, word = f / fs ×
  2³²: at 7.1 MHz 0x07655555 for fs = 245.76 MHz, 0x0ECAAAAA for
  122.88 MHz.
- **Closes.** Q3, Q9; "FPGA: layout of the 0x01 config frame, status
  values, toggles"; the VC6 OUT1 frequency indirectly.

### T2.4 SPI6 timing and CH394 init (Q4)

- **Steps.** Analyser on PG12–PG14 and CS# PG15, ≥ 100 MS/s, at boot
  and while streaming HDSDR. Decode the W5500-style frames. Find the
  init write to register 0x39 and the accesses after each INT# (PC13)
  falling edge.
- **Expected.** SCK ≈ 17.19 MHz (HIGH); bus busy time gives the real
  efficiency.
- **Closes.** Q4 (measured part; the CH394 maximum clock stays a
  datasheet question); "CH394: confirm the INT flag consumers … register
  0x39".

### T2.5 VC6 output

- **Steps.** Active or differential probe on the OUT1 LVDS pair only.
- **Expected.** 245.76 MHz (MEDIUM) or 122.88 MHz (HYPOTHESIS). T2.3 may
  settle this without touching the clock.
- **Closes.** "whether OUT1 is 245.76 or 122.88 MHz".

### T2.6 KEY jack, CTRL cable, Control keying lines

- **Steps.** Power off: continuity from the KEY jack and mic pins to the
  CTRL pins and to Control PE3/PE4/PI5/PI6. Power on: logic probe on
  Main PH3/PH4 while keying, and on the CTRL pins while a stored CW text
  message plays (keys PE3/PE4).
- **Closes.** "confirm KEY jack wiring to Main PH3/PH4"; "CTRL-cable
  routing of PE3/PE4/PI6"; "what PI6, PE3 and PE4 connect to".

### T2.7 H-22 mic line

- **Steps.** Scope on MDATA and MSVSW at the mic connector (a breakout
  cable is enough) while pressing keys.
- **Expected.** Ratio-coded symbols (low/high ≈ 1, 2, 4) on one line.
- **Closes.** "H-22: measure the absolute bit period and confirm which
  mic line feeds PI5".

### T2.8 Power, expander and fold-back

- **Steps.**
  - PH9 and PH5 at power-on, power key and power-off.
  - PCA9557 outputs in RX, TX, Bluetooth on/off.
  - Fold-back, only with the helper: 10 W into a known 2:1 load (a
    100 Ω dummy load) versus 50 Ω; compare forward power and the ALC
    line. Stop at once if anything gets hot.
- **Closes.** "What drives PH5 …; is PH9 a power latch; PCA9557 bit 5";
  "PCA9557 bits 0/1/3/5 and 6/7"; "analog SWR/ALC fold-back".

## Tier 3 — SWD read of option bytes (risky, expert only)

> **Risky. Expert only, read-only.** Never write, never erase, never
> press *Apply* in the option-byte panel. Changing RDP from level 1 to
> 0 erases the flash; level 2 is permanent. Either ends the unit's
> firmware. Do not halt the Main MCU: a halt can freeze the PA state or
> trip the watchdog. Radio in RX, dummy load on the antenna port.

### T3.1 Option bytes and IWDG

- **Steps.**
  1. Locate the SWD pads in the T1 photos; the expert fits the wires
     with the power off.
  2. STM32CubeProgrammer, ST-LINK, mode "Hot plug" (no reset, no halt).
  3. Read and screenshot the option bytes: RDP, BOOT_ADD0/1,
     CPUFREQ_BOOST (Main), IWDG1_SW and freeze bits, BOR, WRP/PCROP.
     Read DBGMCU_IDCODE and the flash-size register.
  4. Memory view, read only: IWDG1 at `0x58004800`, PR (+0x04) and RLR
     (+0x08).
  5. Disconnect. Do not read or save flash contents: a dump is firmware
     and does not belong in this repo.
- **Expected.** Main DEV_ID 0x483 with CPUFREQ_BOOST set (550 MHz);
  Control DEV_ID 0x450, revision V. RDP level 1 likely (HYPOTHESIS).
  Main IWDG off or several seconds (MEDIUM, `docs/architecture.md`).
- **Closes.** "Read the option bytes (RDP, BOOT_ADD, CPUFREQ_BOOST,
  IWDG_SW)"; "IWDG timeout and the IWDG_SW option byte"; "Is the IWDG
  started by the bootloader or by option bytes?"; part numbers (with
  T1).

## Coverage

| Open item | Tests |
| --- | --- |
| Q1 / Q2 / Q3 / Q9 | T0.3, T2.1 / T2.2 / T2.3 / T2.3 |
| Q4 CH394 SPI | T2.4 (plus the datasheet) |
| Q5 FPGA | T1.1 (identification only) |
| Q6 custom Main image | not testable here (bootloader or vendor) |
| Q7 RX during TX / Q8 LO and I/Q | T0.5, T2.2 / T0.4 |
| Part numbers; option bytes; IWDG | T1.1, T1.2, T3.1 |
| VC6 crystal and OUT1 | T1.1, T2.3, T2.5 |
| CH394 INT and register 0x39 | T2.4 |
| wfview layouts | T0.6 |
| CI-V endpoint; USB chips; UART routing | T0.7–T0.10, T1.2 |
| W25Qxx, panel, SDRAM | T0.7, T1.2 |
| Legends, knob/push, GUI ids | T0.1 |
| SPI2 DAC; fold-back | T1.1, T2.8 |
| Bluetooth chip and audio routing | T0.10, T1.2, T2.8 |
| Analog audio over CTRL; KEY; PE3/PE4/PI6 | T0.11, T2.6 |
| PH5/PH9, PCA9557, unknown GPIOs | T1, T2.8 |
| H-22 bit period | T2.7 |

Not covered: who writes the EEPROM settings area, who sends SLIP `0x02`,
the Control bootloader file name and the Main update transport (note the
vendor's update steps and file names if you apply an official update),
the G90 internals, and the tooling items.
