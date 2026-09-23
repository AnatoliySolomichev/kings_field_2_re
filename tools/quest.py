#!/usr/bin/env python3
"""What a conversation can make happen: every level's `0xf4` hook, arm by arm.

    python3 tools/quest.py              every level, every arm, and who calls it
    python3 tools/quest.py 0            one level in full
    python3 tools/quest.py --check      the arm table against tools/ovdis.py
    python3 tools/quest.py --godot      write it out for the port

The conversation language has one opcode that reaches the world, `0xf4`, and
`tools/escript.py` describes it. What it calls is **entry 4 of the level's own
overlay**: `[0x8018fae0]` is the overlay's pointer table at `overlay + 4`, so
`+0x10` is its fifth slot. A RAM snapshot settled that -- ten of ten pointers
in it are what the disc holds, in order -- and `tools/overlay.py` has the
working.

Entry 4 is itself a switch on the argument the `0xf4` carries, and the switch
table sits in the overlay at offset **136**, just past the 32 pointers. So a
conversation saying `f4 1` runs arm 1 of its level's hook, and arm 1 is native
MIPS that asks what the player is carrying and writes story flags.

Which closes the loop the language sits in:

    f4 n                     ->  entry 4, arm n  ->  has_item, take_item,
                                                     give_item, story_flags[i] = v
    f1 flag value label      ->  start the conversation somewhere else
    f9 flag value label      ->  jump to a label mid-conversation

Level 0 is the clearest example. Arm 0 asks -- `has_item(2)`, `has_item(130)`,
`has_item(131)`, `has_item(132)`, then `story_flags[3] = 1` or `0`. Arm 1
does it -- the same four questions, then `story_flags[1] = 1`, four
`take_item` calls, and an unequip if the thing taken was in your hand. So a
talker calls `f4 0` to find out whether it can, reads the answer through a
guard, and calls `f4 1` to go through with it.

The rendering is `tools/decomp.py`'s, and its limits are that tool's: a
comparison it cannot resolve prints as registers, and an instruction it does
not recognise prints as itself rather than being quietly dropped.
"""
import collections
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import decomp                                                        # noqa: E402
import escript                                                       # noqa: E402
import overlay                                                       # noqa: E402

ARM_TABLE = 136            # the switch table's offset in the overlay entry
HOOK = overlay.HOOK_SCRIPT  # entry 4


def arms(lv):
    """(hook address, {argument: arm address}) for one level.

    The hooks come in **two shapes** and both are read rather than assumed.
    A level with many arms uses a jump table: an `sltiu` on `$a1` for the
    bound and a `lui`/`addiu` pair for the table, which sits in the overlay at
    offset 136, just past the 32 pointers. A level with two or three uses a
    chain of comparisons instead -- `beq $a1, <const>`, `beqz $a1`, or a bare
    `bnez $a1` whose fall-through *is* arm 0 -- and those are read off the same
    first few instructions.
    """
    raw, _ptrs, insns = overlay.overlay(lv)
    if not raw:
        return None, {}
    _hdr, ptrs = overlay.hooks(lv)
    hook = ptrs[HOOK] if len(ptrs) > HOOK else None
    if not hook or not (overlay.BASE <= hook < overlay.BASE + len(raw)):
        return None, {}
    at = {a: (m, o) for a, m, o in insns}
    out = {}
    const = {}
    hi = bound = base = None
    for i in range(48):
        a = hook + 4 * i
        if a not in at:
            break
        m, o = at[a]
        p = [x.strip() for x in o.split(",")]
        if m in ("ori", "addiu") and len(p) == 3 and p[1] in ("$zero", "$0"):
            try:
                const[p[0]] = int(p[2], 0)
            except ValueError:
                const.pop(p[0], None)
        elif m == "beq" and len(p) == 3 and p[0] == "$a1" and p[1] in const:
            out.setdefault(const[p[1]], int(p[2], 0))
        elif m == "beq" and len(p) == 3 and p[1] == "$a1" and p[0] in const:
            out.setdefault(const[p[0]], int(p[2], 0))
        elif m == "beqz" and len(p) == 2 and p[0] == "$a1":
            out.setdefault(0, int(p[1], 0))
        elif m == "bnez" and len(p) == 2 and p[0] == "$a1":
            out.setdefault(0, a + 8)       # arm 0 is the fall-through
        elif m == "sltiu" and len(p) == 3 and p[1] == "$a1":
            try:
                bound = int(p[2], 0)
            except ValueError:
                pass
        elif m == "lui" and len(p) == 2 and p[0] == "$at":
            hi = int(p[1], 0) << 16
        elif m == "addiu" and len(p) == 3 and p[1] == "$at" and hi is not None:
            base = (hi + int(p[2], 0)) & 0xFFFFFFFF
    if bound is not None and base is not None:
        off = base - overlay.BASE
        if 0 <= off <= len(raw) - 4 * bound:
            for i in range(bound):
                out[i] = struct.unpack_from("<I", raw, off + 4 * i)[0]
    return hook, out


def body(r, at, stops):
    """One arm's statements, stopped where the next arm begins.

    The decompiler follows the code straight on, and the arms sit one after
    another, so without this every arm is rendered with the ones below it
    tacked on -- which is how level 0's arm 0 appeared to take four items when
    all it does is answer a question.
    """
    end = min([x for x in stops if x > at], default=None)
    out = []
    for a, st in r.run(at):
        if end is not None and a >= end:
            break
        out.append((a, st))
    return out


def callers(levels=range(28)):
    """{level: {arm: [(entity, pc)]}} -- who asks for which arm."""
    out = collections.defaultdict(lambda: collections.defaultdict(list))
    for lv, k, _rec, _h, code in escript.conversations(levels):
        for off, _op, args, mn in escript.decode(code):
            if mn == "call_overlay" and args:
                out[lv][args[0]].append((k, off))
    return out


def check(out=sys.stdout):
    """The arms this file reads, against the ones the walker resolves.

    Two readings of the same table: this one scans the hook's first few
    instructions for the bound and the base, `tools/ovdis.py` runs the whole
    overlay through `tools/rdis.py`'s switch resolver. Where a level's hook is
    a jump table they can be compared; where it is a chain of comparisons
    there is nothing for the walker to resolve, and that is counted separately
    rather than as agreement.
    """
    import ovdis
    ok = bad = chain = 0
    for lv in range(28):
        hook, ar = arms(lv)
        if not ar:
            continue
        w = ovdis.walk(lv)
        found = {}
        # Only the table belonging to the hook itself. Matching loosely picks
        # up an unrelated 46-arm switch elsewhere in level 17's overlay and
        # reports 44 disagreements about a table neither reading is looking at.
        if w is not None and hook in w.funcs:
            for tb in w.funcs[hook].tables:
                if 0 <= tb["at"] - hook < 0x40:
                    for n, t in enumerate(tb["targets"]):
                        found[n] = t
        if not found:
            chain += 1
            continue
        for n in sorted(set(ar) | set(found)):
            if ar.get(n) == found.get(n):
                ok += 1
            else:
                bad += 1
                print(f"  level {lv} arm {n}: this file {ar.get(n)}, "
                      f"the walker {found.get(n)}", file=out)
    print(f"{ok} of {ok + bad} arms agree with tools/ovdis.py; "
          f"{chain} levels use a comparison chain, which has no table to resolve",
          file=out)
    return bad == 0


def render(lv, out=sys.stdout):
    hook, ar = arms(lv)
    if not ar:
        return 0
    who = callers([lv])[lv]
    r = decomp.Reader(lv)
    print(f"=== level {lv}: hook at {hook:#010x}, {len(ar)} arms ===", file=out)
    for n in sorted(ar):
        a = ar[n]
        asked = who.get(n, [])
        tag = ("  <- " + ", ".join(f"entity {k} at pc {pc}"
                                   for k, pc in asked)) if asked else \
              "  (no conversation asks for it)"
        print(f"\n  arm {n} at {a:#010x}{tag}", file=out)
        for at, text, depth in decomp.render_lines(body(r, a, set(ar.values()))):
            pad = "    " * (depth + (0 if text.endswith(":") else 1))
            print(f"   {at:#010x}  {pad}{text}", file=out)
    return len(ar)


def summary():
    """[(level, arms, calls, flags written, items asked about)]"""
    rows = []
    who = callers()
    for lv in range(28):
        hook, ar = arms(lv)
        if not ar:
            continue
        r = decomp.Reader(lv)
        flags, items = set(), set()
        for a in sorted(ar.values()):
            for _at, st in body(r, a, set(ar.values())):
                if st[0] == "store" and str(st[1]).startswith("story_flags["):
                    flags.add(int(str(st[1])[12:str(st[1]).index("]")]))
                if st[0] == "call":
                    name, args = st[1]
                    if "item" in str(name):
                        items.add(f"{name}{tuple(args)}")
        asked = sorted(who.get(lv, {}))
        rows.append((lv, len(ar), sum(len(v) for v in who.get(lv, {}).values()),
                     sorted(flags), len(items),
                     [n for n in asked if n not in ar]))
    return rows


def export(out_dir):
    rows = []
    who = callers()
    for lv in range(28):
        hook, ar = arms(lv)
        if not ar:
            continue
        r = decomp.Reader(lv)
        rows.append({"level": lv, "hook": hook,
                     "arms": [{"n": n, "at": ar[n],
                               "lines": [[x, text, depth] for x, text, depth
                                         in decomp.render_lines(
                                             body(r, ar[n], set(ar.values())))],
                               "called_by": who.get(lv, {}).get(n, [])}
                              for n in sorted(ar)]})
    path = os.path.join(out_dir, "quest.json")
    with open(path, "w") as fh:
        json.dump({"_note": "entry 4 of every level's overlay -- what a "
                            "conversation's 0xf4 opcode runs, arm by arm, "
                            "with the conversations that ask for each arm",
                   "levels": rows}, fh, separators=(",", ":"))
    return path


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg == "--check":
        sys.exit(0 if check() else 1)
    elif arg == "--godot":
        print(export("godot"))
    elif arg is not None:
        render(int(arg))
    else:
        print(__doc__)
        rows = summary()
        print(f"{len(rows)} levels carry a conversation hook\n")
        for lv, n, calls, flags, items, missing in rows:
            print(f"  level {lv:2d}: {n:2d} arms, {calls:2d} f4 calls ask for them, "
                  f"writes story_flags {flags or '-'}, {items} item questions"
                  + (f"   UNRESOLVED ARMS {missing}" if missing else ""))
