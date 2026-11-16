# Voice recorder, voice auto-call and CW memories (Control Unit)

Status: VERIFIED for the software unless noted; the analog routing is a
HYPOTHESIS.

## Voice

- **Files.** 10 slots, VOICE-01.wav to VOICE-10.wav on the SD card
  (volume 0).
- **Format.** PCM, mono, 16-bit, 48 kHz, with a 44-byte RIFF/WAVE
  header (writer `FUN_08052588`). Maximum length 30 s.
- **Recording.** Takes codec input slot 1 (the right channel, presumably
  the mic) into SDRAM, then writes the file.
- **Playback** (`FUN_08052660`).
  - Checks the header tags, PCM, 16-bit and mono; the sample rate is
    not checked.
  - Loads the whole file into SDRAM and plays it from a TIM5 audio
    hook: into codec output slot 1 when voice monitor is off, or both
    slots when it is on.
  - PI6 is driven low while playing (PTT line to the Main Unit?
    HYPOTHESIS).
- **Auto-call.** Repeats the slot with a fixed 1 s gap.
- **No digital path to Main.** No SLIP message carries voice audio. It
  reaches the Main Unit as analog audio over the CTRL cable (MEDIUM).

## CW memories

- **Storage.** 10 messages of up to 60 characters, kept in the CW-call
  INI file on the SPI-flash volume (1:), one section per message. The
  manual says the card; the firmware uses the SPI flash (HIGH
  CONFIDENCE).
- **Sending** (`FUN_08046518`, `FUN_080442c4`):
  1. Force straight-key mode on the Main Unit (`0x01` byte 0x134 = 0).
  2. Convert the text into dots and dashes (WPM 5–50, ratio 2.5–4.5).
  3. Key with Control TIM7 at 1/10-dot resolution, pulling PE3 and PE4
     low together for key-down. A dot is 10 ticks, a dash ratio × 10;
     the letter gap is 3 dots and the word gap 7 dots.
  4. Restore the key type.
- **Auto-call.** Repeats with a 1 s gap.

**Why this needed the firmware:** formats, limits, the storage volume
and the keying path are software choices.
