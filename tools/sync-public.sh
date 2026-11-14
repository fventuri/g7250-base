#!/usr/bin/env bash
#
# sync-public.sh — mirror the clean-room PUBLIC subset of this repo.
#
# The public repository (github.com/fventuri/g7250-base) shares the
# documentation, the reproducible Ghidra/analysis tooling, and derived
# metadata only. It intentionally OMITS the raw decompiler/disassembler
# output — those are verbatim derivatives of the copyrighted OEM firmware
# and stay in this private working tree as reference evidence only.
#
# Filter rule (keep in sync with README "Scope of this public repository"):
#   * every tracked file OUTSIDE  */analysis/
#   * inside */analysis/ : ONLY  *.csv  and  strings/strings.txt
# i.e. EXCLUDE  *_decompile.{c,txt}, *_disassembly.txt, and the
# snippet-bearing evidence *.txt under */analysis/.
#
# Usage:  tools/sync-public.sh [path-to-public-repo]
#   default public repo: ../g7250-base-public
# Dry run: SYNC_DRY=1 tools/sync-public.sh
#
# The script does NOT commit or push; it only updates the working tree of
# the public repo. Review `git -C <public> status` then commit/push there.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-$SRC/../g7250-base-public}"
DEST="$(cd "$DEST" && pwd)"

if [ ! -d "$SRC/.git" ]; then echo "error: $SRC is not a git repo" >&2; exit 1; fi
if [ ! -d "$DEST/.git" ]; then echo "error: $DEST is not a git repo" >&2; exit 1; fi
if [ "$SRC" = "$DEST" ]; then echo "error: source and dest are the same" >&2; exit 1; fi

# Build the include list from tracked files using the filter rule above.
INCLUDE="$(git -C "$SRC" ls-files | awk '
  /\/analysis\//{ if ($0 ~ /\.csv$/ || $0 ~ /strings\/strings\.txt$/) print; next }
  { print }
')"

# Safety assertion: the include list must never contain verbatim OEM code.
if printf '%s\n' "$INCLUDE" | grep -Eq '_decompile\.(c|txt)$|_disassembly\.txt$'; then
  echo "error: filter leaked decompiled/disassembled files — aborting" >&2
  exit 1
fi

n="$(printf '%s\n' "$INCLUDE" | grep -c . || true)"
echo "including $n files from $SRC"

if [ "${SYNC_DRY:-0}" = "1" ]; then
  printf '%s\n' "$INCLUDE"
  echo "(dry run: no files written)"
  exit 0
fi

# Mirror: wipe everything in DEST except its .git, then copy the subset.
find "$DEST" -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +
while IFS= read -r f; do
  [ -n "$f" ] || continue
  mkdir -p "$DEST/$(dirname "$f")"
  cp "$SRC/$f" "$DEST/$f"
done <<< "$INCLUDE"

# Append the public-scope note to the public README (idempotent).
NOTE_MARK='## Scope of this public repository'
if ! grep -qF "$NOTE_MARK" "$DEST/README.md"; then
  cat >> "$DEST/README.md" <<'EOF'

------------------------------------------------------------------------

## Scope of this public repository

This public repository contains the project's **documentation**, the
**reproducible Ghidra / analysis tooling**, and **derived metadata**
(function-range, IRQ, vector, and peripheral-access CSVs, plus extracted
string tables).

It intentionally **omits the raw decompiler and disassembler output**
(`*/analysis/**/*_decompile.*`, `*_disassembly.txt`, and the
snippet-bearing evidence `.txt` files). Those are verbatim derivatives of
the copyrighted OEM firmware; they are kept only in the private working
tree and used strictly as reference evidence under the clean-room rules
in [AGENTS.md](AGENTS.md). Some documents cite those evidence paths — the
referenced raw files are not part of this public tree by design.

The decrypted OEM firmware images are **not** included here.
EOF
fi

echo "synced to $DEST"
echo "next: git -C \"$DEST\" add -A && git -C \"$DEST\" commit && git -C \"$DEST\" push"
