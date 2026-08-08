#!/usr/bin/env python3
"""Read the live object table of the loaded level out of PlayStation RAM.

Found by diffing snapshots around an item pickup: the record whose id flipped
to 0xffff was the herb lying on the ground.

Record layout (68 bytes):
    +0x00  u16  0xffff marker (low byte varies on some entries)
    +0x02  u16  object id -- indexes ITEM.T, so it names itself
    +0x10  s32  world X
    +0x14  s32  world Y (height, negative is up)
    +0x18  s32  world Z

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


def s32(buf, off):
    return struct.unpack_from("<i", buf, off)[0]


def u16(buf, off):
    return struct.unpack_from("<H", buf, off)[0]


def valid(buf, off):
    if off < 0 or off + STRIDE > len(buf):
        return False
    if buf[off + 1] != 0xFF:                      # high byte of the marker
        return False
    x, y, z = s32(buf, off + 0x10), s32(buf, off + 0x14), s32(buf, off + 0x18)
    return (0 <= x < 80 * CELL and 0 <= z < 80 * CELL and -0x8000 < y < 0x8000)


def find_table(buf, lo=0x100000, hi=0x200000):
    """Locate the object table without a known anchor.

    Scans for the longest run of consecutive valid 68-byte records; a fresh
    game session puts the table at a different address.
    """
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


def table(buf, anchor):
    """Walk out from a known record until the layout stops making sense."""
    lo = anchor
    while valid(buf, lo - STRIDE):
        lo -= STRIDE
    hi = anchor
    while valid(buf, hi + STRIDE):
        hi += STRIDE
    out = []
    for off in range(lo, hi + STRIDE, STRIDE):
        script = u16(buf, off + 0x36)
        out.append({
            "addr": RAM_BASE + off,
            "id": u16(buf, off + 2),
            "x": s32(buf, off + 0x10),
            "y": s32(buf, off + 0x14),
            "z": s32(buf, off + 0x18),
            # +0x34..+0x3b is a per-type parameter block: doors keep their own
            # cell there, keyholes the key they want. For scenery the u16 at
            # +0x36 lands inside the level's 254-entry script table, so a value
            # here means the object does something when used. (unverified)
            "script": None if script == 0xFFFF else script,
            "params": buf[off + 0x34:off + 0x3C].hex(" "),
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
    anchor = int(sys.argv[2], 16) - RAM_BASE if len(sys.argv) > 2 else 0x192984
    buf = open(f"out/snap/{label}.ram", "rb").read()
    objs = [o for o in table(buf, anchor) if o["id"] != EMPTY]
    nm = names()
    print(f"{len(objs)} live objects in snapshot '{label}'")
    score = which_level(objs)
    print("level match:", ", ".join(f"{i}={p*100:.0f}%" for p, i in score[:4]))
    print()
    for o in objs:
        gx, gz = o["x"] // CELL, o["z"] // CELL
        print(f"  {o['addr']:08x} id={o['id']:4d} cell=({gx:2d},{gz:2d}) "
              f"pos=({o['x']:6d},{o['y']:7d},{o['z']:6d})  {nm.get(o['id'],'')}")
