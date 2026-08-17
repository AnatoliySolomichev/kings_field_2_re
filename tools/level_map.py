#!/usr/bin/env python3
"""High-resolution renderer for one King's Field II level.

Cell fields recovered by comparing the grid against a screenshot taken at a
known player position:

    [0..4]  a second layer, constant ff 00 00 ff 00 on every level -- unused
    [5]     wall/surface texture id, 255 in solid rock
    [6]     floor height, 100 at the base level (95 was the water channel,
            104-108 the raised stonework in the reference shot)
    [7]     orientation of the step/slope face, 0-3
    [8]     floor texture id, 255 in solid rock
    [9]     flags; bit 6 (64) marks a cell carrying a vertical face
"""
import sys

sys.path.insert(0, "tools")
from maps import levels, cell, W, H          # noqa: E402
import collision                              # noqa: E402
import tim                                    # noqa: E402

SOLID = 255
FACE = 0x40
CELLW = 0x800                                 # world units across one cell
WALL_INK = (220, 139, 76, 255)


def wall_segments(grid, lv):
    """Every wall plane on the level, in cell-local units.

    A wall is a plane *inside* the cell (FORMATS.md section 4), so it is drawn
    where it actually stands rather than on the cell boundary -- `op[0]` of
    1024, half a cell, is the commonest value there is.

        face 0: x = op0          face 2: x = 0x800 - op0
        face 3: z = op0          face 1: z = 0x800 - op0
    """
    lvl = collision.Level(lv, grid)
    for cx, cz, face, off, _lo, _hi in collision.walls(lv, lvl):
        if face == 0:
            yield cx, cz, "x", off
        elif face == 2:
            yield cx, cz, "x", CELLW - off
        elif face == 3:
            yield cx, cz, "z", off
        else:
            yield cx, cz, "z", CELLW - off


def field(grid, x, y, off):
    return cell(grid, x, y, off)


def solid(grid, x, y):
    return field(grid, x, y, 8) == SOLID


def heights(grid):
    """Height range of walkable ground, clipped so a stray outlier cell does
    not flatten the whole ramp."""
    vals = sorted(field(grid, x, y, 6) for y in range(H) for x in range(W)
                  if not solid(grid, x, y))
    if not vals:
        return (0, 1)
    lo = vals[int(len(vals) * 0.02)]
    hi = vals[int(len(vals) * 0.98)]
    return (lo, hi if hi > lo else lo + 1)


def render(grid, scale=12, grid_every=8, north_up=True, lv=None):
    """Draw the level. Community maps put north at the top, which is the grid
    with its Z axis flipped, so that is the default here too."""
    lo, hi = heights(grid)
    rng = max(hi - lo, 1)
    Wp, Hp = W * scale, H * scale
    px = [(0, 0, 0, 255)] * (Wp * Hp)

    def put(x, y, c):
        if 0 <= x < Wp and 0 <= y < Hp:
            px[y * Wp + x] = c

    def gz(row):
        return H - 1 - row if north_up else row

    for cy in range(H):
        for cx in range(W):
            if solid(grid, cx, gz(cy)):
                base = (26, 24, 32, 255)
            else:
                t = (field(grid, cx, gz(cy), 6) - lo) / rng
                t = 0.0 if t < 0 else (1.0 if t > 1 else t)
                # low ground reads cool and mossy, high ground dry and pale
                r = int(52 + 168 * t)
                g = int(74 + 150 * t)
                b = int(72 + 104 * t)
                base = (r, g, b, 255)
            for dy in range(scale):
                for dx in range(scale):
                    put(cx * scale + dx, cy * scale + dy, base)

    # draw a dark edge wherever the floor steps or the cell carries a face
    edge = (18, 16, 22, 255)
    for cy in range(H):
        for cx in range(W):
            hcur = field(grid, cx, gz(cy), 6)
            scur = solid(grid, cx, gz(cy))
            for dx, dy in ((1, 0), (0, 1)):
                nx, ny = cx + dx, cy + dy
                if nx >= W or ny >= H:
                    continue
                hn = field(grid, nx, gz(ny), 6)
                sn = solid(grid, nx, gz(ny))
                if scur == sn and hcur == hn:
                    continue
                if dx:
                    for k in range(scale):
                        put(nx * scale, cy * scale + k, edge)
                else:
                    for k in range(scale):
                        put(cx * scale + k, ny * scale, edge)

    if lv is not None:
        for cx, cz, axis, off in wall_segments(grid, lv):
            cy = (H - 1 - cz) if north_up else cz
            if not (0 <= cx < W and 0 <= cy < H):
                continue
            d = off * scale // CELLW
            if axis == "x":
                x = cx * scale + max(0, min(scale - 1, d))
                for k in range(scale):
                    put(x, cy * scale + k, WALL_INK)
            else:
                # the drawn row runs the other way when north is up, so a plane
                # measured from the cell's low-z edge is measured from its foot
                d = (scale - 1 - d) if north_up else d
                y = cy * scale + max(0, min(scale - 1, d))
                for k in range(scale):
                    put(cx * scale + k, y, WALL_INK)

    if grid_every:
        faint = (255, 255, 255, 255)
        for cy in range(0, H, grid_every):
            for x in range(0, Wp, 3):
                y = cy * scale
                if 0 <= y < Hp:
                    r, g, b, _ = px[y * Wp + x]
                    px[y * Wp + x] = (min(r + 26, 255), min(g + 26, 255),
                                      min(b + 26, 255), 255)
        for cx in range(0, W, grid_every):
            for y in range(0, Hp, 3):
                x = cx * scale
                if 0 <= x < Wp:
                    r, g, b, _ = px[y * Wp + x]
                    px[y * Wp + x] = (min(r + 26, 255), min(g + 26, 255),
                                      min(b + 26, 255), 255)
    return Wp, Hp, px


if __name__ == "__main__":
    lv = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    scale = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    grid = dict(levels())[lv]
    lo, hi = heights(grid)
    print(f"level {lv}: height {lo}..{hi}, "
          f"{sum(1 for y in range(H) for x in range(W) if solid(grid,x,y))} solid cells")
    w, h, px = render(grid, scale, lv=lv)
    out = f"out/maps/level{lv:02d}_detail.png"
    tim.write_png(out, w, h, px)
    print(f"wrote {out} {w}x{h}")
