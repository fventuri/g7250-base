# Control Unit — GUI layer (PARTIAL)

**Library.** SEGGER emWin **V5.44a** (ST's STemWin build), drawing to
the LTDC frame buffer in SDRAM with DMA2D. emWin is used for drawing
only (text, shapes, bitmaps, simple label objects).

**Navigation is the application's own.**
- A superloop task (`FUN_08046cd8`) takes press and release events from
  the GT911 driver and dispatches on the current screen id.
- The screen id is the UI byte `selectUi`; sub-pages use `appUi`,
  `cwMsgUi`, `ssbVoiceUi` and `windows`.
- `selectUi` is saved in config.ini, so the radio reopens the last screen.

**Screens** (`selectUi`, UI +0x920; VERIFIED unless noted).
- **Writers:** the button handler `FUN_08042c20`, the touch handlers and
  `FUN_08046a88`.
- **Readers:** the touch dispatcher `FUN_08046cd8` and the page
  refresher `FUN_080508d0` have cases for 0 and 4–12 only.

| id | screen | opened by |
| ---: | --- | --- |
| 0 | main | every exit path |
| 1–3 | unused (no writer, no dispatch case) | — |
| 4 | Menu 1, general (2 pages × 15 items) | button A0×B3 |
| 5 | Menu 2, display and EQ (2 pages) | button A1×B3 |
| 6 | Menu 3, CW | button A0×B4 on the main screen in CW mode |
| 7 | system; sub-page in UI +0x921: 1 date/time, 2 info (MEDIUM), 3 storage (HYPOTHESIS), 4 Bluetooth (MEDIUM), 5 network, 6 network keyboard, 7 last item (HYPOTHESIS) | button A2×B3 |
| 8 | memory channels (with a name keyboard) | button A0×B0, touch |
| 9 | applications; `appUi` 0 list, 2 SWR scanner, 1 unidentified | button A3×B1 |
| 10 | keyer memory | button A3×B0 in CW/CWR |
| 11 | voice memory | button A3×B0 in voice modes |
| 12 | quick setting (picks the quick-button function) | hold A3×B2 |

The main screen also has overlays in `windows` (UI +0xBAC); 2 is the
band selector. `FUN_080508d0` redraws whichever of ids 4–12 is open
(correction: it is not the memory-channel page).

The band selector is an overlay on the main screen; quick setting is page 12.

**Widgets and settings.**
- Each page is hand-coded; there is no table-driven menu.
- Item actions write one field of the UI state block. The field names are
  those of the config.ini descriptor table (see `storage.md`).
- The state block is copied into the SLIP `0x01` image every superloop
  pass.
- The status bar mirrors the Main status word from `0x03`: MUTE, OVF,
  REMOTE, the LAN icon and the TX state.

**Touch.** There is no user calibration. At start-up the GT911
configuration checksum is checked, then GT911 commands 3 (baseline
update) and 4 (calibrate) are issued. Coordinates are used unscaled
(MEDIUM).

**Licence note.** STemWin may be used only on STM32 parts under ST's
licence; a re-implementation must bring its own copy or another library.

The page functions are: main screen `FUN_0804e670`/`FUN_0804e8a8`; menus `FUN_0805c104`, `FUN_0805e168`, `FUN_080601c0`; system `FUN_08061fa4`; page refresher `FUN_080508d0`; applications `FUN_08052e3c`; keyer memory `FUN_080715dc`; voice `FUN_08077e38`. The navigation task is `FUN_08046cd8`; the status bar is drawn by `FUN_0804de38`.

## Button and encoder map — VERIFIED unless noted

**Events.** `FUN_08042c20` uses the release (short) and hold events.
- A release after a hold is suppressed, and the repeat event is
  discarded.
- PA0 (bit 15) is never compared, and while it is held every matrix
  button is dead.
- Most buttons are ignored while the SWR scanner runs.

Table: `analysis/peripherals/button_map.csv`.

**Buttons (A × B).** 22 matrix codes are used; A4×B1, A4×B3 and A4×B4
are not.

| Position | B0 | B1 | B2 | B3 | B4 |
| --- | --- | --- | --- | --- | --- |
| **A0** | memory page | VFO A/B swap (hold copies B into A) | V/M toggle | Menu 1 | confirm/assign (hold restores the default) |
| **A1** | RIT | XIT | ATU (hold starts a tune) | Menu 2 | filter group FIL1/2/3 (hold resets it) |
| **A2** | NF | NR | NB | system page | MIC/KEY SPEED switch for encoder 4 |
| **A3** | message page (keyer or voice by mode) | applications page | quick button (hold opens quick setting) | backlight step (hold toggles the dial lock) | AF/RF switch for encoder 6 |
| **A4** | band up / next memory channel | — | band down / previous memory channel | — | — |

**Details.**
- On NF, NR and NB, hold opens the level pop-up; on RIT and XIT, hold
  opens their pop-up.
- **Confirm/assign (A0×B4)** assigns a menu item to the MFK, picks the
  quick function, toggles edit mode, or opens Menu 3 in CW.
- The four B4 buttons are probably the knob pushes (HYPOTHESIS).

**Encoders.** The "fast" flag is computed but never read, so no knob
accelerates. Table: `analysis/peripherals/encoder_map.csv`.

| Encoder | Function |
| --- | --- |
| enc0 | value knob: adjusts the open pop-up (notch position, NR/NB level, RIT/XIT ±1500 Hz), otherwise tunes in coarse per-mode steps; on pages it changes the highlighted value or scrolls |
| enc1 | cursor knob, or the MFK on the main screen |
| enc2 / enc3 | shift the FIL2 / FIL1 edge pair by 10 Hz per detent |
| enc4 | MIC gain 0–30 or key speed 5–50 |
| enc5 | RF power 5–100 W |
| enc6 | AF gain 0–100 (2 per detent at 50 and above) or RF gain |
| enc7 | squelch (`sql`, or `fmSql` in FM) |
| main dial | frequency: each TIM2 count moves it by `freqStep` (1 Hz–100 kHz), on a 1 kHz grid for steps of 1 kHz and up; blocked by `lock` |

**MFK list** (`mfkOuterSelect`, 60 entries).

| Entries | Function |
| --- | --- |
| 0 | dial step |
| 1–3 | PRE, ATT, AGC |
| 4–6 | VOX, COMP, SPLIT |
| 7–11 | VOX time and threshold, line in, line out, monitor |
| 12–15 | per-mode steps |
| 16 | MIC gain |
| 17 | flags 1 bit 0 |
| 18–20 | TX bandwidth |
| 21 | band-stack mode |
| 22–24 | handset F1–F3 |
| 25 | ANT |
| 26 | COMP ratio |
| 27 | beep volume |
| 28–33 | FFT ref, span, CW zoom, WF ref, WF gain, scope height |
| 34–37 | screen off, dim, dim enable, waterfall drag |
| 38–49 | EQ bands and enables |
| 50–59 | CW settings |

**Quick button functions** (`quickSelect`, 15 entries): PRE cycle, ATT,
AGC cycle, VOX, COMP, SPLIT, ANT, EQ RX, EQ AM/FM, span, CW zoom, key
type, iambic type, trainer, decoder.

**Level bar.** `progressSelect` shows a bar for 3 s: AF, RF, SQL, MIC,
key speed, RF power, BW/shift, filter reset.

Open: the panel legends, the knob/push pairing, FIL1 versus FIL2
meaning, the PA0 wiring, `appUi` 1, system sub-pages 2/3/4/7 and
`windows` 1/3.

