#!/usr/bin/env python3
"""The extra models a level places itself, and the flicker on them.

    python3 tools/props.py            every level, one line each
    python3 tools/props.py 0          level 0 in full
    python3 tools/props.py --check    against a RAM snapshot
    python3 tools/props.py --godot    write them out for the port

**Block 4 of `FDAT.T` entry `3n + 1`** is 2048 bytes, and `level_load` hands
it to `level_props_init` (`0x80043a08`), which unpacks **128 records of 16
bytes into 128 of 24** at `level_props` (`0x80182968`). `render_walk` then
walks that table every frame and draws each one with `draw_model_lit`.

The 16-byte record on the disc:

    +0   u16  the model, 0xffff ends the list. Bit 0x8000 picks the lit path
              -- `render_walk` adds 0x28 to `id & 0x7fff` for the model index
              -- and without it the draw is gated by `view_bits_at`
    +2   u8   copied to the live record's +3, and it is what the flicker is
              scaled by
    +3   u8   copied to +4
    +4   u8   copied to +2, and `render_walk` uses it as a draw flag mask
    +5   u8   the cell's Z
    +6   u8   the cell's X
    +10  s16  the Z offset inside the cell
    +12  s16  the X offset inside the cell
    +14  s16  added to the ground height under the point

and the live record it becomes:

    +0    u16  the model
    +2..4 the three bytes
    +5    u8   `rand() * record[+3] >> 15` -- rolled once at load, and
               `render_walk` adds 0x80 to it for the brightness it draws with
    +8    s32  x = (cell x << 11) + the offset
    +0xc  s32  y = `collide_at_cell(x, z)` + the record's +14
    +0x10 s32  z = (cell z << 11) + the offset

So a prop is placed by cell and offset like an object, but its height is
taken from the terrain at load rather than stored, and its brightness is a
single random roll. Torches and fires, in other words.

`world_shift` moves the live positions when the world does, which is what
says they are world-space and not per-cell.

**Where a prop's mesh lives is settled, and it is not `MO.T`.**
`draw_model_lit` takes an index into `model_table` (`0x801a92b0`), and
`render_walk` hands it `(id & 0x7fff) + 0x28`. 0x28 is 40, which is exactly
where the resident model bank starts: `FDAT.T` entry 97 block 10, 102900
bytes of length-prefixed models becoming `model_table[40..109]`. So a prop's
mesh is `bank[id & 0x7fff]`, and level 0's nine props are its first two.
`tools/modelbank.py` has it, with 58 of 58 pointers checked against a RAM
snapshot.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import entities                                                      # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BLOCK = 4                      # of entry 3n+1
SRC_ROW, LIVE_ROW, SLOTS = 16, 24, 128
LIVE = 0x80182968
CELL = 11                      # the cell shift: 1 << 11 is 2048
END = 0xFFFF
LIT_BIT = 0x8000
MODEL_BASE = 0x28              # render_walk adds this to id & 0x7fff


def records(lv):
    """[(index, dict)] for one level, stopping at the terminator."""
    raw, bs = entities.blocks(lv)
    if len(bs) <= BLOCK:
        return []
    o, n = bs[BLOCK]
    out = []
    for i in range(min(SLOTS, n // SRC_ROW)):
        r = raw[o + SRC_ROW * i:o + SRC_ROW * (i + 1)]
        ident = struct.unpack_from("<H", r, 0)[0]
        if ident == END:
            break
        out.append((i, {"id": ident, "lit": bool(ident & LIT_BIT),
                        "model": (ident & 0x7FFF) + MODEL_BASE,
                        "flicker": r[2], "b3": r[3], "mask": r[4],
                        "cell": (r[6], r[5]),
                        "x": (r[6] << CELL) + struct.unpack_from("<h", r, 12)[0],
                        "z": (r[5] << CELL) + struct.unpack_from("<h", r, 10)[0],
                        "dy": struct.unpack_from("<h", r, 14)[0]}))
    return out


def check(ram=None, level=0, out=sys.stdout):
    """The unpack, against a RAM snapshot of that level."""
    ram = ram or os.path.join(ROOT, "out", "ram.bin")
    if not os.path.exists(ram):
        print(f"  no RAM snapshot at {ram}; the props are unchecked", file=out)
        return True
    d = open(ram, "rb").read()
    base = LIVE - 0x80000000
    ok = bad = 0
    for i, r in records(level):
        live = d[base + LIVE_ROW * i:base + LIVE_ROW * (i + 1)]
        for name, got, want in (
                ("id", r["id"], struct.unpack_from("<H", live, 0)[0]),
                ("+2", r["mask"], live[2]),
                ("+3", r["flicker"], live[3]),
                ("+4", r["b3"], live[4]),
                ("x", r["x"], struct.unpack_from("<i", live, 8)[0]),
                ("z", r["z"], struct.unpack_from("<i", live, 0x10)[0])):
            if got == want:
                ok += 1
            else:
                bad += 1
                print(f"  record {i} {name}: disc {got}, RAM {want}", file=out)
    print(f"  {ok} of {ok + bad} fields of {len(records(level))} props match "
          f"RAM at {LIVE:#x}", file=out)
    return bad == 0


def export(out_dir, levels=range(28)):
    doc = {"_note": "block 4 of FDAT.T entry 3n+1, unpacked by level_props_init "
                    "(0x80043a08) into level_props (0x80182968): the extra "
                    "models a level places itself, with a brightness rolled "
                    "once from rand() and a height taken from the terrain",
           "model_base": MODEL_BASE, "levels": {}}
    for lv in levels:
        try:
            doc["levels"][str(lv)] = [r for _i, r in records(lv)]
        except Exception:
            continue
    path = os.path.join(out_dir, "props.json")
    with open(path, "w") as fh:
        json.dump(doc, fh, separators=(",", ":"))
    return path


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else None
    if a == "--check":
        sys.exit(0 if check() else 1)
    elif a == "--godot":
        print(export(os.path.join(ROOT, "godot")))
    elif a is not None:
        lv = int(a)
        for i, r in records(lv):
            print(f"  {i:3d} model {r['model']:5d}{'  lit' if r['lit'] else '     '}"
                  f"  cell {r['cell']}  ({r['x']}, {r['z']})  dy {r['dy']:+6d}"
                  f"  flicker {r['flicker']:3d} mask {r['mask']:#04x}")
    else:
        print(__doc__)
        check()
        print()
        tot = 0
        for lv in range(28):
            n = len(records(lv))
            tot += n
            if n:
                print(f"  level {lv:2d}: {n:3d} props")
        print(f"\n{tot} placed props in the game")
