#!/usr/bin/env python3
"""Consistency checker for the G7250 documentation.

Scans docs/*.md and */docs/*.md (plus any --extra files) and reports:

1. ADDR  every FUN_xxxxxxxx and every 0x080xxxxx address, checked against a fresh
         function-ranges export (ExportFunctionRanges.java) of the matching unit:
           error  FUN_x that is neither a function entry nor inside any function body,
                  or an address past the end of the image
           warn   FUN_x that lies inside another function (stale boundary or name);
                  0x080 address outside every function body (data, table, pool or
                  stale), unless it is in a known data range (--data-ranges)
           info   address below the application base (bootloader region)
         Unit selection: main_unit/... uses the Main export, control_unit/... the Control
         export, top-level docs/ accept either unit. A line can force the unit by
         naming it ("Main", "Control") when both exports disagree.
2. CONF  table rows and paragraphs that state a finding (they cite an address,
         a FUN_ name or a register/hex value) but carry no confidence tag, neither
         themselves nor through
           - the section heading chain (also "## Foo — VERIFIED unless noted"),
           - a table "Confidence" column,
           - a bold lead-in directly above a bullet list ("**Foo (HIGH).**" then the
             bullets; also an enclosing list item that opens with such a lead-in),
             or a bold lead-in naming an exempt topic ("**Blocking unknowns:**"),
           - a document status line in the first 15 lines or a section status line
             (first paragraph of a section), e.g. "Status: VERIFIED unless noted"
             or "... unless marked"; the status may wrap onto the next line.
             --conf-all ignores these status lines.
3. STR   any run of >= 20 characters that also occurs in a firmware string table
         (*/analysis/strings/strings.txt), per line and across line breaks. This
         mirrors the repository commit guard (runs with at least 12 letters).

Exit status: 1 if any error-level finding (ADDR error or STR hit), else 0.
The tool only reads files.
"""

from __future__ import annotations

import argparse
import csv
import bisect
import re
import sys
from pathlib import Path

BASE = 0x08020000
TAGS = re.compile(r"\b(VERIFIED|HIGH(?: CONFIDENCE)?|MEDIUM(?: CONFIDENCE)?|HYPOTHESIS|LOW|"
                  r"CONFIRMED|HIGH-CONFIDENCE)\b")
FUN_RE = re.compile(r"\bFUN_([0-9A-Fa-f]{8})\b")
ADDR_RE = re.compile(r"\b0x(080[0-9A-Fa-f]{5})\b")
FINDING_RE = re.compile(r"\bFUN_[0-9A-Fa-f]{8}\b|\b0x[0-9A-Fa-f]{4,8}\b|\b[0-9A-Fa-f]{8}\b")
EXEMPT_HEAD = re.compile(r"unknown|open|todo|question|why this needed|raw evidence|see also|"
                         r"usage|how to|reproduc|status", re.I)
# A status line: a tag followed, within the same paragraph (it may wrap onto the
# next line), by "unless noted" / "unless marked" / "unless otherwise noted".
STATUS_RE = re.compile(r"\b(VERIFIED|HIGH|MEDIUM)\b(?:[^\n]|\n(?![ \t]*\n)){0,60}?"
                       r"\bunless\s+(?:otherwise\s+)?(?:noted|marked|stated)\b")
N = 20


class Unit:
    def __init__(self, name: str, ranges_csv: Path, image_size: int | None,
                 vectors_csv: Path | None = None, data_ranges=()):
        self.name = name
        self.entries: set[int] = set()
        self.vector_targets: set[int] = set()
        self.data_ranges = list(data_ranges)
        if vectors_csv and vectors_csv.exists():
            with open(vectors_csv, newline="") as fh:
                for r in csv.DictReader(fh):
                    if r.get("thumb") == "true" and r.get("in_image") == "true":
                        self.vector_targets.add(int(r["code_address"], 16))
        spans = []
        with open(ranges_csv, newline="") as fh:
            for r in csv.DictReader(fh):
                e = int(r["entry"], 16)
                lo = int(r["body_min"], 16)
                hi = int(r["body_max_exclusive"], 16)
                n = int(r.get("body_bytes") or (hi - lo))
                self.entries.add(e)
                # use the contiguous head only; Ghidra bodies can be fragmented
                spans.append((e, e + n if n else hi))
                if lo < e:
                    spans.append((lo, e))
        spans.sort()
        self.starts = [s for s, _ in spans]
        self.spans = spans
        self.end = BASE + image_size if image_size else max(h for _, h in spans)
        self.first_code = min(self.entries) if self.entries else BASE

    def containing(self, addr: int):
        i = bisect.bisect_right(self.starts, addr) - 1
        while i >= 0:
            s, e = self.spans[i]
            if s <= addr < e:
                return s
            if addr - s > 0x10000:
                break
            i -= 1
        return None

    def classify(self, addr: int, is_fun: bool):
        if addr < BASE:
            return "info", "below the application base (bootloader region)"
        if addr == self.end:
            return "ok", "image end (exclusive bound)"
        if addr > self.end:
            return "error", f"past the end of the {self.name} image (0x{self.end:08X})"
        if addr in self.entries:
            return "ok", ""
        if addr in self.vector_targets:
            return "info", ("vector target that this export has no function for "
                            "(raw-binary import does not create handler functions)")
        if addr < self.first_code and not is_fun:
            return "ok", "vector table / image header"
        for lo, hi in self.data_ranges:
            if lo <= addr <= hi and not is_fun:
                return "ok", "known data range"
        owner = self.containing(addr)
        if owner is not None:
            if is_fun:
                return "warn", f"inside function 0x{owner:08X}, not an entry"
            return "ok", f"inside 0x{owner:08X}"
        if is_fun:
            return "error", "no function at or around this address"
        return "warn", "not inside any function (data / table / literal pool / stale?)"


def load_strings(paths):
    windows = set()
    for p in paths:
        for line in open(p, errors="replace"):
            s = re.sub(r"^ *[0-9a-f]+ ", "", line.rstrip("\n"))
            if len(s) < N:
                continue
            for i in range(len(s) - N + 1):
                w = s[i:i + N]
                if sum(c.isalpha() for c in w) >= 12:
                    windows.add(w)
    return windows


ITEM_RE = re.compile(r"^\s*([-*]|\d+\.)\s+")
# A bold lead-in: "**Foo (HIGH).**" or "**Foo** (…; VERIFIED unless noted)." — the bold
# span plus the rest of its first sentence. Optionally after a list marker.
LEAD_RE = re.compile(r"^\s*(?:(?:[-*]|\d+\.)\s+)?(\*\*(.+?)\*\*([^.:]*[.:]?))")


def bold_lead(text: str):
    """Return (lead_text, bold_text) when text opens with a bold lead-in, else None."""
    m = LEAD_RE.match(text)
    return (m.group(1), m.group(2)) if m else None


def blocks(lines):
    """Yield (kind, first_line_no, text, heading_chain, table_header, leads) blocks.

    leads: for list items (and indented continuation paragraphs of a list), the bold
    lead-ins that govern them, outermost first: the bold lead-in paragraph directly
    above the list ("**Foo (HIGH).**" followed by the bullets) and every enclosing
    list item that opens with a bold lead-in. Each entry is (lead_text, bold_text).
    """
    heads: list[tuple[int, str]] = []
    para: list[tuple[int, str]] = []
    header = None
    in_code = False
    st = {
        "item": False,        # current paragraph is a list item
        "leads": [],          # leads governing the current paragraph
        "in_list": False,     # the previous block was part of a list
        "list_lead": None,    # lead-in paragraph governing the current list
        "stack": [],          # enclosing items: [indent, lead or None]
    }

    def reset_list():
        st["in_list"] = False
        st["list_lead"] = None
        st["stack"] = []

    def flush():
        nonlocal para
        if not para:
            return None
        text = " ".join(t.strip() for _, t in para)
        if st["item"] and st["stack"]:
            st["stack"][-1][1] = bold_lead(text)
        block = ("para", para[0][0], text, list(heads), None, list(st["leads"]))
        para = []
        st["item"] = False
        st["leads"] = []
        return block

    def leads_for(indent):
        out = [st["list_lead"]] + [ld for ind, ld in st["stack"] if ind < indent]
        return [ld for ld in out if ld]

    for no, line in enumerate(lines, 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            f = flush()
            if f:
                yield f
            reset_list()
            continue
        if in_code:
            continue
        m = re.match(r"^(#+)\s+(.*)", line)
        if m:
            f = flush()
            if f:
                yield f
            reset_list()
            level = len(m.group(1))
            heads = [h for h in heads if h[0] < level] + [(level, m.group(2))]
            header = None
            continue
        if line.lstrip().startswith("|"):
            f = flush()
            if f:
                yield f
            reset_list()
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            if header is None:
                header = cells
                yield ("thead", no, line, list(heads), cells, [])
            else:
                yield ("row", no, line, list(heads), header, [])
            continue
        header = None if not line.strip() else header
        if not line.strip():
            f = flush()
            if f:
                yield f
            continue
        indent = len(line) - len(line.lstrip())
        if ITEM_RE.match(line):
            if para and not st["item"] and not st["in_list"]:
                # a paragraph directly followed by a list: a lead-in if it opens in bold
                lead = bold_lead(" ".join(t.strip() for _, t in para))
                f = flush()
                if f:
                    yield f
                reset_list()
                st["list_lead"] = lead
            elif para:
                f = flush()
                if f:
                    yield f
            elif not st["in_list"]:
                reset_list()
            st["stack"] = [e for e in st["stack"] if e[0] < indent]
            st["leads"] = leads_for(indent)
            st["stack"].append([indent, None])
            st["item"] = True
            st["in_list"] = True
        elif not para:
            if st["in_list"] and indent > 0:
                st["leads"] = leads_for(indent)    # indented continuation inside a list
            else:
                reset_list()
        para.append((no, line))
    f = flush()
    if f:
        yield f


def unit_for(path: Path, root: Path):
    rel = path.relative_to(root).as_posix()
    if rel.startswith("main_unit/"):
        return ["main"]
    if rel.startswith("control_unit/"):
        return ["control"]
    return ["main", "control"]


def check_file(path: Path, root: Path, units, windows, findings, conf_all):
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    rel = path.relative_to(root).as_posix()
    wanted = [u for u in unit_for(path, root) if u in units]

    # 1. addresses
    for no, line in enumerate(lines, 1):
        hits = [(m.group(1), True) for m in FUN_RE.finditer(line)]
        hits += [(m.group(1), False) for m in ADDR_RE.finditer(line)]
        for hexa, is_fun in hits:
            addr = int(hexa, 16)
            res = [(u, *units[u].classify(addr, is_fun)) for u in wanted]
            if not res:
                continue
            if any(r[1] == "ok" for r in res):
                continue
            # prefer the unit named on the line
            named = [r for r in res if r[0].lower() in line.lower()]
            pick = named[0] if named else min(res, key=lambda r: ["info", "warn", "error"].index(r[1]))
            label = ("FUN_" if is_fun else "0x") + hexa
            findings.append((pick[1], "ADDR", rel, no, f"{label}: {pick[2]} [{pick[0]}]"))

    # 2. confidence tags
    # document status line: a plain paragraph (not a bold lead-in, not a list item)
    # in the first 15 lines, before the first section heading
    doc_tagged = False
    for kind, no, block, heads, *_ in blocks(lines[:15]):
        if any(level > 1 for level, _ in heads):
            break
        if kind == "para" and not block.startswith("**") and not ITEM_RE.match(block) \
                and STATUS_RE.search(block):
            doc_tagged = True
            break
    status_sections: set[tuple] = set()   # sections opened by a "Status: … unless noted" line
    seen_sections: set[tuple] = set()
    for kind, no, block, heads, header, leads in blocks(lines):
        key = tuple(heads)
        if key not in seen_sections and kind == "para":
            seen_sections.add(key)
            # first paragraph of a section: a section status line ("Status: HIGH unless
            # noted.") tags the section and its subsections, like a document status line
            if heads and not block.startswith("**") and not ITEM_RE.match(block) \
                    and STATUS_RE.search(block):
                status_sections.add(key)
        if kind == "thead":
            continue
        if not FINDING_RE.search(block):
            continue
        if TAGS.search(block):
            continue
        chain = " / ".join(h for _, h in heads)
        if any(EXEMPT_HEAD.search(h) for _, h in heads):
            continue
        # a tag in the heading chain, including "— VERIFIED unless noted" / "unless marked"
        if any(TAGS.search(h) or STATUS_RE.search(h) for _, h in heads):
            continue
        # bullets under a bold lead-in that carries a tag ("**Foo (HIGH).**"), or under a
        # bold lead-in that names an exempt topic ("**Blocking unknowns:**")
        if any(TAGS.search(text) or EXEMPT_HEAD.search(bold) for text, bold in leads):
            continue
        if kind == "row" and header and any(re.search(r"confidence|conf\b|status", c, re.I) for c in header):
            # table has a confidence column but this row left it empty
            findings.append(("warn", "CONF", rel, no, "table row with an empty confidence cell"))
            continue
        if not conf_all and (doc_tagged or
                             any(key[:i] in status_sections for i in range(1, len(key) + 1))):
            continue
        findings.append(("warn", "CONF", rel, no,
                         f"{'table row' if kind == 'row' else 'paragraph'} states a finding without a "
                         f"confidence tag (section: {chain or 'top'})"))

    # 3. firmware strings
    if windows:
        seen = set()
        for no, line in enumerate(lines, 1):
            for i in range(len(line) - N + 1):
                if line[i:i + N] in windows:
                    findings.append(("error", "STR", rel, no, f"verbatim firmware text: {line[i:i + N]!r}"))
                    seen.add(no)
                    break
        flat, owner = [], []
        for no, line in enumerate(lines, 1):
            for ch in re.sub(r"\s+", " ", line.strip()) + " ":
                flat.append(ch)
                owner.append(no)
        flat = "".join(flat)
        i = 0
        while i <= len(flat) - N:
            if flat[i:i + N] in windows:
                no = owner[i]
                if no not in seen and owner[i + N - 1] not in seen:
                    findings.append(("error", "STR", rel, no,
                                     f"verbatim firmware text across lines {no}-{owner[i + N - 1]}: "
                                     f"{flat[i:i + N]!r}"))
                i += N
            else:
                i += 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=Path(__file__).resolve().parent.parent, type=Path)
    ap.add_argument("--main-ranges", type=Path, help="function_ranges CSV for the Main Unit")
    ap.add_argument("--control-ranges", type=Path, help="function_ranges CSV for the Control Unit")
    ap.add_argument("--main-size", type=lambda x: int(x, 0), default=453152,
                    help="Main image size in bytes (default V1.0.1)")
    ap.add_argument("--control-size", type=lambda x: int(x, 0), default=781328,
                    help="Control image size in bytes (default V1.0.1)")
    ap.add_argument("--extra", nargs="*", default=[], help="more Markdown files to scan")
    ap.add_argument("--no-strings", action="store_true")
    ap.add_argument("--conf-all", action="store_true",
                    help="ignore document-level 'VERIFIED unless noted' status lines")
    ap.add_argument("--data-range", action="append", default=[], metavar="UNIT:LO-HI",
                    help="extra known flash data range, e.g. main:0x0808486C-0x080894C4 "
                         "(the V1.0.1 .data load images are built in)")
    ap.add_argument("--only", choices=["ADDR", "CONF", "STR"], action="append")
    ap.add_argument("--csv", type=Path, help="write findings as CSV")
    args = ap.parse_args()

    root = args.root.resolve()
    units = {}
    # V1.0.1 .data load images (memory_map.md); extend with --data-range
    dr = {"main": [(0x0808486C, 0x080894C4)], "control": [(0x080DD568, 0x080DEC00)]}
    for spec in args.data_range:
        u, rng = spec.split(":", 1)
        lo, hi = (int(x, 0) for x in rng.split("-"))
        dr.setdefault(u, []).append((lo, hi))
    if args.main_ranges:
        units["main"] = Unit("Main", args.main_ranges, args.main_size,
                             root / "main_unit/analysis/startup/vectors.csv", dr.get("main", []))
    if args.control_ranges:
        units["control"] = Unit("Control", args.control_ranges, args.control_size,
                                root / "control_unit/analysis/startup/vectors.csv", dr.get("control", []))
    windows = set()
    if not args.no_strings:
        windows = load_strings(sorted(root.glob("*/analysis/strings/strings.txt")))

    files = sorted(root.glob("docs/*.md")) + sorted(root.glob("*/docs/*.md"))
    files += [root / e for e in args.extra]
    findings = []
    for f in files:
        check_file(f, root, units, windows, findings, args.conf_all)
    if args.only:
        findings = [f for f in findings if f[1] in args.only]

    order = {"error": 0, "warn": 1, "info": 2}
    findings.sort(key=lambda f: (f[2], f[3], order[f[0]]))
    for sev, kind, rel, no, msg in findings:
        print(f"{rel}:{no}: {sev}: {kind}: {msg}")
    counts = {}
    for sev, kind, *_ in findings:
        counts[(kind, sev)] = counts.get((kind, sev), 0) + 1
    print("summary: " + ", ".join(f"{k} {s}={n}" for (k, s), n in sorted(counts.items())) if counts
          else "summary: clean", file=sys.stderr)
    if args.csv:
        with open(args.csv, "w", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["file", "line", "severity", "check", "message"])
            for sev, kind, rel, no, msg in findings:
                w.writerow([rel, no, sev, kind, msg])
    sys.exit(1 if any(f[0] == "error" for f in findings) else 0)


if __name__ == "__main__":
    main()
