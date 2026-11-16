#!/usr/bin/env python3
"""Classify every recovered function of a G7250 image as library or application code.

Inputs
------
--ranges   function-ranges CSV from ExportFunctionRanges.java
           (entry, body_min, body_max_exclusive, body_bytes, name); "bytes" in the
           output is body_bytes (Ghidra bodies may be non-contiguous)
--regions  link-region table for this unit
           (start, end, library, module, confidence, evidence); end is exclusive
--names    per-function identifications (address, library, name, confidence, evidence).
           A row overrides the region's library for that one function, so it can mark
           application code inside a CubeMX region and similar cases. An empty name only
           sets the library.

Optional cross-unit propagation (needs both raw images):
--image IMG --peer-image IMG --peer-ranges CSV --peer-names CSV
   Each function body is normalised by masking the immediates of Thumb-2 BL / B.W
   instructions (the only position-dependent bits in -ffunction-sections code that
   uses PC-relative literal pools). A function whose normalised body matches exactly
   one function in the peer unit is reported as "byte-identical", and it takes the
   peer's name when it has none of its own. The confidence of a propagated name is
   capped at HIGH.

Output: one row per function (--out) and per-library totals (stdout or --summary).
The tool reads evidence files only. It never touches a Ghidra project.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import sys
from collections import Counter, defaultdict

BASE = 0x08020000
RANK = {"VERIFIED": 4, "HIGH": 3, "MEDIUM": 2, "HYPOTHESIS": 1, "": 0}


def hx(text: str) -> int:
    return int(text.strip().lower().removeprefix("0x"), 16)


def read_ranges(path):
    rows = []
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            rows.append((hx(r["entry"]), hx(r["body_max_exclusive"]), r.get("name", ""),
                         int(r.get("body_bytes") or 0)))
    return sorted(rows)


def read_regions(path):
    with open(path, newline="") as fh:
        regs = [dict(r, start=hx(r["start"]), end=hx(r["end"])) for r in csv.DictReader(fh)]
    regs.sort(key=lambda r: r["start"])
    for a, b in zip(regs, regs[1:]):
        if a["end"] > b["start"]:
            raise SystemExit(f"overlapping regions at 0x{b['start']:08x}")
    return regs


def read_names(path):
    if not path:
        return {}
    with open(path, newline="") as fh:
        return {hx(r["address"]): r for r in csv.DictReader(fh)}


def region_of(regs, starts, addr):
    i = bisect.bisect_right(starts, addr) - 1
    if i >= 0 and regs[i]["start"] <= addr < regs[i]["end"]:
        return regs[i]
    return None


def normalise(body: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i + 1 < len(body):
        hw = body[i] | body[i + 1] << 8
        if hw >> 11 in (0b11101, 0b11110, 0b11111) and i + 3 < len(body):
            hw2 = body[i + 2] | body[i + 3] << 8
            if hw >> 11 == 0b11110 and hw2 >> 15:          # BL / B.W / Bcc.W
                out += bytes((0xF0, 0, 0, (hw2 >> 8) & 0xD0))
            else:
                out += body[i:i + 4]
            i += 4
        else:
            out += body[i:i + 2]
            i += 2
    return bytes(out)


def digests(image, ranges, min_len=8):
    result = {}
    for entry, end, _, nbytes in ranges:
        # Ghidra bodies can be non-contiguous; hash only the contiguous head.
        body = image[entry - BASE:min(end, entry + nbytes) - BASE]
        if len(body) >= min_len:
            result[entry] = hashlib.sha1(normalise(body)).hexdigest()
    return result


def cap(conf: str, limit: str = "HIGH") -> str:
    return conf if RANK.get(conf, 0) <= RANK[limit] else limit


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ranges", required=True)
    ap.add_argument("--regions", required=True)
    ap.add_argument("--names")
    ap.add_argument("--image")
    ap.add_argument("--peer-image")
    ap.add_argument("--peer-ranges")
    ap.add_argument("--peer-names")
    ap.add_argument("--peer-label", default="peer unit")
    ap.add_argument("--out", required=True)
    ap.add_argument("--summary")
    args = ap.parse_args()

    ranges = read_ranges(args.ranges)
    regs = read_regions(args.regions)
    starts = [r["start"] for r in regs]
    names = read_names(args.names)

    peer_of = {}
    peer_names = {}
    if args.image and args.peer_image and args.peer_ranges:
        own = digests(open(args.image, "rb").read(), ranges)
        peer_ranges = read_ranges(args.peer_ranges)
        peer = digests(open(args.peer_image, "rb").read(), peer_ranges)
        by_hash = defaultdict(list)
        for addr, h in peer.items():
            by_hash[h].append(addr)
        own_count = Counter(own.values())
        for addr, h in own.items():
            if len(by_hash.get(h, ())) == 1 and own_count[h] == 1:
                peer_of[addr] = by_hash[h][0]
        peer_names = read_names(args.peer_names)

    rows = []
    for entry, end, ghidra_name, nbytes in ranges:
        reg = region_of(regs, starts, entry)
        library = reg["library"] if reg else "unclassified"
        module = reg["module"] if reg else ""
        conf = reg["confidence"] if reg else ""
        basis = ["region"] if reg else []
        name = ""
        if entry in names:
            n = names[entry]
            if n.get("library"):
                library = n["library"]
                if not reg or n["library"] != reg["library"]:
                    module = ""
            name = n.get("name", "")
            if n.get("confidence"):
                conf = n["confidence"] if name else max(conf, n["confidence"], key=lambda c: RANK.get(c, 0))
            basis.append("named" if name else "override")
        peer = peer_of.get(entry)
        if peer is not None:
            basis.append(f"byte-identical to {args.peer_label} 0x{peer:08x}")
            pn = peer_names.get(peer)
            if not name and pn and pn.get("name") and pn.get("library") == library:
                name = pn["name"]
                conf = cap(pn.get("confidence", "MEDIUM"))
                basis.append("name from peer")
        if not ghidra_name.startswith(("FUN_", "thunk_FUN_")) and not name:
            name = ghidra_name
        rows.append({
            "address": f"{entry:08x}", "end": f"{end:08x}", "bytes": nbytes,
            "library": library, "module": module, "proposed_name": name,
            "confidence": conf, "basis": "; ".join(basis),
        })

    fields = ["address", "end", "bytes", "library", "module", "proposed_name", "confidence", "basis"]
    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    count = Counter(r["library"] for r in rows)
    size = Counter()
    for r in rows:
        size[r["library"]] += r["bytes"]
    named = Counter(r["library"] for r in rows if r["proposed_name"])
    ident = Counter(r["library"] for r in rows if "byte-identical" in r["basis"])
    lines = ["library,functions,bytes,named,byte_identical_in_peer"]
    for lib in sorted(count, key=lambda k: -size[k]):
        lines.append(f"{lib},{count[lib]},{size[lib]},{named[lib]},{ident[lib]}")
    lines.append(f"TOTAL,{sum(count.values())},{sum(size.values())},{sum(named.values())},{sum(ident.values())}")
    text = "\n".join(lines) + "\n"
    if args.summary:
        open(args.summary, "w").write(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
