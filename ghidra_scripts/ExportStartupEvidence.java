// Export Cortex-M vector entries and Reset_Handler evidence without renaming symbols.
// @category X6100

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.List;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.lang.Register;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.FlowType;
import ghidra.program.model.symbol.Reference;

public class ExportStartupEvidence extends GhidraScript {
	private static final long IMAGE_BASE = 0x08020000L;
	// Upper bound only: the real table length is measured from the image (see vectorCount()).
	// STM32H7 parts have ~150-165 external IRQs; the old fixed STM32F427 value (16 + 91)
	// silently dropped IRQ91+ (e.g. OTG_FS 101, TIM17 118, BDMA 129/130 on these images).
	private static final int MAX_VECTOR_COUNT = 16 + 256;

	@Override
	protected void run() throws Exception {
		String[] args = getScriptArgs();
		if (args.length != 1) {
			throw new IllegalArgumentException("usage: ExportStartupEvidence.java <output-directory>");
		}

		File outputDirectory = new File(args[0]);
		if (!outputDirectory.isDirectory() && !outputDirectory.mkdirs()) {
			throw new IllegalStateException("cannot create output directory: " + outputDirectory);
		}

		Memory memory = currentProgram.getMemory();
		Address vectorBase = toAddr(IMAGE_BASE);
		long initialMsp = readUnsignedInt(memory, vectorBase);
		long resetVector = readUnsignedInt(memory, vectorBase.add(4));
		Address resetAddress = toAddr(resetVector & ~1L);

		exportVectors(memory, vectorBase, new File(outputDirectory, "vectors.csv"));

		Function resetFunction = getFunctionAt(resetAddress);
		if (resetFunction == null) {
			disassemble(resetAddress);
			resetFunction = createFunction(resetAddress, null);
		}
		if (resetFunction == null) {
			throw new IllegalStateException("failed to recover function at " + resetAddress);
		}

		exportDisassembly(resetFunction, new File(outputDirectory, "reset_disassembly.txt"));
		exportDecompilation(resetFunction, new File(outputDirectory, "reset_decompile.c"));
		exportDirectCallees(resetFunction, outputDirectory);
		exportRuntimeArrays(memory, resetFunction, new File(outputDirectory, "runtime_arrays.txt"));

		try (BufferedWriter writer =
			new BufferedWriter(new FileWriter(new File(outputDirectory, "startup_summary.txt")))) {
			writer.write(String.format("image_base=0x%08X%n", IMAGE_BASE));
			writer.write(String.format("initial_msp=0x%08X%n", initialMsp));
			writer.write(String.format("reset_vector=0x%08X%n", resetVector));
			writer.write(String.format("reset_code_address=0x%08X%n", resetVector & ~1L));
			writer.write("reset_current_name=" + resetFunction.getName() + "\n");
			writer.write("reset_body=" + resetFunction.getBody() + "\n");
		}
	}

	/**
	 * Locate __libc_init_array from the Reset_Handler call chain instead of a fixed literal-pool
	 * address. The old code read a hard-coded X6100 address (0x08037f08), which is ordinary code
	 * on the G7250 images, so its preinit/init numbers were garbage.
	 *
	 * newlib's __libc_init_array has a fixed shape: four PC-relative literal loads (preinit
	 * start/end, then init start/end), exactly one direct call (_init) after all four loads, and
	 * indirect calls (blx) through the array entries. A candidate is accepted only if both ranges
	 * validate: end >= start, 4-byte aligned, inside the image, every entry a Thumb pointer into
	 * the image. If nothing matches, the file says so instead of printing numbers.
	 */
	private void exportRuntimeArrays(Memory memory, Function resetFunction, File output)
			throws Exception {
		List<Function> candidates = new ArrayList<>();
		for (Function callee : directCallees(resetFunction)) {
			if (!candidates.contains(callee)) {
				candidates.add(callee);
			}
		}
		LibcInitArray found = null;
		for (Function candidate : candidates) {
			found = matchLibcInitArray(memory, candidate);
			if (found != null) {
				break;
			}
		}

		try (BufferedWriter writer = new BufferedWriter(new FileWriter(output))) {
			if (found == null) {
				writer.write("status=not_found\n");
				writer.write(
					"note=no Reset_Handler callee matches the newlib __libc_init_array shape\n");
				return;
			}
			writer.write("status=ok\n");
			writer.write("method=reset_handler_callee_pattern\n");
			writer.write("libc_init_array=" + found.function.getEntryPoint() + "\n");
			writer.write("init_function=" + found.initCall + "\n");
			writeArray(writer, memory, "preinit", found.preinitStart, found.preinitEnd);
			writeArray(writer, memory, "init", found.initStart, found.initEnd);
		}
	}

	private static final class LibcInitArray {
		Function function;
		Address initCall;
		long preinitStart;
		long preinitEnd;
		long initStart;
		long initEnd;
	}

	private void writeArray(BufferedWriter writer, Memory memory, String name, long start,
			long end) throws Exception {
		writer.write(String.format("%s_start=0x%08X%n", name, start));
		writer.write(String.format("%s_end=0x%08X%n", name, end));
		writer.write(String.format("%s_count=%d%n", name, (end - start) / 4));
		for (long entryAddress = start; entryAddress < end; entryAddress += 4) {
			long value = readUnsignedInt(memory, toAddr(entryAddress));
			Function target = getFunctionAt(toAddr(value & ~1L));
			writer.write(String.format("%s_entry_0x%08X=0x%08X%s%n", name, entryAddress, value,
				target == null ? "" : " (" + target.getName() + ")"));
		}
	}

	private List<Function> directCallees(Function caller) {
		List<Function> result = new ArrayList<>();
		InstructionIterator instructions =
			currentProgram.getListing().getInstructions(caller.getBody(), true);
		while (instructions.hasNext()) {
			Instruction instruction = instructions.next();
			if (!instruction.getFlowType().isCall()) {
				continue;
			}
			for (Address destination : instruction.getFlows()) {
				Function callee = getFunctionAt(destination);
				if (callee != null) {
					result.add(callee);
				}
			}
		}
		return result;
	}

	private LibcInitArray matchLibcInitArray(Memory memory, Function function) throws Exception {
		List<Long> literals = new ArrayList<>();
		List<Integer> literalCountAtCall = new ArrayList<>();
		List<Address> callTargets = new ArrayList<>();
		boolean indirectCall = false;
		InstructionIterator instructions =
			currentProgram.getListing().getInstructions(function.getBody(), true);
		while (instructions.hasNext()) {
			Instruction instruction = instructions.next();
			FlowType flow = instruction.getFlowType();
			if (flow.isCall()) {
				if (flow.isComputed()) {
					indirectCall = true;
				}
				else {
					for (Address destination : instruction.getFlows()) {
						callTargets.add(destination);
						literalCountAtCall.add(literals.size());
					}
				}
				continue;
			}
			if (!isPcRelativeLiteralLoad(instruction)) {
				continue;
			}
			for (Reference reference : instruction.getReferencesFrom()) {
				if (reference.getReferenceType().isRead() &&
					memory.contains(reference.getToAddress())) {
					literals.add(readUnsignedInt(memory, reference.getToAddress()));
					break;
				}
			}
		}
		if (literals.size() != 4 || callTargets.size() != 1 || !indirectCall ||
			literalCountAtCall.get(0) != 4) {
			return null;
		}
		LibcInitArray result = new LibcInitArray();
		result.function = function;
		result.initCall = callTargets.get(0);
		result.preinitStart = Math.min(literals.get(0), literals.get(1));
		result.preinitEnd = Math.max(literals.get(0), literals.get(1));
		result.initStart = Math.min(literals.get(2), literals.get(3));
		result.initEnd = Math.max(literals.get(2), literals.get(3));
		if (!validArray(memory, result.preinitStart, result.preinitEnd) ||
			!validArray(memory, result.initStart, result.initEnd)) {
			return null;
		}
		return result;
	}

	private boolean isPcRelativeLiteralLoad(Instruction instruction) {
		if (!instruction.getMnemonicString().toLowerCase().startsWith("ldr") ||
			instruction.getNumOperands() != 2) {
			return false;
		}
		// Array walks (ldr.w r3,[r5],#0x4) carry a register in the address operand; PC-relative
		// literal loads are shown by Ghidra as a bare address operand.
		for (Object object : instruction.getOpObjects(1)) {
			if (object instanceof Register) {
				return false;
			}
		}
		return true;
	}

	private boolean validArray(Memory memory, long start, long end) throws Exception {
		if (end < start || (start & 3) != 0 || (end & 3) != 0) {
			return false;
		}
		if (end == start) {
			return true;
		}
		if (!memory.contains(toAddr(start)) || !memory.contains(toAddr(end - 4))) {
			return false;
		}
		Address imageMin = currentProgram.getMinAddress();
		Address imageMax = currentProgram.getMaxAddress();
		for (long entry = start; entry < end; entry += 4) {
			long value = readUnsignedInt(memory, toAddr(entry));
			if ((value & 1L) == 0) {
				return false;
			}
			Address target = toAddr(value & ~1L);
			if (target.compareTo(imageMin) < 0 || target.compareTo(imageMax) > 0) {
				return false;
			}
		}
		return true;
	}

	private void exportDirectCallees(Function caller, File outputDirectory) throws Exception {
		InstructionIterator instructions =
			currentProgram.getListing().getInstructions(caller.getBody(), true);
		int callIndex = 0;
		while (instructions.hasNext()) {
			Instruction instruction = instructions.next();
			FlowType flowType = instruction.getFlowType();
			if (!flowType.isCall()) {
				continue;
			}
			for (Address destination : instruction.getFlows()) {
				Function callee = getFunctionAt(destination);
				if (callee == null) {
					disassemble(destination);
					callee = createFunction(destination, null);
				}
				if (callee == null) {
					continue;
				}
				callIndex++;
				String stem =
					String.format("startup_call_%d_%s", callIndex, destination.toString());
				exportDisassembly(callee, new File(outputDirectory, stem + "_disassembly.txt"));
				exportDecompilation(callee, new File(outputDirectory, stem + "_decompile.c"));
			}
		}
	}

	private long readUnsignedInt(Memory memory, Address address) throws Exception {
		return Integer.toUnsignedLong(memory.getInt(address));
	}

	private void exportVectors(Memory memory, Address base, File output) throws Exception {
		try (BufferedWriter writer = new BufferedWriter(new FileWriter(output))) {
			writer.write("index,offset,kind,irq,value,code_address,thumb,in_image\n");
			Address imageMin = currentProgram.getMinAddress();
			Address imageMax = currentProgram.getMaxAddress();
			int vectorCount = vectorCount(memory, base);
			for (int index = 0; index < vectorCount; index++) {
				long value = readUnsignedInt(memory, base.add(index * 4L));
				long codeValue = value & ~1L;
				boolean thumb = (value & 1L) != 0;
				Address codeAddress = toAddr(codeValue);
				boolean inImage = codeAddress.compareTo(imageMin) >= 0 &&
					codeAddress.compareTo(imageMax) <= 0;
				String kind = index == 0 ? "initial_msp" : index < 16 ? "core" : "external";
				String irq = index < 16 ? "" : Integer.toString(index - 16);
				writer.write(String.format("%d,0x%03X,%s,%s,0x%08X,0x%08X,%s,%s%n",
					index, index * 4, kind, irq, value, codeValue, thumb, inImage));
			}
		}
	}

	/**
	 * Measure the vector table: from index 16 on, entries are counted while they are 0 (reserved)
	 * or a Thumb pointer into the image; the first other word ends the table.
	 */
	private int vectorCount(Memory memory, Address base) throws Exception {
		Address imageMin = currentProgram.getMinAddress();
		Address imageMax = currentProgram.getMaxAddress();
		int count = 16;
		while (count < MAX_VECTOR_COUNT) {
			long value = readUnsignedInt(memory, base.add(count * 4L));
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
