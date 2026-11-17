# CI-V implementations

Two independent CI-V parsers exist. Tables:
`main_unit/analysis/protocol/civ_main.csv` and
`control_unit/analysis/protocol/civ_control.csv`.

## Main Unit — wfview CI-V (UDP base port + 1)

**Emulated radio.** An **IC-7300** at address **0xA0**. The parser
(`0x080504E8`) runs only while a wfview session is streaming. It accepts
frames addressed to 0xA0 or 0x00 and replies from 0xA0 to the sender (VERIFIED).

**Dispatch.**
- Commands 0x00–0x06 are handled inline.
- 0x07–0x29 go through the jump table `0x080505A0` (HIGH CONFIDENCE).
- Sub-tables: `0x08050CC0` (0x14 levels) and `0x08050B40` (0x16 functions) (HIGH CONFIDENCE).
- 0x1A and 0x27 have their own handlers.
- 0x29 (VFO prefix) is stripped and the inner command re-dispatched, so
  the VFO selector is ignored.

**Replies.**
- Read commands answer in Icom format.
- Most set commands answer by echoing the command body. Only split, the
  band-stack store and unknown 0x1A sub-commands answer FB.
- Unknown commands are ignored; no FA is sent.
- Replies go through a 16-slot ring to the CI-V socket. When the ring is
  full, the reply is dropped.

**What is implemented.**
- Frequency and mode (00, 03, 04, 06, 25, 26), VFO operations (07), split
  (0F), attenuator (11) and antenna (12).
- Levels (14): AF, RF, SQL, NR, CW pitch, RF power 5–100 W, mic gain, key
  speed 6–48 WPM, compressor ratio, break-in delay, NB, monitor and VOX.
- Meters (15) from the `0x03` status tail: S, Po, SWR, ALC, Vd, Id.
- Functions (16): preamp, NB, NR, auto notch, compressor, monitor, VOX,
  break-in.
- ID (19), extended (1A: band stack, filter width, AGC, data mode),
  PTT/ATU (1C), RIT (21) and scope control (27).
- Several values (tones, PBT, anti-VOX, scope mode) are only stored and
  read back.

**Quirks.**
- 0x05 selects or reads the VFO instead of setting a frequency.
- Setting mode 06 (WFM) results in LSB.

## Control Unit — local CI-V (USART1)

**Transport.** The Control Unit parses CI-V frames from its USART1
receive stream. The same stream carries the Bluetooth module's AT
dialogue; the physical endpoint (Bluetooth SPP and/or the PC serial
bridge) is a HYPOTHESIS.

**Addressing.** It answers any address and replies with FB/FA. 0x19
returns the address it was called with.

**Commands.** 02–07, 0F, 11, 14, 15, 16, 19, 1A, 1C, 1D (vendor
sub-commands), 25 and 26. They act on the front-panel state, which then
reaches Main through SLIP `0x01`.

**Unsolicited output and safety.**
- It sends a 0x00 transceive frame to the last peer when the active VFO
  frequency changes.
- A CI-V PTT is dropped after 10 s without CI-V traffic.

**Why this needed the firmware:** the implemented subset, scaling, reply
style and the second endpoint are not documented by the vendor.
