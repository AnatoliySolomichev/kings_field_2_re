#!/usr/bin/env python3
"""The object table and the level grid as `load_object_placement` leaves them.

    python3 tools/objload.py 0            what the loader makes of level 0
    python3 tools/objload.py --check      against every snapshot that has a level

`load_object_placement` (`0x80044d9c`, 843 instructions) is what turns the
level's 350 placement records into `object_table`. It was named for two of its
stores and read for none of the rest, so four things the port needs were being
**borrowed from a level-0 RAM snapshot** instead: each object's three angles,
its scale, whether it is drawn, and -- by way of the grid -- the walls a door
stands in. This transcribes it, so they come off the disc for every level.

The per-record part, read off the listing:

    +0x04  0xff, then the class arm's opcode      +0x06  the type (0xff: skip)
    +0x00  the placement's byte 0 (always 2)      +0x03  type_row[+3], the flags
    +0x01  0x80   +0x02  0, | 0x80 on flag 0x20   +0x05  0xff
    +0x0c  type_row[+8], or type_row[+8] * p[+0x10] >> 7 on flag 0x10
    +0x0e  type_row[+0xa]                         +0x08 +0x0a +0x10  0
    +0x14  p[+2] << 11 + s16 p[+0xa]              +0x1c  p[+1] << 11 + s16 p[+8]
    +0x18  s16 p[+0xc] - grid[cell, layer].height << 7
    +0x24 +0x26 +0x28   0, -p[+6] & 0xfff, 0      the angles
    +0x2c +0x2e +0x30   0x1000 each, or p[+0x10] << 5 on flag 0x10
    +0x38..+0x3f  p[+0x10..+0x17]                 +0x40..+0x43  0xff

and then a 256-arm switch on `type_row[+0]`, the class (`0x80011c54`).

**The angles.** Two arms, class `0x0d` always and class `0x40` unless
`type_row[+1]` is `0x20`, set each of the three from `p[+0x12..+0x14] << 6`,
skipping a byte of `0xff`. That is the "field conditional on something not yet
found" `tools/level3d.py` recorded: the something is the class. Checked: **347
of 347 objects on level 0 and 200 of 200 on level 4** have exactly the angles
the snapshot has.

**The scale is not only a switch.** On flag `0x10` it is `p[+0x10] << 5`, so
`0x80` is 1.0 -- the trees, types 324 to 326, once put down as graves. It is
zeroed by `object_set_present(r, 0, type_row[+0x17])` in classes `0x07`,
`0x51` and `0x52` when a byte says so, and
**unconditionally by the door arms** -- classes `0x03`, `0x04`, `0x05`, `0x54`
and `0x57` -- because a door is not drawn as a model at all: those arms stamp
its walls and tiles into the grid, and the grid draws it.

**Five arms write the grid**, which is why the level every build but 0 drew
had no doors in it:

* `grid_mark` (`0x80033c4c`, named `grid_query_area` until now; it queries
  nothing) adds 4 to byte +2 of every cell within `r + 0x800` of the object --
  an occupancy count, which the player and awake creatures also add to. Every
  object whose `type_row[+4]` is set, and classes 0x01, 0x1b, 0x00 and 0x02.
* `stamp_rect` (`0x800445b8`) copies a rectangle of layer-1 cells from
  elsewhere on the grid, turned by a quarter of the object's angle -- the rooms
  the game never lets you into are those rectangles. Classes 0x01, 0x1b, 0x00,
  0x02, 0x57 and 0x5a.
* `stamp_table` (`0x800443c8`) walks 10-byte entries in GAME.EXE, turning each
  cell offset by the angle through `game_cos`/`game_sin`, and writes shapes and
  tiles. Classes 0x03, 0x04, 0x05 and 0x54.
* `object_set_present`, absent: `type_row[+0x17]` into the cell's tile.
* Class 0x59 writes shape 0x75 into its own cell.

**And one thing the first frame does**, in `first_frame()`: opcode 9 hides the
object whose slot it carries and turns itself off, so a class-9 record is
never seen with its opcode and what it names is never seen drawn.

**What is not here.** 200 classes go to the level overlay's own hook
(`level_hooks + 0x20`), which is the level's code and not GAME.EXE's; those
records are left as the common part made them, and `hooked` lists them.
Classes 0x1f, 0x16 and 0x12 put a frame count into +0x40, and class 0xe3
tests the player's cell -- runtime, both, and left out of the check.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import movement                                                       # noqa: E402
import objops                                                         # noqa: E402
import placement                                                      # noqa: E402
from tarc import TArc                                                 # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FDAT = os.path.join(ROOT, "extract", "CD", "COM", "FDAT.T")
W, CELL = 80, 10
REC = 0x44
OBJECT_TABLE = 0x80191A5C
LEVEL_GRID = 0x801D4464
LEVEL = 0x8018FAD9
SLOTS = placement.SLOTS            # 350: the loader counts 0x15d down to -1

# `load_object_placement`'s class arms that zero the scale triple at 0x800454e0.
DOORS = (0x03, 0x04, 0x05, 0x54, 0x57)
# The tables `stamp_table` walks, per class, in GAME.EXE.
DOOR_TABLES = {0x03: (0x800828DC, 0x800828FC), 0x04: (0x800828DC, 0x8008291C),
               0x05: (0x8008293C, 0x8008295C)}
DOOR54_TABLE = 0x8008288C          # + 40 * (2 * type_row[+0xe] + (p[+0x16] & 1))
# The arms that store a frame count or read the player: not load-time values.
RUNTIME = (0x1F, 0x16, 0x12, 0xE3)


def grid_of(lv):
    """The grid off the disc, as `level_load` copies it: entry 3n, 64000 bytes."""
    raw = TArc(FDAT).raw(lv * 3)
    return bytearray(raw[4:4 + W * W * CELL])


def s8(v):
    return v - 0x100 if v > 0x7F else v


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v > 0x7FFF else v


class Load:
    """One run of the loader over one level: the records, the grid, the hooks."""

    def __init__(self, lv, grid=None, exe=None):
        import mips
        self.lv = lv
        self.exe = exe or mips.load("game")
        self.rows = objops.type_rows(level=lv)
        self.grid = bytearray(grid) if grid is not None else grid_of(lv)
        self.recs = {}
        self.hooked = []
        raw = TArc(FDAT).raw(lv * 3 + 1)
        seg = raw[placement.BLOCK:placement.BLOCK + SLOTS * placement.RECORD]
        for k in range(SLOTS):
            p = seg[k * placement.RECORD:(k + 1) * placement.RECORD]
            if len(p) == placement.RECORD:
                self._one(k, p)

    # -- the grid ---------------------------------------------------------

    def cell(self, cx, cz):
        return (cz * W + cx) * CELL

    def grid_mark(self, x, z, r, n):
        """`0x80033c4c`: add 4 * n to byte +2 of each cell within r + 0x800."""
        r += 0x800
        x0, z0 = (x - r) >> 11, (z - r) >> 11
        nx, nz = ((x + r) >> 11) - x0, ((z + r) >> 11) - z0
        for cz in range(z0, z0 + nz + 1):
            if not 0 <= cz < W:
                continue
            for cx in range(x0, x0 + nx + 1):
                if 0 <= cx < W:
                    o = self.cell(cx, cz) + 2
                    self.grid[o] = (self.grid[o] + 4 * n) & 0xFF

    def stamp_rect(self, b0, sx, sz, dx, dz, w, h, ang, mask):
        """`0x800445b8`: copy a w x h block of layer-1 cells, turned."""
        if 0xFF in (sx, dx, w):
            return
        rot = (-(s16(ang) >> 10)) & 3
        if rot == 0:
            step, row = 1, W
        elif rot == 1:
            step, row = -W, 1
            dz += w - 1
        elif rot == 2:
            step, row = -1, -W
            dx += w - 1
            dz += h - 1
        else:
            step, row = W, -1
            dx += h - 1
        src = self.cell(sx, sz)
        dst = self.cell(dx, dz)
        if not b0 & 2:
            return
        g = self.grid
        for _ in range(h):
            s, d = src, dst
            for _ in range(w):
                if mask & 1:
                    g[d + 5] = g[s + 5]
                if mask & 2:
                    g[d + 6] = g[s + 6]
                if mask & 4:
                    g[d + 7] = (g[d + 7] & 0xFC) | ((g[s + 7] + rot) & 3)
                if mask & 8:
                    g[d + 8] = g[s + 8]
                if mask & 0x10:
                    g[d + 9] = (g[s + 9] & 0x3F) | (g[d + 9] & 0xC0)
                if mask & 0x20:
                    g[d + 9] = (g[s + 9] & 0x40) | (g[d + 9] & 0xBF)
                if mask & 0x40:
                    g[d + 9] = (g[s + 9] & 0x80) | (g[d + 9] & 0x7F)
                s += CELL
                d += step * CELL
            src += W * CELL
            dst += row * CELL

    def stamp_table(self, b0, x, z, ang, table, sel, flag):
        """`0x800443c8`: 10-byte entries, each a turned cell offset and bytes."""
        up = 5 if b0 != 1 else 0
        low = 5 if up == 0 else 0
        c, s = movement.game_cos(s16(ang)), movement.game_sin(s16(ang))
        cx0, cz0 = x >> 11, z >> 11
        g = self.grid
        e = table
        while self.exe.bytes(e, 1)[0] != 0xFF:
            ent = self.exe.bytes(e, 10)
            ddx, ddz = s8(ent[8]), s8(ent[9])
            cx = ((ddx * c - ddz * s) >> 12) + cx0
            cz = ((ddz * c + ddx * s) >> 12) + cz0
            base = self.cell(cx, cz)
            hi, lo = base + up, base + low
            q = ent[sel * 4:sel * 4 + 4]
            if q[0] != 0xFC:
                g[hi + 3] = q[0]
            if q[1] != 0xFC:
                g[lo + 3] = q[1]
            if q[2] != 0xFF:
                g[hi] = q[2]
            if q[3] != 0xFF:
                g[lo] = q[3]
            if flag != 0xFF:
                g[hi + 4] = (g[hi + 4] & 0x7F) | flag
                g[lo + 4] = (g[lo + 4] & 0x7F) | flag
            e += 10

    def set_absent(self, r, restore):
        """`object_set_present(r, 0, restore)`: the cell's tile, and no scale."""
        o = self.cell(r["x"] >> 11, r["z"] >> 11) + (0 if r["b0"] == 1 else 5)
        self.grid[o] = restore
        r["scale"] = [0, 0, 0]

    # -- one record -------------------------------------------------------

    def _one(self, k, p):
        t = struct.unpack_from("<H", p, 4)[0]
        if t == 0xFFFF:
            t = 0xFF
        if t == 0xFF:
            return
        tr = self.rows[t]
        r = {"slot": k, "type": t, "op": 0xFF, "b0": p[0], "b1": 0x80, "b2": 0,
             "flags": tr[3], "b5": 0xFF, "cls": tr[0], "p": bytes(p)}
        r["angles"] = [0, (-struct.unpack_from("<H", p, 6)[0]) & 0xFFF, 0]
        r["scale"] = [0x1000] * 3
        if r["flags"] & 0x20:
            r["b2"] |= 0x80
        if r["flags"] & 0x10:
            s = p[0x10] << 5
            r["scale"] = [s, s, s]
        r["x"] = (p[2] << 11) + s16(struct.unpack_from("<H", p, 0xA)[0])
        r["z"] = (p[1] << 11) + s16(struct.unpack_from("<H", p, 8)[0])
        c = self.cell(p[2], p[1]) + (0 if p[0] == 1 else 5)
        r["y"] = s16(struct.unpack_from("<H", p, 0xC)[0]) - (self.grid[c + 1] << 7)
        tail = bytearray(p[0x10:0x18]) + b"\xff\xff\xff\xff"   # +0x38..+0x43
        r["tail"] = tail
        # The occupancy mark, before the switch.
        rad = struct.unpack_from("<H", tr, 4)[0]
        if rad:
            if r["flags"] & 0x10:
                rad = (rad * tail[0]) >> 7
            self.grid_mark(r["x"], r["z"], rad, 1)
        elif r["flags"] & 4:
            self.grid_mark(r["x"], r["z"],
                           max(struct.unpack_from("<H", tr, 0xE)[0],
                               struct.unpack_from("<H", tr, 0x10)[0]), 1)
        self.recs[k] = r
        self._arm(r, tr)

    def _arm(self, r, tr):
        cls, tail, ang = r["cls"], r["tail"], r["angles"][1]
        # tail[i] is record +0x38 + i, i.e. placement +0x10 + i
        if cls in (0x01, 0x1B, 0x00):
            if cls == 0x01:
                self.stamp_rect(r["b0"], tail[3] + 1, tail[4], tail[1], tail[2],
                                tr[0xD], tr[0xE], ang, 0x2D)
                r["op"] = 1
            else:
                self.stamp_rect(r["b0"], tail[3] + 3, tail[4], tail[1], tail[2],
                                3, 2, ang, 0x2D)
                r["op"] = 0x1B if cls == 0x1B else 0
            self.grid_mark(r["x"], r["z"], 0x5DC if cls == 0x01 else 0xBB8, 1)
        elif cls in DOOR_TABLES:
            r["op"], r["b1"] = cls, 0
            for tb in DOOR_TABLES[cls]:
                self.stamp_table(r["b0"], r["x"], r["z"], ang, tb, 0, 0xFF)
            r["scale"] = [0, 0, 0]
        elif cls == 0x02:
            r["op"], r["b1"] = 2, 0
            self.stamp_rect(r["b0"], tail[3] + tr[0xD] * 2, tail[4], tail[1],
                            tail[2], tr[0xD], tr[0xE], ang, 0x2D)
            self.grid_mark(r["x"], r["z"], 0x1130, 1)
        elif cls in (0x17, 0x06, 0x08, 0x0F, 0x11, 0x18, 0x1A, 0x19, 0x31,
                     0x13, 0xF0, 0xF2, 0xE9, 0xE5):
            r["op"] = cls
        elif cls == 0x07:
            r["op"], r["b1"] = 7, 0
            if tr[0xC] != 0xFF:
                self.set_absent(r, tr[0x17])
        elif cls == 0x09:
            r["op"] = 9
            tail[8] = r["b0"]
        elif cls == 0x15:
            r["op"] = 9
            tail[8] = r["b0"]
            r["b0"] = 0
        elif cls == 0x53:
            r["op"], r["b1"] = 0x53, 0
        elif cls == 0x54:
            r["b1"] = 0
            tail[8] = r["b0"]
            r["b0"] = 2
            r["op"] = 0x54
            tb = DOOR54_TABLE + 40 * (tr[0xE] * 2 + (tail[6] & 1))
            self.stamp_table(tail[8], r["x"], r["z"], ang, tb, 0, 0)
            r["scale"] = [0, 0, 0]
        elif cls == 0x5F:
            r["b0"] = 0
            r["op"] = 0x5F
        elif cls in (0x51, 0x52):
            r["b1"] = 0
            r["op"] = cls
            tail[8] = 0
            if (tail[3] if cls == 0x51 else tail[5]) != 0xFF:
                self.set_absent(r, tr[0x17])
        elif cls in (0x57, 0x5A):
            r["b1"] = 0
            r["b0"] = 2
            r["op"] = cls
            self.stamp_rect(r["b0"], tail[3] + tail[5], tail[4], tail[1], tail[2],
                            tail[5], tail[6], ang, 0x2D)
            if cls == 0x57:
                r["scale"] = [0, 0, 0]
        elif cls == 0x55:
            r["b1"] = 0
            r["op"] = 0x55
            tail[8] = 0
            a0, a1 = tail[5], tail[3]
            if a1 == a0:
                if tail[4] < tail[6]:
                    tail[10] = 0
                else:
                    tail[10] = 1
                    tail[4], tail[6] = tail[6], tail[4]
            elif tail[4] == tail[6]:
                if a1 < a0:
                    tail[10] = 2
                else:
                    tail[10] = 3
                    tail[3], tail[5] = tail[5], tail[3]
            tail[11] = 1
        elif cls == 0x56:
            r["op"] = 0x56
        elif cls in (0xE7, 0xEA, 0xE1, 0xE6):
            r["b0"] = 0
            r["op"] = cls
            tail[8] = 0
        elif cls == 0xEB:
            r["op"] = 0xEB
            tail[8] = 1
        elif cls == 0xE8:
            r["b1"] = 0x80
            r["op"] = 0xE8
            tail[8] = 0xFF
        elif cls == 0xE0:
            # A trigger: it stands at its cell's corner, and the fine offsets
            # become the far corner of the rectangle it watches.
            r["b0"] = 0
            r["op"] = 0xE0
            fx, fz, fy = (s16(struct.unpack_from("<H", r["p"], o)[0])
                          for o in (0xA, 8, 0xC))
            r["x"] -= fx
            r["z"] -= fz
            r["y"] -= fy
        elif cls in (0xE3, 0xE4):
            r["b0"] = 0
            r["op"] = cls
        elif cls == 0x1F:
            r["b0"] = 0
            r["op"] = 0x1F
        elif cls == 0x0D or (cls == 0x40 and tr[1] != 0x20):
            for i in range(3):
                if tail[2 + i] != 0xFF:
                    r["angles"][i] = tail[2 + i] << 6
            if cls == 0x40 and tail[1] == 0:
                r["op"] = 0x10
        elif cls == 0xE2:
            tail[8] = r["b0"]
            r["b0"] = 0
        elif cls in (0x0B, 0x14):
            r["b0"] = 0
        elif cls == 0x58:
            r["b1"] = 0
            r["op"] = 0x58
        elif cls == 0x59:
            r["op"] = 0x59
            r["b5"] = 0x32
            r["b2"] = (r["b2"] & 0xF8) | 5
            r["y"] += 0x100
            o = self.cell(r["x"] >> 11, r["z"] >> 11) + (0 if r["b0"] == 1 else 5)
            self.grid[o + 3] = 0x75
            tail[10] = r["b0"]
            r["b0"] = 0
        elif cls == 0x32:
            r["op"], r["b1"] = 0x32, 0
        elif cls == 0x30:
            r["op"] = 0x30
            r["b2"] = (r["b2"] & 0xF8) | 5
            r["y"] -= tail[4] << 8
        elif cls in (0x16, 0x12):
            r["op"] = cls
        elif cls in (0x21, 0xFF, 0x40):
            pass
        else:
            self.hooked.append(r["slot"])

    def first_frame(self):
        """What `object_interpreter` does to the table on its first pass.

        Opcode 9 (`0x80048c34`, 18 instructions) is one-shot: it takes the
        slot number in the u16 at +0x3a -- placement bytes +0x12 and +0x13 --
        clears that object's +0 and +0x38, which hides it, and sets its own
        opcode to 0xff. So every class-9 record is 0xff by the time anything
        can look, and what it named is not drawn: 24 of 24 on level 0 and 52
        of 52 on level 4 read 0xff in the snapshots, and the objects they name
        -- items, class 0x40 -- read +0 = 0.
        """
        for k in sorted(self.recs):
            r = self.recs[k]
            if r["op"] != 9:
                continue
            t = struct.unpack_from("<H", r["tail"], 2)[0]
            if t != 0xFFFF and t in self.recs:
                self.recs[t]["b0"] = 0
                self.recs[t]["tail"][0] = 0
            r["op"] = 0xFF
        return self

    def drawn(self, r):
        """Would `render_walk` draw this record, the view aside?

        It skips a type of 0xff and the opcodes 0xe9 and 0xe5, has paths of its
        own for 0x1f, 0xf0 and 0xf2, and otherwise draws when the cell's
        visibility byte ANDs non-zero with record +0 -- or when flag 8 says
        draw regardless. Every visible cell's byte carries 2, which a placed
        record's +0 is, so the view aside it comes down to +0 or flag 8. And a
        scale of zero draws nothing.
        """
        if r["op"] in (0xE9, 0xE5, 0x1F, 0xF0, 0xF2):
            return False
        if not (r["b0"] or r["flags"] & 8):
            return False
        return any(r["scale"])


def snapshots():
    """(path, level) for every RAM snapshot that has a level loaded."""
    d = os.path.join(ROOT, "out", "snap")
    out = []
    if not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d)):
        if not f.endswith(".ram"):
            continue
        ram = open(os.path.join(d, f), "rb").read()
        tid = struct.unpack_from("<H", ram, (OBJECT_TABLE & 0x1FFFFF) + 6)[0]
        if tid == 0:                          # the object table was never filled
            continue
        out.append((os.path.join(d, f), ram[LEVEL & 0x1FFFFF]))
    return out


def check(path, lv, verbose=False):
    """Field by field against one snapshot; returns (label, agree, total)."""
    ram = open(path, "rb").read()
    L = Load(lv).first_frame()
    base = OBJECT_TABLE & 0x1FFFFF
    tally = {}
    bad = []

    def see(name, ok, what):
        a, n = tally.get(name, (0, 0))
        tally[name] = (a + ok, n + 1)
        if not ok:
            bad.append((name, what))

    for k, r in sorted(L.recs.items()):
        s = ram[base + k * REC:base + (k + 1) * REC]
        if struct.unpack_from("<H", s, 6)[0] != r["type"]:
            see("type", False, (k, r["type"]))
            continue
        see("type", True, None)
        see("angles", [x & 0xFFF for x in struct.unpack_from("<3h", s, 0x24)]
            == r["angles"], (k, r["type"], hex(r["cls"])))
        see("scale", list(struct.unpack_from("<3h", s, 0x2C)) == r["scale"],
            (k, r["type"], hex(r["cls"]), r["scale"][0],
             struct.unpack_from("<h", s, 0x2C)[0]))
        see("position", struct.unpack_from("<3i", s, 0x14)
            == (r["x"], r["y"], r["z"]), (k, r["type"], hex(r["cls"])))
        if k in L.hooked or r["cls"] in RUNTIME:
            continue
        see("opcode +4", s[4] == r["op"], (k, r["type"], hex(r["cls"]),
                                           hex(r["op"]), hex(s[4])))
        see("byte +0", s[0] & 0x7F == r["b0"], (k, r["type"], hex(r["cls"]),
                                                r["b0"], s[0]))
        see("flags +3", s[3] & 0x7F == r["flags"] & 0x7F,
            (k, r["type"], hex(r["cls"])))
    out = [(f"{name}", a, n) for name, (a, n) in tally.items()]
    if verbose:
        for b in bad[:40]:
            print("    ", *b)
    return L, out


def grid_check(path, lv):
    """The loader's grid against the snapshot's, field by field.

    Field 2 is left out of the total: the player and every awake creature add
    to it too, so it is compared only where no object touched it.
    """
    ram = open(path, "rb").read()
    live = ram[LEVEL_GRID & 0x1FFFFF:(LEVEL_GRID & 0x1FFFFF) + W * W * CELL]
    disc = grid_of(lv)
    L = Load(lv)
    before = sum(1 for i in range(len(live)) if live[i] != disc[i] and i % CELL != 2)
    after = sum(1 for i in range(len(live)) if live[i] != L.grid[i] and i % CELL != 2)
    return before, after, L


def main():
    args = sys.argv[1:]
    if not args or args[0] == "--check":
        # The snapshots that were taken before anything on the level had been
        # opened are the ones a load-time model can be held to exactly.
        total = {}
        for path, lv in snapshots():
            L, rows = check(path, lv, verbose="-v" in args)
            before, after, _ = grid_check(path, lv)
            print(f"{os.path.basename(path)}  level {lv}: " + ", ".join(
                f"{name} {a}/{n}" for name, a, n in rows)
                + f"; grid bytes differing from the disc {before}, "
                  f"from the loader {after}; {len(L.hooked)} left to the level's hook")
            for name, a, n in rows:
                ta, tn = total.get(name, (0, 0))
                total[name] = (ta + a, tn + n)
            ta, tn = total.get("grid", (0, 0))
            total["grid"] = (ta + (after == 0), tn + 1)
        print("over every snapshot: " + ", ".join(
            f"{name} {a} of {n}" for name, (a, n) in total.items()))
        return
    lv = int(args[0])
    L = Load(lv).first_frame()
    shown = sum(1 for r in L.recs.values() if L.drawn(r))
    print(f"level {lv}: {len(L.recs)} records, {shown} drawn, "
          f"{len(L.hooked)} to the level's hook")
    for k, r in sorted(L.recs.items()):
        print(f"  slot {k:3d} type {r['type']:3d} class {r['cls']:02x} "
              f"op {r['op']:02x} +0 {r['b0']} angles {r['angles']} "
              f"scale {r['scale'][0]:5d} {'drawn' if L.drawn(r) else '-'}"
              f"{' hook' if k in L.hooked else ''}")


if __name__ == "__main__":
    main()
