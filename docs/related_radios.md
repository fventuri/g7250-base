# Related Xiegu radios: public facts that overlap the G7250

Status: every row cites a public source; G7250 facts come from this
repo. Guesses are marked HYPOTHESIS. Architecture, register and CI-V
tables are in `x6100_comparison.md`.

## Split-unit link

- **G90 (VERIFIED as published).** Source: the public reverse-engineering
  project zeroping/xiegu-g90-headprotocol on GitHub (README and its
  Python tools).
  - The head and base talk over two 3.3 V UARTs at 115 200 8N1.
  - The head sends a 96-byte frame about every 30 ms. It has a sync
    word, both VFO records, flags, levels, CW settings, RIT, and a
    CRC-32/MPEG-2 trailer.
  - The base answers about every 80 ms with meters, decoded CW text and
    a 160-point FFT. The author marks this part as work in progress.
  - The same DB-9 cable carries power, the power key and analog audio.
- **G7250 (VERIFIED).** One SLIP/CRC-16 USART at 460 800 baud carries a
  424-byte settings image every 20 ms and `0x03` spectrum/status frames
  (`protocol.md`).
- **Common design (HIGH).** Both radios send the full front-panel state
  on a fixed period instead of commands, and the base returns spectrum
  plus meters. They differ in field order, mode enum, checksum and
  rates. On the G90 the base decodes CW; on the G7250 the Control Unit
  does.

## CI-V and PC link

- **USB (VERIFIED).** The X6100 (manual v1.3, appendix 2) and the G7250
  both put a CH342 USB-serial bridge, a USB sound card and N1MM CW keying
  on the PC port.
- **Stock X6100 CI-V (VERIFIED, Radioddity changelog 2024-09).** It
  follows the IC-705; later releases added CAT over Bluetooth SPP. The
  G7250 Control parser also serves Bluetooth SPP (`civ.md`).
- **Network emulation (VERIFIED from the sources named).**
  - G7250: IC-7300-style LAN emulation at CI-V address 0xA0.
  - The community X6100 firmware (gdyuldin/x6100_gui): IC-705-style
    emulation at 0xA4 on ports 50001–50003, with Icom ± span semantics.
  - Both send the scope as a single division.

## Firmware update

- **G90 (VERIFIED, Xiegu G90 update instructions, 2020).** A boot-time
  countdown on the serial port opens a bootloader menu. The head and the
  base are flashed separately over XMODEM-1K at 115 200 baud.
- **X6100 (VERIFIED, manual v1.3).** It is updated from SD card. App and
  base versions are reported separately, and the base reboots after
  flashing.
- **G7250.** Both bootloaders are outside the analysed images. A
  G90-style serial bootloader on the Main console USART1 is a candidate
  for the Main update path (HYPOTHESIS).

## Microphone, band stack, power

- **Keypad hand mics.** The X6100 hand mic (manual v1.3) and the G7250
  H-22 both offer keypad band and frequency entry, user F-keys and
  MODE and V/M keys (VERIFIED, layout only). Whether they share the
  G7250's serial keypad protocol is unknown (HYPOTHESIS).
- **Band stack (VERIFIED, presence only).** The X6100 has a band-stack
  menu setting and the G90 head frame carries a band-stack flag. The
  G7250 keeps per-VFO band-stack files (`control_unit/docs/storage.md`).
- **PMIC and audio (VERIFIED, public device tree).** The X6100's Linux
  host also uses an AXP223 PMIC. Its host audio is the SoC codec, so the
  AIC3204 is a G7250 Control/Main part, not an X6100 host part.
