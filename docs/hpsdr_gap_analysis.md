# G7250 as a network SDR — HPSDR gap analysis (design study)

Status: DESIGN STUDY. No new firmware analysis. Every G7250 statement
below is taken from this repo's documents and carries their confidence
level. Statements marked **(derived)** are this study's own arithmetic
or inference from those facts, with the confidence given. The HPSDR side
comes only from the public specifications listed under Sources.

**Question.** What would it take for the G7250 to appear as a standard
network SDR, either OpenHPSDR protocol 1 (P1, as on the Hermes-Lite 2)
or protocol 2 (P2, as on ANAN radios)? Alternatively, what would it take
to integrate it directly into a third-party SDR application?

**Short answer.**
- The **radio hardware path fits P1 well**: one receiver, 24-bit I/Q
  from an FPGA, a 48 kHz codec for speaker and mic, and a TX I/Q path
  into the FPGA.
- The **LAN path is the bottleneck**: a CH394 on a 17 MHz SPI bus, with
  8 sockets.
- The **existing LAN modes are not enough**: they give either 48 kHz RX
  I/Q without TX (HDSDR mode), or demodulated audio plus CI-V without
  I/Q (wfview mode).

## 1. What the G7250 already has

### 1.1 Ethernet: CH394 on SPI6

| Item | Value | Conf | Source |
| --- | --- | --- | --- |
| Controller | WCH CH394, W5500-compatible register model | VERIFIED (chip, bus) / HIGH (register model) | `main_unit/docs/peripherals.md` SPI6 |
| Bus | SPI6 master, mode 0, BDMA ch0/ch1, exclusive to the CH394 | VERIFIED | same |
| SCK | PCLK4 137.5 MHz / 8 ≈ 17.19 MHz | HIGH | same; `spi6_ch394.csv` |
| Access framing | 16-bit offset + control byte + data; bulk payload by DMA, single-register reads polled | HIGH | same |
| Sockets | 8 hardware sockets, 16 KB TX + 16 KB RX pool, UDP only (no TCP, no raw) | VERIFIED | `main_unit/docs/network.md` |
| Socket plan | HDSDR mode: socket 0 = 16 KB; wfview mode: sockets 1/2/3 = 2/6/8 KB; 4–7 unused | VERIFIED | `network.md`; `ch394_network.csv` |
| Datagram size | 1–2048 B per send | VERIFIED | `network.md` |
| IP config | static IPv4, gateway, netmask, base port from settings `0x174`–`0x180`; no DHCP; MAC read from the chip | VERIFIED | `network.md`; `docs/protocol.md` |
| ARP/ICMP | handled by the CH394, not the MCU | HIGH | `network.md` |
| Link | 1 s PHY poll, link cycle and hard reset as self-heal | VERIFIED | `network.md` |

**Throughput ceiling (derived, MEDIUM).** 17.19 Mbit/s is the raw SPI
bit rate. It is also the ceiling for the total of all datagrams in both
directions, because the access protocol moves one direction per CS
window. Register polling, the 3-byte access headers, the 8-byte receive
header per datagram and the gaps between DMA bursts all reduce it. This
study uses **~12–14 Mbit/s** as a working budget. The real efficiency
and the CH394's maximum SPI clock are not in the repo (open question
Q4).

### 1.2 Current LAN services

Byte `0x182` of the settings image selects **one** of two exclusive
services (VERIFIED, `network.md`).

| | HDSDR / IQ mode | wfview mode |
| --- | --- | --- |
| Sockets | 1 UDP socket, local port 50002 | 3 UDP sockets: control, CI-V, audio on base port P, P+1, P+2 |
| Discovery | magic + command `0x0101`; reply `0x0201` carries IPv4, port, 4-byte id | Icom-style are-you-there / login / token / conninfo handshake (VERIFIED) |
| RX data | `0x0202`: 192 complex int16, 774 B per packet; the 48 kHz decimated receiver I/Q, tapped before demodulation | demodulated audio, LPCM 16/8-bit mono at 48/16 kHz, every 20 ms (VERIFIED) |
| Tuning | `0x0103` set LO, 64-bit Hz, 0.5–108 MHz | CI-V (IC-7300 emulation, address 0xA0) (VERIFIED) |
| TX | **none** | TX audio into the TX DSP; PTT through CI-V `1C 00` |
| Keep-alive | session drops after 10 s without heartbeat/discover | pings every 100/500 ms; streams dropped after 15 s silence |
| Conf | VERIFIED | VERIFIED (CI-V map PARTIAL) |

The scope commands of the wfview CI-V layer (`27 10`/`27 11`) are
recorded as stored values. The repo does not document a sender for
scope waveform data (HIGH, `docs/civ.md`; `civ_main.csv`).

### 1.3 RX I/Q path, FPGA to Main MCU

- **Bus.** The FPGA is the RF I/Q front end, on a bit-banged 8-bit GPIO
  bus (PE0–PE7 data, PE8/PE9 strobes, PE10 data-ready EXTI). VERIFIED,
  `peripherals.md` FPGA bus.
- **Samples.** Command `0x04` reads signed 24-bit I and Q, with 1, 2, 4
  or 8 complex samples per interrupt for rate settings 0–3. The samples
  go into 192-sample blocks. VERIFIED.
- **Sample rate.** The absolute rate is **not visible in the
  firmware**. 48 kHz × 1/2/4/8 (48/96/192/384 kS/s) is a
  **HYPOTHESIS**. It is consistent with the decimate-by-8/4/2/1 path
  and with a VersaClock 6 output of 245.76 MHz = 5120 × 48 kHz (MEDIUM;
  `peripherals.md`, `vc6_clock_plan.csv`).
- **Rate control.** The span/rate index is settings `0x088` (0..3,
  HIGH). It is sent to the FPGA as a sample-rate code inside the 24-byte
  configuration frame (command `0x01`). That frame also carries three
  32-bit words that may be NCO tuning words (HYPOTHESIS) and per-rate
  calibration bytes.
- **Single receiver.** Only one I/Q stream is read. No second receiver,
  raw-ADC or wideband command is known (VERIFIED for the documented
  command set).
- **Overload.** FPGA status bit 0 = ADC overload, reported as `0x03`
  flags bit 6 (HIGH).
- **Narrow rate (derived, MEDIUM).** The DSP runs on 192-sample blocks,
  and the codec moves 192-frame halves at 48 kHz (VERIFIED). The
  decimated I/Q that the HDSDR tap exports is therefore most likely the
  48 kHz rate. Whether the wider spans really reach 384 kS/s depends on
  the hypothesis above.

### 1.4 Audio, TX path, PTT, CAT

- **Codec.** TLV320AIC3204 on I²S3: 48 kHz, 32-bit stereo, full
  duplex. The mic is on the codec's left ADC. VERIFIED
  (`peripherals.md` I²S3, audio codec).
- **TX chain.** The TX DSP (`dsp.md`) takes mic, line or wfview audio.
  It applies EQ, filters, VOX and the compressor, modulates per mode,
  applies drive and ALC, and copies the I/Q by MDMA into the FPGA TX
  ring (2 × 192 samples). FPGA command `0x03` writes signed 24-bit TX
  I/Q, with zeros for the first 200 interrupts after keying (VERIFIED).
  The TX sample rate on the FPGA side is as unknown as the RX rate.
- **Mode table.** It includes code 10 = IQ and 11 = LBK, loopback
  without the FPGA (VERIFIED). What IQ mode does on TX is not
  documented.
- **Drive and power.** TX power is settings `0x154` as f32 watts
  (VERIFIED). A per-band drive gain and the PA drive DAC code sit in
  the TRX runtime tail (MEDIUM).
- **PTT and T/R.** A 100 Hz arbiter in TIM6 ORs the sources: built-in,
  serial CW key, tune, SWR scan, CI-V/LAN PTT, hardware PTT on PH6, VOX,
  ATU carrier and paddles. It then runs the documented TX/RX entry
  sequences (VERIFIED, `main_unit/docs/flow.md`). The LAN path already
  writes the CI-V PTT flag (VERIFIED).
- **TX permission.** The Main firmware's TX permission check
  (`flow.md`, TX band enforcement) applies to every PTT source. Every
  route in this study leaves it unchanged, and none touches it.
- **CAT.** There are three endpoints (`docs/civ.md`):
  - wfview CI-V over LAN (IC-7300 emulation);
  - the Control Unit CI-V parser on USART1;
  - PC USB CAT plus a sound card on the Control Unit via CH342.

  VERIFIED/HIGH; the physical endpoint of USART1 is a HYPOTHESIS.
- **Front-panel consistency.** While a network client controls the
  radio, Main ignores the `0x01` VFO block and pushes changes to Control
  with the sequenced `0x08` record (VERIFIED, `docs/protocol.md`). Any
  new network service can reuse this mechanism.

## 2. Requirement-by-requirement gap table

Notation: P1 control addresses are C0[7:1], as used in the Hermes-Lite
2 wiki. For example, address 0x09 is C0 = 0x12/0x13. "Fit" is this
study's rating: **OK** = present, **MAP** = present but needs
translation, **GAP** = missing, **NO** = not possible without new
FPGA or hardware capability.

### 2.1 Protocol 1 (Metis / Hermes / Hermes-Lite 2)

| P1 requirement | G7250 counterpart | Fit | Note |
| --- | --- | --- | --- |
| UDP port 1024, discovery `EF FE 02` + 60 zero bytes; reply with status, MAC, code version, board id | CH394 UDP sockets (VERIFIED); MAC readable from the chip (VERIFIED); versions in the `0x06` slave info (VERIFIED) | MAP | One socket is enough, and HDSDR mode already uses a single 16 KB socket. A board id must be chosen (§3) |
| Start/stop `EF FE 04` (bit 0 I/Q+mic, bit 1 wideband) | HDSDR discover/heartbeat session (VERIFIED) | MAP | |
| Host watchdog (HL2: TX stops when host commands stop) | 10 s HDSDR timeout; wfview 15 s stream timeout; 2–3 s SLIP controller timeout drops PTT (VERIFIED) | GAP | Needs a short network-loss TX drop; see §2.3 |
| EP6 frames: 1032-B datagram, 2 × 512-B frames, sync `7F7F7F`, C0–C4, 63 × (I24, Q24, mic16) for one RX | 24-bit FPGA I/Q (VERIFIED); 16-bit mic from I²S3 (VERIFIED) | MAP | The native 24-bit format matches. 192-sample blocks must be repacked into 63-sample frames |
| Rates 48/96/192/384 kHz (address 0x00, C1[1:0]) | span index `0x088` 0..3 (HIGH); absolute rates HYPOTHESIS | MAP / unknown | 384 kHz exceeds the SPI budget (§2.4) |
| Number of receivers (address 0x00, C4[5:3]) | one I/Q stream (VERIFIED) | GAP | Report 1 receiver |
| Duplex bit | RX entry clears the TX rings; RX during TX not documented | unknown | |
| RX1 frequency (address 0x02), TX frequency (address 0x01) | VFO A/B u64 Hz at `0x024`/`0x04C`, split `0x0A4`; HDSDR LO 0.5–108 MHz (VERIFIED) | MAP | 32-bit Hz in P1 is sufficient for HF |
| Preamp, attenuator, RX antenna (address 0x00 C3; HL2 LNA gain address 0x0A) | VFO PRE/ATT bytes, RF gain `0x07B`, antenna `0x09F` (VERIFIED/HIGH) | MAP | The HL2 LNA dB scale needs a table onto PRE/ATT/RF gain |
| Open-collector outputs (address 0x00 C2) | no documented user GPIO | GAP | |
| Drive level 0–255 (address 0x09 C1; HL2 uses 4 bits), PA enable, tune request | TX power f32 W `0x154` (VERIFIED); tune via PTT-source bit 5 (VERIFIED) | MAP | Drive is a host-side level. The G7250 regulates power internally with drive and ALC (MEDIUM) |
| Mic boost / line in (address 0x09 C2) | mic gain `0x0C4`, line-in `0x0C8` (VERIFIED) | MAP | |
| ATU (Apollo bits, address 0x09 C2) | ATU switch `0x0AC`, tune bit (VERIFIED) | MAP | |
| CW settings (internal CW, hang, sidetone) | CW speed, QSK, tone fields (VERIFIED, `x6100_comparison.md`) | MAP | |
| HL2 TX latency / PTT hang (address 0x17) | CW/VOX hang only (VERIFIED) | GAP | Implementable in firmware |
| EP2: 63 × (L16, R16, I16, Q16) at 48 kHz; TX I/Q 16-bit; MOX = C0 bit 0 | codec DAC 48 kHz for L/R (VERIFIED); FPGA TX ring 24-bit (VERIFIED); CI-V/LAN PTT flag (VERIFIED) | MAP | Host I/Q must bypass the TX modulators into the TX ring. A 48 kHz TX rate is plausible but unknown |
| Status C0 bit 0 PTT, bits 1/2 dash/dot | hardware PTT PH6, paddles PH3/PH4 (VERIFIED) | OK | |
| Status: ADC overflow, firmware version | FPGA status bit 0 (HIGH); slave info (VERIFIED) | OK | |
| Status: forward/reverse power, supply, temperature, current (raw ADC counts; host calibrates per board id) | `0x03` tail floats: fwd W, SWR, Vext, Idd, PA temperature (VERIFIED) | MAP | Values are already in engineering units. Reverse power must be derived from fwd and SWR, and the counts back-scaled for the chosen board id |
| EP4 wideband: raw 16-bit ADC blocks | no raw-ADC path; `0x03` spectrum is 512 dB bins (VERIFIED) | NO | |

### 2.2 Protocol 2 (openHPSDR Ethernet protocol v4.x, ANAN)

| P2 requirement | G7250 counterpart | Fit | Note |
| --- | --- | --- | --- |
| Discovery on port 1024, reply with status 0x02/0x03 and board type | as P1 | MAP | |
| Separate fixed ports: general 1024; RX-specific 1025; TX-specific 1026; high priority from PC 1027; audio 1028; DUC I/Q 1029; DDC0 from 1035 (+1 per DDC); mic from 1026; status from 1025; wideband from 1027 | 8 CH394 sockets (VERIFIED) | MAP (tight) | **7 sockets** for one DDC, with the DDC0 port as the seventh local port. 8 sockets allow at most 2 DDCs and no spare. The 16 KB pools give about 2 KB per socket, enough for 1444-B packets |
| Run bit and PTT in the high-priority packet; C&C at least every 1 s, else standby with PTT off | PTT arbiter (VERIFIED); no such watchdog | GAP | Firmware must implement the 1 s standby rule |
| DDC I/Q: 1444-B packets, 238 × 24-bit I/Q, sequence + 64-bit timestamp, 48–1536 kS/s | 24-bit I/Q (VERIFIED); rates 0..3 (HIGH/HYPOTHESIS) | MAP | 768/1536 kS/s: NO. Timestamp can be a sample counter |
| DUC I/Q: 240 × 24-bit at fixed 192 kS/s | FPGA TX 24-bit (VERIFIED); TX rate unknown | MAP / unknown | Probably needs 4:1 decimation in the MCU if the FPGA TX rate is 48 kHz (derived, HYPOTHESIS) |
| Mic: 64 × 16-bit at 48 kHz (132 B) | I²S3 mic (VERIFIED) | OK | |
| RX audio to radio: 64 stereo 16-bit at 48 kHz | codec DAC (VERIFIED) | OK | |
| High-priority status: PTT, ADC overload, fwd/rev power, supply, TX FIFO state | as P1 status, plus a 2 × 192 TX ring | MAP | A host-paced TX FIFO needs a deeper buffer in MCU RAM |
| PureSignal feedback DDCs (RF and DAC feedback) | no TX feedback receiver documented; no I/Q trim in the settings image (VERIFIED, `x6100_comparison.md`) | NO | |
| Wideband ADC data | none | NO | |
| CAT over TCP (added in v4.x) | UDP only in V1.0.1 (VERIFIED); TCP capability of the chip not documented here | GAP | |

### 2.3 Timing and latency

- **Packet period (derived, HIGH).** A P1 packet (126 samples) covers
  2.6 ms at 48 kHz. A G7250 DSP block (192 samples) covers 4 ms at
  48 kHz. Repacking needs one block of buffering, so about 4 ms of added
  latency.
- **PTT latency.** The arbiter runs every 10 ms (VERIFIED). MOX-to-RF
  therefore takes up to 10 ms. Add the T/R sequence, which has no
  explicit delays, and the 200 zero TX samples (about 4 ms at 48 kHz;
  derived, HYPOTHESIS).
- **Network-loss safety.** HPSDR expects TX to drop quickly when the
  host goes silent: 1 s in P2, and HL2 has a watchdog. The existing LAN
  timeouts are 10–15 s (VERIFIED), so a new service needs its own
  sub-second drop of the LAN PTT flag. The Control CI-V path drops PTT
  after 10 s (VERIFIED), which is also longer.
- **Clock pacing.** In P1 the host paces EP2 on the received EP6 rate,
  so the radio's sample clock is the master. That suits a radio whose
  rates come from a 48 kHz-family synthesiser (MEDIUM).

### 2.4 SPI6 bandwidth budget (derived, HIGH for the arithmetic)

The rates are UDP payload only, before CH394 access overhead. The
budget is ~12–14 Mbit/s usable, 17.19 Mbit/s raw.

| Stream set | 48 kHz | 96 kHz | 192 kHz | 384 kHz |
| --- | ---: | ---: | ---: | ---: |
| P1 EP6 RX (1 receiver) | 3.1 | 6.3 | 12.6 | 25.2 |
| P1 EP6 + EP2 (EP2 always 48 kHz, 3.1) | **6.3** | **9.4** | 15.7 | 28.3 |
| P2 DDC0 alone | 2.3 | 4.7 | 9.3 | 18.6 |
| P2 RX set: DDC0 + mic 0.8 + audio 1.6 | **4.7** | **7.1** | 11.7 | 21.0 |
| P2 TX set: RX set + DUC at 192 kHz (9.2) | 13.9 | 16.3 | 20.9 | 30.2 |
| Today, for comparison: HDSDR I/Q at 48 kHz | 1.5 | — | — | — |

Values are in Mbit/s.

**Conclusion (MEDIUM).**
- **P1 at 48 and 96 kHz** fits with margin. 192 kHz is at the edge and
  384 kHz does not fit.
- **P2 receive** fits up to 96 kHz, and 192 kHz only without TX.
- **P2 transmit** is dominated by the fixed 192 kS/s DUC stream, so
  even a 48 kHz receiver leaves almost no margin.

P1 is therefore the better match for this hardware.

## 3. Implementation routes

### (a) New Main-MCU firmware speaking HPSDR

**What it is.** An independent Main firmware, or a new LAN service
inside one. The repo docs are its specification:
- `peripherals.md` for the CH394 register model, socket handling, FPGA
  bus, I²S3, codec, PA bias and RF switching;
- `flow.md` for the T/R sequences and protections;
- `docs/protocol.md` for the SLIP link to the Control Unit;
- `network.md` for the reusable session and self-heal behaviour.

**HPSDR mode would work like this:**
- forward FPGA I/Q (24-bit, as read) in P1 frames;
- take 16-bit mic samples from I²S3;
- route the host's L/R audio to the codec, Hermes-style;
- write host TX I/Q directly into the FPGA TX ring, bypassing the local
  modulators but keeping drive limits, the T/R sequencing and the TX
  permission check;
- map MOX to the existing LAN PTT source;
- push frequency and mode to the Control Unit with `0x08` so the front
  panel follows.

| Pros | Cons |
| --- | --- |
| Full P1 feature set within the SPI budget: RX, TX I/Q, mic, speaker audio, PTT, meters | Requires a complete clean-room Main firmware: ATU, PA bias, protections, SLIP, LAN self-heal |
| 24-bit I/Q end to end; no extra host | Board-id choice: Hermes implies a codec and ANAN-style meters; HL2 implies no codec. Either requires back-scaled meter counts, or an app-side profile for a new id |
| P1 needs only 1 socket; P2 fits in 7 | P2 TX is near the SPI limit; 384 kHz P1 and wideband are out of reach |

**Blocking unknowns:**
- the real FPGA sample rates per index (Q1);
- the FPGA TX rate and the TX meaning of the configuration frame (Q2);
- the NCO-word encoding in configuration command `0x01` (HYPOTHESIS);
- the toggles `0x05/0x06` and `0x09/0x0A`;
- the maximum SPI6 clock (Q4);
- whether a custom Main image can be installed at all (Q6).

### (b) External bridge host

**What it is.** A small computer on the LAN, or on the PC itself, that
speaks HPSDR P1 to the application and the existing G7250 interfaces to
the radio. With stock firmware the bridge has these inputs:
- **HDSDR mode:** 48 kHz int16 RX I/Q plus an LO command (VERIFIED);
- **wfview mode:** demodulated audio, CI-V and TX audio (VERIFIED);
- **PC USB on the Control Unit:** CI-V CAT and a sound card (VERIFIED/
  HIGH).

The LAN modes are mutually exclusive (VERIFIED). A working combination
is HDSDR-mode I/Q plus CI-V CAT and audio over USB.

**What the bridge does:**
- **RX I/Q:** widens int16 to 24-bit and repacks 192-sample packets
  into 63-sample P1 frames.
- **Tuning:** turns the P1 RX frequency into `0x0103` LO commands.
- **Other commands:** turns MOX, mode, power and ATU into CI-V over USB.
- **Keep-alive:** sends heartbeats well inside the 10 s timeout.

| Pros | Cons |
| --- | --- |
| No firmware change; RX panadapter and demodulation in any P1 app soon (HIGH for RX) | **No TX I/Q**: TX would need the app's audio sent to the radio's own SSB/AM/FM modulator via the USB sound card, which most HPSDR apps do not do |
| Bridge code is ordinary host software | 48 kHz span and int16 only; no meters over LAN in HDSDR mode, so they come over CAT |
| No CH394 or SPI constraints beyond today's 1.5 Mbit/s | Two transports (LAN + USB), extra latency, a host to run |

**Blocking unknowns:**
- whether `0x0103` retunes the VFO or an independent LO;
- the exact I/Q scaling and sideband orientation in `0x0202`;
- the 4-byte device id;
- the Control CI-V endpoint (USART1 HYPOTHESIS).

### (c) Native integration of the existing LAN protocol into an app

**What it is.** Implement the documented protocols directly in
application drivers:
- an **HDSDR-mode source** (magic, discover/heartbeat/LO, 774-B I/Q
  packets) as a SoapySDR module or an application source plugin;
- **CI-V over the wfview channel**, which wfview already serves because
  the radio emulates an IC-7300 (VERIFIED).

| Pros | Cons |
| --- | --- |
| Smallest effort; the HDSDR protocol is fully documented in `network.md` (VERIFIED) | RX only, 48 kHz, one mode at a time: I/Q (HDSDR) or control+audio (wfview), never both over LAN |
| No bridge latency; no firmware change | Per-application work; no HPSDR ecosystem features (TX I/Q, meters, CW) |
| wfview users already covered | The IC-7300 emulation has quirks (05 selects the VFO; mode 06 becomes LSB) and only a partial CI-V map |

**Blocking unknowns:**
- the HDSDR-mode device id and any client-side expectations of the
  vendor's own software (not in the repo);
- whether a scope waveform is ever sent in wfview mode.

### Comparison

| Route | RX I/Q | TX I/Q | Max rate (derived) | Firmware change | Main risk |
| --- | --- | --- | --- | --- | --- |
| (a) native HPSDR firmware | 24-bit | yes | P1 96 kHz (192 marginal) | full Main firmware | FPGA unknowns, install path |
| (b) bridge | 16-bit | no (audio only) | 48 kHz | none | split transports, latency |
| (c) app driver | 16-bit | no | 48 kHz | none | per-app effort, RX only |

## 4. Open questions that need hardware

| # | Question | Why it matters | How to answer |
| --- | --- | --- | --- |
| Q1 | The PE10 data-ready rate for span index 0..3 (48 × 1/2/4/8 kHz is a HYPOTHESIS) | Sets the HPSDR rate table and the SPI budget | Scope PE10, or count HDSDR `0x0202` packets per second per span |
| Q2 | The FPGA TX sample rate and how TX I/Q is clocked (per-interrupt count during TX) | Decides between P1 48 kHz and P2 192 kHz DUC and the need to resample | Logic analyser on PE0–PE10 while keyed into a dummy load |
| Q3 | The meaning of the configuration-frame words at TRX `0x200`–`0x208` and the per-rate calibration bytes | Needed to tune the FPGA without the OEM firmware | Correlate with VFO changes on a bus capture |
| Q4 | The maximum SPI clock the CH394 accepts on this board, and the measured SPI6 efficiency | Raises or lowers every row of §2.4 | Datasheet plus a throughput test |
| Q5 | Whether the FPGA can run two DDCs, a feedback receiver or raw-ADC output, given its unknown bitstream (it boots from its own flash, HIGH) | Multi-RX, PureSignal and wideband are impossible without it | FPGA identification on the board; vendor information |
| Q6 | Whether the bootloader (not in the images) accepts an independently built Main image, and how it is delivered (Main has no external USB) | Gate for route (a) | Bootloader analysis or a vendor statement |
| Q7 | Whether RX continues during TX (full-duplex monitoring) | P1 duplex bit, P2 feedback | Observe I/Q while keyed into a dummy load |
| Q8 | The `0x0103` LO semantics and the `0x0202` I/Q orientation and scale | Correct spectra for routes (b) and (c) | Signal-generator test in HDSDR mode |
| Q9 | What the three 16-bit values in FPGA status (`0x02`) are | Possible extra meters or FIFO levels for the HPSDR status words | Bus capture across RX/TX and overload |

**Recommendation (HYPOTHESIS until Q1/Q2 are answered).**
1. **Start with route (c)** for an RX-only HDSDR-mode source. It is a
   cheap way to answer Q1 and Q8 on real hardware.
2. **Build route (b)** on the same code for P1 RX compatibility.
3. **Plan route (a)** around P1 at 48/96 kHz with a single receiver.
   It is the only path to TX I/Q, and only once Q2 and Q6 are settled.

## Sources

**G7250 (this repo):**
- `docs/architecture.md`, `docs/protocol.md`, `docs/civ.md`,
  `docs/x6100_comparison.md`;
- `main_unit/docs/network.md`, `dsp.md`, `peripherals.md`, `flow.md`;
- `main_unit/analysis/peripherals/ch394_network.csv`,
  `spi6_ch394.csv`, `fpga_bus.csv`, `timers.csv`, `vc6_clock_plan.csv`;
- `main_unit/analysis/protocol/msg_types.csv`, `cmd01_fields.csv`,
  `cmd03_fields.csv`, `civ_main.csv`;
- `main_unit/analysis/dsp/dsp_functions.csv`.

**HPSDR (public):**
- OpenHPSDR P1 (Metis Ethernet framing, discovery, start/stop):
  <https://github.com/TAPR/OpenHPSDR-Firmware/blob/master/Protocol%201/Documentation/Metis-%20How%20it%20works_V1.33.pdf>
- OpenHPSDR P1 frame and C&C map (USB protocol V1.58):
  <https://github.com/TAPR/OpenHPSDR-SVN/blob/master/Documentation/USB_protocol_V1.58.doc>
- OpenHPSDR P2 (Ethernet protocol v4.4: ports, DDC/DUC/mic packets,
  watchdog):
  <https://github.com/TAPR/OpenHPSDR-Firmware/blob/master/Protocol%202/Documentation/openHPSDR%20Ethernet%20Protocol%20v4.4.pdf>
- Hermes-Lite 2 protocol (address map, extensions, watchdog, board id):
  <https://github.com/softerhardware/Hermes-Lite2/wiki/Protocol>
