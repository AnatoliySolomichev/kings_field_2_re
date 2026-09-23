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
prologue at entry offset 168. The pointers on the disc are already absolute --
the overlay always loads at the same address -- so nothing is relocated.

**`level_hooks` is this table.** `[0x8018fae0]` read out of a running game is
`0x801e830c`, which is `BASE + 4`: the entry’s `u32` header, then the
pointers. Ten of the ten pointers a snapshot held are what the disc holds, in
order. So `level_overlay_tick` calling `level_hooks->+4` is calling **entry
1**, and a conversation’s `0xf4` calling `level_hooks->+0x10` is calling
**entry 4** -- and entry 4 of every level that has one is a switch on the very
argument the `0xf4` carries.

That closes the loop the conversation language sits in:

    f4 n   ->  the level’s entry 4, arm n  ->  has_item(...)  ->  story_flags[i] = v
    f1 / f9 on story_flags[i]  ->  a different section of dialogue

Level 0’s entry 4 is at `0x801e8a34`, six arms, and arm 0 sets
`story_flags[3]` to 1 when the player holds items 2, 130, 131 and 132 and to
0 when they do not. Sixty `0xf4` calls exist across fifteen levels and every
argument is inside its level’s switch bound.

**Withdrawn:** "`[0x8018fae0]` is a pointer to a structure, not to the
overlay’s own entry table" and "matching `+0x10` to a routine means reading
the pointer live, or finding what writes the structure". The pointer was read
live and it is the table.

The header `u32` is the **level number plus five** for every level that has an
overlay. What it is an index into is not settled.
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


HOOKS = 0x8018FAE0         # the game holds this table’s address here
HOOK_SCRIPT = 4            # the entry a conversation’s 0xf4 calls
HOOK_TICK = 1              # the entry level_overlay_tick calls once a frame


def hooks(lv, path=FDAT):
    """(header u32, the 32 pointers in table order), or (None, []).

    In table order, not sorted: which slot a pointer is in is the whole point.
    """
    raw = TArc(path).raw(lv * 3 + 2)
    if len(raw) < 132:
        return None, []
    return (struct.unpack_from("<I", raw, 0)[0],
            list(struct.unpack_from("<32I", raw, 4)))


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
        if len(sys.argv) > 2 and sys.argv[2] == "hooks":
            hdr, ptrs = hooks(lv)
            print(f"level {lv}: header {hdr} (= level + 5), the table at "
                  f"{BASE + 4:#x} that [0x8018fae0] points at\n")
            for i, p in enumerate(ptrs):
                if not (0x80100000 <= p < 0x80200000):
                    continue
                tag = ""
                if i == HOOK_TICK:
                    tag = "  <- level_overlay_tick calls this once a frame"
                if i == HOOK_SCRIPT:
                    tag = "  <- a conversation\u2019s 0xf4 calls this"
                print(f"  +{4 * i:#04x}  entry {i:2d}: {p:#010x}{tag}")
        elif len(sys.argv) > 2 and sys.argv[2] == "dis":
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
