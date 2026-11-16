// Export non-default STM32F427 interrupt handlers without renaming symbols.
// @category X6100

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.HashSet;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.Memory;

public class ExportInterruptEvidence extends GhidraScript {
	private static final long VECTOR_BASE = 0x08020000L;
	private static final int CORE_VECTOR_COUNT = 16;
	// Upper bound only. The real number of external IRQ slots is measured from the image
	// (see measureIrqCount()); the old fixed STM32F427 value (91) silently dropped IRQ91+
	// (e.g. OTG_FS 101, TIM17 118, BDMA 129/130 on the G7250 images).
	private static final int MAX_EXTERNAL_IRQ_COUNT = 256;
	private int externalIrqCount;

	@Override
	protected void run() throws Exception {
		String[] args = getScriptArgs();
		if (args.length != 1) {
			throw new IllegalArgumentException("usage: ExportInterruptEvidence.java <output-directory>");
		}
		File outputDirectory = new File(args[0]);
		if (!outputDirectory.isDirectory() && !outputDirectory.mkdirs()) {
			throw new IllegalStateException("cannot create output directory: " + outputDirectory);
		}

		Memory memory = currentProgram.getMemory();
		Address vectorBase = toAddr(VECTOR_BASE);
		externalIrqCount = measureIrqCount(memory, vectorBase);
		long defaultValue = mostFrequentHandler(memory, vectorBase);
		Set<Long> exportedAddresses = new HashSet<>();

		try (BufferedWriter writer =
			new BufferedWriter(new FileWriter(new File(outputDirectory, "active_irqs.csv")))) {
			writer.write("irq,standard_name,vector_offset,value,code_address,current_name\n");
			for (int irq = 0; irq < externalIrqCount; irq++) {
				int vectorIndex = CORE_VECTOR_COUNT + irq;
				long value = readUnsignedInt(memory, vectorBase.add(vectorIndex * 4L));
				if (value == 0 || value == defaultValue) {
					continue;
				}
				long codeValue = value & ~1L;
				Address codeAddress = toAddr(codeValue);
				Function function = recoverFunction(codeAddress);
				String currentName = function == null ? "" : function.getName();
				writer.write(String.format("%d,%s,0x%03X,0x%08X,0x%08X,%s%n",
					irq, standardName(irq), vectorIndex * 4, value, codeValue, currentName));

				if (function != null && exportedAddresses.add(codeValue)) {
					String stem = String.format("irq_%02d_%s_%s", irq, standardName(irq),
						codeAddress.toString());
					exportDisassembly(function, new File(outputDirectory, stem + "_disassembly.txt"));
					exportDecompilation(function, new File(outputDirectory, stem + "_decompile.c"));
				}
			}
		}
	}

	private long mostFrequentHandler(Memory memory, Address vectorBase) throws Exception {
		long bestValue = 0;
		int bestCount = 0;
		for (int candidateIrq = 0; candidateIrq < externalIrqCount; candidateIrq++) {
			long candidate = readUnsignedInt(memory,
				vectorBase.add((CORE_VECTOR_COUNT + candidateIrq) * 4L));
			if (candidate == 0) {
				continue;
			}
			int count = 0;
			for (int irq = 0; irq < externalIrqCount; irq++) {
				long value =
					readUnsignedInt(memory, vectorBase.add((CORE_VECTOR_COUNT + irq) * 4L));
				if (value == candidate) {
					count++;
				}
			}
			if (count > bestCount) {
				bestValue = candidate;
				bestCount = count;
			}
		}
		return bestValue;
	}

	// Count external IRQ slots: entries are accepted while they are 0 (reserved) or a Thumb
	// pointer into the image; the first other word ends the table.
	private int measureIrqCount(Memory memory, Address vectorBase) throws Exception {
		Address imageMin = currentProgram.getMinAddress();
		Address imageMax = currentProgram.getMaxAddress();
		int count = 0;
		while (count < MAX_EXTERNAL_IRQ_COUNT) {
			long value = readUnsignedInt(memory,
				vectorBase.add((CORE_VECTOR_COUNT + count) * 4L));
			if (value != 0) {
				Address code = toAddr(value & ~1L);
				boolean ok = (value & 1L) != 0 && code.compareTo(imageMin) >= 0 &&
					code.compareTo(imageMax) <= 0;
				if (!ok) {
					break;
				}
			}
			count++;
		}
		return count;
	}

	private long readUnsignedInt(Memory memory, Address address) throws Exception {
		return Integer.toUnsignedLong(memory.getInt(address));
	}

	private Function recoverFunction(Address address) throws Exception {
		Function function = getFunctionAt(address);
		if (function == null) {
			disassemble(address);
			function = createFunction(address, null);
		}
		return function;
	}

	private String standardName(int irq) {
		switch (irq) {
			case 14:
				return "DMA1_Stream3";
			case 28:
				return "TIM2";
			case 29:
				return "TIM3";
			case 30:
				return "TIM4";
			case 72:
				return "I2C3_EV";
			case 73:
				return "I2C3_ER";
			default:
				return "IRQ" + irq;
		}
	}

	private void exportDisassembly(Function function, File output) throws Exception {
		try (BufferedWriter writer = new BufferedWriter(new FileWriter(output))) {
			InstructionIterator instructions =
				currentProgram.getListing().getInstructions(function.getBody(), true);
			while (instructions.hasNext()) {
				Instruction instruction = instructions.next();
				writer.write(instruction.getAddress() + "  " + instruction + "\n");
			}
		}
	}

	private void exportDecompilation(Function function, File output) throws Exception {
		DecompInterface decompiler = new DecompInterface();
		try {
			decompiler.openProgram(currentProgram);
			DecompileResults results = decompiler.decompileFunction(function, 60, monitor);
			try (BufferedWriter writer = new BufferedWriter(new FileWriter(output))) {
				if (results.decompileCompleted()) {
					writer.write(results.getDecompiledFunction().getC());
				}
				else {
					writer.write("/* Decompilation failed: " + results.getErrorMessage() + " */\n");
				}
			}
		}
		finally {
			decompiler.dispose();
		}
	}
}
