#!/usr/bin/env python3
"""What an object *does*, opcode by opcode.

    python3 tools/objops.py             every opcode, with what its arm touches
    python3 tools/objops.py 0x1f        one opcode in full
    python3 tools/objops.py --census    which opcodes level 0 actually uses
    python3 tools/objops.py --doc       regenerate OBJECTS.md

`object_interpreter` (`0x80047010`) is the third call in every frame and the
largest routine in the game at 3965 instructions. It walks all 396 slots of
`object_table`, and for each one:

```
if record[+4] == 0xff:  skip
published for the handlers:  0x80198394 = the record
                             0x80198390 = object_type_table + 24 * record[+6]
if record[+4] < 236:  switch on it, through the table at 0x8001209c
```

So **byte +4 is the object's behaviour opcode**, and it is a copy of byte +0 of
its type's row in `object_type_table` — which is what FORMATS.md had already
established from the other side, as the class `render_walk` dispatches on.
Doors, chests, levers, signs and the things that hurt you are all one machine
with 236 opcodes, of which 44 have their own code and the rest share a tail.

This tool walks each arm's own blocks -- everything reachable from it without
entering another arm -- and reports what that arm calls and which globals it
touches. None of it is interpreted: the arms are resolved by `tools/rdis.py`
from the `sltiu` that guards the index, and the rest is read off the
instructions in them.

The census is separate and narrower on purpose. `object_type_table` is filled
per level, so a RAM snapshot says which opcodes *that* level uses and nothing
about the other twenty-seven. `out/snap/b.ram` is level 0.
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rdis                                                          # noqa: E402
import syms                                                          # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
INTERP = 0x80047010
TYPE_TABLE = 0x8018FB3C
TYPE_ROW = 24
SNAP = os.path.join(ROOT, "out", "snap", "b.ram")

_W = None


def walk():
    global _W
    if _W is None:
        _W = rdis.build("game")
    return _W


def table(w=None):
    """`{opcode: arm address}` for all 236, out of the resolved switch."""
    w = w or walk()
    fn = w.funcs[INTERP]
    tb = next(t for t in fn.tables if t["base"] == 0x8001209C)
    return {i: t for i, t in enumerate(tb["targets"])}, tb


def arms(w=None):
    """`{arm: [opcodes that reach it]}`, the shared tail included."""
    w = w or walk()
    t, _tb = table(w)
    out = collections.defaultdict(list)
    for op, a in t.items():
        out[a].append(op)
    return dict(out)


def body(w, fn, arm, stops):
    """The blocks that belong to one arm: reachable without entering another.

    A switch's arms share a tail -- every one of them ends up back at the top
    of the loop -- so a plain reachability walk from an arm would sweep up the
    whole routine. Stopping at the other arms keeps each one to its own code,
    and the shared tail then belongs to whichever arm is the fall-through,
    which is the honest place for it.
    """
    starts = {b for b in fn.blocks if b in stops and b != arm}
    seen, queue = set(), [arm]
    blocks = sorted(fn.blocks)
    import bisect

    def block_of(a):
        i = bisect.bisect_right(blocks, a) - 1
        return blocks[i] if i >= 0 else None

    b0 = block_of(arm)
    if b0 is None:
        return []
    queue = [b0]
    while queue:
        b = queue.pop()
        if b in seen or b in starts:
            continue
        seen.add(b)
        for t in rdis._successors(w, fn, fn.blocks[b]):
            if t in fn.blocks:
                queue.append(t)
    return sorted(seen)


def profile(w, fn, blocks):
    """What an arm's own blocks call and touch."""
    calls, glob, consts = [], [], []
    addrs = {a for b in blocks for a in fn.blocks[b]}
    for at, to, _args in fn.calls:
        if at in addrs:
            nm = w.funcs[to].name if to in w.funcs else syms.label_in("game", to)
            if nm not in calls:
                calls.append(nm)
    for at, addr, mode, _wd in fn.refs:
        if at not in addrs:
            continue
        nm = syms.name_in("game", addr, "")
        if nm and (nm, mode) not in glob:
            glob.append((nm, mode))
    for at, v, _mn in fn.consts:
        if at in addrs and abs(v) > 9 and v not in consts:
            consts.append(v)
    return calls, glob, consts


def export(out_dir, path=SNAP):
    """The class of every type on level 0, where the port can read it.

    **Borrowed, not understood.** `object_type_table` is not a straight copy of
    anything on the disc: of the 819 non-zero rows in a level-0 snapshot only
    32 appear verbatim in `FDAT.T` entry 1, at offset 9004, and the rows for
    the low type ids read as item stats -- a weight and a value -- so the table
    is built at load time out of at least two sources and the rest is not
    found. Until it is, the port takes the class bytes out of a snapshot, the
    same arrangement `tools/level3d.py` already has for the object scales and
    the object textures, and says so here rather than in a comment nobody
    reads.
    """
    if not os.path.exists(path):
        return None
    ram = open(path, "rb").read()
    base = TYPE_TABLE - 0x80000000
    rows = {}
    for t in range(0x400):
        row = ram[base + TYPE_ROW * t: base + TYPE_ROW * t + TYPE_ROW]
        if any(row):
            rows[str(t)] = row[0]
    out = os.path.join(out_dir, "objclass.json")
    with open(out, "w") as fh:
        json.dump({"_note": "byte +0 of each type's row in object_type_table, "
                            "out of out/snap/b.ram -- level 0 only, and "
                            "borrowed rather than derived: see "
                            "tools/objops.py export()",
                   "level": 0, "class": rows}, fh, separators=(",", ":"))
    return out


def census(path=SNAP):
    """Which opcodes the level in a snapshot actually uses, and on what."""
    import placement
    if not os.path.exists(path):
        return {}
    ram = open(path, "rb").read()
    base = TYPE_TABLE - 0x80000000
    cls = {}
    for t in range(0x400):
        row = ram[base + TYPE_ROW * t: base + TYPE_ROW * t + TYPE_ROW]
        if any(row):
            cls[t] = row[0]
    out = collections.defaultdict(lambda: {"objects": 0, "types": set()})
    for o in placement.objects(0):
        c = cls.get(o["type"])
        if c is None:
            continue
        out[c]["objects"] += 1
        out[c]["types"].add(o["type"])
    return dict(out)


def report(op=None, out=sys.stdout):
    w = walk()
    fn = w.funcs[INTERP]
    t, tb = table(w)
    grouped = arms(w)
    stops = set(t.values())
    shared = max(grouped, key=lambda a: len(grouped[a]))
    cen = census()
    rows = sorted(grouped.items(), key=lambda kv: min(kv[1]))
    print(f"{len(t)} opcodes through {len(grouped)} arms; "
          f"{len(grouped[shared])} of them share {shared:#010x}", file=out)
    for arm, ops in rows:
        if op is not None and op not in ops:
            continue
        if arm == shared and op is None:
            continue
        blocks = body(w, fn, arm, stops)
        calls, glob, consts = profile(w, fn, blocks)
        n = sum(cen.get(o, {}).get("objects", 0) for o in ops)
        names = ", ".join(f"{o:#04x}" for o in sorted(ops)[:8])
        print(f"\n  {arm:#010x}  opcode{'s' if len(ops) > 1 else ''} {names}"
              + (f" and {len(ops) - 8} more" if len(ops) > 8 else "")
              + (f"   -- {n} objects on level 0" if n else ""), file=out)
        print(f"      {sum(len(fn.blocks[b]) for b in blocks)} instructions in "
              f"{len(blocks)} blocks", file=out)
        if calls:
            print(f"      calls {', '.join(calls[:8])}"
                  + (f" and {len(calls) - 8} more" if len(calls) > 8 else ""),
                  file=out)
        if glob:
            print("      " + ", ".join(f"{m}s {nm}" if m != "addr"
                                       else f"points at {nm}"
                                       for nm, m in glob[:6]), file=out)


def document(path=None):
    path = path or os.path.join(ROOT, "OBJECTS.md")
    import io
    buf = io.StringIO()
    report(None, buf)
    cen = census()
    with open(path, "w") as fh:
        p = lambda *a: print(*a, file=fh)                           # noqa: E731
        p("# What an object does")
        p()
        p("Generated by `tools/objops.py --doc`. Do not edit it.")
        p()
        p("`object_interpreter` (`0x80047010`) is the third call in every frame")
        p("and the largest routine in the game. It walks all 396 slots of")
        p("`object_table`; for each one it publishes the record at `0x80198394`")
        p("and the type's row at `0x80198390`, and switches on **byte +4 of the")
        p("record** -- which is a copy of byte +0 of its type's row, the same")
        p("class `render_walk` draws on.")
        p()
        p("Doors, chests, levers, signs and the things that hurt you are one")
        p("machine with 236 opcodes.")
        p()
        p("## Level 0, by opcode")
        p()
        p("`object_type_table` is filled per level, so this is level 0 alone.")
        p()
        p("| opcode | objects | types |")
        p("| --- | --- | --- |")
        for c, v in sorted(cen.items(), key=lambda kv: -kv[1]["objects"]):
            ts = ", ".join(str(x) for x in sorted(v["types"])[:10])
            p(f"| `{c:#04x}` | {v['objects']} | {ts} |")
        p()
        p("## Every arm")
        p()
        p("```")
        p(buf.getvalue().rstrip())
        p("```")
    return path


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--doc":
        print("wrote " + os.path.relpath(document(), ROOT))
    elif a and a[0] == "--godot":
        got = export("out/godot")
        print("wrote " + os.path.relpath(got, ROOT) if got
              else "no snapshot to take the classes from")
    elif a and a[0] == "--census":
        for c, v in sorted(census().items(), key=lambda kv: -kv[1]["objects"]):
            print(f"  opcode {c:#04x}  {v['objects']:4d} objects  types "
                  + ", ".join(str(x) for x in sorted(v["types"])[:12]))
    elif a:
        report(int(a[0], 0))
    else:
        report()
