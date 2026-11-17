#!/usr/bin/env python3
"""Relocation-masked byte-pattern matching of static-library functions in a raw
firmware image (no third-party dependencies: own ar + ELF32 parser).

For every STT_FUNC symbol in every object of each given `.a` archive, the tool
takes the symbol's bytes and masks every byte covered by an ELF relocation
(BL/B.W immediates, MOVW/MOVT halves, literal-pool address words, ...). It then

  1. SEARCHES the whole image (every 2-byte aligned offset) for the masked
     pattern; a hit is
        exact   - the symbol has no relocations and every byte matches,
        masked  - every invariant (unmasked) byte matches;
  2. optionally SCORES known function entries (--functions CSV) that are not
     covered by a search hit but lie near one (--partial-gap), by aligning the
     firmware halfwords with each symbol's masked halfwords (difflib):
        partial - alignment ratio >= --partial (a variant of the same source,
                  or a Ghidra boundary that differs from the symbol).

Search hits are kept when they have at least --min-invariant invariant bytes,
or at least --min-trivial and are the unique occurrence in the image inside a
block anchored by non-trivial hits of any given archive (--anchor-gap).
Zero-size assembly symbols (memchr, __aeabi_uldivmod, _init, ...) are sized up
to the next named symbol in their section.

Call-graph passes (Thumb-2 BL/B.W decoding at R_ARM_THM_CALL/THM_JUMP24 sites):
  * a rejected hit is accepted when every branch to an already placed symbol
    lands on that symbol ("call target confirmed");
  * same-shape candidates (e.g. the _xxx_r syscall wrappers, acos/asin
    wrappers, printf/fprintf) are told apart by placed callers and by their own
    branch targets; names placed unambiguously elsewhere are excluded;
  * tiny stubs (locks, __errno, ...) are accepted when a placed caller
    branches to them under that name.
--known CSVs (address + name) seed the call-graph evidence with names already
established in the project (e.g. CubeMX _sbrk).

Output CSV: address,size,library,object,symbol,match_quality,invariant_bytes,
ratio,also_in,alternatives,note.  `also_in` lists other archives holding the
identical function; `alternatives` lists other symbol names with the same code
at that address (aliases or unresolved same-shape functions). No code bytes.

Run with python3 -I; archives and images are treated as untrusted data.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import struct
import sys
from collections import defaultdict

# ARM relocation types (ELF for the Arm Architecture) -> patched width in bytes
RELOC_WIDTH = defaultdict(lambda: 4)
for _t in (0, 40):          # R_ARM_NONE, R_ARM_V4BX
    RELOC_WIDTH[_t] = 0
for _t in (7, 11, 52, 102, 103):  # THM_ABS5, THM_PC8, THM_JUMP6, THM_JUMP11, THM_JUMP8
    RELOC_WIDTH[_t] = 2
RELOC_WIDTH[8] = 1          # R_ARM_ABS8
RELOC_WIDTH[5] = 2          # R_ARM_ABS16


# --------------------------------------------------------------------------- #
# ar archive
# --------------------------------------------------------------------------- #
def ar_members(path):
    data = open(path, "rb").read()
    if not data.startswith(b"!<arch>\n"):
        raise ValueError(f"{path}: not an ar archive")
    pos, longnames = 8, b""
    while pos + 60 <= len(data):
        hdr = data[pos:pos + 60]
        name = hdr[0:16].decode("latin1").rstrip()
        size = int(hdr[48:58].decode("latin1").strip())
        body = data[pos + 60:pos + 60 + size]
        pos += 60 + size + (size & 1)
        if name == "//":
            longnames = body
            continue
        if name in ("/", "/SYM64/"):
            continue
        if name.startswith("/") and name[1:].isdigit():
            off = int(name[1:])
            end = longnames.find(b"/\n", off)
            name = longnames[off:end].decode("latin1")
        else:
            name = name.rstrip("/")
        yield name, body


# --------------------------------------------------------------------------- #
# minimal ELF32 little-endian relocatable object parser
# --------------------------------------------------------------------------- #
def elf_functions(blob):
    if blob[:4] != b"\x7fELF" or blob[4] != 1 or blob[5] != 1:
        return []
    e_shoff, = struct.unpack_from("<I", blob, 0x20)
    e_shentsize, e_shnum, e_shstrndx = struct.unpack_from("<HHH", blob, 0x2E)
    secs = []
    for i in range(e_shnum):
        secs.append(struct.unpack_from("<IIIIIIIIII", blob, e_shoff + i * e_shentsize))
    def sdata(s):
        return blob[s[4]:s[4] + s[5]] if s[1] != 8 else b""   # SHT_NOBITS
    shstr = sdata(secs[e_shstrndx])
    def cstr(tab, off):
        return tab[off:tab.index(b"\0", off)].decode("latin1")
    names = [cstr(shstr, s[0]) for s in secs]

    relocs = defaultdict(list)            # target section -> [(off, width)]
    symtab = None
    for i, s in enumerate(secs):
        if s[1] == 9 or s[1] == 4:        # SHT_REL / SHT_RELA
            ent = 8 if s[1] == 9 else 12
            d = sdata(s)
            for k in range(0, len(d), ent):
                off, info = struct.unpack_from("<II", d, k)
                relocs[s[7]].append((off, RELOC_WIDTH[info & 0xFF], info & 0xFF, info >> 8))
        elif s[1] == 2:                   # SHT_SYMTAB
            symtab = s
    if symtab is None:
        return []
    strtab = sdata(secs[symtab[6]])
    d = sdata(symtab)
    def symname(idx):
        st_name, = struct.unpack_from("<I", d, idx * 16)
        st_info = d[idx * 16 + 12]
        return None if (st_info & 0xF) == 3 else cstr(strtab, st_name)   # skip STT_SECTION
    entries = []
    starts = defaultdict(set)           # section -> named symbol offsets (boundaries)
    for k in range(0, len(d), 16):
        st_name, st_value, st_size, st_info, _o, st_shndx = struct.unpack_from("<IIIBBH", d, k)
        if not (0 < st_shndx < 0xFF00):
            continue
        nm = cstr(strtab, st_name)
        if (st_info & 0xF) in (0, 2) and nm and not nm.startswith("$") and not nm.startswith(".L"):
            starts[st_shndx].add(st_value & ~1)
        if (st_info & 0xF) == 2:
            entries.append((nm, st_value, st_size, st_shndx))
    out = []
    for nm, st_value, st_size, st_shndx in entries:
        sec = secs[st_shndx]
        start = st_value & ~1
        if st_size == 0:
            # assembly routine without .size: extend to the next named symbol
            # in the same section, or to the section end
            nxt = [o for o in starts[st_shndx] if o > start]
            st_size = (min(nxt) if nxt else sec[5]) - start
            if st_size <= 0:
                continue
        code = sdata(sec)[start:start + st_size]
        if len(code) < st_size:
            continue
        mask = bytearray(b"\1") * st_size
        nrel = 0
        calls = []
        for off, w, rtype, sidx in relocs.get(st_shndx, ()):
            r = off - start
            if 0 <= r < st_size and rtype in (10, 30):      # R_ARM_THM_CALL / THM_JUMP24
                tn = symname(sidx)
                if tn:
                    calls.append((r, tn))
            if 0 <= r < st_size and w:
                nrel += 1
                for j in range(r, min(r + w, st_size)):
                    mask[j] = 0
        out.append((nm, names[st_shndx], bytes(code), bytes(mask), nrel, calls))
    return out


class Sym:
    __slots__ = ("name", "obj", "lib", "code", "mask", "nrel", "inv", "calls")
    def __init__(self, name, obj, lib, code, mask, nrel, calls=()):
        self.calls = list(calls)
        self.name, self.obj, self.lib = name, obj, lib
        self.code, self.mask, self.nrel = code, mask, nrel
        self.inv = sum(mask)


def load_libs(specs):
    syms = []
    for spec in specs:
        label, path = spec.split("=", 1) if "=" in spec else (os.path.basename(spec), spec)
        if path.endswith(".o"):
            members = [(os.path.basename(path), open(path, "rb").read())]
        else:
            members = ar_members(path)
        for member, blob in members:
            for name, _sec, code, mask, nrel, calls in elf_functions(blob):
                syms.append(Sym(name, member, label, code, mask, nrel, calls))
    return syms


def pattern(sym):
    parts, run = [], bytearray()
    for b, m in zip(sym.code, sym.mask):
        if m:
            run.append(b)
        else:
            if run:
                parts.append(re.escape(bytes(run))); run = bytearray()
            parts.append(b".")
    if run:
        parts.append(re.escape(bytes(run)))
    return re.compile(b"".join(parts), re.DOTALL)


def search(image, base, syms):
    """addr -> list of (sym, quality) for every aligned full-pattern hit."""
    seen = {}
    hits = defaultdict(list)
    occ = {}
    for s in syms:
        key = (s.code if s.nrel == 0 else bytes(c if m else 0 for c, m in zip(s.code, s.mask)), s.mask)
        if key in seen:
            pos_list = seen[key]
        else:
            pat = pattern(s)
            pos_list, p = [], 0
            while True:
                m = pat.search(image, p)
                if not m:
                    break
                if m.start() % 2 == 0:
                    pos_list.append(m.start())
                p = m.start() + 1
            seen[key] = pos_list
        occ[id(s)] = len(pos_list)
        for p in pos_list:
            q = "exact" if s.nrel == 0 else "masked"
            hits[base + p].append((s, q))
    return hits, occ


def thumb_branch_target(image, base, addr):
    """Decode a Thumb-2 BL / B.W (T4) at addr; None if it is neither."""
    off = addr - base
    if off < 0 or off + 4 > len(image):
        return None
    h1, h2 = struct.unpack_from("<HH", image, off)
    if (h1 & 0xF800) != 0xF000 or (h2 & 0xD000) not in (0xD000, 0x9000):
        return None
    s_ = (h1 >> 10) & 1
    j1, j2 = (h2 >> 13) & 1, (h2 >> 11) & 1
    i1, i2 = 1 - (j1 ^ s_), 1 - (j2 ^ s_)
    imm = (s_ << 24) | (i1 << 23) | (i2 << 22) | ((h1 & 0x3FF) << 12) | ((h2 & 0x7FF) << 1)
    if s_:
        imm -= 1 << 25
    return addr + 4 + imm


def load_entries(path):
    ents = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            a = row.get("address") or row.get("entry") or row.get("fw_addr")
            a = int(a, 16)
            if row.get("bytes"):
                n = int(row["bytes"])
            elif row.get("body_bytes"):
                n = int(row["body_bytes"])
            elif row.get("end"):
                n = int(row["end"], 16) - a
            else:
                n = 0
            ents.append((a, n))
    return sorted(set(ents))


def ratio(sym, cand):
    if sym.inv == 0 or len(cand) < len(sym.code):
        return 0.0
    hit = sum(1 for c, b, m in zip(cand, sym.code, sym.mask) if m and c == b)
    return hit / sym.inv


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", required=True)
    ap.add_argument("--base", default="0x08020000")
    ap.add_argument("--lib", action="append", required=True, metavar="LABEL=PATH")
    ap.add_argument("--functions", help="CSV of known function entries (address/entry + bytes/end)")
    ap.add_argument("--min-invariant", type=int, default=24)
    ap.add_argument("--min-trivial", type=int, default=8,
                    help="smallest invariant size accepted for unique in-block hits")
    ap.add_argument("--anchor-gap", type=lambda x: int(x, 0), default=0x400)
    ap.add_argument("--partial", type=float, default=0.80,
                    help="min halfword-alignment ratio for a 'partial' row")
    ap.add_argument("--partial-gap", type=lambda x: int(x, 0), default=0x1000,
                    help="only score known entries within this distance of exact/masked hits")
    ap.add_argument("--length-tol", type=float, default=0.15)
    ap.add_argument("--out", required=True)
    ap.add_argument("--known", action="append",
                    help="CSV of already named functions (address + name/new_name/proposed_name), "
                         "used only as call-graph evidence; repeatable")
    ap.add_argument("--summary", help="write per-archive hit counts CSV")
    a = ap.parse_args()

    base = int(a.base, 16)
    image = open(a.image, "rb").read()
    syms = load_libs(a.lib)
    libs_order = {}
    for spec in a.lib:
        lab = spec.split("=", 1)[0] if "=" in spec else os.path.basename(spec)
        libs_order.setdefault(lab, len(libs_order))
    sys.stderr.write(f"{len(syms)} library function symbols\n")
    hits, occ = search(image, base, syms)

    # anchors: non-trivial hits
    anchors = defaultdict(list)
    for addr, lst in hits.items():
        for s, q in lst:
            if s.inv >= a.min_invariant:
                anchors["*"].append((addr, addr + len(s.code)))

    def anchored(lib, addr):
        return any(lo - a.anchor_gap <= addr <= hi + a.anchor_gap for lo, hi in anchors["*"])

    rows = {}
    for addr, lst in sorted(hits.items()):
        good = [(s, q) for s, q in lst
                if s.inv >= a.min_invariant or
                (s.inv >= a.min_trivial and occ[id(s)] == 1 and anchored(s.lib, addr))]
        if not good:
            continue
        # longest symbol first; among equal code prefer the earliest archive given
        # on the command line, then a public-looking short name
        good.sort(key=lambda t: (-len(t[0].code), libs_order[t[0].lib],
                                 t[0].name.startswith("_"), len(t[0].name), t[0].name))
        s, q = good[0]
        longest = [g for g in good if len(g[0].code) == len(s.code)]
        alts = sorted({f"{g[0].lib}:{g[0].name}" for g in longest[1:]
                       if (g[0].lib, g[0].name) != (s.lib, s.name)})
        rows[addr] = dict(address=f"{addr:08x}", size=len(s.code), library=s.lib, object=s.obj,
                          symbol=s.name, match_quality=q, invariant_bytes=s.inv,
                          ratio="1.000", alternatives=";".join(alts),
                          note=";".join(n for n in (
                              "trivial (unique, inside anchored block)" if s.inv < a.min_invariant else "",
                              f"pattern occurs {occ[id(s)]}x in image" if occ[id(s)] > 1 else "",
                              ("shape-ambiguous; branches to " + " ".join(
                                  f"{thumb_branch_target(image, base, addr + r):08x}" for r, _t in s.calls
                                  if thumb_branch_target(image, base, addr + r) is not None))
                              if len(alts) > 0 and s.calls and len({g[0].obj for g in longest}) > 1 else "") if n))

    # second pass: a rejected (trivial or repeated) hit is accepted when every
    # BL/B.W to a symbol we have already placed decodes to that symbol's address
    for _round in range(3):
        placed = defaultdict(set)
        for r in rows.values():
            placed[r["symbol"]].add(int(r["address"], 16))
            for alt in filter(None, r["alternatives"].split(";")):
                placed[alt.split(":", 1)[1]].add(int(r["address"], 16))
        added = 0
        for addr, lst in sorted(hits.items()):
            if addr in rows:
                continue
            ok = []
            for s, q in lst:
                if s.inv < a.min_trivial or not s.calls:
                    continue
                checks = [(r, t) for r, t in s.calls if t in placed]
                if checks and all(thumb_branch_target(image, base, addr + r) in placed[t]
                                  for r, t in checks):
                    ok.append((s, q, len(checks)))
            if not ok:
                continue
            ok.sort(key=lambda t: (-t[2], -len(t[0].code), libs_order[t[0].lib], len(t[0].name)))
            s, q, nchk = ok[0]
            alts = sorted({f"{o[0].lib}:{o[0].name}" for o in ok[1:] if o[2] == nchk
                           and len(o[0].code) == len(s.code) and o[0].name != s.name})
            rows[addr] = dict(address=f"{addr:08x}", size=len(s.code), library=s.lib, object=s.obj,
                              symbol=s.name, match_quality=q, invariant_bytes=s.inv, ratio="1.000",
                              alternatives=";".join(alts),
                              note=f"call target confirmed ({nchk} branch(es) land on placed symbols)")
            added += 1
        if not added:
            break

    # refinement: pick among same-shape candidates by call-graph evidence
    #   callers: a placed symbol whose BL/B.W to name X lands here names this X
    #   callees: a candidate whose own branches land on its named targets wins
    known = defaultdict(set)
    for path in a.known or ():
        with open(path, newline="") as fh:
            for kr in csv.DictReader(fh):
                nm = kr.get("new_name") or kr.get("name") or kr.get("proposed_name") or ""
                ad = kr.get("address") or kr.get("entry") or ""
                if nm and ad and not nm.startswith("FUN_"):
                    known[nm].add(int(ad, 16))
    for _round in range(3):
        placed = defaultdict(set, {k: set(v) for k, v in known.items()})
        for r in rows.values():
            placed[r["symbol"]].add(int(r["address"], 16))
        unique_elsewhere = defaultdict(set)       # names placed unambiguously
        for r in rows.values():
            if (not r["alternatives"] or "name fixed" in r["note"] or "confirmed" in r["note"]) \
                    and "still ambiguous" not in r["note"]:
                unique_elsewhere[r["symbol"]].add(int(r["address"], 16))
        called_as = defaultdict(set)
        symobj = {}
        for addr, lst in hits.items():
            if addr in rows:
                for s_, q_ in lst:
                    if s_.name == rows[addr]["symbol"] and s_.lib == rows[addr]["library"]:
                        symobj[addr] = s_
        for addr, s_ in symobj.items():
            for r_, t_ in s_.calls:
                tgt = thumb_branch_target(image, base, addr + r_)
                if tgt is not None:
                    called_as[tgt].add(t_)
        changed = 0
        # tiny stubs: a byte-matching hit whose name a placed caller branches to
        for addr, names in list(called_as.items()):
            if addr in rows or addr not in hits:
                continue
            c = [s_ for s_, q_ in hits[addr] if s_.name in names]
            if c:
                c.sort(key=lambda s_: (libs_order[s_.lib], s_.name))
                s_ = c[0]
                rows[addr] = dict(address=f"{addr:08x}", size=len(s_.code), library=s_.lib,
                                  object=s_.obj, symbol=s_.name,
                                  match_quality="exact" if s_.nrel == 0 else "masked",
                                  invariant_bytes=s_.inv, ratio="1.000", alternatives="",
                                  note="small; name confirmed by a placed caller")
                changed += 1
        for addr, row in rows.items():
            if row["match_quality"] == "partial" or addr not in symobj:
                continue
            cur = symobj[addr]
            cands = [s_ for s_, q_ in hits[addr] if len(s_.code) == len(cur.code)]
            if len({c.name for c in cands}) < 2:
                continue
            # a symbol occurs once per image: drop names placed unambiguously elsewhere
            pruned = [c for c in cands if not (unique_elsewhere.get(c.name, set()) - {addr})]
            if pruned and len(pruned) < len(cands) and cur.name not in {c.name for c in pruned}:
                new = sorted(pruned, key=lambda c: (libs_order[c.lib], c.name))[0]
                alts = sorted({f"{c.lib}:{c.name}" for c in pruned if c.name != new.name})
                row.update(library=new.lib, object=new.obj, symbol=new.name,
                           match_quality="exact" if new.nrel == 0 else "masked",
                           invariant_bytes=new.inv, alternatives=";".join(alts),
                           note="same-shape names placed elsewhere excluded" + (
                               "; still ambiguous" if alts else ""))
                changed += 1
                continue
            cands = pruned or cands
            by_caller = [c for c in cands if c.name in called_as.get(addr, ())]
            def callee_score(c):
                sc = 0
                for r_, t_ in c.calls:
                    if t_ in placed:
                        sc += 1 if thumb_branch_target(image, base, addr + r_) in placed[t_] else -1
                return sc
            why = ""
            if by_caller and cur.name not in {c.name for c in by_caller}:
                new, why = by_caller[0], "name fixed by a placed caller"
            elif not by_caller:
                scored = sorted(cands, key=lambda c: -callee_score(c))
                if callee_score(scored[0]) > callee_score(cur) and \
                        (len(scored) < 2 or callee_score(scored[0]) > callee_score(scored[1])):
                    new, why = scored[0], "name fixed by its branch targets"
            if why:
                q_new = "exact" if new.nrel == 0 else "masked"
                alts = sorted({f"{c.lib}:{c.name}" for c in cands if c.name != new.name})
                row.update(library=new.lib, object=new.obj, symbol=new.name, match_quality=q_new,
                           invariant_bytes=new.inv, alternatives=";".join(alts),
                           note=why)
                changed += 1
            elif "confirmed" not in row["note"]:
                sc = sorted((callee_score(c) for c in cands if c.name != cur.name), reverse=True)
                if by_caller:
                    row["note"] = (row["note"] + ";" if row["note"] else "") + "name confirmed by a placed caller"
                    changed += 1
                elif callee_score(cur) > 0 and (not sc or callee_score(cur) > sc[0]):
                    row["note"] = (row["note"] + ";" if row["note"] else "") + "name confirmed by its branch targets"
                    changed += 1
        if not changed:
            break

    if a.functions:
        import difflib
        covered = [(int(r["address"], 16), int(r["address"], 16) + int(r["size"])) for r in rows.values()]
        def is_covered(x):
            return any(lo <= x < hi for lo, hi in covered)
        def near_anchor(x):
            return any(lo - a.partial_gap <= x <= hi + a.partial_gap for lo, hi in anchors["*"])
        def hw(code, mask=None):
            return [(code[i] | code[i + 1] << 8) if (mask is None or (mask[i] and mask[i + 1])) else -1
                    for i in range(0, len(code) - 1, 2)]
        cand_syms = [(s, hw(s.code, s.mask)) for s in syms if s.inv >= a.min_invariant]
        for addr, n in load_entries(a.functions):
            if (n < a.min_invariant or is_covered(addr) or not near_anchor(addr)
                    or any(addr <= lo < addr + n for lo, hi in covered)):
                continue
            off = addr - base
            fw = hw(image[off:off + n])
            best, br = None, 0.0
            for s, shw in cand_syms:
                if abs(len(s.code) - n) > max(8, a.length_tol * len(s.code)):
                    continue
                sm = difflib.SequenceMatcher(None, fw, shw, autojunk=False)
                if sm.real_quick_ratio() <= br or sm.quick_ratio() <= br:
                    continue
                r = sm.ratio()
                if r > br:
                    best, br = s, r
            if best is not None and br >= a.partial:
                rows[addr] = dict(address=f"{addr:08x}", size=n, library=best.lib,
                                  object=best.obj, symbol=best.name, match_quality="partial",
                                  invariant_bytes=best.inv, ratio=f"{br:.3f}", alternatives="",
                                  note=f"halfword alignment vs symbol of {len(best.code)} bytes; variant or wrong boundary")

    for r in rows.values():
        alts = [x.split(":", 1) for x in filter(None, r["alternatives"].split(";"))]
        r["also_in"] = ";".join(sorted({l for l, n in alts if n == r["symbol"] and l != r["library"]}))
        r["alternatives"] = ";".join(sorted({n for l, n in alts if n != r["symbol"]}))
        r["note"] = ";".join(dict.fromkeys(filter(None, r["note"].split(";"))))
    fields = ["address", "size", "library", "object", "symbol", "match_quality",
              "invariant_bytes", "ratio", "also_in", "alternatives", "note"]
    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for k in sorted(rows):
            w.writerow(rows[k])
    cnt = defaultdict(lambda: [0, 0])
    for r in rows.values():
        c = cnt[(r["library"], r["match_quality"])]
        c[0] += 1; c[1] += int(r["size"])
    if a.summary:
        with open(a.summary, "w", newline="") as fh:
            w = csv.writer(fh); w.writerow(["library", "match_quality", "functions", "bytes"])
            for (lib, q), (n, b) in sorted(cnt.items()):
                w.writerow([lib, q, n, b])
    for (lib, q), (n, b) in sorted(cnt.items()):
        sys.stderr.write(f"  {lib:28s} {q:8s} {n:5d} fn {b:7d} B\n")


if __name__ == "__main__":
    main()
