// Add volatile memory regions that are absent from a raw binary import.
//
// Target: STM32H7 single-core (H743/H750/H753-class). Selected because the
// reset vectors place the initial stack pointer in AXI SRAM at 0x24000000
// (ControlUnit MSP = 0x24080000 = top of the 512 KiB AXI SRAM on this class).
// This is HIGH CONFIDENCE pending confirmation of the exact part number; if a
// larger-RAM variant (e.g. H7A3/H7B3) is confirmed, adjust AXI_SRAM size.
//
// These blocks contain no invented initialization data. They only let Ghidra
// create references to RAM addresses the firmware uses. Initial values still
// come solely from the recovered .data copy.
//
// @category G7250

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;

public class MapSTM32H7Memory extends GhidraScript {
	@Override
	protected void run() throws Exception {
		Memory memory = currentProgram.getMemory();
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

	private void addBlock(Memory memory, String name, long startValue, long size, boolean read,
			boolean write, boolean execute) throws Exception {
		Address start = toAddr(startValue);
		MemoryBlock existing = memory.getBlock(start);
		if (existing != null) {
			return;
		}
		MemoryBlock block = memory.createUninitializedBlock(name, start, size, false);
		block.setRead(read);
		block.setWrite(write);
		block.setExecute(execute);
	}
}
