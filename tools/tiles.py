#!/usr/bin/env python3
"""Tile shapes: the little programs that give a level its walls.

    python3 tools/tiles.py            the instruction set and how often each is used
    python3 tools/tiles.py 0 37       level 0, shape 37, disassembled

Cell byte `+8` indexes a table of 254 shapes at the tail of `FDAT.T` entry
`3n + 0`, and a shape is **not geometry but a program**. `tile_shape_reader`
(`0x8003260c`) fetches a halfword, subtracts `0x10`, bounds it at `0x31` and
dispatches through a 49-entry table at `0x80011b0c` -- the third bytecode in
this game, after the entity scripts and the level-state stream.

    header    u16 u16   two values
              u16       0x1000, the fixed-point 1.0 this game uses everywhere
              u16       how many instructions follow
    then      the instructions

Shapes **overlap**: a shape often runs past where the next one begins, so the
instruction count is what ends it, not the gap between offsets. Reading them by
gap is what made an earlier pass fail on all 2351.

Every drawing instruction carries a **face direction**: the handler adds an
operand to the cell's own orientation byte and masks the result to two bits.
`0x20` was the way in -- `(operand[3] + cell[+7]) & 3` -- and the others do the
same at their own operand offsets.

Which of them are walls is **not settled**. The earlier answer here quoted a
90.6 % precision from `mapcheck.score`, which is permissive enough to pass a
badly wrong predicate; `mapcheck.agreement` rasterises the prediction instead
and put the same answer at 12 %. Both are withdrawn.

What the handlers themselves say, so far (`0x20` at `0x800328c0`, read out in
full): an instruction is a **plane inside the cell**, not an edge of it.

    op[0]      how far the plane sits from that side of the cell
    op[1..2]   the height band it blocks -- you can walk over or under it
    op[3]      the face, added to the cell's own `+7` and masked to two bits

Correcting the face mapping alone (see `SIDE`) took agreement with the game's
map from 17 % to 45 % on the `0x20`-`0x25`, `0x31`, `0x32` set. The rest of the
gap is expected to be `op[0]` and the height band, both ignored here, and the
diagonals: `tile_collision` precomputes `tx +- tz`, so some surfaces run at 45
degrees and no axis-aligned rasterisation can place them at all.
"""
import collections
import struct
import sys

sys.path.insert(0, "tools")
from tarc import TArc                                                # noqa: E402

FDAT = "extract/CD/COM/FDAT.T"
GRID = 64000
SCALE = 0x1000
SHAPES = 254

# opcode -> total bytes, taken from each handler's own `addiu $t1, $t1, N`
LEN = {0x10: 4, 0x11: 6, 0x17: 4, 0x18: 4, 0x19: 4,
       0x20: 10, 0x21: 10, 0x22: 10, 0x23: 10, 0x24: 12, 0x25: 16,
       0x30: 14, 0x31: 12, 0x32: 14, 0x33: 10, 0x34: 10, 0x35: 14, 0x40: 4}
# opcode -> which operand holds the face direction, as a halfword index
DIR = {0x20: 3, 0x21: 3, 0x22: 3, 0x23: 3, 0x24: 4, 0x25: 6,
       0x30: 3, 0x31: 4, 0x32: 3, 0x33: 1, 0x34: 1, 0x35: 3}
WALL = {0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x31, 0x32}
# face direction -> the neighbour across the surface, read off handler 0x20.
# With tx = X & 0x7ff and tz = Z & 0x7ff, and r the player radius, it tests
#   0: tx <= op0 + r           low  x   1: tz >= 0x800 - r - op0   high z
#   2: tx >= 0x800 - r - op0   high x   3: tz <= op0 + r           low  z
# X was mirrored here until that was read out: 0 and 2 were the wrong way
# round, which cost the decode two thirds of its agreement with the map.
SIDE = {0: (-1, 0), 1: (0, 1), 2: (1, 0), 3: (0, -1)}


def table(lv, path=FDAT):
    """(the shape block, [offset per shape id])"""
    raw = TArc(path).raw(lv * 3)
    if len(raw) < 4 + GRID + 512:
        return b"", []
    tail = raw[4 + GRID:]
    return tail, list(struct.unpack_from(f"<{SHAPES}H", tail, 4))


def shape(tail, off):
    """(header, [(opcode, operand halfwords)]) -- ended by the count, not the gap."""
    if not off or off + 8 > len(tail):
        return None, []
    hdr = struct.unpack_from("<4H", tail, off)
    p, ops = off + 8, []
    for _ in range(hdr[3]):
        if p + 2 > len(tail):
            break
        op = struct.unpack_from("<H", tail, p)[0]
        n = LEN.get(op, 2)
        ops.append((op, [struct.unpack_from("<H", tail, p + 2 + 2 * k)[0]
                         for k in range((n - 2) // 2) if p + 4 + 2 * k <= len(tail)]))
        p += n
    return hdr, ops


def walls(lv, path=FDAT):
    """shape id -> the set of face directions it declares as walls."""
    tail, offs = table(lv, path)
    out = {}
    for sid, off in enumerate(offs):
        hdr, ops = shape(tail, off)
        if not ops:
            continue
        out[sid] = {args[DIR[op]] & 3 for op, args in ops
                    if op in WALL and len(args) > DIR[op]}
    return out


def cell_walls(grid, wl, x, z, cell):
    """[(dx, dz)] for each side of this cell that carries a wall."""
    sid = cell(grid, x, z, 8)
    if sid == 255:
        return []
    rot = cell(grid, x, z, 7) & 3
    return [SIDE[(f + rot) & 3] for f in wl.get(sid, ())]


if __name__ == "__main__":
    if len(sys.argv) > 2:
        lv, sid = int(sys.argv[1]), int(sys.argv[2])
        tail, offs = table(lv)
        hdr, ops = shape(tail, offs[sid])
        if not hdr:
            print(f"level {lv} has no shape {sid}")
            sys.exit(0)
        print(f"level {lv} shape {sid} at +{offs[sid]}: "
              f"header {hdr[0]}, {hdr[1]}, scale {hdr[2]:#06x}, {hdr[3]} instructions\n")
        for op, args in ops:
            face = ""
            if op in DIR and len(args) > DIR[op]:
                face = f"   face {args[DIR[op]] & 3}" + ("  WALL" if op in WALL else "")
            print(f"  {op:#04x}  " + " ".join(f"{a:5d}" for a in args) + face)
    else:
        freq, nshapes = collections.Counter(), 0
        for lv in range(28):
            tail, offs = table(lv)
            for off in offs:
                hdr, ops = shape(tail, off)
                if not ops:
                    continue
                nshapes += 1
                for op, _ in ops:
                    freq[op] += 1
        print(f"{nshapes} shapes across the game\n")
        print(f"{'opcode':8s} {'bytes':>6s} {'uses':>7s}  role")
        for op in sorted(LEN):
            role = "wall" if op in WALL else ("draws, not a wall" if op in DIR else "")
            print(f"  {op:#04x}  {LEN[op]:6d} {freq[op]:7d}  {role}")
