#!/usr/bin/env bash
set -euo pipefail

# Apply the VERIFIED renames of one CSV to the imported program (writes the project).
#
# Rows that cannot be applied are logged (SKIP / ERROR lines) and skipped; the run
# ends with a "RENAME SUMMARY:" line. analyzeHeadless itself exits 0 even when a
# script throws, so this wrapper exits 1 when the script reported a fatal problem
# (unreadable or empty file, unexpected header, bad arguments) or never printed its
# summary (program not found, project locked, ...). Skipped rows are not fatal.

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

CSV="$(abspath "$1")"
if [[ ! -r "$CSV" ]]; then
	echo "$0: cannot read $CSV" >&2
	exit 1
fi

mkdir -p "$GHIDRA_CONFIG_DIR"
LOG="$(mktemp "${TMPDIR:-/tmp}/g7250-renames.XXXXXX")"
trap 'rm -f "$LOG"' EXIT

rc=0
XDG_CONFIG_HOME="$GHIDRA_CONFIG_DIR" \
"$GHIDRA_INSTALL/support/analyzeHeadless" \
	"$PROJECT_DIR" "$PROJECT_NAME" \
	-process "$PROGRAM_NAME" \
	-noanalysis \
	-scriptPath "$(pwd)/ghidra_scripts" \
	-postScript RenameVerifiedFromCsv.java "$CSV" 2>&1 | tee "$LOG" || rc=$?

if ((rc != 0)); then
	echo "$0: analyzeHeadless exited with status $rc" >&2
	exit "$rc"
fi
if grep -q 'REPORT SCRIPT ERROR' "$LOG"; then
	echo "$0: RenameVerifiedFromCsv.java aborted (fatal error above)" >&2
	exit 1
fi
if ! grep -q 'RENAME SUMMARY:' "$LOG"; then
	echo "$0: no rename summary found; the script did not run to completion" >&2
	exit 1
fi
exit 0
