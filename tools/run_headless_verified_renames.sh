#!/usr/bin/env bash
set -euo pipefail

# Output (and input) paths may be absolute or relative to the current directory
# (the repository root, which -scriptPath below also assumes).
abspath() { case "$1" in /*) printf '%s\n' "$1" ;; *) printf '%s/%s\n' "$(pwd)" "$1" ;; esac; }

if (($# != 1)); then
	echo "usage: $0 <verified-renames.csv>" >&2
	exit 2
fi

: "${GHIDRA_INSTALL:?set GHIDRA_INSTALL to the Ghidra directory}"
: "${JAVA_HOME:?set JAVA_HOME to the JDK directory}"
: "${PROJECT_DIR:?set PROJECT_DIR to the persistent Ghidra project directory}"
: "${PROJECT_NAME:?set PROJECT_NAME to the persistent Ghidra project name}"
GHIDRA_CONFIG_DIR="${GHIDRA_CONFIG_DIR:-/tmp/g7250-ghidra-config}"
PROGRAM_NAME="${PROGRAM_NAME:?set PROGRAM_NAME to the imported program; run: source tools/env-main.sh or tools/env-control.sh}"

mkdir -p "$GHIDRA_CONFIG_DIR"

XDG_CONFIG_HOME="$GHIDRA_CONFIG_DIR" \
"$GHIDRA_INSTALL/support/analyzeHeadless" \
	"$PROJECT_DIR" "$PROJECT_NAME" \
	-process "$PROGRAM_NAME" \
	-noanalysis \
	-scriptPath "$(pwd)/ghidra_scripts" \
	-postScript RenameVerifiedFromCsv.java "$(abspath "$1")"
