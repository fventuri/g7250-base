// Create functions at every in-image vector-table target (reset, faults and IRQ
// handlers) of a raw STM32H7 image, then let auto-analysis follow their calls.
//
// A raw-binary import does not create functions at vector targets, so handlers and
// everything only reachable from them (e.g. SystemInit, called from Reset_Handler)
// stay undiscovered or are absorbed into a neighbouring function body. Run this once
// on a WRITABLE project right after import (tools/run_full_export.sh does so).
//
// Optional argument: vector-table base (default 0x08020000).
// It does not rename anything; names stay FUN_xxxxxxxx.
// @category G7250

import ghidra.app.cmd.function.CreateFunctionCmd;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.mem.Memory;

public class CreateVectorFunctions extends GhidraScript {
	@Override
	protected void run() throws Exception {
		String[] args = getScriptArgs();
		Memory memory = currentProgram.getMemory();
		FunctionManager fm = currentProgram.getFunctionManager();
		// default: the G7250 application base (the RAM blocks added by
		// MapSTM32H7Memory make getMinAddress() useless here)
		Address base = toAddr(args.length > 0 ? args[0] : "0x08020000");
		ghidra.program.model.mem.MemoryBlock image = memory.getBlock(base);
		if (image == null || !image.isInitialized()) {
			throw new IllegalArgumentException("no initialized image block at " + base);
		}
		long lo = image.getStart().getOffset();
		long hi = image.getEnd().getOffset();

		int created = 0, split = 0, existing = 0, entries = 0;
		// entry 0 is the initial MSP; stop at the first word that is not an odd
		// in-image pointer or zero (reserved slots are zero)
		// STM32H7: 16 core + at most 165 external vectors
		for (int i = 1; i < 16 + 165; i++) {
			long v = memory.getInt(base.add(4L * i)) & 0xffffffffL;
			if (v == 0) {
				continue;
			}
			if ((v & 1) == 0 || v < lo || v > hi) {
				break;
			}
			entries++;
			Address target = toAddr(v & ~1L);
			if (fm.getFunctionAt(target) != null) {
				existing++;
				continue;
			}
			Function owner = fm.getFunctionContaining(target);
			Address ownerEntry = null;
			if (owner != null) {
				ownerEntry = owner.getEntryPoint();
				fm.removeFunction(ownerEntry);
				split++;
			}
			disassemble(target);
			if (new CreateFunctionCmd(target).applyTo(currentProgram, monitor)) {
				created++;
			} else {
				printerr("could not create a function at " + target);
			}
			if (ownerEntry != null && fm.getFunctionAt(ownerEntry) == null) {
				new CreateFunctionCmd(ownerEntry).applyTo(currentProgram, monitor);
			}
		}
		analyzeChanges(currentProgram);
		println(String.format("vector entries %d: created %d (split %d), already present %d",
			entries, created, split, existing));
	}
}
