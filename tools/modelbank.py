#!/usr/bin/env python3
"""The models that are always there: `FDAT.T` entry 97 block 10.

    python3 tools/modelbank.py            what is in it
    python3 tools/modelbank.py --check    against a RAM snapshot
    python3 tools/modelbank.py --godot    write the bank out for the port

`draw_model_lit` takes a model **index**, not a pointer: its last act before
the vertices is `model_table[index]` at `0x801a92b0`. `model_ptr`
(`0x800405e8`) is the same lookup with a residency test, and it says a model
below `0x68` is taken as-is while anything above has to be answered for.

Block 10 of entry 97 is where the low ones come from. It is **102900 bytes**,
`init_level_state` copies it to `0x800aedc4`, and its shape is:

    u32          70 -- how many models follow
    <model>[70]  each opening with its own u32 size

and they become `model_table[40]` through `model_table[109]`. Walking the
chain from the disc reproduces **58 of 58** of the pointers a RAM snapshot
holds (the other twelve read zero there, which is `model_ptr`'s residency
answer rather than a gap in the chain), and the walk consumes 102900 of
102900 bytes — it ends exactly where the block does.

That settles where a **prop's** mesh lives. `render_walk` hands
`draw_model_lit` the index `(id & 0x7fff) + 0x28` for each record of
`level_props`, and 0x28 is 40 — the first model of this bank. So a prop's
model is `bank[id & 0x7fff]`, and level 0's nine props are its first two.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tarc import TArc                                                # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FDAT = os.path.join(ROOT, "extract", "CD", "COM", "FDAT.T")
ENTRY, BLOCK = 97, 10
LIVE_BASE = 0x800AEDC4         # where init_level_state copies it
TABLE = 0x801A92B0             # model_table
FIRST = 40                     # the index the bank starts at, and 0x28


def block(path=FDAT):
    """(raw entry, offset of block 10, its length)."""
    raw = TArc(path).raw(ENTRY)
    o, n = 0, 0
    while o + 4 <= len(raw):
        sz = struct.unpack_from("<I", raw, o)[0]
        if n == BLOCK:
            return raw, o + 4, sz
        if sz == 0:
            break
        o += 4 + sz
        n += 1
    return raw, None, 0


def models(path=FDAT):
    """[(index, offset in the block, size)] for every model in the bank."""
    raw, at, n = block(path)
    if at is None:
        return []
    count = struct.unpack_from("<I", raw, at)[0]
    out, off = [], 4
    for k in range(count):
        if off + 4 > n:
            break
        size = struct.unpack_from("<I", raw, at + off)[0]
        if size == 0 or off + size > n:
            break
        out.append((FIRST + k, off, size))
        off += size
    return out


def check(ram=None, out=sys.stdout):
    ram = ram or os.path.join(ROOT, "out", "ram.bin")
    if not os.path.exists(ram):
        print(f"  no RAM snapshot at {ram}; the model bank is unchecked", file=out)
        return True
    d = open(ram, "rb").read()
    ok = bad = absent = 0
    for idx, off, _size in models():
        want = LIVE_BASE + off
        got = struct.unpack_from("<I", d, TABLE - 0x80000000 + 4 * idx)[0]
        if got == 0:
            absent += 1
        elif got == want:
            ok += 1
        else:
            bad += 1
            if bad <= 2:
                print(f"  model {idx}: chain {want:#x}, table {got:#x}", file=out)
    raw, at, n = block()
    used = models()[-1][1] + models()[-1][2] if models() else 0
    print(f"  {ok} of {ok + bad} model pointers match RAM at {TABLE:#x} "
          f"({absent} not resident), and the chain uses {used} of {n} bytes",
          file=out)
    return bad == 0 and used == n


def export(out_dir):
    ms = models()
    path = os.path.join(out_dir, "modelbank.json")
    with open(path, "w") as fh:
        json.dump({"_note": "FDAT.T entry 97 block 10: a count word then that "
                            "many length-prefixed models, which become "
                            "model_table[40..] -- the models that are resident "
                            "whatever level is loaded. A prop's mesh is "
                            "bank[id & 0x7fff]",
                   "first_index": FIRST, "count": len(ms),
                   "models": [{"index": i, "at": o, "size": s} for i, o, s in ms]},
                  fh, separators=(",", ":"))
    return path


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else None
    if a == "--check":
        sys.exit(0 if check() else 1)
    elif a == "--godot":
        print(export(os.path.join(ROOT, "godot")))
    else:
        print(__doc__)
        check()
        ms = models()
        print(f"\n{len(ms)} models, indices {ms[0][0]}..{ms[-1][0]}\n")
        for i, o, s in ms[:12]:
            print(f"  model {i:3d}  at {o:6d}  {s:6d} bytes")
        print("  ...")
