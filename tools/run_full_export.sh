#!/usr/bin/env bash
# Reproducible full export run for one or both G7250 units.
#
#   tools/run_full_export.sh [options] <output-root> [main|control|all]
#
# Steps per unit (each wraps an existing tools/run_headless_*.sh wrapper):
#   1. --import   tools/import.sh <unit>                  (writes the Ghidra project)
#   2. --vectors  CreateVectorFunctions.java              (writes the project; creates
#                 handler functions a raw import misses)
#   3. --renames  tools/run_headless_verified_renames.sh  (writes the project)
#   4. exports (read-only):
#        function_ranges.csv, callgraph.csv, globals.csv, peripheral_accesses.csv,
#        startup/ (vectors.csv + reset evidence), interrupts/ (active_irqs.csv + handler
#        evidence), and with --decompile-all decompile/all_functions.txt
#   5. MANIFEST.csv (sha256 of every output; tools/generate_evidence_manifest.py)
#
# Output layout: <output-root>/<unit>/...  The startup/, interrupts/ and decompile/
# folders hold raw decompiler and disassembly evidence. The whole output root must
# therefore be OUTSIDE the repository or git-ignored; the script refuses otherwise.
#
# Environment (same as the other wrappers): GHIDRA_INSTALL, JAVA_HOME, PROJECT_DIR,
# PROJECT_NAME, GHIDRA_CONFIG_DIR, FW_DIR (for --import). G7250_REPO overrides the
# repository root (default: the parent of this script's directory).
# Works with the macOS system bash 3.2.
set -euo pipefail

usage() {
	echo "usage: $0 [--import] [--vectors] [--renames] [--decompile-all] [--all-steps] <output-root> [main|control|all]" >&2
	exit 2
}

DO_IMPORT=0 DO_VECTORS=0 DO_RENAMES=0 DO_DECOMPILE=0
while (($#)); do
	case "$1" in
		--import) DO_IMPORT=1 ;;
		--vectors) DO_VECTORS=1 ;;
		--renames) DO_RENAMES=1 ;;
		--decompile-all) DO_DECOMPILE=1 ;;
		--all-steps) DO_IMPORT=1 DO_VECTORS=1 DO_RENAMES=1 ;;
		-h|--help) usage ;;
		--*) echo "unknown option $1" >&2; usage ;;
		*) break ;;
	esac
	shift
done
(($# >= 1 && $# <= 2)) || usage
OUT_ARG="$1"
WHICH="${2:-all}"
case "$WHICH" in main) UNITS=(main) ;; control) UNITS=(control) ;; all) UNITS=(main control) ;; *) usage ;; esac

: "${GHIDRA_INSTALL:?set GHIDRA_INSTALL to the Ghidra directory}"
: "${JAVA_HOME:?set JAVA_HOME to the JDK directory}"
export GHIDRA_INSTALL JAVA_HOME
export PROJECT_DIR="${PROJECT_DIR:-/tmp/g7250-ghidra-project}"
export PROJECT_NAME="${PROJECT_NAME:-g7250_import}"
export GHIDRA_CONFIG_DIR="${GHIDRA_CONFIG_DIR:-/tmp/g7250-ghidra-config}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${G7250_REPO:-$(cd "$SCRIPT_DIR/.." && pwd)}"
cd "$REPO"   # the wrappers resolve ghidra_scripts/ and outputs against $(pwd)

# resolve without creating anything yet (the guard below must run first)
OUT="$(python3 -I -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$OUT_ARG")"
REPO_REAL="$(pwd -P)"

# --- clean-room guard: raw evidence must never land in a tracked location -------
case "$OUT/" in
	"$REPO_REAL"/*)
		probe="${OUT#"$REPO_REAL"/}/.probe"
		if ! git -C "$REPO_REAL" check-ignore -q "$probe"; then
			echo "refusing: $OUT is inside the repository and not git-ignored." >&2
			echo "Use a directory outside the repo (recommended) or an ignored path." >&2
			exit 1
		fi ;;
esac

mkdir -p "$OUT"

# The wrappers write to "$(pwd)/<arg>", so hand them a path relative to the repo.
rel() { python3 -I -c 'import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))' "$1" "$REPO_REAL"; }

headless() {   # direct call for the two steps without a wrapper (writable project)
	XDG_CONFIG_HOME="$GHIDRA_CONFIG_DIR" "$GHIDRA_INSTALL/support/analyzeHeadless" \
		"$PROJECT_DIR" "$PROJECT_NAME" -process "$PROGRAM_NAME" \
		-scriptPath "$REPO_REAL/ghidra_scripts;$SCRIPT_DIR/../ghidra_scripts" \
		-preScript MapSTM32H7Memory.java "$@"
}

log() { printf '>>> [%s] %s\n' "$UNIT" "$*"; }

for UNIT in "${UNITS[@]}"; do
	# shellcheck source=/dev/null
	source "tools/env-$UNIT.sh"           # sets PROGRAM_NAME (OUTPUT_ROOT is not used)
	U_OUT="$OUT/$UNIT"
	R="$(rel "$U_OUT")"
	mkdir -p "$U_OUT/logs"

	if ((DO_IMPORT)); then
		log "import"
		tools/import.sh "$UNIT" > "$U_OUT/logs/import.log" 2>&1
	fi
	if ((DO_VECTORS)); then
		log "create vector-target functions"
		headless -postScript CreateVectorFunctions.java > "$U_OUT/logs/vectors.log" 2>&1
		grep -E 'vector entries' "$U_OUT/logs/vectors.log" || true
	fi
	if ((DO_RENAMES)); then
		log "apply verified renames"
		tools/run_headless_verified_renames.sh "${UNIT}_unit/analysis/renames/verified_renames.csv" \
			> "$U_OUT/logs/renames.log" 2>&1
	fi

	log "function ranges";      tools/run_headless_function_ranges.sh "$R/function_ranges.csv" > "$U_OUT/logs/ranges.log" 2>&1
	log "call graph";           tools/run_headless_callgraph.sh "$R/callgraph.csv" > "$U_OUT/logs/callgraph.log" 2>&1
	log "globals";              tools/run_headless_globals.sh "$R/globals.csv" > "$U_OUT/logs/globals.log" 2>&1
	log "peripheral accesses";  tools/run_headless_peripheral_accesses.sh "$R/peripheral_accesses.csv" > "$U_OUT/logs/periph.log" 2>&1
	log "startup evidence";     OUTPUT_DIR="$R/startup" tools/run_headless_startup.sh > "$U_OUT/logs/startup.log" 2>&1
	log "interrupt evidence";   OUTPUT_DIR="$R/interrupts" tools/run_headless_interrupts.sh > "$U_OUT/logs/interrupts.log" 2>&1

	if ((DO_DECOMPILE)); then
		log "decompile all functions"
		ENTRIES=()
		while IFS=, read -r entry _; do ENTRIES+=("$entry"); done < <(tail -n +2 "$U_OUT/function_ranges.csv")
		mkdir -p "$U_OUT/decompile"
		tools/run_headless_decompile.sh "$R/decompile/all_functions.txt" "${ENTRIES[@]}" \
			> "$U_OUT/logs/decompile.log" 2>&1
	fi

	if grep -l -E '^(ERROR|.*Exception)' "$U_OUT"/logs/*.log >/dev/null 2>&1; then
		log "WARNING: errors in $(grep -l -E '^(ERROR|.*Exception)' "$U_OUT"/logs/*.log | xargs -n1 basename | tr '\n' ' ')"
	fi
	log "manifest"
	python3 -I "$SCRIPT_DIR/generate_evidence_manifest.py" "$U_OUT" --out "$U_OUT/MANIFEST.csv" \
		--note "program=$PROGRAM_NAME git=$(git -C "$REPO_REAL" rev-parse --short HEAD 2>/dev/null || echo none)"
done
echo ">>> done: $OUT"
