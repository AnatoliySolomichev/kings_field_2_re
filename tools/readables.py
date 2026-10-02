#!/usr/bin/env python3
"""Every object in the world you can read, and what it says.

    python3 tools/readables.py            all snapshots
    python3 tools/readables.py b          one of them

The path is short and entirely in `0x8005e2d0`, the object interaction handler:

    lhu   $a1, 0x26($s0)     the object's own facing
    addiu $a1, $a1, 0x800    turned around
    jal   0x80016a2c         is the player looking at it, within 0x155?
    beqz  $v0, skip
    lhu   $a1, 0x38($s0)     the object's +0x38, as a halfword
    ori   $a0, $zero, 6      archive 6 is ITEM.T
    addiu $a1, $a1, 0x96
    jal   load_entry         show ITEM.T[150 + it]

So the text an object shows is `ITEM.T[150 + u16 at +0x38]`, and 150 is exactly
where the signs and nameplates start in our index of that archive. Before that
the object's +0x3e must not be 0, and the facing is asked only while its +0x3d
is 0 (FORMATS.md, "How it is shown"; the fade and the page are below).

`+0x38` is part of the union every object class reads differently, so the index
only means anything for the classes that read. **Type 299 is the readable one**
-- 13 of them on level 0, 4 on level 4 -- with types 159, 314 and 317 also
landing in range. Everything else puts values there that run past the end of
the archive, which is how you can tell them apart.

Placement has since been decoded off the disc (`tools/placement.py`), so this
covers **all 28 levels** with no emulator involved. Pass a snapshot name to read
the live table instead, which shows what the player has already changed.
"""
import glob
import os
import struct
import sys

sys.path.insert(0, "tools")
import objects as O                                                  # noqa: E402

TEXT_BASE = 0x96          # ITEM.T entry 150, where the signs begin
READABLE = 299            # the type that reads as a sign or a plaque
READ_CLASSES = (0x0D, 0x14)   # the two classes object_interact's .L38 reads

# How the game shows it. `object_interact` (.L38) asks that the object's
# +0x3e is not 0 and, unless +0x3d is, that the player faces it within 0x155
# (facing_test(facing, yaw + 0x800, 0x155)); then `load_entry(6, 0x96 +
# u16 +0x38)` (0x800441d4):
#
#   the entry read; ClearImage of VRAM (960, 256, 64, 240) to 0; its TIMs
#   loaded where each says -- the words land somewhere on that 4-bit page,
#   under the CLUT the TIM brings to (96, 480); the screen kept
#   load_wait_screen(0, 0xc) -- each frame: the kept screen darkened to
#   0x80 - s2 / 2, the page's (0,0)-(255,208) drawn at (32, 32) twice, a
#   subtraction one texel down and right and an addition, both at s2; then
#   s2 += 0xc, and while it is 1..0x77 the pad: up first, then a press ends
#   it early. Ten frames, s2 = 0 .. 0x6c
#   if no press came: wait for one -- the pad up, then any -- with nothing
#   drawn, and fade out from 0x50; else fade out from where it got to
#   load_wait_screen(s2, -0xc): seven frames from 0x50, down to 8
#
# The page is the same palette as the banners', STP on every colour.
PAGE_X, PAGE_Y, PAGE_W, PAGE_H = 960, 256, 256, 208
FADE_IN, FADE_OUT_FROM = 0xC, 0x50


ARCHIVE_FILES = {6: "ITEM.T", 7: "TALK.T"}     # load_entry's archive numbers


def archive(number):
    """The TArc load_entry reads for archive `number` -- 6 ITEM.T, 7 TALK.T."""
    from tarc import TArc
    return TArc(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                             "extract", "CD", "COM", ARCHIVE_FILES[number]))


def page(n, arc=None):
    """RGBA rows, 256 x 208, of ITEM.T[150 + n] as load_entry lays it in VRAM."""
    return page_entry(arc or archive(6), TEXT_BASE + n)


def page_entry(arc, entry):
    """RGBA rows, 256 x 208, of entry `entry` of `arc` as load_entry lays it in
    VRAM: the cleared page with every TIM of the entry loaded at its own place."""
    raw = arc.raw(entry)
    words, clut, off = {}, [0] * 16, 0
    while raw and off + 8 <= len(raw):
        magic, flags = struct.unpack_from("<II", raw, off)
        if magic != 0x10:
            break
        p = off + 8
        if flags & 8:
            ln, x, y, w, h = struct.unpack_from("<I4H", raw, p)
            clut = list(struct.unpack_from(f"<{w * h}H", raw, p + 12))
            p += ln
        ln, x, y, w, h = struct.unpack_from("<I4H", raw, p)
        for row in range(h):
            for col in range(w):
                words[(x + col, y + row)] = struct.unpack_from(
                    "<H", raw, p + 12 + 2 * (row * w + col))[0]
        off = p + ln
    out = []
    for v in range(PAGE_H):
        for u in range(PAGE_W):
            word = words.get((PAGE_X + (u >> 2), PAGE_Y + v), 0)
            c = clut[(word >> (4 * (u & 3))) & 0xF]
            if c == 0:
                out.append((0, 0, 0, 0))
                continue
            r, g, b = (c & 31) << 3, ((c >> 5) & 31) << 3, ((c >> 10) & 31) << 3
            out.append((r | r >> 5, g | g >> 5, b | b >> 5, 255))
    return out


def wait_screen(s2, step, press):
    """load_wait_screen (0x80043bb8): [s2 of each frame drawn] and what it
    returns -- s2 after a press, else -1 or -2 by whether the pad went up.
    `press(i)` is the pad on the i-th check: 0 up, else a button."""
    frames, armed, i = [], -1, 0
    while True:
        frames.append(s2)
        s2 += step
        if not 0 <= s2 - 1 < 0x77:
            return frames, armed
        pad = press(i)
        i += 1
        if armed == -1:
            if pad == 0:
                armed = -2
        elif pad != 0:
            return frames, s2


def show(pad):
    """load_entry's frames for a pad history: [s2 drawn], fade in to fade out.
    `pad(i)` is the pad at the i-th look, across the whole of it."""
    looks = [0]

    def press(_i):
        v = pad(looks[0])
        looks[0] += 1
        return v
    frames, s0 = wait_screen(0, FADE_IN, press)
    if s0 < 0:
        while True:
            v = press(0)
            if s0 == -1:
                if v == 0:
                    s0 = -2
            elif v != 0:
                s0 = FADE_OUT_FROM
                break
    out, _ = wait_screen(s0, -FADE_IN, lambda _i: 0)
    return frames, out


def export(out_dir, lv=0):
    """read/<n>.png for every page level `lv`'s readable objects show, and
    readcheck.json: load_entry's frames for two pad histories, for selftest."""
    import json
    import objload
    import tim
    ld = objload.Load(lv)
    want = sorted({struct.unpack_from("<H", r["tail"], 0)[0]
                   for r in ld.recs.values() if r["cls"] in READ_CLASSES})
    os.makedirs(os.path.join(out_dir, "read"), exist_ok=True)
    for n in want:
        if n == 0xFFFF or TEXT_BASE + n >= 970:
            continue
        tim.write_png(os.path.join(out_dir, "read", f"{n}.png"), PAGE_W, PAGE_H, page(n))
    cases = []
    # USE still down at the start, up on the third look, a press on the
    # twentieth; and a press during the fade in
    for history in ([1, 1, 0] + [0] * 16 + [1], [1, 0, 0, 0, 1]):
        def pad(i, h=history):
            return h[i] if i < len(h) else h[-1]
        a, b = show(pad)
        cases.append({"pad": history, "in": a, "out": b})
    path = os.path.join(out_dir, "readcheck.json")
    with open(path, "w") as fh:
        json.dump({"cases": cases}, fh, separators=(",", ":"))
    return path


def readables(buf, names=None):
    """[(object, text index, text)] for everything with a usable text index."""
    names = names if names is not None else O.names()
    out = []
    for o in O.table(buf):
        off = o["addr"] - O.RAM_BASE
        f38 = struct.unpack_from("<H", buf, off + 0x38)[0]
        if f38 == 0xFFFF:
            continue
        entry = TEXT_BASE + f38
        if entry >= 970:                  # past the end of ITEM.T, so not text
            continue
        out.append((o, entry, names.get(entry, "")))
    return out


def split(found):
    """(confirmed, candidates) -- type 299 is the readable one, the rest are not.

    Accepting anything whose index happens to resolve pulls in noise: four
    type-297 objects sitting in a row at the edge of level 4 all carry 0 there
    and would each read as the inn sign. Type is the honest filter.
    """
    sure = [t for t in found if t[0]["id"] == READABLE]
    maybe = [t for t in found if t[0]["id"] != READABLE and t[2]]
    return sure, maybe


def from_disc(names=None):
    """[(level, cell x, cell z, ITEM.T entry, text)] for every readable in the game."""
    import placement
    names = names if names is not None else O.names()
    out = []
    for lv in range(28):
        for o in placement.objects(lv):
            if o["type"] != READABLE or o["text"] is None:
                continue
            cx, cz, entry = o["cx"], o["cz"], TEXT_BASE + o["text"]
            if entry >= 970:
                continue
            out.append((lv, cx, cz, entry, names.get(entry, "")))
    return out


if __name__ == "__main__":
    if not sys.argv[1:]:
        names = O.names()
        rows = from_disc(names)
        print(f"{len(rows)} readable objects across all 28 levels\n")
        for lv, cx, cz, entry, text in rows:
            print(f"  level {lv:2d} cell ({cx:2d},{cz:2d})  ITEM[{entry}]"
                  f"   {text[:56] if text else '(not decoded)'}")
        sys.exit(0)
    want = sys.argv[1:]
    names = O.names()
    for label in want:
        path = f"out/snap/{label}.ram"
        if not os.path.exists(path):
            continue
        buf = open(path, "rb").read()
        sure, maybe = split(readables(buf, names))
        if not sure and not maybe:
            continue
        print(f"=== {label} ===")
        for title, group in (("readable objects", sure), ("other types, unconfirmed", maybe)):
            if not group:
                continue
            print(f"  -- {title} --")
            for o, entry, text in sorted(group, key=lambda t: (t[0]["z"], t[0]["x"])):
                cx, cz = o["x"] // O.CELL, o["z"] // O.CELL
                print(f"    cell ({cx:2d},{cz:2d})  type {o['id']:3d}  ITEM[{entry}]"
                      f"   {text[:56] if text else '(not decoded)'}")
        print()
