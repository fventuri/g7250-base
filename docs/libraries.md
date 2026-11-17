# Libraries and code layout (both units)

About 45 % of the Main code and 36 % of the Control code (in bytes) is
library, CubeMX-generated or toolchain code. That code does not need
reverse engineering: a compatible firmware can use the same public
libraries. Per-function tables:
- `*/analysis/libs/lib_functions.csv` (address, library, proposed name,
  confidence, basis);
- `lib_regions.csv`;
- `lib_names.csv`;
- `lib_summary.csv`.

## Method

Three independent signals, each region tagged with its own confidence:

1. **Link order.** CubeIDE links objects in source-path order. The plain
   `.text` input sections (crt, libgcc, newlib assembly) land before all
   per-function sections.
2. **Cross-unit identity.** Function bodies are normalised by masking
   BL/B.W immediates and then compared between the two units. 174
   functions are byte-identical across the units.
3. **Shape signatures.** Register use, constants, assert-text
   references, sizes and file order.

**Toolchain (VERIFIED).** Both images were linked with ST's build of GNU
Tools for STM32 12.3.rel1 (the STM32CubeIDE 1.17.0 toolchain plugin,
built in late September 2024). The multilib is `thumb/v7e-m+dp/hard`
with newlib-nano (`--specs=nano.specs`) and float `printf` enabled; Main
also enables float `scanf`. Arm's own 12.3.Rel1 release matches libgcc
but not most of newlib and libm: ST rebuilt newlib, so match against
ST's archives.

## Main Unit layout (HIGH CONFIDENCE unless noted)

| Range | Content |
| --- | --- |
| `0x08020000`–`0x08020DE0` | toolchain runtime |
| –`0x080245A8` | CubeMX Core/Src (adc → usart order) |
| –`0x08027728` | CMSIS-DSP |
| –`0x080312B4` | ST HAL, modules in alphabetical order (hal, adc, cortex, crc, dac, dma, gpio, i2c, i2s, pwr, rcc, rtc, spi, tim, uart) |
| –`0x08052C44` | application |
| –`0x08057534` | newlib-nano libc |
| –`0x0805AEC0` | libm (VERIFIED: starts with acos at `0x08057534`) |
| after that | crti/crtn |

## Control Unit layout (HIGH CONFIDENCE unless noted)

| Range | Content |
| --- | --- |
| `0x08020000`–`0x08020D48` | toolchain runtime |
| –`0x080236D0` | CubeMX Core/Src |
| –`0x08024B68` | CMSIS-DSP |
| –`0x08031BC4` | ST HAL plus LL FMC/SDMMC/USB |
| –`0x080375E4` | application drivers |
| `0x080375E4`–`0x08037D68` | minIni |
| –`0x08039B9C` | ST USB device library (MEDIUM) |
| –`0x08039FBC` | STemWin glue (MEDIUM) |
| –`0x0803D904` | FatFS |
| –`0x0803DF14` | CubeMX USB_DEVICE |
| –`0x0807AC6C` | application |
| –`0x08084ED0` | SEGGER emWin (GUI context pointer `0x24000038`) |
| –`0x0808A0FC` | newlib (libc and libm); crti `_init` at `0x0808A0FC` |

## Counts (functions / bytes)

| Library | Main | Control |
| --- | --- | --- |
| application | 305 / 111 400 | 850 / 238 072 |
| ST HAL | 139 / 32 204 | 221 / 47 262 |
| CubeMX generated | 81 / 13 358 | 131 / 15 474 (Core/Src, USB_DEVICE, STemWin glue) |
| newlib libc (+ libm) | 139 / 30 366 | 111 / 19 662 |
| CMSIS-DSP | 35 / 12 132 | 12 / 5 192 |
| toolchain runtime | 16 / 1 796 | 16 / 1 750 |
| SEGGER emWin | — | 316 / 29 180 |
| FatFS | — | 35 / 14 444 |
| minIni | — | 6 / 1 838 |
| ST USB device library | — | 23 / 1 106 |
| **Total** | **715 / 201 256** | **1721 / 373 980** |

The counts come from an export with the vector-target functions
created (`CreateVectorFunctions.java`).

## Notable results

- **Logging (HIGH CONFIDENCE).** `FUN_08053A4C` and `FUN_08053B2C` on
  Main are newlib `printf` and `puts`. Their output reaches USART1
  through the `_write` syscall.
- **DSP routines.**
  - The DF2T biquad `0x0803AB34` is application code that only looks
    CMSIS-shaped (HIGH CONFIDENCE).
  - The FIR, decimator and interpolator routines (`0x08024FC8`,
    `0x08025378`, `0x080257A4`) are stock CMSIS-DSP (HIGH CONFIDENCE).
- **Shared module (HIGH CONFIDENCE).** The AIC3204 codec driver is
  byte-identical on both units: Main `0x08044034`–`0x080444D4` equals
  Control `0x08031EB8`–`0x080324F4`. SLIP encode/decode and the CRC-16
  are also identical.
- **emWin version.** V5.44a, the STemWin build from STM32Cube (VERIFIED; see `control_unit/docs/gui.md`).
- **Licensing (non-technical note).** SEGGER emWin is licensed to ST
  customers for STM32 use. An independent firmware needs its own GUI
  library or a licence check.

## Exact toolchain matching

`tools/match_static_libs.py` searches each image for every function in
libc_nano.a, libm.a, libgcc.a and the crt objects of the ST toolchain.
Bytes under relocations are masked; short or same-shape functions are
confirmed by decoding their branches. Results are in
`*/analysis/libs/toolchain_matches.csv` (address, size, archive, object,
symbol, match quality; no code bytes), and the multilib comparison in
`main_unit/analysis/libs/multilib_comparison.csv`.

| | Main | Control |
| --- | --- | --- |
| libc_nano (exact / masked) | 34 / 80 functions, 19.3 KB | 34 / 92 functions, 20.5 KB |
| libm | 56 functions, 14.2 KB | 5 functions, 0.6 KB |
| libgcc | 23 functions, 4.1 KB | 21 functions, 4.0 KB |
| crtbegin + crti | 3 | 3 |

Every newlib function in the Main layout is matched; Control is matched
except for 4-byte stubs. No match falls outside the toolchain regions
(VERIFIED). Results:
- The two 64-bit division wrappers are `__aeabi_ldivmod` and
  `__aeabi_uldivmod`.
- Main `FUN_08053B2C` is the `puts` wrapper; `_puts_r` is at
  `0x08053A80`.
- Main `_read_r` and `_write_r` call application code, which overrides
  the weak CubeMX syscalls (HIGH CONFIDENCE).
- Control libm is only `llround`, `sinf` and the float error helpers.

## Open

- STemWin 5.44a exact matching: the archive is only distributed after
  st.com login or e-mail confirmation, so it was not used.
- Exact start of Control libc (about `0x08084ED0`), the USB library
  extent, and the Main libm boundary.
