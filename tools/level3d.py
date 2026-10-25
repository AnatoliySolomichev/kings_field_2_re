#!/usr/bin/env python3
"""Build a whole level as geometry a modern engine can open.

    python3 tools/level3d.py 0                 out/godot/ -- obj, mtl, textures, project
    python3 tools/level3d.py 0 --cells 20      a 20x20 corner of it, for a quick look

Everything this needs is decoded (FORMATS.md section 4):

    model      RTMD.T[level], object cell[+5]      tools/tmd.py
    texture    the page and CLUT its primitives name, out of RTIM.T
    place at   cx * 2048 + 1024,  -128 * cell[+6],  cz * 2048 + 1024
    turned by  cell[+7] & 3, which is Ry(rot * 90 degrees)

**The rotation had to be recovered rather than read.** The four matrices at
`0x801aeb8c` are not clean quarter turns: the camera is already multiplied into
them and they are rebuilt every frame. What survives is the relation between
them -- `M1 = M0 . Ry(90)` holds row for row on all four -- so the tile's own
part is a quarter turn about Y, which in PlayStation axes sends `(x, y, z)` to
`(z, y, -x)`.

Axes: the PlayStation has Y pointing down and Z pointing away from the viewer;
an engine has Y up and -Z away. **Both** are negated, which is a half turn about
X and leaves handedness alone. Negating Y by itself was the first attempt, and
it is a mirror -- the level came out reflected left to right, which is obvious
once seen in the game and invisible in any map or top-down view, since those
are symmetric under exactly that flip.

Face winding is not assumed at all: each triangle is turned to agree with the
model's own normal, so the axis convention can change without breaking it.

One cell becomes 2.048 metres, which puts the player's eye at about 1.5.
"""
import math
import os
import struct
import sys

sys.path.insert(0, "tools")
import collision as coll                                             # noqa: E402
import gltf                                                           # noqa: E402
import lighting                                                       # noqa: E402
import rtim                                                           # noqa: E402
import tim                                                            # noqa: E402
import tmd                                                            # noqa: E402

W, CELLB = 80, 10
CELL = 0x800
UNIT = 1000.0            # world units per metre
VOID = 0xF0              # cell[+5] at or above this is solid rock


def _rot3(rx, ry, rz):
    """A rotation matrix from the game's three angles, 4096 to the turn.

    **M = Ry . Rx . Rz**, so a vertex is turned about Z first, then X, then Y.
    That is read off `0x800166f4`, which builds it in this order:

        temp = Rz(angle[+4])          0x80016680, the Z matrix
        dest = Rx(angle[+0])          0x80016598, the X matrix
        0x80074628(dest, temp)        writes into $a0: dest = dest . temp
        temp = Ry(angle[+2])          0x8001660c, the Y matrix
        0x80074734(temp, dest)        writes into $a1: dest = temp . dest

    Each helper is named by the cells it fills -- the X one writes `0x1000`
    into [0][0] and cos, -sin, sin, cos into the lower right, and so on. The
    two multiplies are told apart by which argument they store through, which
    is the whole difference between them.

    **The Y matrix had its signs the wrong way round**, and nothing checked it:
    `rot_matrix_y` (`0x8001660c`) stores cos at [0][0], **-sin at [0][2]** and
    **sin at [2][0]** (`negu $v1, $s0; sh $v1, 4($s1)` and `sh $s0, 0xc($s1)`),
    where this had sin and -sin. So every object turned by -yaw instead of
    yaw -- invisible at 0 and half a turn, half a turn wrong at the quarters --
    and a door swung the wrong way, which is how a player caught it. The X and
    Z matrices were right.

    An earlier version of this composed them the other way round and said so:
    it was a choice, not a reading, and a player looking at a helmet in both
    windows could see it was wrong. The angle triple is read at +0, +2 and +4
    as X, Y and Z, which is also what the live record's +0x24, +0x26 and +0x28
    hold.
    """
    def cs(a):
        t = (a % 4096) / 4096.0 * 2.0 * math.pi
        return math.cos(t), math.sin(t)
    cx, sx = cs(rx)
    cy, sy = cs(ry)
    cz, sz = cs(rz)
    ry_m = ((cy, 0.0, -sy), (0.0, 1.0, 0.0), (sy, 0.0, cy))
    rx_m = ((1.0, 0.0, 0.0), (0.0, cx, -sx), (0.0, sx, cx))
    rz_m = ((cz, -sz, 0.0), (sz, cz, 0.0), (0.0, 0.0, 1.0))

    def mul(a, b):
        return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3))
                           for j in range(3)) for i in range(3))
    return mul(ry_m, mul(rx_m, rz_m))


def spin(v, rot):
    """Ry(rot * 90 degrees) in PlayStation axes."""
    x, y, z = v
    for _ in range(rot & 3):
        x, z = z, -x
    return x, y, z


def fog_of(look, cls):
    """The depth cue's (near, far) for a lighting class: its record's +0x68, +0x6a.

    Every drawing routine hands these to fog_range_set (0x80035358) for what it
    draws, and draw_tmd_object fades each face from its lit colour at `near`
    toward the far colour at `far`; godot/scroll.gd does the same per vertex.
    """
    return struct.unpack_from("<2H", look, 108 * cls + 0x68)


def light_class(look, cls, rot):
    """The GTE lighting a cell's class applies: (direction, colour, background).

    A record is four 20-byte light-direction matrices, one per orientation, then
    the light-colour matrix at +0x50 and the background at +0x64. Each 20-byte
    block is five words of packed halfwords, which is the GTE's own matrix
    layout: R11R12, R13R21, R22R23, R31R32, R33.
    """
    base = cls * 108

    def mat(off):
        hw = struct.unpack_from("<10h", look, base + off)
        return (hw[0:3], hw[3:6], hw[6:9])
    return (mat(rot * 20), mat(0x50),
            [look[base + 0x64 + k] * 16 for k in range(3)])


def shade(normal, llm, lcm, bk):
    """One face's colour, as the GTE computes it. Never reaches black: the
    background term is added after the light, which is why nothing in the real
    game is unlit and why an engine light on top of this would be wrong.

    The fourth value is the class's background byte (its red, +0x64) over
    255, 254 at most -- the vertex colour's alpha, which nothing else reads --
    so godot/scroll.gd can move it as sub_80034394 moves the record's
    (the darkness, the light, an effect's pulse) and the colour with it."""
    ir = [max(0, min(0x7FFF, (llm[r][0] * normal[0] + llm[r][1] * normal[1]
                              + llm[r][2] * normal[2]) >> 12)) for r in range(3)]
    out = []
    for r in range(3):
        v = (bk[r] * 4096 + lcm[r][0] * ir[0] + lcm[r][1] * ir[1]
             + lcm[r][2] * ir[2]) >> 12
        out.append(max(0.0, min(1.0, v / 4096.0)))
    out.append(min(bk[0] // 16, 254) / 255.0)
    return out


_grids = {}


def grid_of(lv):
    """The level's grid as `load_object_placement` leaves it, off the disc.

    `level_load` copies `FDAT.T` entry 3n, and the object loader then stamps
    every door into it (`tools/objload.py`). This used to be a dump of level
    0's live grid for level 0 and the bare disc grid for every other level --
    so every level but 0 was drawn with its doors missing. The loader's grid
    matches the live one, outside the occupancy count, on every snapshot taken
    before a door was opened.
    """
    if lv not in _grids:
        import objload
        _grids[lv] = bytes(objload.Load(lv).grid)
    return _grids[lv]


def build(lv, limit=None):
    grid = grid_of(lv)
    _flags, objs = tmd.load("RTMD", lv)
    vram = object_vram(lv)

    mats = {}                                    # (tpage, clut) -> name
    verts, uvs, norms, faces = [], [], [], {}
    n = 0
    span = range(min(limit, W)) if limit else range(W)
    for cz in span:
        for cx in span:
            c = grid[(cz * W + cx) * CELLB:(cz * W + cx) * CELLB + CELLB]
            sid = c[5]
            if sid >= VOID or sid >= len(objs):
                continue
            obj = objs[sid]
            if not obj.prims:
                continue
            n += 1
            rot = c[7] & 3
            ox, oy, oz = cx * CELL + CELL // 2, -128 * c[6], cz * CELL + CELL // 2
            base, nbase = len(verts), len(norms)
            for v in obj.verts:
                x, y, z = spin(v, rot)
                # a half turn about X: Y down becomes Y up, +Z away becomes -Z
                verts.append(((ox + x) / UNIT, -(oy + y) / UNIT, -(oz + z) / UNIT))
            for nv in obj.normals:
                x, y, z = spin(nv, rot)
                norms.append((x / 4096.0, -y / 4096.0, -z / 4096.0))
            for pr in obj.prims:
                if not pr.tex or len(pr.verts) < 3 or max(pr.verts) >= obj.nv:
                    continue
                key = (pr.tpage, pr.clut)
                mats.setdefault(key, f"tex_{pr.tpage:04x}_{pr.clut:04x}")
                uv0 = len(uvs)
                for u, v in pr.uvs:
                    uvs.append((u / 256.0, 1.0 - v / 256.0))
                idx = [base + i + 1 for i in pr.verts]
                t = [uv0 + i + 1 for i in range(len(pr.uvs))]
                nrm = [nbase + i + 1 for i in pr.norms if i < obj.nn] or [0]
                tri = ([(0, 1, 2), (1, 3, 2)] if pr.quad else [(0, 1, 2)])
                for a, b, cc in tri:
                    # Wind each triangle to agree with the model's own normal
                    # rather than with an assumption about TMD's convention --
                    # which is what let the axis fix above land without also
                    # having to reason about which way the faces then pointed.
                    order = (a, b, cc)
                    ni = nrm[0] - 1 - nbase
                    if 0 <= ni < len(obj.normals):
                        f = [verts[idx[i] - 1] for i in order]
                        gx = ((f[1][1] - f[0][1]) * (f[2][2] - f[0][2])
                              - (f[1][2] - f[0][2]) * (f[2][1] - f[0][1]))
                        gy = ((f[1][2] - f[0][2]) * (f[2][0] - f[0][0])
                              - (f[1][0] - f[0][0]) * (f[2][2] - f[0][2]))
                        gz = ((f[1][0] - f[0][0]) * (f[2][1] - f[0][1])
                              - (f[1][1] - f[0][1]) * (f[2][0] - f[0][0]))
                        nn = norms[nbase + ni]
                        if gx * nn[0] + gy * nn[1] + gz * nn[2] < 0:
                            order = (cc, b, a)
                    faces.setdefault(key, []).append(
                        tuple((idx[i], t[i], nrm[0]) for i in order))
    return verts, uvs, norms, faces, mats, vram, n


def lift_tiles(lv):
    """{(cx, cz): slot} for the cells whose drawn tile a lift door rewrites.

    A lift door (opcodes 3 to 5, tools/doors.py) is drawn by the grid while it
    is shut -- its tile table writes the wall tile into layer 1 of its two
    cells at load -- and by its own model while it moves, when the same table
    writes 0xfc there, which draw_terrain skips. So those cells cannot be part of
    the one level mesh: each door's go into a node of their own, `tNNN` by
    the door's slot, that godot/doors.gd hides and shows as the stamps do.
    """
    import objload
    import doors
    ld = objload.Load(lv)
    out = {}
    for k, r in sorted(ld.recs.items()):
        if r["op"] not in doors.LIFT_OPS + doors.WALL_OPS:
            continue
        drawn = 2 if r["b0"] != 1 else 3       # the byte that lands in cell[+5]
        for cx, cz, q in doors.lift_stamps(ld, r)[1]:
            if q[drawn] != 0xFF or q[4 + drawn] != 0xFF:
                out.setdefault((cx, cz), k)
    return out


def build_gltf(lv, out="out/godot", limit=None):
    """The level as glTF: baked lighting, nearest sampling, no engine lights.

    One node, `level<lv>`, for the grid; and one, `tNNN`, for the cells each
    lift door draws over (lift_tiles)."""
    grid = grid_of(lv)
    _flags, objs = tmd.load("RTMD", lv)
    vram = object_vram(lv)
    look = lighting.table()
    g = gltf.Gltf()
    whole = {}
    lifts = lift_tiles(lv)
    apart = {}                                   # door slot -> its own groups
    span = range(min(limit, W)) if limit else range(W)
    ncell = 0
    for cz in span:
        for cx in span:
            c = grid[(cz * W + cx) * CELLB:(cz * W + cx) * CELLB + CELLB]
            sid = c[5]
            if sid >= VOID or sid >= len(objs) or not objs[sid].prims:
                continue
            obj = objs[sid]
            ncell += 1
            groups = (apart.setdefault(lifts[(cx, cz)], {})
                      if (cx, cz) in lifts else whole)
            rot = c[7] & 3
            llm, lcm, bk = light_class(look, c[9] & 0x3F, rot)
            fog = fog_of(look, c[9] & 0x3F)
            ox, oy, oz = cx * CELL + CELL // 2, -128 * c[6], cz * CELL + CELL // 2

            def place(v):
                x, y, z = spin(v, rot)
                return ((ox + x) / UNIT, -(oy + y) / UNIT, -(oz + z) / UNIT)

            for pr in obj.prims:
                if not pr.tex or len(pr.verts) < 3 or max(pr.verts) >= obj.nv:
                    continue
                ni = pr.norms[0] if pr.norms and pr.norms[0] < obj.nn else None
                raw = obj.normals[ni] if ni is not None else (0, -4096, 0)
                rgb = shade(raw, llm, lcm, bk)
                nx, ny, nz = spin(raw, rot)
                nrm = (nx / 4096.0, -ny / 4096.0, -nz / 4096.0)
                pts = [place(obj.verts[i]) for i in pr.verts]
                key = (pr.tpage, pr.clut, bool(pr.mode & 2))
                bag = groups.setdefault(key, ([], [], [], [], []))
                for a, b, cc in ([(0, 1, 2), (1, 3, 2)] if pr.quad
                                 else [(0, 1, 2)]):
                    order = (a, b, cc)
                    f = [pts[i] for i in order]
                    gx = ((f[1][1] - f[0][1]) * (f[2][2] - f[0][2])
                          - (f[1][2] - f[0][2]) * (f[2][1] - f[0][1]))
                    gy = ((f[1][2] - f[0][2]) * (f[2][0] - f[0][0])
                          - (f[1][0] - f[0][0]) * (f[2][2] - f[0][2]))
                    gz = ((f[1][0] - f[0][0]) * (f[2][1] - f[0][1])
                          - (f[1][1] - f[0][1]) * (f[2][0] - f[0][0]))
                    if gx * nrm[0] + gy * nrm[1] + gz * nrm[2] < 0:
                        order = (cc, b, a)
                    for i in order:
                        bag[0].append(pts[i])
                        bag[1].append(nrm)
                        u, v = pr.uvs[i]
                        bag[2].append((u / 256.0, v / 256.0))
                        bag[3].append((rgb[0], rgb[1], rgb[2], rgb[3] if len(rgb) > 3 else 1.0))
                        bag[4].append(fog)

    ntri, mats = 0, {}

    def prims_of(groups):
        nonlocal ntri
        prims = []
        for key, (pos, nrm, uv, col, fogs) in groups.items():
            m = material_for(g, mats, out, lv, key, vram, double=False)
            p = g.primitive(pos, nrm, uv, col, fogs)
            p["material"] = m
            prims.append(p)
            ntri += len(pos) // 3
        return prims
    # No `-col` suffix: the level is not handed to a physics engine at all.
    # Movement runs the game's own collision (godot/collision.gd), which is the
    # only way ramps, stairs, steppable walls and drowning come out right.
    items = [(f"level{lv}", prims_of(whole), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))]
    for slot, groups in sorted(apart.items()):
        items.append((f"t{slot:03d}", prims_of(groups), (0.0, 0.0, 0.0),
                      (0.0, 0.0, 0.0, 1.0)))
    path, nbytes = g.write_nodes(f"{out}/level{lv:02d}.gltf", items)
    print(f"level {lv}: {ncell} cells, {ntri} triangles, {len(mats)} materials, "
          f"{len(apart)} lift doors' cells apart -> {path}")
    return path


def write(lv, out="out/godot", limit=None):
    verts, uvs, norms, faces, mats, vram, ncell = build(lv, limit)
    rels = {}
    for (tpage, clut), name in mats.items():
        rels[name] = page_texture(out, lv, tpage, clut, vram)
        if rels[name] is None:                   # 8-bit or 15-bit page
            print(f"  note: {name} is not a 4-bit page, skipping its texture")

    with open(f"{out}/level{lv:02d}.mtl", "w") as f:
        for name in mats.values():
            f.write(f"newmtl {name}\nKd 1 1 1\nKa 1 1 1\nd 1\nillum 1\n"
                    + (f"map_Kd {rels[name]}\n" if rels[name] else "") + "\n")

    obj = f"{out}/level{lv:02d}.obj"
    ntri = 0
    with open(obj, "w") as f:
        f.write(f"# King's Field II, level {lv}: {ncell} cells\n")
        f.write(f"mtllib level{lv:02d}.mtl\n")
        for x, y, z in verts:
            f.write(f"v {x:.4f} {y:.4f} {z:.4f}\n")
        for u, v in uvs:
            f.write(f"vt {u:.5f} {v:.5f}\n")
        for x, y, z in norms:
            f.write(f"vn {x:.4f} {y:.4f} {z:.4f}\n")
        for key, tris in faces.items():
            f.write(f"usemtl {mats[key]}\no {mats[key]}\n")
            for tri in tris:
                f.write("f " + " ".join(f"{a}/{b}/{c}" for a, b, c in tri) + "\n")
                ntri += 1
    print(f"level {lv}: {ncell} cells, {len(verts)} vertices, {ntri} triangles, "
          f"{len(mats)} textures -> {obj}")
    return obj, ncell, ntri


# `importer_defaults` matters more than it looks. Left alone, Godot sees the
# textures used in 3D and re-imports them mipmapped and VRAM-compressed, which
# on sixteen-colour pixel art is ruinous -- block compression has nothing to
# work with and the brickwork turns to mush.
def build_collision_gltf(lv, out="out/godot"):
    """The game's own collision, drawn as translucent quads.

    Not for walking on -- the level mesh does that -- but for *looking at*. This
    is where `tools/collision.py` says the game blocks you, and the interesting
    places are where it disagrees with what is drawn: a wall you can see through,
    a room the geometry reaches and the collision seals off.
    """
    lvl = coll.Level(lv)
    g = gltf.Gltf()
    pos, nrm, uv, col = [], [], [], []
    n = 0
    for cx, cz, face, off, lo, hi in coll.walls(lv, lvl):
        n += 1
        x0, z0 = cx * CELL, cz * CELL
        if face in (0, 2):
            x = x0 + (off if face == 0 else CELL - off)
            quad = [(x, lo, z0), (x, lo, z0 + CELL),
                    (x, hi, z0 + CELL), (x, hi, z0)]
            nv = (1.0, 0.0, 0.0)
        else:
            z = z0 + (off if face == 3 else CELL - off)
            quad = [(x0, lo, z), (x0 + CELL, lo, z),
                    (x0 + CELL, hi, z), (x0, hi, z)]
            nv = (0.0, 0.0, 1.0)
        p = [(x / UNIT, -y / UNIT, -z / UNIT) for x, y, z in quad]
        for a, b, c in ((0, 1, 2), (0, 2, 3)):
            for i in (a, b, c):
                pos.append(p[i])
                nrm.append(nv)
                uv.append((0.0, 0.0))
                col.append((1.0, 1.0, 1.0, 1.0))
    prim = g.primitive(pos, nrm, uv, col)
    prim["material"] = g.plain("collision", (1.0, 0.25, 0.2, 0.35))
    path, nbytes = g.write(f"{out}/collision{lv:02d}.gltf", [prim],
                           f"collision{lv}")
    print(f"collision overlay: {n} wall planes, {len(pos) // 3} triangles, "
          f"{nbytes // 1024} KB -> {path}")
    return path


def object_vram(lv):
    """What the GPU holds on level `lv`: `FDAT.T` entry 96, then `RTIM.T[lv]`.

    The objects sample pages `0x0b` to `0x0f`, which `RTIM.T` leaves empty,
    and for a long time this filled them from a level-0 RAM snapshot because
    nothing on the disc seemed to hold them. Entry 96 does: `init_level_state`
    streams it into VRAM once at game start, the same way `level_load` streams
    each level's `RTIM.T` on top (tools/rtim.py, `level_vram`). Rebuilt that
    way, the object pages match the snapshots on 776 955 of 782 320 halfwords,
    the rest being frames of an animated water texture -- so the geometry, the
    objects and the creatures all sample this now, on every level.
    """
    return bytes(rtim.level_vram(lv))


# What this run has written already, so the objects, the creatures and the
# gallery can share a page without cutting it three times.
_written = set()


def page_texture(out, lv, tpage, clut, vram, semi=False):
    """One page under one CLUT as a PNG; its path relative to `out`, or None.

    **The path carries the level and the VRAM it was cut from**, because the
    same page and CLUT are different pixels on different levels: each level
    loads its own `RTIM.T` into the same VRAM. These used to be
    `tex/tex_<page>_<clut>.png` for every level, and the objects' copy was
    written only when the file was missing. Building levels 1 to 14 therefore
    left their pixels under names level 0 reuses, and level 0's 73 trees
    (types 324 to 326) came out wearing another level's wall of statues in
    niches -- which a player saw as big pictures standing among the things on
    the ground. 9 of level 0's 100 object textures were another level's, or
    the geometry's.

    One VRAM serves the geometry, the objects and the creatures alike --
    `object_vram`, the disc's two streams -- so one file per page and CLUT is
    enough within a level. There used to be two, when the geometry saw
    `RTIM.T` alone and the objects a snapshot's pages, and they disagreed:
    level 0's water sheet sampled a CLUT only the snapshot had, and was
    invisible.

    Pages at 8 or 16 bits a pixel are not written -- `page4` reads four -- and
    get None, for a plain material rather than one naming a missing file.
    """
    if (tpage >> 7) & 3:
        return None
    rel = f"tex/lv{lv:02d}/tex_{tpage:04x}_{clut:04x}{'_semi' if semi else ''}.png"
    path = f"{out}/{rel}"
    if path not in _written:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tim.write_png(path, 256, 256, rtim.page4(vram, tpage, clut, semi))
        _written.add(path)
    return rel


# Semi-transparency the glTF cannot say: rates 1 and 3 add, rate 2 subtracts.
# godot/scroll.gd reads the suffix and sets the material's blend mode.
BLEND_SUFFIX = ("", "_add", "_sub", "_add")


def material_for(g, mats, out, lv, key, vram, double=True):
    """The glTF material for one (tpage, clut, semi) group, made once a file.

    A primitive whose mode has ABE set (bit 1) is semi-transparent, and on the
    PlayStation that works texel by texel: a colour with bit 15 set is blended
    with what is behind it at the page's rate, any other is drawn solid, and
    colour 0 not at all. Level 0's water is sixteen such primitives at rate 0,
    half and half, and it was drawn as solid blue until this; the game's own
    screenshot shows the bank through it.
    """
    tpage, clut, semi = key
    name = f"tex_{tpage:04x}_{clut:04x}"
    if semi:
        name += "_semi" + BLEND_SUFFIX[(tpage >> 5) & 3]
    if name not in mats:
        rel = page_texture(out, lv, tpage, clut, vram, semi)
        mats[name] = (g.material(name, rel, double=double, blend=semi) if rel
                      else g.plain(name + "_flat", (0.8, 0.75, 0.7, 1.0)))
    return mats[name]


def emit_object(objs, place, colour, groups, normal_of=None, fog=(0, 0)):
    """Append one model's triangles into `groups`, keyed by (tpage, clut, semi).

    **Shared deliberately.** The world build and the catalogue each had their own
    copy of this loop and the copies drifted: the catalogue never turned a
    triangle to agree with the model's own normal, so about half of every model
    faced away from the camera and was culled. A player looking at the same
    helmet in both said it was whole in the world and torn into layers in the
    catalogue, with "some polygons transparent" -- which is exactly what a
    back-facing triangle looks like against a single-sided material.

    The other copy also had `if i >= len(pts): continue` inside the vertex loop,
    which can emit two vertices for a triangle and shift every triangle after it
    in that group. One skipped vertex corrupted the rest of the model.

    `place` maps a model vertex to world space, `colour` gives a primitive its
    rgb, and `normal_of` maps a model normal the same way `place` maps a vertex.
    """
    for obj in objs:
        for pr in obj.prims:
            if not pr.tex or len(pr.verts) < 3 or max(pr.verts) >= obj.nv:
                continue
            if len(set(pr.verts)) < 3:
                continue
            ni = pr.norms[0] if pr.norms and pr.norms[0] < obj.nn else None
            raw = obj.normals[ni] if ni is not None else (0, -4096, 0)
            nrm = normal_of(raw) if normal_of else (raw[0] / 4096.0,
                                                    -raw[1] / 4096.0,
                                                    -raw[2] / 4096.0)
            rgb = colour(raw)
            pts = [place(obj.verts[i]) for i in pr.verts]
            if len(pts) < (4 if pr.quad else 3):
                continue
            bag = groups.setdefault((pr.tpage, pr.clut, bool(pr.mode & 2)),
                                    ([], [], [], [], []))
            # No winding correction: the materials are double-sided, because the
            # PlayStation does not cull and these models rely on it. Turning
            # each triangle to agree with its own normal was tried and made
            # things visibly worse -- the per-face normal is not a reliable
            # guide here.
            for a, b, c in ([(0, 1, 2), (1, 3, 2)] if pr.quad else [(0, 1, 2)]):
                for i in (a, b, c):
                    bag[0].append(pts[i])
                    bag[1].append(nrm)
                    u, v = pr.uvs[i]
                    bag[2].append((u / 256.0, v / 256.0))
                    bag[3].append((rgb[0], rgb[1], rgb[2], rgb[3] if len(rgb) > 3 else 1.0))
                    bag[4].append(fog)


ACTOR_TABLE, ACTOR_STRIDE, ACTOR_SLOTS = 0x80185DA8, 0x88, 128
ENTITY_TABLE, ENTITY_STRIDE = 0x8018C7E8, 120
MODEL_TAG = 0x400        # entity[+0] is 0x400 | model number


def build_actors_gltf(lv, out="out/godot"):
    """The creatures, one node each, standing where the disc puts them.

    `tools/actors.py` reads the level's actor table off its own FDAT entry the
    way `0x800530f8` builds it, home and floor height included, and that agrees
    with a RAM snapshot of level 0 in all 58 slots, to the unit. So this needs
    no snapshot any more, and every level has its creatures. (It used to take
    them from one, and said the disc did not place them. It does: link 1 of the
    same chain the objects come from.)

    Each actor is a node of its own, `a<slot>`, at its home and turned by its
    placed yaw, so `actors.gd` can run the game's activation machine over them
    and show only the ones the game would draw. What the machine needs goes
    beside the mesh, in `actors<lv>.json`.

    The node carries the turn rather than the vertices. A creature has one
    angle: `render_walk` hands the actor's +0x40, +0x42 and +0x44 to the matrix
    builder and the spawner zeroes two of them. With the axes flipped the way
    this file flips them, x kept and y and z negated, the game's Ry(t) --
    `rot_matrix_y`, cos, -sin / sin, cos -- is a turn of **+t** about Godot's up
    axis. This said -t, from a Y matrix with its signs reversed.
    """
    import json
    import actors as act
    grid = grid_of(lv)
    table = act.table(lv, grid)
    vram = object_vram(lv)
    look = lighting.table()
    g = gltf.Gltf()
    mats, items, rows = {}, [], []
    placed = missing = ntri = 0
    for a in table:
        if a is None:
            continue
        rows.append(a)
        m = a["model"]
        arch, entry = ("MO", m) if m < tmd.MO_COUNT else ("MOF", m - tmd.MO_COUNT)
        try:
            _flags, objs = tmd.load(arch, entry)
        except Exception:
            missing += 1
            continue
        cx, cz = a["x"] >> 11, a["z"] >> 11
        if not (0 <= cx < W and 0 <= cz < W):
            continue
        c = grid[(cz * W + cx) * CELLB:(cz * W + cx) * CELLB + CELLB]
        llm, lcm, bk = light_class(look, c[9] & 0x3F, c[7] & 3)
        groups = {}
        emit_object(objs, lambda v: (v[0] / UNIT, -v[1] / UNIT, -v[2] / UNIT),
                    lambda raw: shade(raw, llm, lcm, bk), groups,
                    fog=fog_of(look, c[9] & 0x3F))
        prims = []
        for key, (pos, nrm, uv, col, fogs) in groups.items():
            pr = g.primitive(pos, nrm, uv, col, fogs)
            pr["material"] = material_for(g, mats, out, lv, key, vram)
            prims.append(pr)
            ntri += len(pos) // 3
        if not prims:
            missing += 1
            continue
        half = a["yaw"] * math.pi / 4096.0       # half of the turn, in radians
        items.append((f"a{a['slot']:03d}", prims,
                      (a["x"] / UNIT, -a["y"] / UNIT, -a["z"] / UNIT),
                      (0.0, math.sin(half), 0.0, math.cos(half))))
        placed += 1
    os.makedirs(out, exist_ok=True)
    with open(f"{out}/actors{lv:02d}.json", "w") as f:
        json.dump(rows, f, separators=(",", ":"))
    if not items:
        return None
    path, _n = g.write_nodes(f"{out}/actors{lv:02d}.gltf", items)
    print(f"creatures: {placed} placed, one node each, {missing} without a "
          f"model, {ntri} triangles -> {path}")
    return path


# The resident models effects draw: render_walk hands draw_model_plain
# model_table[slot +3 + 0x28] (0x80041794) -- 0x4c the spore (+3 0x24), 0x3e
# the puff a bolt leaves (+3 0x16), 0x4a the bobbing bolt 0x1f (+3 0x22), 0x49
# the dart 0x22 (+3 0x21), 0x31 the fire ball (+3 9), 0x52 a splash (+3 0x2a). This said 0x40 for the
# spore, which is its +0xe, a value render_walk puts in the scratchpad
# (0x1f800084), not a model. The attacking spells' (their arms of
# effect_spawn): 0x34 bortecth's puffs (+3 0xc), 0x35 wind cutter (0xd), 0x36
# earth wave (0xe), 0x37 stone and meteor (0xf), 0x3e haze (0x16), 0x44 and
# 0x45 meteor's puffs (0x1c, 0x1d), 0x46 shudom's ring and meteor's blast
# (0x1e), 0x47 walwind's wave and bortecth (0x1f), 0x48 bortecth's hold
# (0x20), 0x5a walwind (0x32), 0x5b shudom (0x33). Orladin's: 0x5f the bolt
# (0x37), 0x3d its bursts (0x15), 0x33 its rays (0xb), 0x4d its puffs (0x25).
# 0x30 tornado (8), 0x50 fire wall (0x28); fire storm is the fire ball's (9);
# 0x51 flame's head (0x29), drawn unanimated.
EFFECT_MODELS = (0x30, 0x31, 0x33, 0x34, 0x35, 0x36, 0x37, 0x3D, 0x3E, 0x44, 0x45, 0x46, 0x47,
                 0x48, 0x49, 0x4A, 0x4C, 0x4D, 0x50, 0x51, 0x52, 0x5A, 0x5B, 0x5F)


def build_effects_gltf(lv, out="out/godot"):
    """The resident models the effects draw (model_table[+3 + 0x28]), one
    node each, `mNNN`, for godot/effects.gd to copy. Lit by the level's
    lighting class 0 -- which class the effect draw uses is not read yet."""
    import modelbank
    vram = object_vram(lv)
    look = lighting.table()
    llm, lcm, bk = light_class(look, 0, 0)
    g = gltf.Gltf()
    mats, items = {}, []
    for m in EFFECT_MODELS:
        try:
            _flags, objs = modelbank.load(m)
        except Exception as e:
            print(f"effect model {m}: {e}")
            continue
        groups = {}
        emit_object(objs, lambda v: (v[0] / UNIT, -v[1] / UNIT, -v[2] / UNIT),
                    lambda raw: shade(raw, llm, lcm, bk), groups,
                    fog=fog_of(look, 0))
        prims = []
        for key, (pos, nrm, uv, col, fogs) in groups.items():
            pr = g.primitive(pos, nrm, uv, col, fogs)
            pr["material"] = material_for(g, mats, out, lv, key, vram)
            prims.append(pr)
        if prims:
            items.append((f"m{m:03d}", prims, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)))
    os.makedirs(out, exist_ok=True)
    path, _n = g.write_nodes(f"{out}/effects{lv:02d}.gltf", items)
    print(f"effect models: {len(items)} -> {path}")
    return path


HELD_WEAPONS = range(0x22)        # the weapons, items 0..33; equip_weapon installs any


def build_held_gltf(lv, out="out/godot", weapons=HELD_WEAPONS):
    """The hand and weapon draw_held_item draws while the player swings --
    FDAT.T entry 0x62 + the weapon, one node `wNNN` each, for godot/held.gd:
    every weapon, since the equipment screen can put any in hand. Four
    entries (18, 19, 25, 26) hold no model. draw_held_item lights it with the
    player's cell; this bakes the level's class 0 into it."""
    import anim
    vram = object_vram(lv)
    look = lighting.table()
    llm, lcm, bk = light_class(look, 0, 0)
    g = gltf.Gltf()
    mats, items = {}, []
    for w in weapons:
        try:
            raw = anim.load_weapon(w).raw
        except Exception:
            continue                                 # no model in the entry
        o = tmd.find_tmd(raw)
        data = raw[o:]
        _idv, _flags, nobj = struct.unpack_from("<3I", data, 0)
        objs = [tmd.Obj(data, struct.unpack_from("<7i", data, tmd.HDR + 28 * k))
                for k in range(nobj)]
        groups = {}
        emit_object(objs, lambda v: (v[0] / UNIT, -v[1] / UNIT, -v[2] / UNIT),
                    lambda raw: shade(raw, llm, lcm, bk), groups,
                    fog=fog_of(look, 0))
        prims = []
        for key, (pos, nrm, uv, col, fogs) in groups.items():
            pr = g.primitive(pos, nrm, uv, col, fogs)
            pr["material"] = material_for(g, mats, out, lv, key, vram)
            prims.append(pr)
        if prims:
            items.append((f"w{w:03d}", prims, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)))
    os.makedirs(out, exist_ok=True)
    path, _n = g.write_nodes(f"{out}/held{lv:02d}.gltf", items)
    print(f"held models: {len(items)} -> {path}")
    return path


# The opcodes whose objects turn on a hinge: `object_interpreter`'s arm for
# opcode 1 (0x8004814c) swings the model a quarter turn and back. godot/doors.gd
# runs it; the other door classes (0x00, 0x1b, and the grid-drawn 0x03 to 0x05)
# are not ported yet.
DOOR_OPS = (0x01,)


def build_objects_gltf(lv, out="out/godot"):
    """Everything standing on the level: doors, chests, trees, save points.

    These are not tiles. The 24-byte placement records in `FDAT.T` entry
    `3n + 1` name a type id, a cell, a fine offset inside it and a rotation, and
    the model is **`MO.T[type + 128]`**, continuing into `MOF.T` past its 428
    entries. The 128 was measured, not reasoned: a player named four pairs from
    the gallery and all four differed by exactly that. `MO.T[type]`, which this
    used before and which nothing had ever checked, put a two-cell model where
    the healing grass should be and armour where the doors are.

    **From type 300 up the level is part of the model number** — `model_of_type`
    (`0x80040568`) adds `32 * level` — so `MOF.T` is banked 32 models to a
    level and level *n* uses bank *n + 4*. That holds for all 1424 such objects
    in the game. Ignoring it is right only on level 0, which is why it survived
    this long.

    **Everything about where an object stands and whether it is drawn comes
    from `tools/objload.py`**, the transcription of `load_object_placement`:
    the position with the record's own height (a chest's lid is one body-height
    up, not on the floor), all three angles, the scale, and the game's rule for
    drawing -- the opcode, the record's `+0` against the view byte, and a scale
    of zero. Until it was read, the scale, the angles and the render class came
    out of a level-0 RAM snapshot, so every other level had none of them.

    That rule is also why type 299 is not drawn: it is class 0x14, whose arm
    zeroes `+0`. It is the box two cells across that marks where an inscription
    can be read, and drawing it once put stone columns over the bull's head and
    the *Broken Cart* -- a player saw it beside the emulator. The doors are not
    drawn as models either: their arms zero the scale and stamp them into the
    grid, which draws them.
    """
    import json
    import objload
    load = objload.Load(lv).first_frame()
    grid = grid_of(lv)
    vram = object_vram(lv)
    look = lighting.table()
    g = gltf.Gltf()
    groups = {}
    placed = missing = hidden = 0
    doors, door_rows = [], []
    loot = loot_slots(load)
    import doors as doormod
    for _k, o in sorted(load.recs.items()):
        if o["slot"] in loot:
            continue                    # a node of its own: build_loot
        if o["op"] in doormod.GATE_OPS:
            continue                    # a node of its own that rises: build_lifts
        # The game's own rule, read off load_object_placement and render_walk:
        # the opcode, the record's +0 against the view byte, and the scale.
        if not load.drawn(o):
            hidden += 1
            continue
        try:
            _flags, objs = tmd.load(*tmd.model_of(o["type"], lv))
        except Exception:
            missing += 1
            continue
        cx, cz = o["x"] >> 11, o["z"] >> 11
        if not (0 <= cx < W and 0 <= cz < W):
            continue
        c = grid[(cz * W + cx) * CELLB:(cz * W + cx) * CELLB + CELLB]
        llm, lcm, bk = light_class(look, c[9] & 0x3F, c[7] & 3)
        # Position, angles and scale are the live record's, as the loader
        # makes them: the angles already negated off the disc, the X and Z
        # ones only for the classes that carry them. And render_walk hands the
        # matrix builder the Y angle **plus 0x800** -- `addiu $v0, $v0, 0x800`
        # at 0x80041374 -- so every object is drawn half a turn round from its
        # record. This file left that out for as long as it placed objects:
        # symmetric things hid it, and a door stood closed inside its wall.
        rx, ry, rz = o["angles"]
        m = _rot3(rx, ry + 0x800, rz)
        placed += 1
        sx, sy, sz = (v / 4096.0 for v in o["scale"])
        ox, oy, oz = o["x"], o["y"], o["z"]
        # A door turns on its hinge, so it is a node of its own with its
        # vertices about its own position (godot/doors.gd).
        door = o["op"] in DOOR_OPS
        if door:
            ox = oy = oz = 0

        def place(v, m=m, sx=sx, sy=sy, sz=sz, ox=ox, oy=oy, oz=oz):
            x, y, z = v[0] * sx, v[1] * sy, v[2] * sz
            ax = m[0][0] * x + m[0][1] * y + m[0][2] * z
            ay = m[1][0] * x + m[1][1] * y + m[1][2] * z
            az = m[2][0] * x + m[2][1] * y + m[2][2] * z
            return ((ox + ax) / UNIT, -(oy + ay) / UNIT, -(oz + az) / UNIT)

        def spin_normal(n, m=m):
            # The same matrix the vertices go through, so a tilted object is
            # lit the way it is turned. Only the axis flip is applied after.
            nx, ny, nz = n
            ax = m[0][0] * nx + m[0][1] * ny + m[0][2] * nz
            ay = m[1][0] * nx + m[1][1] * ny + m[1][2] * nz
            az = m[2][0] * nx + m[2][1] * ny + m[2][2] * nz
            return (ax / 4096.0, -ay / 4096.0, -az / 4096.0)

        own = {} if door else groups
        emit_object(objs, place, lambda raw: shade(raw, llm, lcm, bk), own,
                    spin_normal, fog=fog_of(look, c[9] & 0x3F))
        if door:
            doors.append((o, own))

    mats = {}

    def prims_of(bags):
        out_prims, n = [], 0
        for key, (pos, nrm, uv, col, fogs) in bags.items():
            p = g.primitive(pos, nrm, uv, col, fogs)
            p["material"] = material_for(g, mats, out, lv, key, vram)
            out_prims.append(p)
            n += len(pos) // 3
        return out_prims, n

    prims, ntri = prims_of(groups)
    if not prims:
        print("no objects placed")
        return None
    items = [(f"objects{lv}", prims, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))]
    lifts = build_lifts(lv, load, grid, look, prims_of, door_rows)
    items += lifts
    loot_rows = []
    items += build_loot(lv, load, grid, look, prims_of, loot_rows, loot)
    spawn = {}
    items += build_drops(lv, load, look, prims_of, spawn)
    keys, pedestal_rows = {}, []
    items += build_pedestals(lv, load, look, prims_of, pedestal_rows, keys)
    with open(f"{out}/loot{lv:02d}.json", "w") as f:
        json.dump({"rows": loot_rows, "spawn": spawn, "pedestals": pedestal_rows,
                   "keys": keys, "find": find_rows(load),
                   # the class (byte 0) of each of the level's 332 type rows,
                   # which level_state_write looks a thing's arm up by
                   "classes": [r[0] if r else 0 for r in load.rows[:332]]},
                  f, separators=(",", ":"))
    for o, bags in doors:
        dp, dn = prims_of(bags)
        ntri += dn
        items.append((f"d{o['slot']:03d}", dp,
                      (o["x"] / UNIT, -o["y"] / UNIT, -o["z"] / UNIT),
                      (0.0, 0.0, 0.0, 1.0)))
        tr = load.rows[o["type"]]
        door_rows.append({
            "slot": o["slot"], "type": o["type"], "op": o["op"],
            "x": o["x"], "y": o["y"], "z": o["z"], "yaw": o["angles"][1],
            "b0": o["b0"], "height": o["height"], "tail": list(o["tail"][:8]),
            "reach": struct.unpack_from("<H", tr, 6)[0],
            "w": tr[0xD], "h": tr[0xE]})
    path, nbytes = g.write_nodes(f"{out}/objects{lv:02d}.gltf", items)
    with open(f"{out}/doors{lv:02d}.json", "w") as f:
        json.dump(door_rows, f, separators=(",", ":"))
    print(f"objects: {placed} placed, {len(doors)} of them doors on their own "
          f"node, {len(lifts)} lift doors and gates, {len(loot_rows)} chests, things to take and "
          f"things to read, {missing} without a model, {hidden} the game does not draw, "
          f"{ntri} triangles, {len(mats)} materials -> {path}")
    return path


LOOT_OPS = (6, 7)        # the small chest's lid and the big chest (tools/chests.py)
SEAL_OPS = (0x17, 0x1A)  # Orladin's seals and pedestals, which fade away (tools/seals.py)
ITEM_CLASS = 0x40        # what object_give hands over


def loot_slots(load):
    """The objects that are nodes of their own for godot/loot.gd: every chest
    (opcodes 6 and 7), every class-0x40 thing the game draws, and what the
    chests hide -- the slot each one's +0x3a names, hidden on their first
    frame and shown when they open -- and Orladin's seals and pedestals
    (opcodes 0x17 and 0x1a), which go, with what a seal holds (+0x3a) and
    the key it raises (+0x3c)."""
    out = set()
    for k, o in load.recs.items():
        if o["op"] in LOOT_OPS + SEAL_OPS:
            out.add(k)
            for at in {6: (2,), 7: (2,), 0x17: (2, 4)}.get(o["op"], ()):
                inside = struct.unpack_from("<H", o["tail"], at)[0]
                if inside in load.recs and load.recs[inside]["cls"] == ITEM_CLASS:
                    out.add(inside)
        elif o["cls"] == ITEM_CLASS and load.drawn(o):
            out.add(k)
    return out


def droppable(lv, load):
    """The types a creature on level `lv` can leave when it dies: the gold
    (0x95), what each category-1 creature was placed with (its +0xb), and the
    thing each kind's dying behaviour names at its +0xc (tools/ai.py drops)."""
    import actors as act
    import ai
    out = {0x95}
    for a in act.table(lv):
        if a and a["cat"] == 1 and a["b6"] != 0xFF:
            out.add(a["b6"])
    for k in sorted({a["kind"] for a in act.table(lv) if a}):
        try:
            kd = ai.kind_of(lv, k)
        except Exception:
            continue
        for b in kd.get("behaviours", []):
            raw = b["raw"]
            if b["op"] == 3 and raw[0xC] != 0xFF:
                out.add(raw[0xC])
    return sorted(t for t in out if t < len(load.rows))


def build_drops(lv, load, look, prims_of, spawn):
    """A hidden node, `tNNN` by type, for everything droppable(): godot/loot.gd
    copies it when a creature leaves one. Its rows go to lootNN.json's
    "spawn": what object_give and the falls (tools/chests.py) need of the type
    row. Lit by class 0, as the held weapon is."""
    import chests
    items = []
    llm, lcm, bk = light_class(look, 0, 0)
    for t in droppable(lv, load):
        try:
            _flags, objs = tmd.load(*tmd.model_of(t, lv))
        except Exception:
            continue
        tr = load.rows[t]
        k = 2.0 if tr[3] & 0x10 else 1.0              # spawn_thing doubles the scale
        own = {}
        emit_object(objs, lambda v, k=k: (v[0] * k / UNIT, -v[1] * k / UNIT,
                                          -v[2] * k / UNIT),
                    lambda raw: shade(raw, llm, lcm, bk), own)
        dp, _dn = prims_of(own)
        if not dp:
            continue
        items.append((f"t{t:03d}", dp, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)))
        spawn[str(t)] = {
            "type": t, "kind": tr[1], "flags": tr[3],
            "reach": struct.unpack_from("<H", tr, 6)[0],
            "top": struct.unpack_from("<H", tr, 8)[0],
            "c": struct.unpack_from("<h", tr, 0xC)[0],
            "e": struct.unpack_from("<h", tr, 0xE)[0],
            "op": 0x62 if t == chests.GOLD_TYPE else chests.DROP_OP.get(tr[1], 0xFF),
            "rest": 0 if (t == chests.GOLD_TYPE or t in chests.LIE_FLAT) else 0x400}
    return items


def build_loot(lv, load, grid, look, prims_of, rows, slots):
    """The chests and the things to take, one node each, `kNNN` by slot, and
    their rows for lootNN.json.

    The vertices are the model's own, scaled but not turned, and the node
    carries the place and the turn: a lid turns about its hinge as it opens
    (its X angle, +0x24), a thing taken flies to the eye and spins, and a big
    chest's model is posed by its counter (godot/anim.gd), which needs the
    vertices unturned to match its poses to."""
    items = []
    for k in sorted(slots):
        o = load.recs[k]
        try:
            _flags, objs = tmd.load(*tmd.model_of(o["type"], lv))
        except Exception:
            continue
        cx, cz = o["x"] >> 11, o["z"] >> 11
        if not (0 <= cx < W and 0 <= cz < W):
            continue
        c = grid[(cz * W + cx) * CELLB:(cz * W + cx) * CELLB + CELLB]
        llm, lcm, bk = light_class(look, c[9] & 0x3F, c[7] & 3)
        sx, sy, sz = (v / 4096.0 for v in o["scale"])
        own = {}
        emit_object(objs, lambda v, sx=sx, sy=sy, sz=sz: (v[0] * sx / UNIT,
                                                         -v[1] * sy / UNIT,
                                                         -v[2] * sz / UNIT),
                    lambda raw: shade(raw, llm, lcm, bk), own,
                    fog=fog_of(look, c[9] & 0x3F))
        dp, _dn = prims_of(own)
        if not dp:
            continue
        rx, ry, rz = o["angles"]
        items.append((f"k{k:03d}", dp, (o["x"] / UNIT, -o["y"] / UNIT, -o["z"] / UNIT),
                      quaternion(_rot3(rx, ry + 0x800, rz))))
        tr = load.rows[o["type"]]
        tail = o["tail"]
        # what a chest or a seal hides as the loader left it: loot.gd runs
        # the first frame, after the level's record
        b0, lock = getattr(load, "loaded", {}).get(k, (o["b0"], tail[0]))
        rows.append({
            "slot": k, "cls": o["cls"], "op": o["op"], "type": o["type"],
            "x": o["x"], "y": o["y"], "z": o["z"], "angles": list(o["angles"]),
            "b0": b0, "b1": o.get("b1", 0x80),
            "lock": lock, "inside": struct.unpack_from("<H", tail, 2)[0],
            "trap": tail[4], "tail": list(tail[:8]),
            "reach": struct.unpack_from("<H", tr, 6)[0],
            "top": struct.unpack_from("<H", tr, 8)[0],
            # object_give's row: +1 0x20 for gold, the flight's +0xc and +0xe
            "kind": tr[1], "c": struct.unpack_from("<h", tr, 0xC)[0],
            "e": struct.unpack_from("<h", tr, 0xE)[0],
            "model": lift_model(o["type"], lv)})
    # and what object_interact reads (.L38): rows only, the objects stay where
    # the level's own mesh has them, or nowhere -- type 299 is not drawn
    import readables
    for k, o in sorted(load.recs.items()):
        if o["cls"] not in readables.READ_CLASSES:
            continue
        tr = load.rows[o["type"]]
        rows.append({
            "slot": k, "cls": o["cls"], "op": o["op"], "type": o["type"],
            "x": o["x"], "y": o["y"], "z": o["z"], "angles": list(o["angles"]),
            "b0": o["b0"], "b1": o.get("b1", 0x80), "lock": o["tail"][0],
            "text": struct.unpack_from("<H", o["tail"], 0)[0],
            "facing": o["tail"][5], "on": o["tail"][6], "inside": 0xFFFF,
            "trap": 0xFF, "reach": struct.unpack_from("<H", tr, 6)[0],
            "top": struct.unpack_from("<H", tr, 8)[0], "kind": tr[1],
            "c": 0, "e": 0, "model": 0})
    return items


PEDESTAL_OPS = (0x18,)
# use_item's arms: Silviera's key asks for type 0x101, Orladin's for 0x102
# (whose pedestals, opcode 0x1a, are loot.gd's rows: tools/seals.py); level
# 23's own entry 2 puts 0x86 on its type 0x13f (tools/useitem.py level_use)
PEDESTAL_KEYS = {0x101: 141, 0x102: 0x88, 0x13F: 0x86}


def build_pedestals(lv, load, look, prims_of, rows, keys):
    """The pedestals (opcode 0x18), their rows for lootNN.json, and a hidden
    node `qNNN` for each key a pedestal takes here -- Silviera's, 141, on a
    type-0x101 pedestal, and Orladin's, 0x88, on a type-0x102 one (opcode
    0x1a) -- which godot/loot.gd copies when the key is put there. At the
    model's own size: object_use_state's init_object_record leaves the scale
    0x1000, where a drop's is doubled. Lit by class 0."""
    items, wanted = [], set()
    for k, o in sorted(load.recs.items()):
        if o["op"] == 0x1A and o["type"] in PEDESTAL_KEYS:
            wanted.add(PEDESTAL_KEYS[o["type"]])
        if o["op"] not in PEDESTAL_OPS:
            continue
        tr = load.rows[o["type"]]
        rows.append({"slot": k, "type": o["type"], "op": o["op"],
                     "x": o["x"], "y": o["y"], "z": o["z"], "angles": list(o["angles"]),
                     "b0": o["b0"], "tail": list(o["tail"][:8]),
                     "reach": struct.unpack_from("<H", tr, 6)[0],
                     "top": struct.unpack_from("<H", tr, 8)[0]})
        if o["type"] in PEDESTAL_KEYS:
            wanted.add(PEDESTAL_KEYS[o["type"]])
    llm, lcm, bk = light_class(look, 0, 0)
    for t in sorted(wanted):
        try:
            _flags, objs = tmd.load(*tmd.model_of(t, lv))
        except Exception:
            continue
        own = {}
        emit_object(objs, lambda v: (v[0] / UNIT, -v[1] / UNIT, -v[2] / UNIT),
                    lambda raw: shade(raw, llm, lcm, bk), own)
        dp, _dn = prims_of(own)
        if not dp:
            continue
        items.append((f"q{t:03d}", dp, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)))
        tr = load.rows[t]
        keys[str(t)] = {
            "type": t, "kind": tr[1],
            "reach": struct.unpack_from("<H", tr, 6)[0],
            "top": struct.unpack_from("<H", tr, 8)[0],
            "c": struct.unpack_from("<h", tr, 0xC)[0],
            "e": struct.unpack_from("<h", tr, 0xE)[0]}
    return items


def find_rows(load):
    """find_object's view of every object the level places: [slot, class,
    type, x, y, z, yaw, the record's +0xc, the type's +6 and +8] -- what it
    tests a point against, for godot/loot.gd find_object -- and the opcode
    and the lock (+0x38) key_test asks of what it finds; then +0x39 and the
    halfword at +0x3a, which with the rest are what level_state_write reads of
    a slot (godot/levelstate.gd's table); then the record's +0 and +0x40 as
    the loader leaves them, which use_item's truth glass asks (godot/useitem.gd),
    and +0x3d, the thing level 5's own entry 2 asks an opcode-0x53 object for."""
    out = []
    for k, o in sorted(load.recs.items()):
        tr = load.rows[o["type"]]
        out.append([k, o["cls"], o["type"], o["x"], o["y"], o["z"], o["angles"][1],
                    o["height"], struct.unpack_from("<H", tr, 6)[0],
                    struct.unpack_from("<H", tr, 8)[0], o["op"], o["tail"][0],
                    o["tail"][1], struct.unpack_from("<H", bytes(o["tail"]), 2)[0],
                    o["b0"], o["tail"][8], o["tail"][5]])
    return out


def quaternion(m):
    """The game's rotation matrix `m` (_rot3), as a Godot quaternion (x, y, z,
    w): with x kept and y and z negated, M becomes F M F, F = diag(1, -1, -1)."""
    f = (1.0, -1.0, -1.0)
    r = [[f[i] * m[i][j] * f[j] for j in range(3)] for i in range(3)]
    tr = r[0][0] + r[1][1] + r[2][2]
    if tr > 0:
        k = math.sqrt(tr + 1.0) * 2
        return ((r[2][1] - r[1][2]) / k, (r[0][2] - r[2][0]) / k,
                (r[1][0] - r[0][1]) / k, k / 4)
    i = max(range(3), key=lambda a: r[a][a])
    j, k_ = (i + 1) % 3, (i + 2) % 3
    k = math.sqrt(1.0 + r[i][i] - r[j][j] - r[k_][k_]) * 2
    q = [0.0, 0.0, 0.0, (r[k_][j] - r[j][k_]) / k]
    q[i] = k / 4
    q[j] = (r[j][i] + r[i][j]) / k
    q[k_] = (r[k_][i] + r[i][k_]) / k
    return tuple(q)


def lift_model(type_id, lv):
    """The key godot/anim.gd files a lift door's model under: its MO.T entry,
    or MO_COUNT on for MOF.T -- the numbering tools/anim.py load takes."""
    arch, entry = tmd.model_of(type_id, lv)
    return entry if arch == "MO" else tmd.MO_COUNT + entry


def build_lifts(lv, load, grid, look, prims_of, rows):
    """The lift doors' models, one node each, `lNNN` by slot, and their rows
    in doorsNN.json.

    The loader leaves a lift door's scale at 0, so render_walk draws nothing
    of it while it is shut; the arm sets the scale to 0x1000 when it starts to
    lift and draws the model through draw_model_plain (its +3 is 3, no 0x40 or
    8), animated -- the animation the record's +1 names, 0, at the clock of
    its counter +0xa (the stack arguments 0x1c and 0x20 of the call at
    0x800414a4). So the vertices here are the model's own, unturned and at
    scale 1, which is what godot/anim.gd matches its poses to, and the node
    carries the turn: the angles with 0x800 on the yaw, as for every object.
    """
    import doors
    items = []
    for k, o in sorted(load.recs.items()):
        if o["op"] not in doors.LIFT_OPS + doors.GATE_OPS + doors.WALL_OPS:
            continue
        try:
            _flags, objs = tmd.load(*tmd.model_of(o["type"], lv))
        except Exception:
            continue
        cx, cz = o["x"] >> 11, o["z"] >> 11
        c = grid[(cz * W + cx) * CELLB:(cz * W + cx) * CELLB + CELLB]
        llm, lcm, bk = light_class(look, c[9] & 0x3F, c[7] & 3)
        rx, ry, rz = o["angles"]
        m = _rot3(rx, ry + 0x800, rz)
        # vertices and normals both unturned: the node turns them
        own = {}
        emit_object(objs, lambda v: (v[0] / UNIT, -v[1] / UNIT, -v[2] / UNIT),
                    lambda raw: shade(raw, llm, lcm, bk), own,
                    fog=fog_of(look, c[9] & 0x3F))
        dp, _dn = prims_of(own)
        items.append((f"l{k:03d}", dp, (o["x"] / UNIT, -o["y"] / UNIT, -o["z"] / UNIT),
                      quaternion(m)))
        tr = load.rows[o["type"]]
        if o["op"] in doors.GATE_OPS:
            # a gate: stamp_rect from its templates, the model standing shut
            rows.append({
                "slot": k, "type": o["type"], "op": o["op"],
                "x": o["x"], "y": o["y"], "z": o["z"], "yaw": o["angles"][1],
                "b0": o["b0"], "height": o["height"], "tail": list(o["tail"][:8]),
                "reach": struct.unpack_from("<H", tr, 6)[0],
                "top": struct.unpack_from("<H", tr, 8)[0],
                "w": tr[0xD], "h": tr[0xE],
                "model": lift_model(o["type"], lv), "anim": o.get("b1", 0)})
            continue
        shape, tile = doors.lift_stamps(load, o)
        row = {
            "slot": k, "type": o["type"], "op": o["op"],
            "x": o["x"], "y": o["y"], "z": o["z"], "yaw": o["angles"][1],
            "b0": o["b0"], "height": o["height"], "tail": list(o["tail"][:8]),
            "reach": struct.unpack_from("<H", tr, 6)[0],
            "top": struct.unpack_from("<H", tr, 8)[0],
            "model": lift_model(o["type"], lv), "anim": o.get("b1", 0),
            # stamp_table's two tables: cells and each entry's eight bytes,
            # and which layer of the port's collision cells (0 or 3) is the
            # upper one the entry's first and third bytes go to
            "stamps": [[[x, z, list(q)] for x, z, q in t] for t in (shape, tile)],
            "hi": 3 if o["b0"] != 1 else 0}
        if o["op"] in doors.WALL_OPS:
            # a hidden wall: one table for both, laid with the +0 the loader
            # kept at +0x40; the rectangle the player opens it from
            row["hi"] = 3 if o["tail"][8] != 1 else 0
            row["rect"] = list(doors.wall_rect(o["tail"]))
            row["stay"] = bool(o["tail"][6] & 2)
        rows.append(row)
    return items


# The sky. render_walk (0x80040ae4) gives an object of class 0xf0 a path of its
# own: while sky_on (0x801aeaea) is set and object_in_view passes, it draws
# model_table[type - 0xdd] through sub_800400ac -- the angles at +0x24 made a
# matrix and turned by the view, but **no translation but (0, 0x64, 0), in view
# space**: the model sits on the eye, 100 below it, whatever the player's
# position -- lit by the class at +0x3b, its faces filed in the side ordering
# table that frame_end_3d links in at 0x1ffe, so everything else is drawn over
# it. Levels
# 0-7 and 9-11 place one, type 265, which is model 44 of the resident bank: a
# textured dome 1000 across and 1250 high, 97 vertices and 96 faces, lit by
# class 0x3d.
#
# Class 0xe3 objects switch it: each frame the interpreter (0x8004a954) asks
# player_in_rect of each one's cell rectangle, +0x38 by +0x39 cells, and one
# that holds the player writes its +0x3a to 0x801aeae9 and +0x3b to sky_on, so
# the last in slot order wins; game_main starts sky_on at 1 (0x80035610).
SKY_CLASS = 0xF0
SKY_MODEL_BASE = 0xDD        # model_table[type - 0xdd], at 0x80040fe0
SKY_LIFT = 0x64              # the view-space translation, 0x800400e8
ZONE_CLASS = 0xE3


def build_sky_gltf(lv, out="out/godot"):
    """The sky dome as `skyNN.gltf`, and the zones that switch it as `skyNN.json`."""
    import json
    import modelbank
    import objload
    load = objload.Load(lv)
    recs = [r for _k, r in sorted(load.recs.items())]
    zones = [[r["x"] >> 11, r["z"] >> 11, r["tail"][0], r["tail"][1],
              r["tail"][2], r["tail"][3]] for r in recs if r["cls"] == ZONE_CLASS]
    skies = [r for r in recs if r["cls"] == SKY_CLASS]
    gl = f"{out}/sky{lv:02d}.gltf"
    doc = {"zones": zones, "lift": SKY_LIFT, "sky": bool(skies)}
    with open(f"{out}/sky{lv:02d}.json", "w") as f:
        json.dump(doc, f, separators=(",", ":"))
    if not skies:
        for leftover in (gl, gl[:-5] + ".bin"):
            if os.path.exists(leftover):
                os.remove(leftover)
        print(f"sky: none on level {lv}, {len(zones)} zones")
        return None
    o = skies[0]
    index = o["type"] - SKY_MODEL_BASE
    _flags, objs = modelbank.load(index)
    look = lighting.table()
    llm, lcm, bk = light_class(look, o["tail"][3] & 0x7F, 0)
    rx, ry, rz = o["angles"]
    m = _rot3(rx, ry, rz)              # no + 0x800 on this path

    def place(v, m=m):
        x, y, z = v
        return ((m[0][0] * x + m[0][1] * y + m[0][2] * z) / UNIT,
                -(m[1][0] * x + m[1][1] * y + m[1][2] * z) / UNIT,
                -(m[2][0] * x + m[2][1] * y + m[2][2] * z) / UNIT)

    groups = {}
    emit_object(objs, place, lambda raw: shade(raw, llm, lcm, bk), groups)
    g = gltf.Gltf()
    mats = {}
    vram = object_vram(lv)
    prims = []
    ntri = 0
    for key, (pos, nrm, uv, col, fogs) in groups.items():
        p = g.primitive(pos, nrm, uv, col, fogs)
        p["material"] = material_for(g, mats, out, lv, key, vram)
        prims.append(p)
        ntri += len(pos) // 3
    path, _n = g.write_nodes(gl, [("sky", prims, (0.0, 0.0, 0.0),
                                   (0.0, 0.0, 0.0, 1.0))])
    print(f"sky: slot {o['slot']}, type {o['type']} -> model {index}, "
          f"{ntri} triangles, lit by class {o['tail'][3]:#x}, "
          f"{len(zones)} zones -> {path}")
    return path


PROJECT = """config_version=5

[application]
config/name="King's Field II - level {lv}"
run/main_scene="res://boot.tscn"
config/features=PackedStringArray("4.2", "GL Compatibility")

[rendering]
renderer/rendering_method="gl_compatibility"
textures/canvas_textures/default_texture_filter=0

[importer_defaults]

texture={{
"compress/mode": 0,
"detect_3d/compress_to": 0,
"mipmaps/generate": false,
"process/fix_alpha_border": false
}}
"""

# The camera sees what the game's does. The GTE's projection distance is H = 200
# -- SetGeomScreen(200), `ctc2 $t4, H` at 0x800353f8 and again at 0x800354d4,
# and sub_8004290c sets the same -- on a 320x240 screen centred at (160, 120),
# so the vertical field of view is 2 * atan(120 / 200) = 61.93 degrees and the
# horizontal, at 4:3, 77.3. Godot's own 75 vertical showed more than the game
# above and below. The eye is 1.6 up because sync_player_pos forms it as
# player Y + EYE_HEIGHT, 0x640.
# A .gltf imports as a scene, so it is instanced rather than assigned to a mesh.
# There are **no lights**: the materials are unlit and carry the game's own
# lighting in their vertex colours. Adding a light here would shade the level a
# second time, over shading it already has.
SCENE = """[gd_scene load_steps={load_steps} format=3]

[ext_resource type="PackedScene" path="res://level{lv:02d}.gltf" id="1"]
[ext_resource type="Script" path="res://player.gd" id="2"]
[ext_resource type="PackedScene" path="res://collision{lv:02d}.gltf" id="3"]
[ext_resource type="PackedScene" path="res://objects{lv:02d}.gltf" id="4"]
[ext_resource type="PackedScene" path="res://actors{lv:02d}.gltf" id="7"]
[ext_resource type="Script" path="res://actors.gd" id="16"]
[ext_resource type="Script" path="res://ghost.gd" id="5"]
[ext_resource type="Script" path="res://labels.gd" id="6"]
[ext_resource type="Script" path="res://cutscene.gd" id="14"]
[ext_resource type="Script" path="res://scroll.gd" id="17"]
[ext_resource type="Script" path="res://doors.gd" id="18"]
[ext_resource type="Script" path="res://sky.gd" id="19"]
[ext_resource type="Script" path="res://hud.gd" id="20"]
[ext_resource type="Script" path="res://compass.gd" id="21"]
[ext_resource type="PackedScene" path="res://effects{lv:02d}.gltf" id="22"]
[ext_resource type="Script" path="res://effects.gd" id="23"]
[ext_resource type="PackedScene" path="res://held{lv:02d}.gltf" id="24"]
[ext_resource type="Script" path="res://held.gd" id="25"]
[ext_resource type="Script" path="res://loot.gd" id="26"]
[ext_resource type="Script" path="res://messages.gd" id="27"]
[ext_resource type="Script" path="res://document.gd" id="28"]
[ext_resource type="Script" path="res://info.gd" id="29"]
[ext_resource type="Script" path="res://menu.gd" id="30"]
[ext_resource type="Script" path="res://crossing.gd" id="31"]
{gallery_res}

[sub_resource type="Environment" id="Env"]
background_mode = 1
background_color = Color(0.02, 0.02, 0.03, 1)
ambient_light_source = 0

[node name="World" type="Node3D"]

[node name="Level" parent="." instance=ExtResource("1")]

[node name="Objects" parent="." instance=ExtResource("4")]

[node name="Creatures" parent="." instance=ExtResource("7")]

[node name="CollisionView" parent="." instance=ExtResource("3")]
visible = false

[node name="WorldEnvironment" type="WorldEnvironment" parent="."]
environment = SubResource("Env")

[node name="Player" type="Node3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, {px:.2f}, {py:.2f}, {pz:.2f})
script = ExtResource("2")

[node name="Camera" type="Camera3D" parent="Player"]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 1.6, 0)
current = true
fov = 61.9275
far = 400.0

[node name="Held" type="Node3D" parent="Player/Camera"]
script = ExtResource("25")

[node name="HeldModels" parent="Player/Camera/Held" instance=ExtResource("24")]
visible = false

[node name="Actors" type="Node" parent="."]
script = ExtResource("16")

[node name="EffectModels" parent="." instance=ExtResource("22")]
visible = false

[node name="Effects" type="Node3D" parent="."]
script = ExtResource("23")

[node name="Doors" type="Node" parent="."]
script = ExtResource("18")

[node name="Loot" type="Node" parent="."]
script = ExtResource("26")

[node name="Info" type="Node" parent="."]
script = ExtResource("29")

[node name="Crossing" type="Node" parent="."]
script = ExtResource("31")

[node name="Scroll" type="Node" parent="."]
script = ExtResource("17")

[node name="Sky" type="Node3D" parent="."]
script = ExtResource("19")

[node name="Ghost" type="Node3D" parent="."]
script = ExtResource("5")

[node name="Gallery" type="Node3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 400, 0)
visible = false
{gallery_nodes}

[node name="Labels" type="Node3D" parent="."]
script = ExtResource("6")

[node name="Cutscene" type="CanvasLayer" parent="."]
script = ExtResource("14")

[node name="UI" type="CanvasLayer" parent="."]

[node name="Panel" type="Control" parent="UI"]
anchors_preset = 15
anchor_right = 1.0
anchor_bottom = 1.0
mouse_filter = 2
script = ExtResource("20")

[node name="Messages" type="Control" parent="UI"]
anchors_preset = 15
anchor_right = 1.0
anchor_bottom = 1.0
mouse_filter = 2
script = ExtResource("27")

[node name="Menu" type="Control" parent="UI"]
anchors_preset = 15
anchor_right = 1.0
anchor_bottom = 1.0
mouse_filter = 2
script = ExtResource("30")

[node name="Document" type="Control" parent="UI"]
anchors_preset = 15
anchor_right = 1.0
anchor_bottom = 1.0
mouse_filter = 2
script = ExtResource("28")

[node name="Compass" type="Control" parent="UI"]
anchors_preset = 15
anchor_right = 1.0
anchor_bottom = 1.0
mouse_filter = 2
script = ExtResource("21")

[node name="Hud" type="Label" parent="UI"]
offset_left = 12.0
offset_top = 8.0
text = "F1  walk / fly    N  object labels    K  the model gallery"

[node name="Compare" type="Label" parent="UI"]
offset_left = 12.0
offset_top = 96.0
text = "C  compare with the emulator"
"""

BOOT_SCENE = """[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://boot.gd" id="1"]

[node name="Shell" type="Node"]
script = ExtResource("1")
"""

PLAYER = '''extends CharacterBody3D
# Two ways round the level, because both are needed.
#
#   WALK  collides with the level mesh, has gravity and a step up
#   FLY   passes through everything -- which is the point: this level has
#         rooms the game never lets you reach, and the only way to look at
#         them is to go through the wall
#
#   F   walk / fly          G   show the game\'s own collision
#   Space  jump             Shift  faster        Escape  release the mouse
#
# The readout gives the cell you are standing in, in the game\'s own numbering,
# so anything found here can be pointed at in the data.

const WALK := 4.5
const FLY := 9.0
const GRAVITY := 18.0
const JUMP := 6.0
const CELL := 2.048

var flying := true
var pitch := 0.0

func _ready() -> void:
    Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
    _ensure_collision(get_node_or_null("../Level"))
    _refresh()

func _ensure_collision(n: Node) -> void:
    # The `-col` suffix on the glTF node should have built this at import time.
    # Doing it again here takes a moment and removes the dependence on an import
    # hint quietly not applying, which would leave the level with no floor at all.
    if n == null:
        return
    if n is MeshInstance3D and n.get_child_count() == 0:
        n.create_trimesh_collision()
    for c in n.get_children():
        _ensure_collision(c)

func _refresh() -> void:
    $Shape.disabled = flying
    var hud := get_node_or_null("../UI/Hud")
    if hud:
        var cx := int(floor(position.x / CELL))
        var cz := int(floor(-position.z / CELL))
        hud.text = "%s   cell (%d, %d)   height %.2f\\nF walk/fly   G collision   Esc mouse" % [
            "FLY" if flying else "WALK", cx, cz, position.y]

func _unhandled_input(e: InputEvent) -> void:
    if e is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
        rotate_y(-e.relative.x * 0.003)
        pitch = clamp(pitch - e.relative.y * 0.003, -1.4, 1.4)
        $Camera.rotation.x = pitch
    elif e is InputEventKey and e.pressed and not e.echo:
        match e.keycode:
            KEY_F:
                flying = not flying
                velocity = Vector3.ZERO
                _refresh()
            KEY_G:
                var v := get_node_or_null("../CollisionView")
                if v:
                    v.visible = not v.visible
            KEY_ESCAPE:
                Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
            KEY_TAB:
                Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func _physics_process(dt: float) -> void:
    var dir := Vector3.ZERO
    if Input.is_key_pressed(KEY_W): dir -= transform.basis.z
    if Input.is_key_pressed(KEY_S): dir += transform.basis.z
    if Input.is_key_pressed(KEY_A): dir -= transform.basis.x
    if Input.is_key_pressed(KEY_D): dir += transform.basis.x
    var fast := 3.0 if Input.is_key_pressed(KEY_SHIFT) else 1.0

    if flying:
        if Input.is_key_pressed(KEY_Q): dir -= Vector3.UP
        if Input.is_key_pressed(KEY_E): dir += Vector3.UP
        # moved directly, so nothing is asked of the physics engine and
        # nothing stops us
        position += dir.normalized() * FLY * fast * dt
    else:
        var flat := Vector3(dir.x, 0, dir.z).normalized()
        velocity.x = flat.x * WALK * fast
        velocity.z = flat.z * WALK * fast
        velocity.y -= GRAVITY * dt
        if is_on_floor() and Input.is_key_pressed(KEY_SPACE):
            velocity.y = JUMP
        move_and_slide()
    _refresh()
'''


def project(lv, out="out/godot", start=(57, 4)):
    """Write the Godot side: the scene, the scripts, and the collision data.

    The scripts live in `godot/` rather than in string literals here, so they
    can be edited as code.
    """
    import shutil
    import gdcoll
    grid = grid_of(lv)
    cx, cz = start
    h = grid[(cz * W + cx) * CELLB + 6]
    px = (cx * CELL + CELL // 2) / UNIT
    pz = -(cz * CELL + CELL // 2) / UNIT
    py = 128 * h / UNIT                          # the feet; the camera sits 1.6 up
    os.makedirs(out, exist_ok=True)
    open(f"{out}/project.godot", "w").write(PROJECT.format(lv=lv))
    # The gallery decides how many pieces there are -- Godot takes at most 256
    # surfaces in a mesh -- so it is built before the scene that names them.
    import gallery
    import glob
    gallery.build(out=out)
    gallery.world_labels(lv, out)
    pieces = sorted(glob.glob(f"{out}/gallery*.gltf"))
    # The gallery's ids start at 100. They once started at 7, which is the id
    # the creatures were given, and a repeated id in a .tscn is not an error:
    # Godot keeps the last one. So the Creatures node quietly instanced a slab
    # of the model gallery and `actors00.gltf` was never placed in the world at
    # all -- which reads, in the running port, as a level with no monsters in
    # it. Then they started at 8, under ids 14 to 16 given out by hand, which
    # holds only while the gallery has six pieces or fewer.
    res = "\n".join(f'[ext_resource type="PackedScene" '
                    f'path="res://{os.path.basename(q)}" id="{100 + i}"]'
                    for i, q in enumerate(pieces))
    nodes = "\n".join(f'\n[node name="g{i}" parent="Gallery" '
                       f'instance=ExtResource("{100 + i}")]'
                       for i in range(len(pieces)))
    scene = SCENE.format(lv=lv, px=px, py=py, pz=pz, gallery_res=res,
                         gallery_nodes=nodes, load_steps=24 + len(pieces))
    # world.tscn is the level built last, which the project is named for;
    # worldNN.tscn stays for each level built, for a crossing to load
    open(f"{out}/world.tscn", "w").write(scene)
    open(f"{out}/world{lv:02d}.tscn", "w").write(scene)
    # The boot chain: the shell, the opening and the pad, which is where the
    # project now starts. world.tscn is still the level and boot.gd hands over
    # to it the way SLUS_002.55 hands over to GAME.EXE.
    open(f"{out}/boot.tscn", "w").write(BOOT_SCENE)
    for name in ("player.gd", "collision.gd", "selftest.gd", "ghost.gd",
                 "labels.gd", "pad.gd", "boot.gd", "opening.gd",
                 "cutscene.gd", "actors.gd", "levelup.gd",
                 "game.gd", "objects.gd", "escript.gd", "items.gd",
                 "damage.gd", "equip.gd", "objcoll.gd", "scroll.gd",
                 "doors.gd", "sky.gd", "hud.gd", "compass.gd", "ai.gd",
                 "weapon.gd", "anim.gd", "effects.gd", "held.gd",
                 "loot.gd", "messages.gd", "document.gd", "talk.gd", "info.gd", "menu.gd",
                 "crossing.gd", "card.gd", "levelstate.gd", "loadscreen.gd", "useitem.gd"):
        shutil.copyfile(f"godot/{name}", f"{out}/{name}")
    try:
        import opening
        opening.main(f"{out}/opening")
    except Exception as e:                       # no disc image, no title screen
        print(f"opening assets skipped: {e}")
    gdcoll.export(lv, out)
    try:
        import spells
        spells.export(out)
    except Exception as e:                       # no disc, no spells
        print(f"spells skipped: {e}")
    try:
        import strings
        strings.export(out)
    except Exception as e:                       # no disc, no strings
        print(f"strings skipped: {e}")
    try:
        import itemtext
        itemtext.export(out)
    except Exception as e:                       # no disc, no item names
        print(f"item names skipped: {e}")
    try:
        import damage
        damage.export(out)
    except Exception as e:                       # no log, no recorded hits
        print(f"damage cases skipped: {e}")
    try:
        import knock
        knock.export(out)
    except Exception as e:
        print(f"knock-back cases skipped: {e}")
    try:
        import weapon
        weapon.export(out)
    except Exception as e:
        print(f"weapon cases skipped: {e}")
    try:
        import anim
        anim.export(out, lv)
    except Exception as e:
        print(f"creature animation skipped: {e}")
    try:
        import effects
        effects.export(out)
        effects.export_strikes(out)
    except Exception as e:
        print(f"effect cases skipped: {e}")
    try:
        import doors
        doors.export(out)
    except Exception as e:
        print(f"lift door cases skipped: {e}")
    try:
        import chests
        chests.export(out)
    except Exception as e:
        print(f"chest cases skipped: {e}")
    try:
        import seals
        seals.export(out)
    except Exception as e:
        print(f"seal cases skipped: {e}")
    try:
        import fade
        fade.export(out)
    except Exception as e:
        print(f"fade cases skipped: {e}")
    try:
        import routines
        routines.export(out)
    except Exception as e:
        print(f"routine cases skipped: {e}")
    try:
        import readables
        readables.export(out, lv)
    except Exception as e:
        print(f"inscriptions skipped: {e}")
    try:
        import talk
        talk.export(out, lv)
    except Exception as e:
        print(f"conversations skipped: {e}")
    try:
        import ui
        ui.export(out)
        ui.export_guide(out)
    except Exception as e:
        print(f"menu pages skipped: {e}")
    try:
        import crossing
        crossing.export(out, lv)
    except Exception as e:
        print(f"crossings skipped: {e}")
    try:
        import escript
        escript.export(out)
    except Exception as e:                       # no disc, no scripts
        print(f"entity scripts skipped: {e}")
    try:
        import actors
        actors.export(out)
    except Exception as e:                       # no disc, no creatures
        print(f"actors skipped: {e}")
    try:
        import levelstate
        levelstate.export(out)
        levelstate.export_check(out)
    except Exception as e:                       # no recording, no streams
        print(f"level state skipped: {e}")
    try:
        import status
        status.export(out)
        status.export_tick(out)
        import magic
        magic.export(out)
        magic.export_attacks(out)
        import hit
        hit.export(out)
    except Exception as e:                       # no snapshot of a fresh character
        print(f"take_hit cases skipped: {e}")
    try:
        import replay
        replay.export_caps(out)
    except Exception as e:                       # no bp16 log, no runs
        print(f"run caps skipped: {e}")
    try:
        import memcard
        memcard.export(out)
    except Exception as e:                       # no card, nothing to continue
        print(f"memory card skipped: {e}")
    try:
        import levelmap
        levelmap.export(out)
    except Exception as e:                       # no disc, no maps
        print(f"level maps skipped: {e}")
    try:
        import hud
        hud.export(out)
    except Exception as e:                       # no disc, no panel
        print(f"panel skipped: {e}")
    try:
        import compass
        compass.export(out)
    except Exception as e:                       # no disc, no compass
        print(f"compass skipped: {e}")
    try:
        import ai
        ai.export(out, lv)
    except Exception as e:                       # no disc, no behaviours
        print(f"creature behaviours skipped: {e}")
    try:
        import modelbank
        modelbank.export(out)
    except Exception as e:                       # no disc, no bank
        print(f"model bank skipped: {e}")
    try:
        import props
        props.export(out)
    except Exception as e:                       # no disc, no props
        print(f"props skipped: {e}")
    try:
        import objcoll
        objcoll.export(out)
    except Exception as e:                       # no disc, no collision shapes
        print(f"object collision skipped: {e}")
    try:
        import menutext
        menutext.export(out)
    except Exception as e:                       # no exe, no menu text
        print(f"menu text skipped: {e}")
    try:
        import quest
        quest.export(out)
    except Exception as e:                       # no disc, no quest hooks
        print(f"quest hooks skipped: {e}")
    try:
        import equip
        equip.export(out)
    except Exception as e:                       # no disc, no equipment tables
        print(f"equipment tables skipped: {e}")
    try:
        import objops
        objops.export(out)
    except Exception as e:                       # no snapshot, no object classes
        print(f"object classes skipped: {e}")
    try:
        import levelup
        levelup.export(out)
    except Exception as e:                       # no disc image, no level table
        print(f"level table skipped: {e}")
    try:
        import useitem
        useitem.export(out, lv)
    except Exception as e:                       # no snapshot, no use_item cases
        print(f"use_item cases skipped: {e}")
    print(f"godot project in {out}/ — player starts in cell ({cx},{cz})")


def verify(out="out/godot"):
    """Load the project headless and report anything Godot complains about.

    Worth the seconds it costs: `out/godot` is generated, but it is also a live
    Godot project, and the editor writes into it. A stray keystroke into the
    script editor once left eighteen Cyrillic characters in the middle of
    `collision.gd`, which no amount of reading the source would have found --
    the source was clean and only the copy was broken.
    """
    import shutil
    import subprocess
    godot = shutil.which("godot-4") or shutil.which("godot")
    if not godot:
        print("godot not found; skipping the load check")
        return True
    bad = []
    # --import first, always. Godot only refreshes `.godot/imported/` when the
    # editor runs, so a rebuilt mesh beside a stale cache is shown as the old
    # one, silently. See gallery.reimport.
    for args in (["--import"], ["--quit-after", "60"]):
        r = subprocess.run([godot, "--headless", "--path", out] + args,
                           capture_output=True, text=True, timeout=900)
        for line in (r.stdout + r.stderr).splitlines():
            if "SCRIPT ERROR" in line or line.startswith("ERROR:"):
                bad.append(line.strip())
    if bad:
        print(f"godot reported {len(bad)} problems:")
        for line in bad[:8]:
            print("   " + line)
        return False
    # And then make it answer a question, because loading cleanly only says the
    # syntax is intact. `selftest.gd` replays the frames `tools/movement.py`
    # produced and prints how many of them the GDScript copy reproduced.
    r = subprocess.run([godot, "--headless", "--path", out,
                        "--script", "res://selftest.gd"],
                       capture_output=True, text=True, timeout=900)
    for line in (r.stdout + r.stderr).splitlines():
        if line.startswith(("loaded:", "movement:", "steps:", "creature steps:",
                            "fences:",
                            "creature run:",
                            "levels:", "use_item:", "warp_to:", "angles:",
                            "scripts:", "damage:", "equipment:", "player_recalc_stats:", "knock-back:", "weapon:", "animation:", "effects:", "lift doors:", "chests:", "seals:", "fades:", "inscriptions:", "conversations:", "menus:", "routines:", "saves:", "level states:", "the run:", "player_take_hit:", "the status:", "casting:", "the attacking arms:", "creature hits:", "creature strikes:", "creature holds:", "FAIL", "  first",
                            "  level case", "  angle (", "  script level",
                            "  hit ")):
            print("   " + line.strip())
    if r.returncode != 0:
        print("the port and the Python model disagree")
        return False
    print("godot loads the project cleanly")
    return True


if __name__ == "__main__":
    lv = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    limit = None
    if "--cells" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--cells") + 1])
    if "--obj" in sys.argv:
        write(lv, limit=limit)            # the flat, unlit OBJ, kept for viewers
    else:
        build_gltf(lv, limit=limit)
        build_objects_gltf(lv)
        build_actors_gltf(lv)
        build_effects_gltf(lv)
        build_held_gltf(lv)
        build_collision_gltf(lv)
        build_sky_gltf(lv)
    project(lv)
    if "--no-check" not in sys.argv:
        verify()
