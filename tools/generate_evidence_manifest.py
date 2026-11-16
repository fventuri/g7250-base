#!/usr/bin/env python3
"""Write a deterministic SHA-256 manifest of an export tree.

    generate_evidence_manifest.py <root> [--out MANIFEST.csv] [--note TEXT]

Every file under <root> is listed (sorted, relative path) with its kind, size and
SHA-256, except logs/ and the manifest itself. Kinds: decompile, disassembly
(raw evidence - never commit), csv, text, other. A '#' comment line can carry a
note such as the program name and the git revision of the tooling.

Replaces the X6100-era generate_reverse_evidence_manifest.py, which hard-coded
an analysis/ folder at the repository root and wrote into the repository.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path


def kind(path: Path) -> str:
    name = path.name.lower()
    if "disassembly" in name:
        return "disassembly"
    if "decompil" in name or name.endswith(".c"):
        return "decompile"
    if name.endswith(".csv"):
        return "csv"
    if name.endswith((".txt", ".md")):
        return "text"
    return "other"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    root = args.root.resolve()
    out = args.out.resolve() if args.out else None
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root)
        if rel.parts[0] == "logs" or path == out:
            continue
        data = path.read_bytes()
        rows.append((rel.as_posix(), kind(path), len(data), hashlib.sha256(data).hexdigest()))

    stream = open(out, "w", newline="", encoding="utf-8") if out else sys.stdout
    with stream:
        if args.note:
            stream.write(f"# {args.note}\n")
        w = csv.writer(stream, lineterminator="\n")
        w.writerow(("path", "kind", "bytes", "sha256"))
        w.writerows(rows)


if __name__ == "__main__":
    main()
