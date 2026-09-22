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
with 236 opcodes. **Two of the 44 targets are not handlers at all**, and a
session with `emu/bp20.lua` armed is what made that obvious:

* `0x8004b4b4`, which 191 opcodes reach, is **a call into the level's own
  code** -- it loads `level_hooks` (`0x8018fae0`), takes its `+0x24` and
  `jalr`s it. So an object whose class has no handler of its own is handed to
  the level, which is the opposite of the "shared do-nothing tail" this tool
  called it at first.
* `0x8004b4d0` is the **loop's continue**, `$s2 += 0x44`. The two opcodes that
  point there, `0xe5` and `0xe9`, therefore do nothing at all -- which is what
  FORMATS.md already said about them from the drawing side, a chest closed and
  one other.

A breakpoint on `0x8004b4d0` fires for every object that finishes, not for the
two opcodes, which is exactly what the log showed.

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


TYPES_ENTRY, TYPES_OFFSET = 97, 4     # FDAT.T entry 97, past its length word


def type_rows(path=None):
    """The object type table, off the disc: 300 rows of 24 bytes.

    `FDAT.T` entry 97 opens with a length word of **7200 = 300 * 24** and the
    table follows it. All 300 rows are byte for byte what a level-0 RAM
    snapshot holds at `object_type_table`, so it is loaded whole and it is the
    same on every level -- there is nothing per-level about it.

    **300 is where `model_of_type` changes its mind too.** Below that type the
    model is `type + 0x100`; from 300 up the level is added, and from 300 up
    there is no row here either. The two facts are the same boundary seen from
    either side, and either one on its own reads like a coincidence.
    """
    import struct
    from tarc import TArc
    raw = TArc(path or os.path.join(ROOT, "extract", "CD", "COM",
                                    "FDAT.T")).raw(TYPES_ENTRY)
    n = struct.unpack_from("<I", raw, 0)[0] // TYPE_ROW
    return [raw[TYPES_OFFSET + TYPE_ROW * t:
                TYPES_OFFSET + TYPE_ROW * (t + 1)] for t in range(n)]


# What a type's 24-byte row holds. Only the fields that are established are
# named; the rest are left as offsets, because a guess in this table would read
# exactly like the three that are read.
ROW = """
+0   the behaviour opcode, and the render class -- the same byte
+1   0x00 on all 300
+2   0xff on all 300
+3   copied into the live record's +3 by load_object_placement
+6   u16, a size: 800, 900, 1000, 1200, 1350, 1400, 1500, 2000 -- the shapes
     the player's own radius (800) and body height (1700) come in
+8   u16, a second size
+0xa copied into the live record's +0x6a
+0x17  the byte object_set_present restores into the cell when the object goes
"""


def markers():
    """The types whose row is empty past +3, and which are therefore not
    things but **places**.

    A type with nothing after +3 has no size, no second size and nothing to
    copy into the live record, and every one of them carries an opcode in the
    trigger range. They have no model because they are not meant to be drawn:
    578 of the 707 placed objects in the game that `tools/tmd.py` cannot find a
    model for are these.
    """
    rows = type_rows()
    return {t: r[0] for t, r in enumerate(rows) if not any(r[3:])}


def modelless(out=sys.stdout):
    """Every placed object with no usable model, and why.

    This is the queue's fourth item, answered from the data: of 707, **578 are
    markers**, 76 are type 299 -- the volume that says an inscription can be
    read here -- and 42 carry a class, `0xe5` or `0xe9`, that means never
    drawn. Ten objects of type 298 and one past the end of the type table are
    what is left.
    """
    import collections
    import placement
    import tmd
    rows = type_rows()
    mk = markers()
    never = {0xE5, 0xE9}
    cache, acc, left, total = {}, collections.Counter(), collections.Counter(), 0
    for lv in range(28):
        for o in placement.objects(lv):
            t = o["type"]
            total += 1
            key = (t, lv)
            if key not in cache:
                try:
                    arch, e = tmd.model_of(t, lv)
                    cache[key] = bool(tmd.load(arch, e)[1])
                except Exception:
                    cache[key] = False
            if cache[key]:
                continue
            if t >= len(rows):
                acc["past the type table, type 300 or above"] += 1
            elif t in mk:
                acc["a marker: the row is empty past +3"] += 1
            elif rows[t][0] in never:
                acc["a class that means never drawn (0xe5, 0xe9)"] += 1
            elif t == 299:
                acc["type 299, the inscription volume"] += 1
            else:
                acc["still unexplained"] += 1
                left[t] += 1
    print(f"{total} placed objects; {sum(acc.values())} have no usable model",
          file=out)
    for k, v in acc.most_common():
        print(f"  {v:4d}  {k}", file=out)
    if left:
        print("  what is left, by type: "
              + ", ".join(f"{t} x{n}" for t, n in sorted(left.items())),
              file=out)
    return acc


def export(out_dir):
    """The class of every type, where the port can read it.

    Off the disc and for every level, not borrowed from a snapshot: the table
    is one block and the same everywhere.
    """
    rows = type_rows()
    out = os.path.join(out_dir, "objclass.json")
    with open(out, "w") as fh:
        json.dump({"_note": f"byte +0 of each row of the object type table -- "
                            f"FDAT.T entry {TYPES_ENTRY} at offset "
                            f"{TYPES_OFFSET}, {len(rows)} rows of {TYPE_ROW} "
                            "bytes. The behaviour opcode and the render class "
                            "are the same byte",
                   "types": len(rows),
                   "class": {str(t): r[0] for t, r in enumerate(rows)}}, fh,
                  separators=(",", ":"))
    return out


def census(levels=range(28)):
    """Which opcodes the game actually uses, over every level, from the disc.

    An object of type 300 or above has no row -- the table stops there -- and
    those are counted separately rather than read off the end of it, which is
    what an earlier pass did: it took whatever followed the table in RAM as
    three hundred more type rows and reported classes for types that have none.
    """
    import placement
    rows = type_rows()
    out = collections.defaultdict(lambda: {"objects": 0, "types": set(),
                                           "levels": set()})
    over = {"objects": 0, "types": set()}
    for lv in levels:
        for o in placement.objects(lv):
            t = o["type"]
            if t >= len(rows):
                over["objects"] += 1
                over["types"].add(t)
                continue
            c = rows[t][0]
            out[c]["objects"] += 1
            out[c]["types"].add(t)
            out[c]["levels"].add(lv)
    return dict(out), over


def report(op=None, out=sys.stdout):
    w = walk()
    fn = w.funcs[INTERP]
    t, tb = table(w)
    grouped = arms(w)
    stops = set(t.values())
    shared = max(grouped, key=lambda a: len(grouped[a]))
    # 0x8004b4b4 is the one 191 opcodes reach, and it is a call into the
    # level's hooks rather than a tail; 0x8004b4d0 is the loop's continue.
    CONTINUE = 0x8004B4D0
    cen, _over = census()
    rows = sorted(grouped.items(), key=lambda kv: min(kv[1]))
    print(f"{len(t)} opcodes through {len(grouped)} arms; "
          f"{len(grouped[shared])} of them reach {shared:#010x}, which is not "
          f"a handler but a call into the level's own code "
          f"(level_hooks+0x24); {len(grouped.get(CONTINUE, []))} reach "
          f"{CONTINUE:#010x}, which is the loop's continue and does nothing",
          file=out)
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
              + (f"   -- {n} objects in the game" if n else ""), file=out)
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
    cen, over = census()
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
        p("## Every placed object in the game, by opcode")
        p()
        p("The type table is one block on the disc -- `FDAT.T` entry 97 at")
        p("offset 4, 300 rows of 24 bytes -- and it is the same on every")
        p("level, so this is the whole game and not one level of it.")
        p()
        p(f"**{over['objects']} placed objects have a type of 300 or above**,")
        p("which is where the table stops, so they have no row and no opcode:")
        p("the same boundary `model_of_type` changes its mind at.")
        p()
        p("| opcode | objects | levels | types |")
        p("| --- | --- | --- | --- |")
        for c, v in sorted(cen.items(), key=lambda kv: -kv[1]["objects"]):
            ts = ", ".join(str(x) for x in sorted(v["types"])[:10])
            p(f"| `{c:#04x}` | {v['objects']} | {len(v['levels'])} | {ts} |")
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
    elif a and a[0] == "--types":
        print(ROW.strip())
        print()
        mk = markers()
        print(f"{len(mk)} of the 300 types are markers -- the row is empty "
              f"past +3:")
        import collections
        for op, ts in sorted(collections.Counter(mk.values()).items()):
            print(f"   opcode {op:#04x}: "
                  + ", ".join(str(t) for t in sorted(mk) if mk[t] == op))
        print()
        modelless()
    elif a and a[0] == "--census":
        cen, over = census()
        for c, v in sorted(cen.items(), key=lambda kv: -kv[1]["objects"]):
            print(f"  opcode {c:#04x}  {v['objects']:5d} objects on "
                  f"{len(v['levels']):2d} levels  types "
                  + ", ".join(str(x) for x in sorted(v["types"])[:10]))
        print(f"\n  {over['objects']} objects have a type of 300 or above, "
              f"past the end of the table: {len(over['types'])} distinct")
    elif a:
        report(int(a[0], 0))
    else:
        report()
