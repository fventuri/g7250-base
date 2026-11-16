# Contributors

The G7250 reverse-engineering effort, documentation, and tooling base were
started and are maintained by **Franco Venturi** (`fventuri`).

## Contributors

- **ON8ST** — the *todo-sweep* contribution (69 commits).
  Worked through the open TODO list and a self-identified second round of
  44 follow-up items, closing most of them with confidence-leveled,
  evidence-chained documentation. Highlights: clock trees and STM32H7
  sub-family identification for both units; GPIO / DMA / NVIC allocation;
  PA bias and T/R sequencing; the built-in ATU algorithm; the CI-V command
  set (both parsers); the SLIP message blocks (0x01/0x02/0x03/0x06/0x08)
  and TRX runtime struct; the audio / I-Q path (AIC3204, FPGA bus);
  EEPROM/NVPARAM layout; library identification; the Control-unit input,
  display, storage, and update paths. Also improved the Ghidra exporters
  and added a reproducible full-export runner and a documentation checker.

All contributions follow the clean-room rules in [AGENTS.md](AGENTS.md):
no firmware images or bytes, no decompiler or disassembler output, and
paraphrased log strings. Contributions were reviewed for clean-room
compliance before being merged.
