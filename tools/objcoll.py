#!/usr/bin/env python3
"""What makes an object solid, and the game's own answers to it.

    python3 tools/objcoll.py            every type that can stop you
    python3 tools/objcoll.py --check    the model against what was recorded
    python3 tools/objcoll.py --godot    write the shapes out for the port

`collide_query`'s mask bit `0x20` means "test the objects", and that branch is
`object_collide` (`0x80045ac8`). It walks all 396 slots -- skipping a type of
`0xff`, a byte `+0` of zero and whichever slot is `current_object` -- and
tests what is left **two ways**:

    radius = object_type_table[type] + 4                     a u16
    if object_type_table[type] + 3 has bit 0x10:
        radius = radius * object[+0x38] // 128               the object's own scale

    radius  > 0                  -> a circle of that radius, through in_range
    radius == 0 and object[+3] has bit 4
                                 -> an oriented rectangle, half-extents from
                                    the row's +0xe and +0x10, turned by the
                                    angle at object[+0x26], through
                                    in_oriented_rect (0x80016d3c)
    otherwise                    -> the object does not stop you

So an object's collision is **in its type's row, not in its placement
record** -- which is why every pass that looked in the record found nothing.
The record carries the scale byte that stretches the shape and the angle that
turns it.

`player_horizontal` is the other half: it reads the slot `collide_query` left
at `collide_object` (`0x801e6490`), checks the object's byte `+3` for bit 4
again, and slides the player around using the angle at `object+0x26`.

**Checked against the game.** `emu/bp23.lua` sat where `player_horizontal`
picks the answer up and logged every touch while the player walked into
things: 401 lines, 13 distinct shapes, and the scaled radii come out exactly
-- 650 * 255 // 128 = 1294, 650 * 210 // 128 = 1066, 600 * 135 // 128 = 632,
350 * 255 // 128 = 697.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import objops                                                        # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCALE_BIT = 0x10               # in the type row's byte +3
RECT_BIT = 0x04                # in the object's own byte +3
RADIUS_AT = 4
RECT_AT = (0x0E, 0x10)
SCALE_SHIFT = 7                # the object's +0x38 is over 128


def u16(rec, off):
    return rec[off] | (rec[off + 1] << 8)


def shape(row, obj_scale=128, obj_flags=0):
    """(kind, a, b) -- `('circle', r, 0)`, `('rect', w, h)` or `('none', 0, 0)`."""
    r = u16(row, RADIUS_AT)
    if row[3] & SCALE_BIT:
        r = (r * obj_scale) >> SCALE_SHIFT
    if r:
        return ("circle", r, 0)
    if obj_flags & RECT_BIT:
        return ("rect", u16(row, RECT_AT[0]), u16(row, RECT_AT[1]))
    return ("none", 0, 0)


# What emu/bp23.lua recorded on 2026-09-24 while the player walked into things
# on level 0: the type, the row's byte +3 and radius, the object's scale byte
# and its byte +3, the rectangle in the row, and the radius the game came to.
RECORDED = [
    {"type": 314, "row3": 0x04, "radius": 0, "scale": 255, "expect_radius": 0, "rect": [700, 20], "obj3": 0x84, "times": 48},
    {"type": 308, "row3": 0x04, "radius": 0, "scale": 255, "expect_radius": 0, "rect": [250, 200], "obj3": 0x84, "times": 31},
    {"type": 325, "row3": 0x50, "radius": 650, "scale": 210, "expect_radius": 1066, "rect": [0, 0], "obj3": 0xd0, "times": 13},
    {"type": 324, "row3": 0x50, "radius": 350, "scale": 255, "expect_radius": 697, "rect": [0, 0], "obj3": 0xd0, "times": 4},
    {"type": 301, "row3": 0x04, "radius": 0, "scale": 255, "expect_radius": 0, "rect": [350, 650], "obj3": 0x84, "times": 29},
    {"type": 326, "row3": 0x50, "radius": 600, "scale": 135, "expect_radius": 632, "rect": [0, 0], "obj3": 0xd0, "times": 11},
    {"type": 253, "row3": 0x00, "radius": 128, "scale": 255, "expect_radius": 128, "rect": [0, 0], "obj3": 0x80, "times": 5},
    {"type": 325, "row3": 0x50, "radius": 650, "scale": 255, "expect_radius": 1294, "rect": [0, 0], "obj3": 0xd0, "times": 48},
    {"type": 212, "row3": 0x00, "radius": 450, "scale": 255, "expect_radius": 450, "rect": [0, 0], "obj3": 0x80, "times": 25},
    {"type": 155, "row3": 0x04, "radius": 0, "scale": 255, "expect_radius": 0, "rect": [130, 330], "obj3": 0x84, "times": 89},
    {"type": 257, "row3": 0x04, "radius": 0, "scale": 255, "expect_radius": 0, "rect": [200, 300], "obj3": 0x84, "times": 56},
    {"type": 257, "row3": 0x04, "radius": 0, "scale": 141, "expect_radius": 0, "rect": [200, 300], "obj3": 0x84, "times": 41},
    {"type": 257, "row3": 0x04, "radius": 0, "scale": 141, "expect_radius": 0, "rect": [200, 300], "obj3": 0x04, "times": 1}
]


def check(out=sys.stdout):
    ok = bad = 0
    for c in RECORDED:
        row = bytearray(24)
        row[3] = c["row3"]
        row[RADIUS_AT] = c["radius"] & 0xFF
        row[RADIUS_AT + 1] = c["radius"] >> 8
        for at, v in zip(RECT_AT, c["rect"]):
            row[at] = v & 0xFF
            row[at + 1] = v >> 8
        kind, a, b = shape(row, c["scale"], c["obj3"])
        want_kind = "circle" if c["expect_radius"] else (
            "rect" if c["obj3"] & RECT_BIT else "none")
        want = (want_kind, c["expect_radius"] or (c["rect"][0] if want_kind == "rect" else 0),
                c["rect"][1] if want_kind == "rect" else 0)
        if (kind, a, b) == want:
            ok += c["times"]
        else:
            bad += c["times"]
            print(f"  type {c['type']}: model {kind} {a},{b}, game {want}", file=out)
    print(f"  {ok} of {ok + bad} recorded touches reproduced "
          f"({len(RECORDED)} distinct shapes)", file=out)
    return bad == 0


def solid(level=0):
    """[(type, kind, a, b)] for every type on a level that can stop you.

    The object's own byte `+3` is a copy of the row's, which
    `load_object_placement` makes and `object_set_present` then sets bit
    `0x80` in: across the 401 recorded touches `obj+3 == row+3 | 0x80` holds
    400 times, and the one that does not has the `0x80` clear -- an object
    that was not present at that instant. So both the scale bit and the rectangle bit are properties of
    the **type**, and this question has a per-type answer.

    An object's own `+0x38` still stretches a circle, so the radius here is
    the unscaled one -- what the type is worth at scale 128.
    """
    rows = objops.type_rows(level=level)
    out = []
    for t, row in enumerate(rows):
        kind, a, b = shape(row, 128, row[3])
        if kind == "rect" and not (0 < a < 8000 and 0 < b < 8000):
            continue                  # +0xe and +0x10 are not extents here
        if kind != "none":
            out.append((t, kind, a, b))
    return out


def export(out_dir, levels=range(28)):
    doc = {"_note": "object_collide (0x80045ac8): an object's collision shape "
                    "comes from its type row -- a circle of the u16 at +4, "
                    "scaled by the object's byte +0x38 over 128 when the row's "
                    "byte +3 has bit 0x10; or, when that radius is zero and "
                    "the object's byte +3 has bit 4, an oriented rectangle "
                    "with half-extents at +0xe and +0x10",
           "scale_bit": SCALE_BIT, "rect_bit": RECT_BIT,
           "levels": {}}
    for lv in levels:
        try:
            doc["levels"][str(lv)] = [
                {"type": t, "kind": k, "a": a, "b": b} for t, k, a, b in solid(lv)]
        except Exception:
            continue
    doc["recorded"] = RECORDED
    path = os.path.join(out_dir, "objcoll.json")
    with open(path, "w") as fh:
        json.dump(doc, fh, separators=(",", ":"))
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
        print()
        for lv in (0,):
            s = solid(lv)
            circles = [x for x in s if x[1] == "circle"]
            rects = [x for x in s if x[1] == "rect"]
            print(f"level {lv}: of 332 types, {len(circles)} stop you as a "
                  f"circle and {len(rects)} as an oriented rectangle")
            for t, k, x, y in s[:24]:
                print(f"   type {t:3d}  {k:6s} {x}" + (f" x {y}" if k == "rect" else ""))
