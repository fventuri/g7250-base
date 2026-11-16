#!/usr/bin/env python3
"""Frequency response of an FIR table or a biquad cascade (generic, unit-agnostic).

Replaces the X6100-era verify_tx_biquads.py (fixed 12.5 kHz rate and 31-float
filter entries), which does not apply to the G7250: its TX/RX biquads are designed
at run time (main_unit/docs/dsp.md) and only the SSB FIR tables sit in flash.

Coefficient sources (pick one):
  --csv FILE              ExportFloatArray.java output (column float_value)
  --image BIN --addr A --count N   read N little-endian float32 from a raw image
                          (file offset = A - --base)
  --values v1,v2,...      literal list

Modes:
  fir                     taps h[0..N-1]
  biquad                  stages of 5 coefficients b0,b1,b2,a1,a2 (--stride 5).
                          --convention cmsis (default): a1,a2 are stored with the
                          CMSIS-DSP sign, i.e. y = b0*x + ... + a1*y[n-1] + a2*y[n-2]
                          (same as the DF2T primitive); --convention standard uses
                          1 + a1 z^-1 + a2 z^-2 in the denominator.

Output: CSV frequency_hz,magnitude,db,phase_deg (and, for FIR, group delay in
samples estimated from the phase slope). --summary prints symmetry/antisymmetry,
DC gain and the peak/passband figures that tell a Hilbert from a delay FIR.
"""

from __future__ import annotations

import argparse
import cmath
import csv
import math
import struct


def load(args) -> list[float]:
    if args.csv:
        with open(args.csv, newline="") as fh:
            return [float(r["float_value"]) for r in csv.DictReader(fh)]
    if args.image:
        data = open(args.image, "rb").read()
        off = int(args.addr, 0) - int(args.base, 0)
        return list(struct.unpack_from(f"<{args.count}f", data, off))
    return [float(v) for v in args.values.split(",")]


def fir_h(taps, w):
    return sum(t * cmath.exp(-1j * w * n) for n, t in enumerate(taps))


def biquad_h(coefs, w, convention):
    z1 = cmath.exp(-1j * w)
    z2 = z1 * z1
    h = 1.0
    for i in range(0, len(coefs) - len(coefs) % 5, 5):
        b0, b1, b2, a1, a2 = coefs[i:i + 5]
        if convention == "cmsis":
            a1, a2 = -a1, -a2
        h *= (b0 + b1 * z1 + b2 * z2) / (1.0 + a1 * z1 + a2 * z2)
    return h


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["fir", "biquad"])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv")
    src.add_argument("--image")
    src.add_argument("--values")
    ap.add_argument("--addr")
    ap.add_argument("--count", type=int)
    ap.add_argument("--base", default="0x08020000")
    ap.add_argument("--fs", type=float, required=True, help="sample rate in Hz")
    ap.add_argument("--freqs", default="", help="comma list in Hz (default: 0..fs/2 in 25 steps)")
    ap.add_argument("--gain", type=float, default=1.0)
    ap.add_argument("--convention", choices=["cmsis", "standard"], default="cmsis")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()
    if args.image and (args.addr is None or args.count is None):
        ap.error("--image needs --addr and --count")

    coefs = load(args)
    freqs = ([float(f) for f in args.freqs.split(",")] if args.freqs
             else [args.fs / 2 * k / 24 for k in range(25)])

    def h(f):
        w = 2 * math.pi * f / args.fs
        v = fir_h(coefs, w) if args.mode == "fir" else biquad_h(coefs, w, args.convention)
        return v * args.gain

    print("frequency_hz,magnitude,db,phase_deg")
    for f in freqs:
        v = h(f)
        m = abs(v)
        db = 20 * math.log10(m) if m > 0 else float("-inf")
        print(f"{f:.3f},{m:.9g},{db:.4f},{math.degrees(cmath.phase(v)):.3f}")

    if args.summary and args.mode == "fir":
        n = len(coefs)
        sym = max(abs(coefs[i] - coefs[n - 1 - i]) for i in range(n))
        anti = max(abs(coefs[i] + coefs[n - 1 - i]) for i in range(n))
        nz = [i for i, c in enumerate(coefs) if abs(c) > 1e-12]
        even_zero = all(abs(coefs[i]) < 1e-9 for i in range(0, n, 2)) or \
            all(abs(coefs[i]) < 1e-9 for i in range(1, n, 2))
        peak = max(range(n), key=lambda i: abs(coefs[i]))
        print(f"# taps={n} nonzero={len(nz)} max|h|={abs(coefs[peak]):.6g} at index {peak}")
        print(f"# symmetric_err={sym:.3g} antisymmetric_err={anti:.3g} "
              f"alternate_taps_zero={even_zero} dc_gain={sum(coefs):.6g}")
        print(f"# linear-phase delay = {(n - 1) / 2:g} samples")


if __name__ == "__main__":
    main()
