// Add volatile memory regions that are absent from a raw binary import.
//
// The two G7250 MCUs are different STM32H7 sub-families (docs/mcu_identification.md):
//
//   H743  Control Unit: STM32H743xI (H742/H743/H750/H753 class, RM0433).
//         Initial MSP 0x24080000 = top of the 512 KiB AXI SRAM. VERIFIED from the
//         reset vector. Layout below is unchanged from the original version of
//         this script.
//
//   H72X  Main Unit: STM32H725xG / H735xG (H723/H725/H730/H733/H735 class, RM0468).
//         Initial MSP 0x24050000 = top of a 320 KiB AXI SRAM, i.e. the default
//         TCM/AXI split (the 192 KiB shared block assigned to AXI). The firmware's
//         own MPU setup programs a 32 KiB region at 0x30000000 (D2 SRAM) and a
//         16 KiB region at 0x38000000 (SRAM4), which matches the RM0468 sizes.
//         Sizes taken from RM0468 from memory; see the per-line confidence notes.
//
// Layout selection, in order of precedence:
//   1. script argument:  -preScript MapSTM32H7Memory.java h72x   (or h743)
//   2. program name:     contains "MainUnit"    -> H72X
//                        contains "ControlUnit" -> H743
//   3. default:          H743 (the original behaviour of this script)
//
// These blocks contain no invented initialization data. They only let Ghidra
// create references to RAM addresses the firmware uses. Initial values still
// come solely from the recovered .data copy. Existing blocks are never touched,
// so re-running the script on an already-imported program is a no-op.
//
// @category G7250

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;

public class MapSTM32H7Memory extends GhidraScript {

	private static final String H743 = "h743";
	private static final String H72X = "h72x";

	@Override
	protected void run() throws Exception {
		String layout = selectLayout();
		println("MapSTM32H7Memory: layout " + layout + " for " + currentProgram.getName());
		Memory memory = currentProgram.getMemory();
		if (H72X.equals(layout)) {
			mapH72x(memory);
		}
		else {
			mapH743(memory);
		}
	}

	private String selectLayout() {
		String[] args = getScriptArgs();
		if (args != null && args.length > 0 && args[0] != null) {
			String a = args[0].trim().toLowerCase();
			if (a.equals(H72X) || a.equals("h723") || a.equals("h725") || a.equals("h730") ||
				a.equals("h733") || a.equals("h735") || a.equals("main")) {
				return H72X;
			}
			if (a.equals(H743) || a.equals("h742") || a.equals("h750") || a.equals("h753") ||
				a.equals("control")) {
				return H743;
			}
			printerr("MapSTM32H7Memory: unknown layout argument '" + args[0] +
				"', falling back to program-name detection");
		}
		String name = currentProgram.getName();
		if (name != null) {
			if (name.contains("MainUnit")) {
				return H72X;
			}
			if (name.contains("ControlUnit")) {
				return H743;
			}
		}
		return H743;
	}

	// STM32H742/H743/H750/H753 (RM0433). Identical to the original script.
	private void mapH743(Memory memory) throws Exception {
		// Tightly-coupled memory
		addBlock(memory, "ITCM", 0x00000000L, 0x10000L, true, true, true);   // 64 KiB
		addBlock(memory, "DTCM", 0x20000000L, 0x20000L, true, true, false);  // 128 KiB
		// D1 domain
		addBlock(memory, "AXI_SRAM", 0x24000000L, 0x80000L, true, true, true); // 512 KiB
		// D2 domain
		addBlock(memory, "SRAM1", 0x30000000L, 0x20000L, true, true, false); // 128 KiB
		addBlock(memory, "SRAM2", 0x30020000L, 0x20000L, true, true, false); // 128 KiB
		addBlock(memory, "SRAM3", 0x30040000L, 0x08000L, true, true, false); // 32 KiB
		// D3 domain
		addBlock(memory, "SRAM4", 0x38000000L, 0x10000L, true, true, false); // 64 KiB
		addBlock(memory, "BACKUP_SRAM", 0x38800000L, 0x1000L, true, true, false); // 4 KiB
	}

	// STM32H723/H725/H730/H733/H735 (RM0468), default TCM_AXI_SHARED setting.
	private void mapH72x(Memory memory) throws Exception {
		// Tightly-coupled memory. ITCM is 64 KiB with the default shared-RAM split
		// (it can grow to 256 KiB through the option bytes, at the expense of AXI).
		// HIGH CONFIDENCE; the Main firmware never references ITCM.
		addBlock(memory, "ITCM", 0x00000000L, 0x10000L, true, true, true);   // 64 KiB
		// DTCM 128 KiB (fixed). HIGH CONFIDENCE; unused by the Main firmware.
		addBlock(memory, "DTCM", 0x20000000L, 0x20000L, true, true, false);  // 128 KiB
		// D1 domain: 128 KiB fixed + 192 KiB shared = 320 KiB in the default split.
		// VERIFIED against the Main Unit stack top 0x24050000.
		addBlock(memory, "AXI_SRAM", 0x24000000L, 0x50000L, true, true, true); // 320 KiB
		// D2 domain: SRAM1 16 KiB + SRAM2 16 KiB, contiguous (no SRAM3 on this class).
		// HIGH CONFIDENCE; the firmware's MPU region for 0x30000000 is exactly 32 KiB.
		addBlock(memory, "SRAM1", 0x30000000L, 0x4000L, true, true, false);  // 16 KiB
		addBlock(memory, "SRAM2", 0x30004000L, 0x4000L, true, true, false);  // 16 KiB
		// D3 domain: SRAM4 16 KiB. HIGH CONFIDENCE; the firmware's MPU region for
		// 0x38000000 is exactly 16 KiB.
		addBlock(memory, "SRAM4", 0x38000000L, 0x4000L, true, true, false);  // 16 KiB
		// Backup SRAM 4 KiB. HIGH CONFIDENCE; MPU region 4 KiB.
		addBlock(memory, "BACKUP_SRAM", 0x38800000L, 0x1000L, true, true, false); // 4 KiB
	}

	private void addBlock(Memory memory, String name, long startValue, long size, boolean read,
			boolean write, boolean execute) throws Exception {
		Address start = toAddr(startValue);
		Address end = toAddr(startValue + size - 1);
		MemoryBlock existing = memory.getBlock(start);
		if (existing != null) {
			return;
		}
		if (memory.getBlock(end) != null) {
			printerr("MapSTM32H7Memory: " + name + " overlaps an existing block, skipped");
			return;
		}
		MemoryBlock block = memory.createUninitializedBlock(name, start, size, false);
		block.setRead(read);
		block.setWrite(write);
		block.setExecute(execute);
	}
}
