#!/usr/bin/env bash
set -euo pipefail

if (($# == 0)); then
	echo "usage: $0 <address>..." >&2
	exit 2
fi

: "${GHIDRA_INSTALL:?set GHIDRA_INSTALL to the Ghidra directory}"
: "${JAVA_HOME:?set JAVA_HOME to the JDK directory}"
PROJECT_DIR="${PROJECT_DIR:-/tmp/g7250-ghidra-project}"
PROJECT_NAME="${PROJECT_NAME:-g7250_import}"
GHIDRA_CONFIG_DIR="${GHIDRA_CONFIG_DIR:-/tmp/g7250-ghidra-config}"
OUTPUT_DIR="${OUTPUT_DIR:-analysis/functions}"
PROGRAM_NAME="${PROGRAM_NAME:?set PROGRAM_NAME to the imported program; run: source tools/env-main.sh or tools/env-control.sh}"

mkdir -p "$GHIDRA_CONFIG_DIR" "$OUTPUT_DIR"

XDG_CONFIG_HOME="$GHIDRA_CONFIG_DIR" \
"$GHIDRA_INSTALL/support/analyzeHeadless" \
	"$PROJECT_DIR" "$PROJECT_NAME" \
	-process "$PROGRAM_NAME" \
	-readOnly \
	-scriptPath "$(pwd)/ghidra_scripts" \
	-preScript MapSTM32H7Memory.java \
	-postScript ExportFunctionsByAddress.java "$(pwd)/$OUTPUT_DIR" "$@"
