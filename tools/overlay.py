#!/usr/bin/env python3
"""`FDAT.T` entry `3n + 2` — the code each level ships with it.

    python3 tools/overlay.py            what every level requires, in one table
    python3 tools/overlay.py 0          level 0: entry points and what it calls
    python3 tools/overlay.py 0 dis      level 0, disassembled

This is the piece that explains the rest. The entry is a `u32`, then 32 pointers
into `0x801e8xxx`, then **MIPS code** — `03e00008`, `27bdffc8`, prologues and
all. Every level carries its own routines, relocated on load, and they call
straight into the game's own:

    has_item   34 times across the game
    take_item  16
    give_item   3
    announce  190

So "which NPC wants which item" was never in a table. It is per-level native
code, and this reads it out. It also touches `object_table` 36 times, which is
where the missing object placement most likely is.

The base is `0x801e8308`: bytes at entry offset 132 were found in a RAM snapshot
at `0x801e838c`, and the first pointer, `0x801e83b0`, then lands exactly on the
prologue at entry offset 168.
"""
import collections
import struct
import sys

sys.path.insert(0, "tools")
import disasm                                                        # noqa: E402
import syms                                                          # noqa: E402
from tarc import TArc                                                # noqa: E402

FDAT = "extract/CD/COM/FDAT.T"
BASE = 0x801E8308
PRIMITIVES = {
    0x8005D7BC: "has_item",
    0x8005D7F8: "take_item",
    0x8005D898: "give_item",
    0x80041EEC: "announce",
    0x800441D4: "load_entry",
}


def overlay(lv, path=FDAT):
    """(raw entry, [entry point addresses], [instructions])"""
    raw = TArc(path).raw(lv * 3 + 2)
    if len(raw) < 256:
        return None, [], []
    ptrs = [struct.unpack_from("<I", raw, 4 + 4 * i)[0] for i in range(32)]
    ptrs = sorted({p for p in ptrs if 0x80100000 <= p < 0x80200000})
    cs = disasm.Cs()
    cs.load(raw, BASE)
    return raw, ptrs, cs.all(0)


def arg0(insns, i):
    """The literal put in $a0 for a call, or None when it comes from a register."""
    for j in list(range(i + 1, i + 2)) + list(range(i - 1, max(0, i - 12), -1)):
        _, m, o = insns[j]
        p = [x.strip() for x in o.split(",")]
        if p and p[0] == "$a0":
            if m in ("ori", "addiu") and len(p) == 3 and p[1] in ("$zero", "$0"):
                try:
                    return int(p[2], 0)
                except ValueError:
                    return None
            return None
    return None


def demands(lv):
    """[(routine, item id or None)] for one level, in the order they appear."""
    raw, ptrs, insns = overlay(lv)
    out = []
    for i, (a, m, o) in enumerate(insns):
        if m == "jal" and o.startswith("0x") and int(o, 0) in PRIMITIVES:
            out.append((PRIMITIVES[int(o, 0)], arg0(insns, i)))
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1:
        lv = int(sys.argv[1])
        raw, ptrs, insns = overlay(lv)
        if len(sys.argv) > 2 and sys.argv[2] == "dis":
            for a, m, o in insns:
                print(f"  {a:#010x}  {m:8s} {syms.annotate(o)}")
        else:
            print(f"level {lv}: {len(raw)} bytes, {len(ptrs)} entry points, "
                  f"{len(insns)} instructions")
            print("  entry points: " + ", ".join(f"{p:#x}" for p in ptrs))
            calls = collections.Counter(int(o, 0) for a, m, o in insns
                                        if m == "jal" and o.startswith("0x"))
            print("  calls:")
            for t, n in calls.most_common():
                print(f"    {syms.label(t):26s} x{n}")
    else:
        print("what each level asks of the player, from its own code:\n")
        totals = collections.Counter()
        for lv in range(28):
            d = demands(lv)
            if not d:
                continue
            for fn, v in d:
                totals[fn] += 1
            wanted = collections.Counter(f"{fn}({v})" for fn, v in d
                                         if fn != "announce" and fn != "load_entry")
            print(f"  level {lv:2d}: " + ", ".join(f"{k}" + (f" x{n}" if n > 1 else "")
                                                  for k, n in sorted(wanted.items())))
        print("\n  totals: " + ", ".join(f"{k} {v}" for k, v in totals.most_common()))
