#!/usr/bin/env python3
"""Numeric QC for ComfyUI renders.

This agent cannot view images, so success is judged by comparing statistics
against a known-good reference render rather than by looking.

Usage (on the ComfyUI host, in any directory):
    /mnt/linux-games/comfyui-venv/bin/python imgstats.py *.png

Pass the reference image first so deltas are reported against it.
"""
import sys

from PIL import Image
import numpy as np


def stats(path):
    im = Image.open(path).convert("RGB")
    a = np.asarray(im, dtype=np.float64)
    g = a.mean(axis=2)

    dh = np.abs(np.diff(g, axis=1)).mean()
    dv = np.abs(np.diff(g, axis=0)).mean()
    local = (dh + dv) / 2.0
    # rough: neighbourhood gradient relative to global spread.
    # High for a structured image, low for smooth/flat or noise fields.
    rough = local / (g.std() + 1e-6) * 100.0 / 8.0

    return {
        "size": "%dx%d" % im.size,
        "mean": g.mean(),
        "std": g.std(),
        "dH": dh,
        "dV": dv,
        "rough": rough,
    }


def main(argv):
    if not argv:
        print(__doc__)
        return 2

    rows = [stats(p) for p in argv]
    ref = rows[0]

    hdr = "%-34s %-11s %7s %7s %7s %7s %7s" % (
        "file", "size", "mean", "std", "|dH|", "|dV|", "rough")
    print(hdr)
    print("-" * len(hdr))
    for path, s in zip(argv, rows):
        name = path.split("/")[-1]
        if len(name) > 33:
            name = name[:30] + "..."
        print("%-34s %-11s %7.1f %7.1f %7.2f %7.2f %7.2f" % (
            name, s["size"], s["mean"], s["std"], s["dH"], s["dV"], s["rough"]))

    if len(rows) > 1:
        print()
        print("deltas vs %s" % argv[0].split("/")[-1])
        for path, s in zip(argv[1:], rows[1:]):
            name = path.split("/")[-1]
            if len(name) > 30:
                name = name[:27] + "..."
            def pct(key):
                if abs(ref[key]) < 1e-9:
                    return float("nan")
                return (s[key] - ref[key]) / ref[key] * 100.0
            print("  %-33s mean %+6.1f%%  std %+6.1f%%  rough %+6.1f%%" % (
                name, pct("mean"), pct("std"), pct("rough")))

    print()
    print("Reading: std collapses + rough collapses -> noise or washed out;")
    print("         low std with pale mean            -> too few steps (undercooked);")
    print("         all metrics within ~5% of ref     -> healthy match.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
