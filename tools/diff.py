#!/usr/bin/env python3
"""Compare RAM snapshots to locate game structures.

    python3 tools/diff.py still1 still2            # what changes on its own
    python3 tools/diff.py a1 b --mask still1 still2

The mask pair is two snapshots taken while nothing happened; every address that
differs between them is background churn (timers, RNG, animation) and is
subtracted from the real comparison so only the interesting bytes remain.
"""
import sys

RAM_BASE = 0x80000000
WORD = 4


def load(label):
    return open(f"out/snap/{label}.ram", "rb").read()


def changed(a, b, step=1):
    return {i for i in range(0, min(len(a), len(b)), step) if a[i] != b[i]}


def runs(addrs, gap=8):
    """Collapse a set of offsets into contiguous regions."""
    out = []
    for a in sorted(addrs):
        if out and a - out[-1][1] <= gap:
            out[-1][1] = a
        else:
            out.append([a, a])
    return [(s, e) for s, e in out]


def report(a, b, mask=frozenset(), top=40):
    diff = changed(a, b) - mask
    reg = runs(diff)
    print(f"differing bytes: {len(diff)}   regions: {len(reg)}")
    reg.sort(key=lambda r: -(r[1] - r[0]))
    for s, e in reg[:top]:
        n = e - s + 1
        print(f"  {RAM_BASE + s:08x}..{RAM_BASE + e:08x}  {n:6d} bytes"
              f"   {a[s:s+16].hex()} -> {b[s:s+16].hex()}")
    return diff


if __name__ == "__main__":
    args = sys.argv[1:]
    mask = frozenset()
    if "--mask" in args:
        k = args.index("--mask")
        m1, m2 = args[k + 1], args[k + 2]
        mask = changed(load(m1), load(m2))
        print(f"mask from {m1}/{m2}: {len(mask)} noisy bytes")
        args = args[:k]
    report(load(args[0]), load(args[1]), mask)
