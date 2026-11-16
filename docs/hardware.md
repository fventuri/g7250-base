# G7250 hardware & feature reference (from the Operation Manual)

Ground-truth external hardware, accessories, interfaces, and the
user-facing feature set, taken from the OEM document:

> **Xiegu G7250 Operation Manual**, EN rev 0.1, 2026-10-08 / Rev 1.01
> (`~/radios/g7250/Xiegu_G7250_Operation_Manual_EN_rev0.1_20261008.pdf`),
> © WeiSheng Communication, edition Jul 2026, doc `XDT-B00`.

The manual is authoritative for **observable behavior and external
hardware** (connectors, accessories, specs, menu/parameter set). It does
**not** describe internal chip wiring — so firmware-internal claims here
stay at the confidence they had in the per-unit docs; this file only adds
what the manual itself states (VERIFIED as OEM documentation) plus
explicit cross-references to the firmware findings.

------------------------------------------------------------------------

## 1. Physical architecture

Two physically separate boxes joined by a **dedicated CTRL cable**:

- **Controller Unit (head)** — display + front panel. This is the
  **Control Unit MCU** firmware.
- **Main Unit** — RF / PA / baseband. This is the **Main Unit MCU**
  firmware.

> "The split design allows the head unit (display and controller) and the
> main unit to be deployed independently." — confirms the two-MCU model
> in `architecture.md`. The CTRL cable carries the inter-MCU link
> (USART2 SLIP, see `protocol.md`) plus power between the units.

### Main Unit — rear panel connectors

| # | Connector | Notes / firmware tie-in |
| --- | --- | --- |
| External DC power socket | 13.8 V, red=+, black=− | PMIC = AXP223 (no battery) |
| Grounding nut | chassis ground | |
| ANT1 / ANT2 | two antenna ports | menu `ANT SELECT` → `0x01` block |
| External Tuner (TUNER) | GND / +13.8 / RET / TRG | external ATU trigger/return |
| ALC | RCA, output ALC signal | |
| SEND | RCA, transmit control (PTT out to amp) | |
| **CTRL** | to Controller | inter-MCU USART2 SLIP link |
| **LAN** | wired Ethernet | **CH394 SPI-Ethernet** (Main); HDSDR / wfview network RX, CI-V over LAN, baseband streaming |

> **The LAN/Ethernet port is on the MAIN unit** — confirms CH394 is on
> the Main Unit, on SPI6 (VERIFIED, `main_unit/docs/peripherals.md`). There is **no USB on the Main Unit**.

### Controller Unit — connectors

| Side | Connector | Notes / firmware tie-in |
| --- | --- | --- |
| Left | **TF (microSD) card slot** | format FAT32; SDMMC1 + FatFS (Control) |
| Left | **Microphone** (H-22) | serial keypad over MDATA/MSVSW (see §3) |
| Rear | **CTRL** (to Main) | inter-MCU USART2 SLIP link |
| Rear | **SSPK** external speaker | 4–8 Ω passive (GY10 / GY-03); **not** earphones |
| Rear | **KEY** Morse key | 3.5 mm: Dot / Dash / Common (straight or iambic) |
| Rear | **USB** (to PC) | **CH342 USB-serial**: CAT/control **+ audio (sound card) + firmware update**; N1MM CW keying |

> **The PC-facing USB is on the CONTROLLER**, not the Main Unit, and the
> PC driver is **CH342** (WCH USB-serial). It carries CAT control, a
> built-in sound card (used as line-in for digital modes, "DIG-ON"), and
> firmware update. See the reconciliation note in §6 — the per-unit
> `peripherals.md` previously attributed "PC CAT/audio" USB to the Main
> Unit.

------------------------------------------------------------------------

## 2. Host / network interfaces

- **CAT**: PC connects to the **Controller USB** (CH342). Software
  selects model **"XIEGU G7250"** or a compatible **CI-V** model.
  (Icom-style CI-V — matches the wfview emulation in `protocol.md`.)
- **Network**: **Main Unit LAN** port. IPv4 / gateway / netmask / port
  (default 50001) set in the SYSTEM → NETWORK menu; these map to the
  IPv4 fields already decoded in the `0x01` block
  (`0x174`/`0x178`/`0x17C`/`0x180`). Used by **HDSDR** and **wfview** to
  receive the digital baseband and control the radio remotely.
- **Bluetooth**: module **"XG-BT-G7250"** on the Controller — establishes
  a two-way **audio channel + control channel** to a phone (mobile data
  APP). Not yet mapped to a firmware peripheral (candidate: a UART-
  attached BT module on the Control Unit). HYPOTHESIS.
- **Storage**: TF/microSD, FAT32, ≤32 GB. Holds voice recordings
  (≤30 s each, 10 slots), and is required for the voice Auto-Call
  feature. CW messages and `config.ini` also live on the card.

------------------------------------------------------------------------

## 3. H-22 microphone

The shipped accessory microphone is the **H-22** (not the HM-133 named in
earlier docs — that was an X6100/Icom carryover). Layout: F1–F3
(user-assignable), HOME, Up/Down step, Vol ±, A/B, MODE, V/M, DWN/UP
(channel), and a numeric keypad (direct band entry / frequency input).

MIC connector pinout (manual §Interface Definitions):

| Pin | Signal |
| --- | --- |
| MICE | mic ground |
| MIC | mic audio |
| **MDATA** | mic serial data |
| PTT | PTT |
| **MSVSW** | mic serial data |
| NC | — |
| +8V | 8 V DC |
| GND | ground |

> The keypad/keys are read over the **MDATA/MSVSW serial lines**, not
> discrete GPIO — consistent with the Control Unit's TIM8 "mic service"
> handler (`control_unit/docs/peripherals.md`, IRQ46). The internal
> handler may still implement Xiegu's legacy mic serial protocol; only
> the **shipped mic model** is corrected to H-22 here.

F1/F2/F3 defaults (M1 menu `HANDLE F1/F2/F3`): **PRE / ATT / AGC**.

------------------------------------------------------------------------

## 4. Specifications (manual §Parameters)

| Item | Value |
| --- | --- |
| RX range | 0.5–30 MHz, 50.00–54.00 MHz |
| TX bands | 1.8–2.0, 3.5–3.9, 7.0–7.2, 10.1–10.15, 14.0–14.35, 18.068–18.168, 21.0–21.45, 24.89–24.99, 28.0–29.7, 50.0–54.0 MHz |
| Modes | CW, AM, SSB, FM, WFM |
| Min tuning step | 1 Hz |
| Antenna impedance | 50 Ω |
| Temp range | 0 … +50 °C |
| Freq stability | ±1.5 ppm (10 min warm-up); 1 ppm/hr @25 °C |
| Supply | DC 13.8 V ±15 %, negative ground |
| Current | RX 1.2 A max; TX 23 A max (PSU ≥25 A) |
| RF output | SSB/CW/NFM 100 W ±1 dB; AM 25 W ±1 dB @13.8 V |
| Spurious / carrier suppression | ≥50 dB |
| RX circuit | **RF direct sampling** |
| Sideband suppression | ≥50 dB |
| MDS | −138 dBm (CW, BW 500 Hz) |
| Audio out | 2 W (4 Ω, ≤10 % THD), 4–16 Ω |
| ATU range | 20–150 Ω; initial tune ≤10 s; memory recall ≤0.1 s |
| Main unit | ~240×210×75 mm (LWH), ~2.97 kg |
| Controller | ~249×148×38 mm (LWH), ~1.33 kg |

Direct-sampling RX confirms the Main Unit is a direct-sampling SDR. In
the firmware, the RF sampling sits in the FPGA, which delivers 24-bit
I/Q to the MCU DSP. The Main Unit has no external SDRAM (VERIFIED, see
`main_unit/docs/peripherals.md`).

------------------------------------------------------------------------

## 5. Feature / parameter catalog → firmware state

The front-panel menus define the authoritative parameter set and value
ranges. These are the radio's shared state; many map directly to the
inter-MCU `0x01` settings block (`protocol.md`). Use this as a key when
pinning the still-unmapped `0x01` offsets.

### Status / RX chain

- **PRE**: PRE1 (~12 dB) / PRE2 (~17 dB) preamp.
- **ATT**: pre-attenuator on/off.
- **AGC**: OFF / SLOW / FAST / AUTO.
- **NF** (digital notch), **NR** (digital noise reduction, level),
  **NB** (pulse noise blanker, level) — each has an on/off + level
  pop-up (`0x01` carries "DNR1/DNR2 threshold").
- **RIT / XIT**: ± fine tuning, ±Hz (decoded: `0x074` RIT, `0x076` XIT).

### Digital filters

- Three filter groups **FIL1 / FIL2 / FIL3** per mode. Example (USB):
  FIL1 2900 Hz, FIL2 2400 Hz, FIL3 1800 Hz. Built from an **L-CUT**
  (low cut) + **H-CUT** (high cut) pair; overlap = effective bandwidth.
- **OPT FILT** (M1-2 §24): four high-performance narrowband filters for
  **80 m / 40 m / 30 m / 20 m** (3.5 / 7 / 10 / 14 MHz). Steep roofing
  filters; see Appendix 2. On/off.
- **TXBW SSB / AM / FM**: WIDE / MID / NAR (TX audio bandwidth)
  (`0x01` carries AM/SSB/FM LPF + SSB HPF TX filters: `0x0DA`–`0x0E8`).

### TX / audio

- **MIC GAIN** (`0x01` `0x0C4`), **Po** (TX power → PA DAC, `0x01`
  `0x154`).
- **VOX** switch (`0x0EA`), **VOX TIMEOUT**, **VOX THRESHOLD**.
- **COMP** (speech compressor) on/off + **COMP RATIO**.
- **LINE IN GAIN / LINE OUT GAIN** (digital-mode audio via the USB sound
  card; the `sample rate` field `0x088` is in this area).
- **MONITOR LEVEL**; **BEEP VOL**.
- **EQ**: 2 × 5-band graphic EQ, enabled by `EQ-RX` / `EQ-AMFM` switches.
  - EQ RX bands: 300 / 700 / 1200 / 1800 / 2300 Hz.
  - EQ AMFM bands: 500 / 1000 / 2000 / 3000 / 5500 Hz.

### CW (M3 menu)

- **KEY TYPE**: STRAIGHT / SQUZ KEY / SQUZ KEY(R).
- **KEY SPEED** (WPM), **IAMBIC** A/B, **DI/DA RATIO**.
- **TONE** (sidetone freq) + **TONE LEVEL**.
- **QSK TIME** (TX/RX switch time); **CW TRAINER** (sidetone only, no
  RF); **CW DECODER** + **CWD THRESH** (waterfall-area decode).

### Display / spectrum (M2 menu)

- **FFT SPAN**: 384k / 192k / 96k / 48k.
- **FFT CW ZOOM**: 2×/4×/8× / OFF (CW-mode spectrum zoom).
- **FFT REF LEVEL**, **WF REF LEVEL**, **WF GAIN**, **SCOPE HEIGHT**,
  **WF MOVE**, screen-off / dim / saver times.

### Memory / band

- **100 memory channels** (name tag + freq/mode), V/M switching, band
  stacking register (HAM BAND / ALL BAND).

------------------------------------------------------------------------

## 6. Reconciliation: manual ↔ firmware docs

| Topic | Firmware docs said | Manual says | Action |
| --- | --- | --- | --- |
| Shipped mic | "HM-133" | **H-22** | Corrected in `architecture.md`; firmware handler note added (§3) |
| PC USB (CAT+audio) | HIGH on **Main** USB_OTG_FS | USB is on the **Controller** (CH342); Main has **no USB** | Flagged; see open item below |
| Controller USB | "firmware update / MSC?" | CAT + **audio (sound card)** + firmware update | Role broadened |
| Ethernet/LAN | CH394 on Main, SPI6 (VERIFIED) | LAN connector **on Main** | Confirmed |
| Power | AXP223, no battery | 13.8 V mains, no battery | Confirmed |
| Touch | GT911 @0x5D | capacitive touchscreen | Confirmed |
| Storage | SDMMC1 + FatFS | TF/microSD FAT32 | Confirmed |
| ATU | EEPROM stores ATU/band data | per-band tuner data auto-stored | Confirmed |

### Open items raised by the manual

- **Main Unit `USB_OTG_FS`** (base ref ×32) cannot be the PC CAT/audio
  port (no USB connector on the Main Unit). Re-examine: vestigial,
  internal, or firmware-update only? → de-rate the "PC CAT/audio" guess.
- **Audio / line-in codec path**: the manual's "controller's built-in
  sound card" (DIG-ON line input) points at a **USB audio device on the
  Controller**, with line audio relayed to the Main Unit over the SLIP
  link — a lead for the open "audio/I-Q codec control path" task.
- **Bluetooth** (XG-BT-G7250) peripheral on the Controller — unmapped.
