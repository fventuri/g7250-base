// Apply only explicitly VERIFIED function renames from a CSV file.
//
// CSV format (unchanged): header line
//   address,current_name,new_name,confidence,evidence
// followed by one rename per line; the evidence field may contain commas.
//
// Each row is validated and applied on its own. A row that cannot be applied
// (malformed line, not VERIFIED, bad address, address inside another function
// or outside loaded memory, current-name mismatch, target name already used
// elsewhere, function creation failure) is logged with its line number and
// skipped; the remaining rows are still processed. A summary line is printed
// at the end:
//   RENAME SUMMARY: rows=N renamed=R created=C unchanged=U skipped=S errors=E
// "skipped" counts rows rejected by validation, "errors" counts rows where an
// unexpected exception occurred while applying them.
//
// Only fatal problems abort the script with an exception (wrong arguments,
// unreadable or empty file, unexpected header).
// @category X6100

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.IOException;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;
import ghidra.program.model.symbol.Symbol;

public class RenameVerifiedFromCsv extends GhidraScript {
	private static final String HEADER = "address,current_name,new_name,confidence,evidence";

	/** A row rejected by validation; skipped, not fatal. */
	private static class SkipRow extends Exception {
		SkipRow(String message) {
			super(message);
		}
	}

	private int rows;
	private int renamed;
	private int created;
	private int unchanged;
	private int skipped;
	private int errors;

	@Override
	protected void run() throws Exception {
		String[] args = getScriptArgs();
		if (args.length != 1) {
			throw new IllegalArgumentException(
				"usage: RenameVerifiedFromCsv.java <renames.csv>");
		}
		File input = new File(args[0]);
		if (!input.isFile() || !input.canRead()) {
			throw new IOException("cannot read rename CSV: " + input);
		}

		try (BufferedReader reader = new BufferedReader(new FileReader(input))) {
			String header = reader.readLine();
			if (header == null) {
				throw new IllegalArgumentException("empty rename CSV: " + input);
			}
			header = stripLineNoise(header);
			if (header.startsWith("﻿")) {
				header = header.substring(1);
			}
			if (!HEADER.equals(header)) {
				throw new IllegalArgumentException("unexpected CSV header in " + input);
			}

			String line;
			int lineNumber = 1;
			while ((line = reader.readLine()) != null) {
				lineNumber++;
				line = stripLineNoise(line);
				if (line.isBlank()) {
					continue;
				}
				rows++;
				try {
					applyRow(line);
				}
				catch (SkipRow e) {
					skipped++;
					printerr("SKIP line " + lineNumber + ": " + e.getMessage());
				}
				catch (Exception e) {
					errors++;
					printerr("ERROR line " + lineNumber + ": " + e.getClass().getSimpleName() +
						": " + e.getMessage());
				}
			}
		}

		println("RENAME SUMMARY: rows=" + rows + " renamed=" + renamed + " created=" + created +
			" unchanged=" + unchanged + " skipped=" + skipped + " errors=" + errors);
	}

	private static String stripLineNoise(String line) {
		// Tolerate CRLF files.
		if (line.endsWith("\r")) {
			return line.substring(0, line.length() - 1);
		}
		return line;
	}

	private void applyRow(String line) throws Exception {
		String[] fields = line.split(",", 5);
		if (fields.length != 5) {
			throw new SkipRow("malformed line (expected 5 fields, found " + fields.length + ")");
		}
		String addressText = fields[0].trim();
		String currentName = fields[1].trim();
		String newName = fields[2].trim();
		if (!"VERIFIED".equals(fields[3].trim())) {
			throw new SkipRow("not an explicit VERIFIED rename (confidence '" +
				fields[3].trim() + "')");
		}
		if (addressText.isEmpty() || newName.isEmpty()) {
			throw new SkipRow("empty address or new name");
		}

		Address address;
		try {
			address = toAddr(addressText);
		}
		catch (Exception e) {
			address = null;
		}
		if (address == null) {
			throw new SkipRow("unparsable address '" + addressText + "'");
		}

		Function function = getFunctionAt(address);
		boolean create = false;
		if (function == null) {
			Function container = getFunctionContaining(address);
			if (container != null) {
				throw new SkipRow("address " + address + " lies inside function " +
					container.getName() + " at " + container.getEntryPoint());
			}
			if (!currentProgram.getMemory().contains(address)) {
				throw new SkipRow("address is outside loaded memory at " + address);
			}
			create = true;
		}
		if (!create && !function.getName().equals(currentName) &&
				!function.getName().equals(newName)) {
			throw new SkipRow("name mismatch at " + address + ": expected " + currentName +
				" or " + newName + ", found " + function.getName());
		}

		for (Symbol collision : currentProgram.getSymbolTable().getGlobalSymbols(newName)) {
			if (collision.getAddress().compareTo(address) != 0) {
				throw new SkipRow("target name " + newName + " already exists at " +
					collision.getAddress());
			}
		}

		if (create) {
			if (currentProgram.getListing().getInstructionAt(address) == null) {
				disassemble(address);
			}
			function = createFunction(address, newName);
			if (function == null) {
				throw new SkipRow("could not create function at " + address);
			}
			created++;
			println(address + ": <missing> -> " + newName);
			return;
		}
		if (function.getName().equals(newName)) {
			unchanged++;
			return;
		}
		String oldName = function.getName();
		function.setName(newName, SourceType.USER_DEFINED);
		renamed++;
		println(address + ": " + oldName + " -> " + newName);
	}
}
