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

**Screens** (page ↔ id MEDIUM):

| id | screen |
| ---: | --- |
| 0 | main |
| 4 | Menu 1 (general, 2 pages) |
| 5 | Menu 2 (display, 2 pages) |
| 6 | Menu 3 (CW) |
| 7 | system (time, info, network, SD format, factory reset) |
| 8 | memory channels |
| 9 | applications (SWR scanner, Bluetooth, CW trainer) |
| 10 | keyer memory |
| 11 | voice memory/recorder |

Quick-setting and band-stack overlays sit on top of the main screen.

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

The page functions are: main screen `FUN_0804e670`/`FUN_0804e8a8`; menus `FUN_0805c104`, `FUN_0805e168`, `FUN_080601c0`; system `FUN_08061fa4`; memory channels `FUN_080508d0`; applications `FUN_08052e3c`; keyer memory `FUN_080715dc`; voice `FUN_08077e38`. The navigation task is `FUN_08046cd8`; the status bar is drawn by `FUN_0804de38`.
