#!/usr/bin/env python3
"""Read the live object table of the loaded level out of PlayStation RAM.

Found by diffing snapshots around an item pickup: the record whose id flipped
to 0xffff was the herb lying on the ground. The record boundary was off by four
bytes for a while -- the game's own code settled it, see FORMATS.md section 5.

Record layout (68 bytes), every offset below taken from code that touches it:

    +0x00  u8   visible/flags; the spawner writes 2
    +0x04  u8   0xff on a fresh record
    +0x06  u16  object id -- indexes MO.T for the model and the type table
    +0x08  u16  interaction state, driven by the use handler
    +0x14  s32  world X          (the spawner copies the player position
    +0x18  s32  world Y           at 0x801B25F0 into +0x14..+0x20)
    +0x1c  s32  world Z
    +0x24  s16  rotation X, Y, Z at +0x24 +0x26 +0x28; zeroed on spawn
    +0x2c  s16  scale X, Y, Z    at +0x2c +0x2e +0x30; 0x1000 is 1.0
    +0x36  s16  velocity, for whatever moves (0x8004b288)
    +0x38  u8   interaction gate; 0xff on spawn, other values pick a refusal
    +0x3a  u16  gold, but only for class 0x20 -- other classes reuse the bytes
    +0x3b  u8   index of another object, in the 0x86/0x88/0x8d branch
    +0x3d  u8   interaction parameters, checked as a pair
    +0x3e  u8   0 makes the handler skip the object; level data leaves 0xff
    +0x40  u16  index of another object

World units are 2048 per map cell, over the 80x80 grid in FDAT.T.
"""
import pickle
import struct
import sys

sys.path.insert(0, "tools")

RAM_BASE = 0x80000000
STRIDE = 0x44
CELL = 2048
EMPTY = 0xFFFF

# The array is a fixed global, not something that moves per session: the use
# handler at 0x8005dd10 forms it as CLASSES + 0x1f20 and indexes it by 0x44.
# Every snapshot we hold has it here.
TABLE = 0x80191A5C
# Per-type table, 24 bytes each, ending exactly where the object array starts,
# so it holds 0x1f20 / 24 = 332 types -- one more than the highest id we see.
CLASSES = 0x8018FB3C
NTYPES = 332
CLASS_GOLD = 0x20                             # only type 149 carries it
# The array is a fixed 396 slots, ending at 0x8019838c. Level 0 happens to fill
# the first 158 contiguously, which is what made walking until the records stop
# parsing look like it worked; level 4 has 209 live records with 196 freed slots
# mixed in among them, and a walk stops dead at the third one.
COUNT = 396
FREED = 0x00FF          # what the pickup handler writes into the id on removal


def s32(buf, off):
    return struct.unpack_from("<i", buf, off)[0]


def u16(buf, off):
    return struct.unpack_from("<H", buf, off)[0]


def valid(buf, off):
    if off < 0 or off + STRIDE > len(buf):
        return False
    if buf[off + 5] != 0xFF:                      # high byte of the marker
        return False
    x, y, z = s32(buf, off + 0x14), s32(buf, off + 0x18), s32(buf, off + 0x1C)
    return (0 <= x < 80 * CELL and 0 <= z < 80 * CELL and -0x8000 < y < 0x8000)


def obj_class(buf, oid):
    """Class byte of an object type, from the 24-byte-per-type table."""
    if not 0 <= oid < NTYPES:
        return None
    return buf[CLASSES - RAM_BASE + oid * 24 + 1]


def find_table(buf, lo=0x100000, hi=0x200000):
    """Locate the object table.

    TABLE is fixed, so that is the answer whenever it parses; the scan below is
    only kept as a fallback for a build or a state where it does not.
    """
    if valid(buf, TABLE - RAM_BASE):
        return TABLE - RAM_BASE
    best = (0, None)
    off = lo
    while off < hi - STRIDE:
        if not valid(buf, off):
            off += 4
            continue
        n, cur = 0, off
        while valid(buf, cur):
            n += 1
            cur += STRIDE
        if n > best[0]:
            best = (n, off)
        off = cur if cur > off else off + 4
    return best[1]


def slots(buf, base=None):
    """(slot index, offset) for every live record in the array.

    Free slots sit among the live ones rather than after them, so this walks
    all COUNT of them and filters, instead of stopping at the first gap.
    """
    base = (TABLE - RAM_BASE) if base is None else base
    for k in range(COUNT):
        off = base + k * STRIDE
        if off + STRIDE > len(buf):
            return
        if u16(buf, off + 6) in (EMPTY, FREED):
            continue
        if valid(buf, off):
            yield k, off


def table(buf, anchor=None):
    """Every live object record. `anchor` is the array base, not a member."""
    out = []
    for _, off in slots(buf, anchor):
        oid = u16(buf, off + 6)
        cls = obj_class(buf, oid)
        gate = buf[off + 0x38]
        out.append({
            "addr": RAM_BASE + off,
            "id": oid,
            "cls": cls,
            "x": s32(buf, off + 0x14),
            "y": s32(buf, off + 0x18),
            "z": s32(buf, off + 0x1C),
            # +0x38..+0x3f is a union the class byte selects between, so the
            # only field that can be read blind is the one whose class we know.
            "gold": u16(buf, off + 0x3A) if cls == CLASS_GOLD else None,
            # 0xff is the spawn default and the only value the use handler acts
            # on; scenery reuses the byte for its own purposes, which is why
            # trees carry round numbers here.
            "usable": gate == 0xFF,
            "f38": gate,
            # 0xff is what level data leaves here and 0 is what the spawner
            # writes; the handler at 0x8005e594 skips the object when it is 0.
            "f3e": buf[off + 0x3E],
            "params": buf[off + 0x38:off + 0x40].hex(" "),
        })
    return out


def names():
    """ITEM.T entry -> first line of its decoded text, when we have one."""
    out = {}
    try:
        d = pickle.load(open("out/text.pkl", "rb"))["ITEM"]
        for i, ents in d.items():
            for t, q in ents:
                if q < 0.15 and t.strip():
                    out[i] = t.split("\n")[0]
                    break
    except OSError:
        pass
    try:
        import propocr
        imgs = pickle.load(open("out/imgs.pkl", "rb"))
        idx = propocr.index(imgs)
        font = pickle.load(open("out/propfont_map.pkl", "rb"))
        for i, (w, h, b) in idx.items():
            t = propocr.decode(w, h, b, font)
            if t and "?" not in t:
                out.setdefault(i, t.split("\n")[0])
    except (OSError, ImportError):
        pass
    return out


HEIGHT_UNIT = 128          # world Y = -HEIGHT_UNIT * height byte


def which_level(objs, tol=200):
    """Identify the loaded level by the height relation.

    Walkability alone is far too weak -- the levels with no solid cells score
    100 % against anything. Matching each object's world Y against the terrain
    height byte under it is decisive: the real level scores far above the rest.
    """
    from maps import levels, cell, W, H
    best = []
    for idx, grid in levels():
        solid = sum(1 for y in range(H) for x in range(W)
                    if cell(grid, x, y, 8) == 255)
        if solid == 0:                    # degenerate grid, carries no terrain
            continue
        ok = 0
        for o in objs:
            gx, gz = o["x"] // CELL, o["z"] // CELL
            if not (0 <= gx < W and 0 <= gz < H):
                continue
            h = cell(grid, gx, gz, 6)
            if cell(grid, gx, gz, 8) != 255 and abs(h * HEIGHT_UNIT + o["y"]) <= tol:
                ok += 1
        best.append((ok / max(len(objs), 1), idx))
    best.sort(reverse=True)
    return best


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "b"
    anchor = int(sys.argv[2], 16) - RAM_BASE if len(sys.argv) > 2 else TABLE - RAM_BASE
    buf = open(f"out/snap/{label}.ram", "rb").read()
    objs = [o for o in table(buf, anchor) if o["id"] != EMPTY]
    nm = names()
    print(f"{len(objs)} live objects in snapshot '{label}'")
    score = which_level(objs)
    print("level match:", ", ".join(f"{i}={p*100:.0f}%" for p, i in score[:4]))
    print()
    for o in objs:
        gx, gz = o["x"] // CELL, o["z"] // CELL
        extra = f" gold={o['gold']}" if o["gold"] is not None else ""
        if o["usable"]:
            extra += " usable"
        print(f"  {o['addr']:08x} id={o['id']:4d} cls={o['cls']:#04x} "
              f"cell=({gx:2d},{gz:2d}) pos=({o['x']:6d},{o['y']:7d},{o['z']:6d})"
              f"{extra}  {nm.get(o['id'],'')}")
