#!/usr/bin/env bash
# Import the G7250 firmware image(s) into the shared read-only Ghidra project.
#
# Each image is a raw ARM Cortex-M7 (Thumb-2, little-endian) binary whose
# application load base is 0x08020000 (the vectors below that live in a
# bootloader region not present in these images). The STM32H7 RAM blocks are
# added before auto-analysis so address references resolve.
#
#   GHIDRA_INSTALL=/opt/ghidra JAVA_HOME=/usr/lib/jvm/java ./tools/import.sh [main|control|all]
#
set -euo pipefail

: "${GHIDRA_INSTALL:?set GHIDRA_INSTALL to the Ghidra directory}"
: "${JAVA_HOME:?set JAVA_HOME to the JDK directory}"
PROJECT_DIR="${PROJECT_DIR:-/tmp/g7250-ghidra-project}"
PROJECT_NAME="${PROJECT_NAME:-g7250_import}"
GHIDRA_CONFIG_DIR="${GHIDRA_CONFIG_DIR:-/tmp/g7250-ghidra-config}"
FW_DIR="${FW_DIR:-/home/franco/radios/g7250/FW}"
BASE_ADDR="${BASE_ADDR:-0x08020000}"
PROCESSOR="${PROCESSOR:-ARM:LE:32:Cortex}"

which="${1:-all}"
declare -a IMAGES=()
case "$which" in
	main)    IMAGES=("G7250_MainUnit_Fw_V1.0.1.bin") ;;
	control) IMAGES=("G7250_ControlUnit_Fw_V1.0.1.bin") ;;
	all)     IMAGES=("G7250_MainUnit_Fw_V1.0.1.bin" "G7250_ControlUnit_Fw_V1.0.1.bin") ;;
	*) echo "usage: $0 [main|control|all]" >&2; exit 2 ;;
esac

mkdir -p "$GHIDRA_CONFIG_DIR" "$PROJECT_DIR"

for img in "${IMAGES[@]}"; do
	echo ">>> importing $img at $BASE_ADDR ($PROCESSOR)"
	XDG_CONFIG_HOME="$GHIDRA_CONFIG_DIR" \
	"$GHIDRA_INSTALL/support/analyzeHeadless" \
		"$PROJECT_DIR" "$PROJECT_NAME" \
		-import "$FW_DIR/$img" \
		-processor "$PROCESSOR" \
		-loader BinaryLoader \
		-loader-baseAddr "$BASE_ADDR" \
		-scriptPath "$(pwd)/ghidra_scripts" \
		-preScript MapSTM32H7Memory.java \
		-overwrite
done
echo ">>> done. Programs are in project $PROJECT_NAME under $PROJECT_DIR"
