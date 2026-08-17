#!/usr/bin/env python3
"""Where the game decides what an item does.

Three leaf routines carry every inventory change, and finding their call sites
turns "which NPC wants which item" from a question about play into a question
about code. Run with no arguments for the whole map:

    python3 tools/items.py

The inventory is two parallel byte arrays 150 apart, so item ids run 0..149:

    A = 0x800c85e8   how many you carry, capped at 99
    B = 0x800c867e   a second array the same routines fall back to

Pickups need no table: the handler at 0x8005e01c calls give_item with the
object's own type id, so an object's type id *is* the item id it yields. That
is why inventory slot 104 tracked the Earth Herb lying on the ground.

What is *not* data-driven is using an item on something. That lives in one
759-instruction function, 0x8005cbe0, which takes the selected item in $s5 and
branches on the type id of whatever the player is facing.
"""
import collections
import pickle
import re
import sys

sys.path.insert(0, "tools")
import syms                                                          # noqa: E402

INV_A = 0x800C85E8
INV_B = 0x800C867E
PRIMITIVES = {
    0x8005D7BC: "has_item",     # A[id] != 0 or B[id] != 0
    0x8005D7F8: "take_item",    # A[id] -= 1, else falls back to B
    0x8005D898: "give_item",    # A[id] += 1 while under 99, else B
}
USE_HANDLER = (0x8005CBE0, 0x8005D7BC)     # start, end
CACHE = "out/insns.pkl"


def load():
    """The disassembly, cached because building it takes a while."""
    try:
        return pickle.load(open(CACHE, "rb"))
    except (OSError, ValueError):
        import disasm
        cs, base, entry, insns = disasm.build()
        pickle.dump((base, entry, insns), open(CACHE, "wb"))
        return base, entry, insns


def arg0(insns, i):
    """The item id a call was given: the delay slot first, then backwards."""
    for j in list(range(i + 1, i + 2)) + list(range(i - 1, max(0, i - 12), -1)):
        _, m, o = insns[j]
        p = [x.strip() for x in o.split(",")]
        if not p or p[0] != "$a0":
            continue
        if m in ("ori", "addiu") and len(p) == 3 and p[1] in ("$zero", "$0"):
            try:
                return int(p[2], 0)
            except ValueError:
                return None
        return None                     # comes from a register, so from data
    return None


def call_sites(insns):
    """primitive name -> [(call address, literal item id or None)]"""
    out = collections.defaultdict(list)
    for i, (a, m, o) in enumerate(insns):
        if m == "jal" and o.startswith("0x") and int(o, 0) in PRIMITIVES:
            out[PRIMITIVES[int(o, 0)]].append((a, arg0(insns, i)))
    return out


def recipes(insns):
    """Walk the use handler and pair each target id with what follows.

    The shape is a chain of `ori $vN, $zero, <type id>` / `bne`, so the most
    recent compared constant is the object the player is pointing at when the
    calls below it run.
    """
    idx = {a: i for i, (a, m, o) in enumerate(insns)}
    lo, hi = idx[USE_HANDLER[0]], idx[USE_HANDLER[1]]
    out, target, prev, field_reg = [], None, None, None
    for k in range(lo, hi):
        a, m, o = insns[k]
        if m in ("lbu", "lb") and re.search(r"0x38\(\$s[0-9]\)", o):
            # the next comparison tests this field, not the type of the target
            field_reg = o.split(",")[0].strip()
            out.append((a, target, "reads +0x38 of it", None))
        elif m in ("beq", "bne") and prev and prev[1] == "ori" and ", $zero, " in prev[2]:
            reg = o.split(",")[0].strip()
            want = int(prev[2].split(", ")[-1], 0)
            if reg == field_reg:
                out.append((a, target, "+0x38 must be", want))
                field_reg = None
            else:
                target = want
        elif m == "jal" and o.startswith("0x") and int(o, 0) in PRIMITIVES:
            out.append((a, target, PRIMITIVES[int(o, 0)], arg0(insns, k)))
        prev = (a, m, o)
    return out


if __name__ == "__main__":
    base, entry, insns = load()
    print(f"inventory arrays: A={INV_A:#x}  B={INV_B:#x}  (ids 0..149)\n")
    for name, sites in call_sites(insns).items():
        lit = [(a, v) for a, v in sites if v is not None]
        dyn = [a for a, v in sites if v is None]
        print(f"{name:10s} {len(sites):3d} call sites, "
              f"{len(lit)} with a literal id, {len(dyn)} taken from data")
        for a, v in lit:
            print(f"    {syms.label(a):24s} item {v}")
    print(f"\nuse-item recipes inside {USE_HANDLER[0]:#x}:")
    for a, target, what, v in recipes(insns):
        t = f"facing type {target}" if target is not None else "no target yet"
        arg = "" if v is None else f" {v}"
        print(f"    {syms.label(a):24s} {t:20s} -> {what}{arg}")
